"""Vidorq Engine — local HTTP server that powers the desktop apps.

Zero external dependencies beyond the Vidorq venv (faster-whisper, PyAV, Pillow).
Pattern borrowed from CursorBridge: stdlib http.server + a worker thread.

Endpoints:
    GET  /health     -> {"ok": true, "version": ...}
    GET  /progress   -> {"step", "percent", "detail", "result", "error"}
    GET  /workspaces -> {"active": name, "list": [names]}
    GET  /profile    -> brand profile of the active workspace
    POST /workspaces -> {"create": name} | {"activate": name}
    POST /profile    -> saves brand profile into the active workspace
    POST /config     -> {"anthropicKey"|"openaiKey"|"geminiKey": ...} -> config.json
    GET  /tramos     -> {"tramos": [...]} the montage cut into segments, with text
    GET  /history    -> {"edits": [...]} every edit made, newest first
    POST /history    -> clears that list
    POST /edit       -> {"video", "preset", "captions", "output", "prompt"} starts a job

Workspaces live in %APPDATA%/Vidorq/workspaces/<name>/ (brand.json + future memory);
each one is a brand/project with its own style profile.

Presets (no API key needed, fully local):
    clean    keep speech, drop silences/dead air
    podcast  clean + a marker/zoom on every question
    montage  keep the highest-energy chunks (beta)
A prompt decides the whole edit. Anything it states with numbers in it is
arithmetic and never reaches a model; for the rest the provider is a choice,
and the factory default is the Ollama on the user's own machine.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST, PORT = "127.0.0.1", 9877
VERSION = "0.1.0"
HELPERS = Path(__file__).resolve().parent.parent / "skill" / "helpers"
PYTHON = sys.executable
CONFIG_DIR = Path(os.environ.get("APPDATA", ".")) / "Vidorq"
CONFIG = CONFIG_DIR / "config.json"
BRIDGE = "http://127.0.0.1:9876"

# Windows gives every child process its own console window when the parent has
# none, and the parent here has none: Resolve starts the engine with pythonw so
# nothing flashes. The result was the opposite, a console blinking on screen for
# every single ffmpeg, and with one ffmpeg per preview that is a blink on every
# button press. CREATE_NO_WINDOW is what stops it, and it does not exist off
# Windows, hence the getattr.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# The caption presets and the filler-word lists live with the renderers that use
# them, so the engine borrows them instead of keeping a second copy.
sys.path.insert(0, str(HELPERS))
import captions as cap  # noqa: E402
import vision  # noqa: E402
import translate as tl  # noqa: E402
import director  # noqa: E402
import resolve_captions  # noqa: E402
import faces  # noqa: E402
import providers  # noqa: E402
import looks  # noqa: E402
import autocolor  # noqa: E402
import overlays  # noqa: E402
import previews  # noqa: E402
import speech  # noqa: E402

_lock = threading.Lock()
_progress = {"step": "", "percent": 0, "detail": "", "result": "", "error": "",
             "stopped": False}
_busy = False

# Parar. Un turno puede tardar un minuto y medio, y hasta ahora la unica forma
# de cancelar una frase mal dicha era esperar a que acabara de trabajar en ella.
_stop = threading.Event()
# Lo que corre FUERA de este proceso y no mira ninguna bandera: Whisper y
# ffmpeg. Se apuntan aqui mientras viven para poder matarlos al parar.
_live = []
_live_lock = threading.Lock()


class Stopped(Exception):
    """Lo paro el usuario. No es un error y no se ensena como tal."""


def track(proc):
    with _live_lock:
        _live.append(proc)


def untrack(proc):
    with _live_lock:
        if proc in _live:
            _live.remove(proc)


# La CLI del proveedor tambien entra en la lista de lo que se puede matar: es la
# fase mas larga de un retoque y es justo donde se pulsa "Parar".
providers.ON_SPAWN = lambda proc: track(proc)
providers.ON_DONE = lambda proc: untrack(proc)


def stop_all():
    """Poner la bandera y matar lo que ya esta corriendo."""
    _stop.set()
    with _live_lock:
        alive = list(_live)
    for proc in alive:
        try:
            proc.kill()
        except Exception:
            pass
    return len(alive)

# El texto que ve el usuario sale de aqui: la interfaz manda su idioma en /edit y el
# motor responde en ese idioma, para que no se mezclen los dos en la misma pantalla.
_lang = "es"

TEXT = {
    "es": {
        "busy": "Ya hay una edición en marcha",
        "no_video": "No encuentro el vídeo: %s",
        "did_shots": "%d planos vistos",
        "cannot_do": "esto no sé hacerlo: %s",
        "failed_moments": "no he podido aplicar lo que pedías en momentos concretos: %s",
        "failed_colour": "no he podido calcular el color automático: %s",
        "failed_translate": "no he podido traducir los subtítulos: %s",
        "failed_voice": "no he podido decir la línea del segundo %.0f: %s",
        "no_eye": "he encontrado los planos por el movimiento, pero no he podido "
                  "DESCRIBIR lo que se ve: para eso hace falta un modelo de visión "
                  "en Ollama.",
        "no_brain": "he leído tu frase solo con mis reglas, sin modelo: no hay "
                    "ninguno local instalado ni clave puesta. Entiende bastante, "
                    "pero para lo raro pon un modelo en Ollama o una clave en Ajustes.",
        "no_speech": "En este vídeo no se oye hablar a nadie, y Vidorq corta por lo "
                     "que se dice. Dime tú el trozo y lo hago: por ejemplo «quédate "
                     "del segundo 2 al 8».",
        "kept_nothing": "Después de cortar no quedaba nada que conservar. Prueba con "
                        "otro estilo de corte, o dime tú de qué segundo a qué segundo "
                        "quieres quedarte.",
        "preparing": "Preparando...",
        "transcribing": "Transcribiendo (Whisper local)...",
        "watching": "Mirando el vídeo (planos y movimiento)...",
        "watched": "%d planos vistos%s",
        "deciding": "Decidiendo los cortes...",
        "decided": "Cortes decididos",
        "rendering": "Renderizando (GPU)...",
        "building": "Montando timeline en Resolve...",
        "done": "Listo",
        "stopped": "Parado",
        "colouring": "Mirando el color de tu vídeo...",
        "colouring_help": "Niveles, dominante de color y saturación",
        "colour_ok": "el color ya estaba bien, no toco nada",
        "no_moment": "no he encontrado el momento exacto; dime el segundo o el minuto y lo hago",
        "stopped_help": "Lo que ya estaba puesto se queda en el timeline",
        "stopped_by_you": "Lo paraste tú a mitad. Lo que ya estaba hecho se queda.",
        "timeline_made": "Timeline '%s' creado en Resolve",
        "captioning": "Poniendo los subtítulos en Resolve...",
        "captioning_n": "%d subtítulos, uno a uno",
        "captions_made": "con %d subtítulos editables",
        "cut_report": "%d cortes, %d muletillas fuera, %d tomas repetidas",
        "snapped": ", %d cortes movidos a un momento quieto",
        "jumps": ", %d saltos tapados cambiando el encuadre",
        "beats": ", %d cortes sobre el movimiento",
        "translating": "Traduciendo los subtítulos a %s...",
        "srt_made": "Subtítulos guardados en %s",
        "directing": "Leyendo lo que has pedido...",
        "directed": "%s decidió: %s",
        "no_deps": ("Al motor le falta %s. Lo han arrancado con el Python "
                    "equivocado: ciérralo y usa engine\\start_engine.bat"),
        "framing": "Buscando la cara para encuadrar...",
        "framing_help": "Detector local, milisegundos por fotograma",
        "framed": "Encuadre sobre la cara en %d de %d tramos",
        "framed_none": "Sin caras: recorte centrado",
        "no_gpu": "Sin GPU para transcribir, va por CPU y tarda más",
        "moments": "Leyendo lo que pides en momentos concretos...",
        "moments_done": "En momentos concretos: %s",
        "refine_reading": "Se lo estoy preguntando a la IA...",
        "not_understood": "No he entendido qué cambiar, así que no he tocado nada.",
        "did_cuts": "%d tramos",
        "did_cut": "%d tramo",
        "did_beats": "%d cortes sobre el movimiento, con su golpe de cámara",
        "did_beats_one": "%d corte sobre el movimiento, con su golpe de cámara",
        "did_snapped": "%d cortes movidos a un momento quieto de la imagen",
        "did_snapped_one": "%d corte movido a un momento quieto de la imagen",
        "did_jumps": "%d saltos tapados cambiando el encuadre",
        "did_jumps_one": "%d salto tapado cambiando el encuadre",
        "did_caps": "%d subtítulos",
        "literal": "Lo has dicho con los segundos puestos: no hace falta pensarlo.",
        "carded": "%d %s en su sitio.",
        "did_voice": "%d voz en off",
        "did_voice_none": "la voz pedida no se ha puesto: su segundo cae en un trozo ya cortado",
        "did_voice_none_many": "las %d voces pedidas no se han puesto: sus segundos caen en un trozo ya cortado",
        "painting": "Coloreando en Resolve...",
        "painting_help": "Una corrección primaria por clip, que puedes seguir tocando a mano",
        "painted": "%d clips con el filtro '%s'",
        "overlaying": "Poniendo las transiciones...",
        "overlaying_help": "Una capa animada en cada corte, en su propia pista",
        "overlaid": "%d transiciones '%s'",
        "refining": "Retoque %d: leyendo lo que pides...",
        "refine_kept": "Sigo sobre el montaje que ya hay (%d tramos). Cambias: %s",
        "refine_nothing_said": "solo lo de momentos concretos",
        "history_first": "primera edición",
        "did_order": "%d tramos puestos en otro orden",
        "said_order": "cambiar de sitio un tramo",
        "only_mp4": "en el MP4",
        "did_undo": "vuelto al montaje de antes",
        "said_undo": "deshacer el último cambio",
        "voice_making": "Poniendo voz a la línea %d de %d...",
        "voice_only_mp4": "%d voz(es) generadas, pero en Resolve no se pueden meter por API: salen solo en el MP4.",
        "nesting": "Poniendo los subtítulos encima de tu edición...",
    },
    "en": {
        "busy": "There is already an edit running",
        "no_video": "Cannot find the video: %s",
        "did_shots": "%d shots seen",
        "cannot_do": "I do not know how to do this: %s",
        "failed_moments": "I could not carry out what you asked for at particular moments: %s",
        "failed_colour": "I could not work out the automatic colour: %s",
        "failed_translate": "I could not translate the captions: %s",
        "failed_voice": "I could not speak the line at second %.0f: %s",
        "no_eye": "I found the shots from the movement, but I could not DESCRIBE "
                  "what is on screen: that needs a vision model in Ollama.",
        "no_brain": "I read your sentence with my own rules only, with no model: "
                    "there is none installed locally and no key set. It gets a lot, "
                    "but for anything unusual add a model to Ollama or a key in "
                    "Settings.",
        "no_speech": "Nobody speaks in this video, and Vidorq cuts by what is said. "
                     "Tell me the piece yourself and I will do it: for example "
                     "\"keep from second 2 to 8\".",
        "kept_nothing": "There was nothing left after the cut. Try another cut style, "
                        "or tell me which second to which second you want to keep.",
        "preparing": "Getting ready...",
        "transcribing": "Transcribing (local Whisper)...",
        "watching": "Watching the video (shots and movement)...",
        "watched": "%d shots seen%s",
        "deciding": "Deciding the cuts...",
        "decided": "Cuts decided",
        "rendering": "Rendering (GPU)...",
        "building": "Building the timeline in Resolve...",
        "done": "Done",
        "stopped": "Stopped",
        "colouring": "Looking at your video's colour...",
        "colouring_help": "Levels, colour cast and saturation",
        "colour_ok": "the colour was already fine, nothing to change",
        "no_moment": "I could not find the exact moment; tell me the second or minute and I will do it",
        "stopped_help": "Whatever was already placed stays on the timeline",
        "stopped_by_you": "You stopped this halfway. What was already done stays.",
        "timeline_made": "Timeline '%s' created in Resolve",
        "captioning": "Putting the captions into Resolve...",
        "captioning_n": "%d captions, one by one",
        "captions_made": "with %d editable captions",
        "cut_report": "%d cuts, %d filler words out, %d repeated takes",
        "snapped": ", %d cuts moved onto a still moment",
        "jumps": ", %d jump cuts hidden by changing the framing",
        "beats": ", %d cuts placed on the action",
        "translating": "Translating the captions into %s...",
        "srt_made": "Captions saved to %s",
        "directing": "Reading what you asked for...",
        "directed": "%s decided: %s",
        "no_deps": ("The engine is missing %s. It was started with the wrong "
                    "Python: close it and use engine\\start_engine.bat"),
        "framing": "Finding the face to frame on...",
        "framing_help": "Local detector, milliseconds per frame",
        "framed": "Framed on the face in %d of %d cuts",
        "framed_none": "No faces found: centred crop",
        "no_gpu": "No GPU for transcription, running on CPU and slower",
        "moments": "Reading what you asked for at specific moments...",
        "moments_done": "At specific moments: %s",
        "refine_reading": "Asking the AI about it...",
        "not_understood": "I did not understand what to change, so I left everything alone.",
        "did_cuts": "%d pieces",
        "did_cut": "%d piece",
        "did_beats": "%d cuts placed on the action, with a camera shake",
        "did_beats_one": "%d cut placed on the action, with a camera shake",
        "did_snapped": "%d cuts moved to a still moment in the picture",
        "did_snapped_one": "%d cut moved to a still moment in the picture",
        "did_jumps": "%d jump cuts hidden by changing the framing",
        "did_jumps_one": "%d jump cut hidden by changing the framing",
        "did_caps": "%d captions",
        "literal": "You gave the seconds, so there is nothing to work out.",
        "carded": "%d %s placed.",
        "did_voice": "%d voice line(s)",
        "did_voice_none": "the voice line was not added: its second falls in a piece that was cut",
        "did_voice_none_many": "the %d voice lines were not added: their seconds fall in a piece that was cut",
        "painting": "Grading in Resolve...",
        "painting_help": "One primary correction per clip, still yours to adjust by hand",
        "painted": "%d clips with the '%s' look",
        "overlaying": "Putting the transitions in...",
        "overlaying_help": "One animated layer on every cut, on its own track",
        "overlaid": "%d '%s' transitions",
        "refining": "Change %d: reading what you asked...",
        "refine_kept": "Carrying on from the edit you have (%d pieces). Changing: %s",
        "refine_nothing_said": "only the specific moments",
        "history_first": "first edit",
        "did_order": "%d segments put in another order",
        "said_order": "move a segment",
        "only_mp4": "in the MP4",
        "did_undo": "back to the previous edit",
        "said_undo": "undo the last change",
        "voice_making": "Voicing line %d of %d...",
        "voice_only_mp4": "%d voice line(s) made, but Resolve takes no audio over its API: they only come out in the MP4.",
        "nesting": "Laying the captions over your edit...",
    },
}


# The engine is stdlib only, but the helpers it shells out to are not, and they
# run under this same interpreter. Started with the wrong Python it answers
# /health perfectly and then dies half way through the first job with "No module
# named av", which reads like a broken video file. So it says so up front.
NEEDS = ("av", "faster_whisper", "numpy", "PIL")


def missing_modules():
    """Which of the helpers' imports this interpreter cannot satisfy."""
    import importlib.util
    out = []
    for name in NEEDS:
        try:
            if importlib.util.find_spec(name) is None:
                out.append(name)
        except Exception:
            out.append(name)
    return out


# The MP4 renderer knows how to draw these; the names are here because the app
# has to offer them and Resolve cannot do transitions by API at all.
TRANSITION_LABELS = {
    "es": {"none": "Corte seco", "dissolve": "Disolvencia", "dip": "Fundido a negro",
           "white": "Fundido a blanco", "flash": "Destello",
           "slide": "Deslizamiento", "wipe": "Barrido", "zoom": "Zoom"},
    "en": {"none": "Hard cut", "dissolve": "Dissolve", "dip": "Dip to black",
           "white": "Dip to white", "flash": "Flash", "slide": "Slide",
           "wipe": "Wipe", "zoom": "Zoom"},
}


# The shapes an edit can come out in. Vertical is the one a short needs.
RATIO_LABELS = {
    "es": {"source": "Como el original", "vertical": "Vertical 9:16",
           "portrait": "Retrato 4:5", "square": "Cuadrado 1:1", "wide": "Horizontal 16:9"},
    "en": {"source": "As the source", "vertical": "Vertical 9:16",
           "portrait": "Portrait 4:5", "square": "Square 1:1", "wide": "Wide 16:9"},
}


def tr(key, *args):
    text = TEXT.get(_lang, TEXT["es"]).get(key, key)
    return text % args if args else text


def tr_in(lang, key, *args):
    """Lo mismo, pero en un idioma que se pasa a mano.

    Los catalogos (los botones de una pregunta, las etiquetas) se piden con su
    idioma como argumento y no con el global, porque los sirve un endpoint que
    puede estar contestandole a otra ventana.
    """
    text = TEXT.get(lang, TEXT["es"]).get(key, key)
    return text % args if args else text

QUESTION_RE = re.compile(
    r"^\s*(qu[eé]|c[oó]mo|cu[aá]l|qui[eé]n|por qu[eé]|d[oó]nde|cu[aá]ndo|cu[aá]nt)", re.I)
PROGRESS_RE = re.compile(r"^PROGRESS (\d+) (\d+)")


def set_progress(step, percent, detail="", result="", error=""):
    """El estado que lee la ventana, y tambien donde se para.

    Cada fase informa de su progreso, asi que mirar la bandera AQUI cubre las
    cuarenta llamadas sin sembrar un `if` en cada una, y para en el primer sitio
    donde el trabajo levanta la cabeza. Lo que no pasa por aqui son los
    subprocesos largos, y esos se matan aparte.

    La llamada final (la que trae `result` o `error`) no se para: es la que
    cuenta como acabo la cosa, y tragarsela dejaria la ventana esperando.
    """
    if _stop.is_set() and not (result or error):
        raise Stopped()
    with _lock:
        _progress.update(step=step, percent=percent, detail=detail, result=result,
                         error=error, stopped=False)


def set_stopped(step, detail=""):
    """Cerrar el turno diciendo que lo paraste tu, no que fallo algo."""
    with _lock:
        _progress.update(step=step, percent=100, detail=detail, result="", error="",
                         stopped=True)


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# Workspaces (one folder per brand/project)
# --------------------------------------------------------------------------- #
WORKSPACES = CONFIG_DIR / "workspaces"


def _safe_name(name):
    return re.sub(r"[^\w\- ]", "", (name or "").strip())[:40] or "Principal"


def _new_ws_name(raw):
    """Nombre para un workspace RECIEN CREADO, sin caer en "Principal".

    `_safe_name` cae en "Principal" cuando no queda nada aprovechable (solo
    espacios, solo emoji, solo signos), que esta bien como valor por defecto
    para saber en que proyecto estamos, pero es un desastre para crear uno
    nuevo: el cuadro de "Nuevo workspace" es un `window.prompt` sin validar
    nada, asi que un fallo de teclado fusionaba en silencio el workspace
    nuevo con el que ya hubiera en "Principal" y sus datos, sin avisar.
    """
    name = re.sub(r"[^\w\- ]", "", (raw or "").strip())[:40]
    if name:
        return name
    existing = set(ws_list()["list"])
    i = 2
    while ("Workspace %d" % i) in existing:
        i += 1
    return "Workspace %d" % i


def ws_list():
    WORKSPACES.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in WORKSPACES.iterdir() if p.is_dir())
    if not names:
        (WORKSPACES / "Principal").mkdir(parents=True, exist_ok=True)
        names = ["Principal"]
    active = load_config().get("activeWorkspace", names[0])
    if active not in names:
        active = names[0]
    return {"active": active, "list": names}


def ws_dir():
    d = WORKSPACES / ws_list()["active"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def profile_load():
    try:
        return json.loads((ws_dir() / "brand.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def profile_save(p):
    (ws_dir() / "brand.json").write_text(
        json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")


# --------------------------------------------------------------------------- #
# EDL builders (deterministic presets — no LLM required)
# --------------------------------------------------------------------------- #
# A cut shorter than this is a flash, not an edit.
MIN_KEEP_S = 0.45
# How isolated a filler has to be before cutting it is safe. Below this the word
# is glued to the speech around it and removing it leaves an audible click.
FILLER_ISLAND_S = 0.12
# Two takes of the same sentence look like this much of the same text.
TAKE_SAME = 0.82


def _norm(text):
    """Text reduced to what matters when comparing two takes."""
    return re.sub(r"[^\w\s]", "", cap.strip_accents((text or "").lower())).strip()


def drop_repeated_takes(transcript, threshold=TAKE_SAME):
    """Drop all but the last attempt when a sentence is said twice in a row.

    People restart sentences constantly, and the last take is nearly always the
    keeper. Only neighbours are compared, so a phrase that legitimately comes
    back later in the video survives.
    """
    segs = transcript.get("segments", [])
    keep, dropped = [], 0
    for seg in segs:
        if keep:
            a, b = _norm(keep[-1].get("text", "")), _norm(seg.get("text", ""))
            if a and b and difflib.SequenceMatcher(None, a, b).ratio() >= threshold:
                keep[-1] = seg     # the later take wins
                dropped += 1
                continue
        keep.append(seg)
    return keep, dropped


def _speech_words(segs, lang):
    """Every spoken word worth keeping, fillers on their own island removed.

    Returns (words, fillers_removed). A segment without word timings falls back
    to one entry covering the whole segment, so an older transcript still cuts.
    """
    words, removed = [], 0
    for seg in segs:
        ws = [w for w in seg.get("words", []) if (w.get("w") or "").strip()]
        if not ws:
            words.append({"s": float(seg["start"]), "e": float(seg["end"])})
            continue
        for i, w in enumerate(ws):
            if cap.is_filler(w["w"], lang):
                before = float(w["s"]) - float(ws[i - 1]["e"]) if i else FILLER_ISLAND_S
                after = float(ws[i + 1]["s"]) - float(w["e"]) if i + 1 < len(ws) else FILLER_ISLAND_S
                if before >= FILLER_ISLAND_S or after >= FILLER_ISLAND_S:
                    removed += 1
                    continue
            words.append({"s": float(w["s"]), "e": float(w["e"])})
    return words, removed


def snap_to_picture(edl, track, window=0.30):
    """Nudge each cut onto the calmest instant near it.

    The audio decides WHERE to cut; the picture decides exactly WHEN. A cut that
    lands while the camera whips or a hand crosses frame reads as a mistake even
    with perfect audio, so each boundary slides up to `window` seconds onto the
    stillest moment nearby. Nothing moves far enough to swallow a word: the
    window is smaller than the padding around the speech.
    """
    if not track or not edl:
        return edl, 0
    moved = 0
    for i, seg in enumerate(edl):
        for key in ("start", "end"):
            t = float(seg[key])
            here = vision.motion_at(track, t)
            best = vision.quiet_moment(track, t, window)
            there = vision.motion_at(track, best)
            # Only move when there is a reason to. On footage that is uniformly
            # calm the calmest instant is a coin toss, and shifting every cut a
            # third of a second for nothing is worse than leaving them alone.
            if here < max(there * 1.8, there + 2.0):
                continue
            # Never cross into a neighbour, and never invert the segment.
            low = edl[i - 1]["end"] if key == "start" and i else 0.0
            high = edl[i + 1]["start"] if key == "end" and i + 1 < len(edl) else best + 1
            if low <= best <= high and abs(best - t) > 0.02 and seg["end"] - seg["start"] > 0.5:
                seg[key] = round(best, 3)
                moved += 1
    return edl, moved


def pace_gap(pace):
    """El ritmo de tu marca, traducido a los dos numeros que cortan de verdad.

    El deslizador de "Tu marca" decia "corta cuando sobra, respira cuando toca"
    y no cortaba ni respiraba: viajaba dentro del JSON de la marca hasta el
    prompt del modelo y ahi se quedaba, asi que moverlo de 1 a 10 no cambiaba
    una sola edicion salvo que ademas escribieras una frase Y el modelo se
    acordara de el.

    Los dos numeros que sí deciden son cuanto silencio se aguanta dentro de un
    tramo (`max_gap`) y cuanto aire se deja a cada lado (`pad`).

    El 6 devuelve exactamente lo de siempre (0.60 y 0.15) a proposito: quien no
    toque el deslizador no debe notar que existe.

    Devuelve (max_gap, pad).
    """
    p = max(1, min(10, int(pace or 6)))
    return round(1.10 - (p - 1) * 0.10, 2), round(0.25 - (p - 1) * 0.02, 3)


def edl_from_speech(transcript, lang="es", max_gap=0.6, pad=0.15, drop_takes=True,
                    shake=False,
                    track=None):
    """Keep the speech, drop the dead air, the fillers and the retries.

    Built from word timings rather than whole phrases, which is what makes it
    possible to cut an 'eh' out of a pause without touching the words around it.
    With a motion `track` from the vision pass the cuts also avoid landing in the
    middle of a camera move. Returns (edl, report).
    """
    segs = transcript.get("segments", [])
    if not segs:
        return [], {}
    dropped = 0
    if drop_takes:
        segs, dropped = drop_repeated_takes(transcript)
    words, fillers = _speech_words(segs, lang)
    if not words:
        return [], {}

    out = []
    cur = {"start": max(0.0, words[0]["s"] - pad), "end": words[0]["e"]}
    for w in words[1:]:
        if w["s"] - cur["end"] <= max_gap:
            cur["end"] = max(cur["end"], w["e"])
        else:
            out.append(cur)
            cur = {"start": max(0.0, w["s"] - pad), "end": w["e"]}
    out.append(cur)

    # Pad the tail, then fold away anything too short to read as a shot. Folding
    # into the previous keep is better than dropping it: the words survive.
    duration = float(transcript.get("duration") or 0) or out[-1]["end"] + pad
    merged = []
    for seg in out:
        seg["end"] = min(seg["end"] + pad, duration)
        if merged and (seg["end"] - seg["start"] < MIN_KEEP_S
                       or seg["start"] - merged[-1]["end"] <= 0):
            merged[-1]["end"] = max(merged[-1]["end"], seg["end"])
        else:
            merged.append(seg)
    if len(merged) > 1 and merged[0]["end"] - merged[0]["start"] < MIN_KEEP_S:
        merged[1]["start"] = merged[0]["start"]
        merged.pop(0)
    for seg in merged:
        seg["zoom"] = 1.0
        seg["note"] = ""
    merged, moved = snap_to_picture(merged, track)
    merged, beat_cuts = cut_on_beats(merged, track, shake=shake)
    merged, hidden = hide_jump_cuts(merged, track)
    return merged, {"takes": dropped, "fillers": fillers, "cuts": len(merged),
                    "beats": beat_cuts,
                    "snapped": moved, "jumps": hidden}


# How much bigger the framing goes on the far side of a jump cut. Small on
# purpose: enough that the join stops reading as a glitch, not so much that it
# announces itself as an effect.
JUMP_ZOOM = 1.07


# A beat has to sit this far inside a segment to be worth cutting on. Cutting a
# third of a second from either edge produces a flash, not an edit.
BEAT_MARGIN_S = 0.8
# How far in the tighter side of a beat cut sits. The two halves of a beat cut
# are CONTIGUOUS - nothing was removed - so without a difference in framing the
# split renders identically and the cut does not exist. Alternating in and out
# across the beat is the punch-in every vlog editor does on an action, and 1.09
# is enough to read as a new shot without looking like a zoom effect.
BEAT_ZOOM = 1.09


def cut_on_beats(edl, track, log=None, shake=False):
    """Split a shot where the picture does something, so the action gets a cut.

    Speech says WHERE a cut is allowed; it says nothing about where one is
    wanted. A jump, a whip pan, a hand thrown at the lens - an editor cuts on
    those, and the cut is invisible because the motion covers it. Without this
    Vidorq only ever cut at silences, so a ten second take with a jump in the
    middle stayed one flat block.

    The split alone changes nothing on screen; what makes it read as a cut is
    the alternating punch across it. With `shake` on, the piece that starts ON
    the beat also gets a short impact shake, which is the CapCut move: the cut
    lands and the camera flinches. Only the pieces that START on a beat get it,
    never the first one, because the first one starts where the speech did and
    nothing happened there.
    """
    if not track or not edl:
        return edl, 0
    marks = vision.beats(track)
    if not marks:
        return edl, 0
    out, made = [], 0
    for seg in edl:
        a, b = float(seg["start"]), float(seg["end"])
        inside = [t for t in marks if a + BEAT_MARGIN_S <= t <= b - BEAT_MARGIN_S]
        if not inside:
            out.append(seg)
            continue
        at, tight, first = a, False, True
        for t in inside:
            out.append(dict(seg, start=round(at, 3), end=round(t, 3),
                            zoom=BEAT_ZOOM if tight else float(seg.get("zoom", 1.0)),
                            shake=bool(shake and not first)))
            at, tight, first = t, not tight, False
            made += 1
        out.append(dict(seg, start=round(at, 3), end=round(b, 3),
                        zoom=BEAT_ZOOM if tight else float(seg.get("zoom", 1.0)),
                        shake=bool(shake and not first)))
    if log and made:
        log("%d cortes puestos sobre el movimiento" % made)
    return out, made


def hide_jump_cuts(edl, track, zoom=JUMP_ZOOM):
    """Change the framing across cuts that would otherwise jump.

    This is the difference between a video that was cut and a video that looks
    edited. Take a silence out of a locked-off talking head and both sides of the
    join show the same thing from the same place, so the subject teleports. The
    fix every editor uses is to make the framing different across the cut.

    Only the joins that need it get touched: the fingerprints say whether the two
    sides look alike, so a genuine change of shot - where the picture already
    changed - is left exactly as it was. A segment that already carries a zoom
    for another reason is left alone too.
    """
    if not track or len(edl) < 2:
        return edl, 0
    fixed = 0
    for i in range(1, len(edl)):
        prev, cur = edl[i - 1], edl[i]
        # Nothing was removed here, so nothing jumps.
        if cur["start"] - prev["end"] < 0.04:
            continue
        if not vision.looks_same(track, prev["end"] - 0.1, cur["start"] + 0.1):
            continue
        if float(cur.get("zoom", 1.0)) > 1.001:
            continue
        # Alternate, so three joins in a row do not all land on the same framing.
        cur["zoom"] = 1.0 if float(prev.get("zoom", 1.0)) > 1.001 else zoom
        if cur["zoom"] > 1.001:
            fixed += 1
    return edl, fixed


def mark_questions(transcript, edl):
    """Tag segments that open a question; used for zooms and Resolve markers."""
    q_times = [s["start"] for s in transcript["segments"]
               if "?" in s["text"] or QUESTION_RE.match(s["text"])]
    for seg in edl:
        for t in q_times:
            if seg["start"] <= t < seg["end"]:
                seg["zoom"] = 1.05
                seg["note"] = "pregunta / cambio de tema"
                break
    return edl


def audio_energy(video):
    """Loudness per second, as {second: rms}, in one pass over the audio."""
    import av
    import numpy as np
    out = {}
    try:
        c = av.open(video)
        a = c.streams.audio[0]
        for frame in c.decode(a):
            t = int(float(frame.pts * a.time_base)) if frame.pts is not None else 0
            arr = frame.to_ndarray().astype("float32")
            out.setdefault(t, []).append(float((arr ** 2).mean()))
        c.close()
    except Exception:
        return {}
    return {t: float(np.sqrt(np.mean(v))) for t, v in out.items()}


def edl_montage(video, transcript, keep_ratio=0.45, track=None, lang="es",
                max_gap=0.6, pad=0.15):
    """Keep the best moments, chosen on what is said, how loud it is and how
    much the picture is doing.

    The first version scored one-second buckets of raw loudness, which is how a
    montage ends up starting mid-word: a bucket has no idea where a sentence
    begins. This scores whole spoken segments instead, so every kept moment is a
    complete thought, and it only ever picks from what survived the cleanup, so
    the fillers and the retries are already gone.
    """
    base, report = edl_from_speech(transcript, lang, max_gap=max_gap, pad=pad,
                                   track=track)
    if len(base) < 3:
        return base, report

    import numpy as np
    energy = audio_energy(video)

    def loudness(seg):
        vals = [energy[t] for t in range(int(seg["start"]), int(seg["end"]) + 1)
                if t in energy]
        return float(np.mean(vals)) if vals else 0.0

    def movement(seg):
        if not track:
            return 0.0
        vals = [p["diff"] for p in track if seg["start"] <= p["t"] < seg["end"]]
        return float(np.mean(vals)) if vals else 0.0

    loud = [loudness(s) for s in base]
    move = [movement(s) for s in base]

    def norm(vals):
        lo, hi = min(vals), max(vals)
        return [0.5] * len(vals) if hi - lo < 1e-6 else [(v - lo) / (hi - lo) for v in vals]

    nl, nm = norm(loud), norm(move)
    # Loudness carries the most, because in a talking video the emphasis is in
    # the voice; movement is a tiebreaker that favours a shot where something
    # happens over a static one saying the same thing.
    score = [0.65 * a + 0.35 * b for a, b in zip(nl, nm)]

    order = sorted(range(len(base)), key=lambda i: score[i], reverse=True)
    total = sum(s["end"] - s["start"] for s in base)
    target = total * keep_ratio
    chosen, got = set(), 0.0
    for i in order:
        if got >= target and chosen:
            break
        chosen.add(i)
        got += base[i]["end"] - base[i]["start"]

    keep = []
    for i in sorted(chosen):
        seg = dict(base[i])
        seg["note"] = "momento fuerte"
        keep.append(seg)
    # Neighbours that both survived should not be shown as two cuts.
    joined = []
    for seg in keep:
        if joined and seg["start"] - joined[-1]["end"] < 0.12:
            joined[-1]["end"] = seg["end"]
        else:
            joined.append(seg)
    report = dict(report, cuts=len(joined), kept=round(got, 1), of=round(total, 1))
    return joined, report


# --------------------------------------------------------------------------- #
# Output backends
# --------------------------------------------------------------------------- #
# One connection to the bridge, kept open, instead of a new one per call.
#
# Measured against the real bridge: a request that does nothing at all costs
# 41.5 ms with a fresh connection and 2.0 ms on a reused one. Putting one
# caption on a Resolve timeline takes three calls, and a ten minute video has
# 751 captions, so the handshake alone was over a minute of pure waiting.
#
# urllib opens and closes a socket every time and offers no way not to, hence
# http.client directly. It is guarded by a lock because the engine answers on
# threads and a shared connection is not thread safe: two requests interleaved
# on one socket come back as each other's answers.
_bridge_conn = None
_bridge_lock = threading.Lock()

# And the host is written as 127.0.0.1 on purpose, never "localhost". Measured
# on this machine: the same request through the name takes 2082 ms against
# 41 ms through the address, because the resolver tries IPv6 first and waits
# for it to fail. Two seconds a call, times 2253 calls, is forty minutes.
BRIDGE_HOST, BRIDGE_PORT = "127.0.0.1", 9876


def _bridge_call(method, path, body=None, timeout=30):
    """One request on the shared connection, reopening it if it went away."""
    global _bridge_conn
    import http.client
    data = json.dumps(body or {}).encode() if method == "POST" else None
    head = {"Content-Type": "application/json"} if data is not None else {}
    with _bridge_lock:
        for attempt in (1, 2):
            try:
                if _bridge_conn is None:
                    _bridge_conn = http.client.HTTPConnection(
                        BRIDGE_HOST, BRIDGE_PORT, timeout=timeout)
                # The timeout belongs to the socket, and it changes per call:
                # two seconds for "are you alive", three minutes for "list the
                # clips". Setting it on the live connection avoids reopening.
                if _bridge_conn.sock is not None:
                    _bridge_conn.sock.settimeout(timeout)
                _bridge_conn.timeout = timeout
                _bridge_conn.request(method, path, data, head)
                return json.loads(_bridge_conn.getresponse().read().decode())
            except Exception:
                # A dead connection looks exactly like a dead bridge from here,
                # so the first failure always earns one clean retry.
                try:
                    _bridge_conn.close()
                except Exception:
                    pass
                _bridge_conn = None
                if attempt == 2:
                    raise
    return {}


def bridge_post(path, body):
    return _bridge_call("POST", path, body, timeout=30)


# How long to wait when the answer is a whole timeline. Two seconds is right for
# "is Resolve alive", and catastrophically wrong for "list the clips": measured
# on a ten minute video, listing the 1513 caption titles takes 4.7 seconds, the
# two second reader gave up, the empty list it returned looked like a timeline
# with no clips, and every single caption was left with Text+'s factory text
# saying "Custom Title". Silence again, and this time it reached the screen.
PATIENT = 180


def bridge_get_slow(path):
    """Same reader, for calls whose answer grows with the size of the edit."""
    return bridge_get(path, timeout=PATIENT)


def bridge_get(path, timeout=2):
    """One GET to the bridge, or None if it is down or has nothing to say."""
    try:
        data = _bridge_call("GET", path, timeout=timeout)
    except Exception:
        return None
    return None if isinstance(data, dict) and data.get("error") else data


def bridge_status():
    """What the guided setup needs to know: is the bridge up, and is a project open?

    The browser cannot ask the bridge directly (no CORS headers there), so the
    engine asks on its behalf and reports it in one shape.

    /status only says whether the bridge reached Resolve; the project and the
    timeline live behind their own endpoints, so they need their own calls.

    Answering on the port is not enough to call it up. When Resolve dies its
    script host can outlive it and keep serving, with every Resolve field come
    back null - measured after a crash. Trusting the port there would light the
    setup screen green over something that cannot do anything.
    """
    status = bridge_get("/status")
    if not status or not status.get("product"):
        return {"bridge": False, "project": None, "timeline": None}
    project = bridge_get("/project") or {}
    timeline = bridge_get("/timeline") or {}
    return {
        "bridge": True,
        "project": project.get("name"),
        "timeline": timeline.get("name"),
    }


def video_shape(path):
    """(fps, width, height) of the source, read from the file itself.

    Worth reading rather than assuming: at a hardcoded 29.97 a 24 or 60 fps clip
    has every single cut land on the wrong frame, and the error grows along the
    timeline.
    """
    try:
        import av
        with av.open(path) as c:
            v = c.streams.video[0]
            fps = float(v.average_rate or v.base_rate or 30)
            return fps, int(v.codec_context.width), int(v.codec_context.height)
    except Exception:
        return 30000 / 1001, 1920, 1080


RATIO_SIZES = {"vertical": (1080, 1920), "portrait": (1080, 1350),
               "square": (1080, 1080), "wide": (1920, 1080)}


def out_frame(ratio, w, h):
    """The output size for a shape, or the source size when it is not changing."""
    return RATIO_SIZES.get(ratio) or (w, h)


def fill_zoom(w, h, out_w, out_h):
    """How much to zoom a clip so it fills a differently shaped timeline.

    Resolve fits a mismatched clip inside the frame, which means a wide clip in a
    vertical timeline arrives with black bars above and below. Scaling by the
    ratio of the two aspect ratios covers the frame exactly: no bars, and no more
    cropping than the shape change already forces. From 1920x1080 into 1080x1920
    that is 3.16.
    """
    if not all((w, h, out_w, out_h)) or (out_w, out_h) == (w, h):
        return 1.0
    src, dst = w / h, out_w / out_h
    return max(src / dst, dst / src)


def resolve_clips():
    """The video files already sitting in the open Resolve project.

    Vidorq runs INSIDE Resolve, on top of a media pool that already knows where
    the footage is, and it was still asking people to drag a file into it. That
    is the app making the user do its own lookup.

    A media pool item is not always a file: timelines live there too, and they
    have no path behind them. So anything without a File Path is skipped rather
    than offered and then failing when it is clicked.
    """
    from urllib.parse import quote
    pool = bridge_get("/mediapool", timeout=8) or {}
    out = []
    for c in pool.get("clips", []):
        name = c.get("name") or ""
        if not name:
            continue
        info = bridge_get("/mediapool/clip/info?clip_name=" + quote(name),
                          timeout=8) or {}
        props = info.get("properties") or {}
        path = props.get("File Path") or ""
        if not path or "Video" not in (props.get("Type") or ""):
            continue
        out.append({"name": name, "path": path,
                    "resolution": props.get("Resolution", ""),
                    "fps": props.get("FPS", ""),
                    "duration": props.get("Duration", "")})
    return out


def drop_timelines(names):
    """Throw away timelines Vidorq itself made on an earlier round.

    A change used to leave the previous version behind, and each round leaves
    TWO of them: the edit and its nested caption track. Five changes and the
    project holds ten timelines nobody asked for.

    There is no /timeline/delete on the bridge. But in Resolve a timeline sits
    in the media pool like any other item, and MediaPool.DeleteClips takes it.
    Measured: two names in, {"success": true, "deleted": 2}, both gone.

    Only names this program created and wrote down are ever passed in. It never
    goes hunting for things that look like its own work, because a timeline
    somebody made by hand can look exactly like one of ours.

    Two rules learned by watching Resolve die: never delete the timeline that is
    currently open, and never delete a pile of them in one call.
    """
    if not names:
        return 0
    doomed = set(names)

    # Primero, quitarse de encima el que se va a borrar. Resolve se CIERRA si le
    # borras el timeline que tiene delante, y ese es justo el caso normal: la
    # ronda anterior termino dejandolo abierto con el cabezal puesto. Visto en
    # vivo el 2026-08-19, con la ventana de "DaVinci Resolve quit unexpectedly".
    if (bridge_get("/timeline") or {}).get("name") in doomed:
        total = int((bridge_get("/project") or {}).get("timelineCount", 0))
        movido = False
        for idx in range(1, total + 1):
            got = bridge_post("/timeline/switch", {"index": idx})
            if got.get("timeline") and got["timeline"] not in doomed:
                movido = True
                break
        if not movido:
            # No hay donde ponerse: en el proyecto solo estan los que iban a
            # caer. Un timeline de sobra estorba; perder Resolve a mitad de una
            # edicion no se parece en nada.
            return 0

    # De uno en uno, no en bloque. Veintidos de golpe fue lo que lo tiro, y asi
    # un fallo se queda en un timeline en vez de llevarse la sesion entera.
    gone = 0
    for name in names:
        try:
            got = bridge_post("/mediapool/clips/delete", {"clipNames": [name]})
            gone += int(got.get("deleted") or 0)
        except Exception:
            traceback.print_exc()
    return gone


def paint_clips(look, n, log=None, numbers=None):
    """El filtro de color, clip a clip, con el CDL nativo de Resolve.

    Los mismos numeros que el .cube del MP4 (skill/helpers/looks.py), asi que
    las dos salidas se ven igual. Va por CDL y no por LUT a proposito: queda en
    la pagina de color como una correccion primaria normal, que se puede abrir y
    seguir tocando a mano. Un LUT seria una caja negra encima del plano.
    """
    if not look or look == looks.DEFAULT:
        return 0
    # `numbers` son los del color automatico, calculados mirando este video. Sin
    # ellos vale el catalogo, que es lo que hacen los ocho filtros de estilo.
    cdl = looks.resolve_cdl(look, 1, numbers)
    done = 0
    for i in range(n):
        got = bridge_post("/color/set-cdl", {"trackType": "video", "trackIndex": 1,
                                             "clipIndex": i, "cdl": cdl})
        if got.get("success"):
            done += 1
    if log:
        log(tr("painted", done, look))
    return done


def output_resolve(video, edl, transcript, captions=False, preset=cap.DEFAULT_PRESET,
                   workdir=None, anim="", chunks=None, ratio="source",
                   drop=None, look="", transition="none", cdl=None,
                   cards=None, card_style="", card_color=""):
    """Builds the edit in Resolve. Returns (what to tell the user, names made)."""
    name = Path(video).stem[:40]
    # La version anterior se va ANTES de crear la nueva, para que el nombre bueno
    # quede libre y el timeline no acabe llamandose "..._4" sin motivo.
    if drop:
        try:
            drop_timelines(drop)
        except Exception:
            # Un timeline viejo que no se pudo borrar es suciedad, no un fallo.
            traceback.print_exc()
    mine = []
    fps, width, height = video_shape(video)
    out_w, out_h = out_frame(ratio, width, height)
    # The whole point of the Resolve output is watching the edit appear, and
    # somebody sitting on the Fusion or the Colour page watches nothing at all.
    # So the curtain goes up first: the Edit page, every time, before a single
    # clip is inserted.
    bridge_post("/page", {"page": "edit"})

    # import media (idempotent) + timeline + inserts
    bridge_post("/media/import", {"filePaths": [video]})

    # Resolve refuses a name it already has, and the old code read straight past
    # the refusal: editing the same video twice appended the second edit onto the
    # end of the first one, nested captions and all. Same numbering the caption
    # timelines use.
    timeline = None
    for n in range(1, 40):
        candidate = f"Vidorq_{name}" if n == 1 else f"Vidorq_{name}{n}"
        if bridge_post("/timeline/create", {"name": candidate}).get("success"):
            timeline = candidate
            break
    if not timeline:
        raise RuntimeError("No pude crear un timeline para '%s' en Resolve" % name)
    mine.append(timeline)
    if (out_w, out_h) != (width, height):
        # A vertical timeline holding a wide clip letterboxes it, so the timeline
        # is reshaped and every clip is zoomed just enough to fill the new frame.
        #
        # One key per call, and useCustomSettings first: a timeline ignores a
        # resolution it has not been told to keep. This used to go out as a
        # single {"settings": {...}} and the bridge answered "key is required",
        # which nobody read, so every timeline stayed 16:9 while the progress
        # line happily said vertical. Hence the check below.
        for key, value in (("useCustomSettings", "1"),
                           ("timelineResolutionWidth", str(out_w)),
                           ("timelineResolutionHeight", str(out_h))):
            got = bridge_post("/timeline/setting", {"key": key, "value": value})
            if not got.get("success"):
                raise RuntimeError("Resolve no acepto %s=%s: %s"
                                   % (key, value, got.get("error", got)))
    tl_now = bridge_get("/timeline") or {}
    start_tc = tl_now.get("startTimecode") or "01:00:00:00"
    start_frame = int(tl_now.get("startFrame", 0))
    # El reloj del TIMELINE, no el del video. Son numeros distintos y usar el
    # equivocado tuerce todo lo que se coloque por frames: es el mismo fallo que
    # descolocaba los subtitulos dos minutos y medio al final de un video de
    # diez, y aqui descolocaria cada transicion de su corte.
    tl_fps = resolve_captions.timeline_fps(tl_now, fps)
    # En SEGUNDOS, no en fotogramas del video. Los dos relojes otra vez: los
    # fotogramas de aqui son del archivo (29,97 en este ejemplo) y el frameId de
    # una marca es del TIMELINE (24). Contando en fotogramas del archivo, una
    # marca pedida en el segundo 6 aterrizaba en el 7,5, y cuanto mas avanzado
    # el video, mas lejos. Medido el 20-ago-2026.
    record_s = 0.0
    inserted = 0
    for seg in edl:
        sf = round(seg["start"] * fps)
        ef = max(sf, round(seg["end"] * fps) - 1)
        if bridge_post("/media/insert", {"clipName": Path(video).name,
                                         "startFrame": sf, "endFrame": ef}).get("success"):
            inserted += 1
        if seg.get("note"):
            # Donde cae dentro del tramo, si se pidio en un segundo concreto.
            dentro = max(0.0, min(float(seg.get("note_at") or 0.0),
                                   (ef - sf) / max(1.0, fps)))
            bridge_post("/marker/add",
                        {"frameId": int(round((record_s + dentro) * tl_fps)),
                         "color": "Yellow",
                         "name": seg["note"][:40], "note": seg["note"]})
        record_s += (ef - sf + 1) / max(1.0, fps)
    if edl and not inserted:
        raise RuntimeError(
            "Resolve no acepto ningun trozo de '%s' en el timeline."
            % Path(video).name)
    # `AppendToTimeline` puede contestar exito y devolver un TimelineItem real
    # incluso cuando Resolve clasifico el archivo como SOLO AUDIO o como fuera
    # de linea: medido el 20-ago-2026 con un origen AV1/Opus, la pista de video
    # se quedaba vacia con la API diciendo que todo habia ido bien. La unica
    # forma fiable de saberlo es volver a mirar la pista.
    if edl:
        on_track = bridge_get("/timeline/clips?track_type=video&track_index=1") or {}
        if not (on_track.get("clips") or []):
            raise RuntimeError(
                "Resolve dice que ha insertado '%s' pero la pista de video del "
                "timeline se ha quedado vacia: seguramente el archivo tiene un "
                "codec que Resolve no decodifica (medido con AV1/Opus). Prueba "
                "con la salida MP4, que decodifica por su cuenta." % Path(video).name)
    fill = fill_zoom(width, height, out_w, out_h)
    for i, seg in enumerate(edl):
        punch = float(seg.get("zoom", 1.0))
        # El punch se ANIMA con un comp en el clip; el `fill` no, porque no es
        # un efecto sino lo que hace falta para que un 16:9 llene un 9:16 y ahi
        # moverse seria un fallo. Si el comp no entra, el punch se queda quieto
        # dentro del mismo numero de siempre: peor, pero no nada.
        movido = False
        if punch > 1.001:
            try:
                movido = resolve_captions.zoom_clip(
                    bridge_post, i, tl_fps, punch,
                    workdir or Path(video).parent)
            except Exception:
                traceback.print_exc()
        z = (fill if movido else punch * fill)
        props = {}
        if z > 1.001:
            props.update(ZoomX=z, ZoomY=z)
        # Zoom alone only fills the frame, it does not choose WHICH part of the
        # frame survives, so without this the vertical crop in Resolve is always
        # centred while the MP4 one aims at the face. Once zoomed, the clip is
        # out_w * z wide inside a window out_w wide, so moving the visible window
        # onto fx means sliding the picture the other way by that fraction of its
        # zoomed width. Pan is in timeline pixels.
        fx = float(seg.get("frame_x", 0.5))
        if (out_w, out_h) != (width, height) and abs(fx - 0.5) > 0.005:
            props["Pan"] = -(fx - 0.5) * out_w * z
        if props:
            bridge_post("/clip/properties", {"trackType": "video", "trackIndex": 1,
                                             "clipIndex": i, "properties": props})

    made = tr("timeline_made", timeline)
    # La pista donde caen los overlays. V1 es la edicion, V2 los subtitulos
    # anidados, y de V3 para arriba lo que se ponga encima.
    ov_track = 3
    if transition in overlays.AS_OVERLAY and len(edl) > 1:
        set_progress(tr("overlaying"), 78, tr("overlaying_help"))
        plan = overlays.at_cuts(edl, transition, tl_fps, start_frame)
        for ev in plan:
            ev["fps"] = tl_fps
        n = resolve_captions.place_overlays(bridge_post, bridge_get_slow, plan,
                                            workdir or Path(video).parent,
                                            out_w, out_h)
        made += " " + tr("overlaid", n, transition) if n else ""
        if n:
            ov_track = 4

    # Los rotulos y las chapas, cada uno en su segundo del montaje. Van despues
    # de las transiciones porque las transiciones ya han decidido si la pista 3
    # esta ocupada.
    if cards and card_style:
        set_progress(tr("overlaying"), 79, tr("overlaying_help"))
        plan = overlays.at_times(
            [{"at": c["at"], "secs": c.get("secs"), "kind": card_style,
              "text": c.get("text", "")} for c in cards],
            tl_fps, start_frame)
        for ev in plan:
            ev["fps"] = tl_fps
        n = resolve_captions.place_overlays(bridge_post, bridge_get_slow, plan,
                                            workdir or Path(video).parent,
                                            out_w, out_h, track=ov_track,
                                            color=card_color)
        if n:
            # Con su nombre y en el numero que toca. Antes decia "1 de tipo
            # rotulo puestos", que es el id crudo y el plural equivocado.
            made += " " + tr("carded", n,
                             overlays.label_of(card_style, _lang, n != 1).lower())

    if look and look != looks.DEFAULT:
        set_progress(tr("painting"), 80, tr("painting_help"))
        paint_clips(look, len(edl), numbers=cdl,
                    log=lambda m: set_progress(tr("painting"), 82, m))

    if captions:
        # Caption times have to follow the CUT video, not the original, so the
        # transcript is folded onto the edit before the chunks are built.
        chunks = chunks or cap.build_chunks(retime_transcript(transcript, edl), preset,
                                            out_w, out_h)
        if chunks:
            # Order measured, not assumed. Building the captions BEFORE the edit
            # was tried and is worse to watch: the user gets a timeline they do
            # not recognise for forty seconds and then their edit appears fully
            # formed in one second, which looks like nothing happened. This way
            # it reads as three acts - your video gets cut, the captions get
            # written one by one, here it is finished - and the middle act is
            # the one that looks like a machine editing, which is the point.
            set_progress(tr("captioning"), 85, tr("captioning_n", len(chunks)))
            out = resolve_captions.build_subs(
                bridge_post, bridge_get_slow, timeline, chunks, preset,
                workdir or Path(video).parent, out_w, out_h, fps,
                log=lambda m: set_progress(tr("captioning"), 88, m), anim=anim)
            if out.get("timeline"):
                mine.append(out["timeline"])
                set_progress(tr("captioning"), 96, tr("nesting"))
                resolve_captions.nest_subs(bridge_post, bridge_get_slow,
                                           timeline, out["timeline"])
            made += " " + tr("captions_made", out["captions"])
    # Back to the top and on the Edit page. The playhead is left wherever the
    # last caption went, which is the middle of the timeline, and a finished
    # edit that opens halfway through does not look finished. This is the last
    # frame of the show and it costs two calls.
    bridge_post("/page", {"page": "edit"})
    bridge_post("/playhead", {"timecode": start_tc})
    bridge_post("/project/save", {})
    return made, mine


def to_edited(t, edl):
    """A second of the ORIGINAL video, expressed in the edited timeline.

    Everything the prompt asks for is stated against the video the user watched,
    because that is the only clock they can see. The edit moves all of it
    earlier by whatever was cut in front. A moment that fell inside a cut has no
    place on the new timeline, so it comes back as None and the caller drops it
    rather than parking it at a wrong second.
    """
    offset = 0.0
    for seg in edl:
        a, b = float(seg["start"]), float(seg["end"])
        # Se pregunta por PERTENENCIA, no por "ya lo hemos pasado". Da lo mismo
        # con un montaje en orden, y es lo unico que vale con uno reordenado:
        # ahi el tramo que va primero puede ser el que en el original iba
        # ultimo, y descartar por "t < a" se llevaba por delante todo lo demas.
        if a <= t <= b:
            return offset + (t - a)
        offset += b - a
    return None                             # cayo en un hueco que se ha ido


def to_original(t, edl):
    """A second of the EDITED timeline, back in the original video's clock.

    The inverse of to_edited, and the thing that makes a second round of prompts
    mean anything. After one pass the user is looking at the EDIT, so when they
    say "cut the bit at minute three" they mean minute three of what is on their
    screen, not of the file they dropped in. Everything downstream still works
    in original seconds, so this is where the two clocks are reconciled.

    Past the end of the edit it returns None: asking for something after the
    video ends is a mistake worth dropping, not rounding to the last frame.
    """
    left = max(0.0, float(t))
    for i, seg in enumerate(edl):
        a, b = float(seg["start"]), float(seg["end"])
        span = b - a
        # Menor ESTRICTO salvo en el ultimo. El final de un trozo y el principio
        # del siguiente son el mismo segundo del montaje, y con `<=` ese segundo
        # se resolvia al final del trozo de delante, que es material CORTADO:
        # justo el fotograma que no esta. Lo que el usuario ve en ese instante
        # es el plano siguiente. En el ultimo si vale, porque ahi no hay
        # siguiente y el final del video es un sitio legitimo al que apuntar.
        if left < span or (left == span and i == len(edl) - 1):
            return a + left
        left -= span
    return None


def actions_to_original(acts, edl):
    """Move a round of actions from edited seconds into the original's clock.

    Done before anything touches the EDL, and in one pass, because the moment
    the first cut is applied the mapping has changed underneath the rest. An
    action whose second no longer exists is dropped rather than moved somewhere
    plausible: a card two seconds off is worse than a card that never appeared,
    since only one of the two is easy to notice.
    """
    out = []
    for a in acts:
        at = to_original(float(a["at"]), edl)
        if at is None:
            continue
        moved = dict(a, at=round(at, 3))
        if "until" in a:
            until = to_original(float(a["until"]), edl)
            if until is None:
                # Hasta el final de lo que hay: pedir "quita desde el minuto 3"
                # sin decir hasta donde es normal y tiene una respuesta obvia.
                until = float(edl[-1]["end"])
            if until <= at:
                continue
            moved["until"] = round(until, 3)
        out.append(moved)
    return out


def reordered(edl, order):
    """El mismo montaje con los tramos en otro orden.

    `order` son los indices del montaje actual en el orden nuevo. Se exige una
    permutacion EXACTA: cada tramo una vez y ninguno inventado. Cualquier otra
    cosa devuelve el montaje intacto en vez de adivinar, porque una lista mal
    formada aqui no da un error visible, da una edicion silenciosamente
    equivocada, que es peor.

    Solo cambia el orden. Ni corta, ni alarga, ni toca los zooms: cada tramo
    viaja entero con lo suyo.
    """
    if not isinstance(order, list) or len(order) != len(edl):
        return edl
    try:
        idx = [int(i) for i in order]
    except (TypeError, ValueError):
        return edl
    if sorted(idx) != list(range(len(edl))):
        return edl
    return [edl[i] for i in idx]


def apply_actions(edl, acts, log=None):
    """Carry out what the prompt asked for at particular moments.

    Cuts and zooms change the EDL, markers ride along on the segment they land
    in, and titles and voice lines are handed back because they cannot be placed
    until the EDL has stopped moving: their second only means something once the
    cuts that come before it are final.
    """
    titles, spoken = [], []
    done = {"cut": 0, "zoom": 0, "marker": 0, "title": 0, "voice": 0}
    for act in acts:
        kind, at = act["do"], float(act["at"])
        if kind == "cut":
            until = float(act["until"])
            fresh = []
            for seg in edl:
                a, b = float(seg["start"]), float(seg["end"])
                if until <= a or at >= b:
                    fresh.append(seg)            # fuera del recorte, intacto
                    continue
                done["cut"] += 1
                if a < at:                       # se queda el trozo de delante
                    fresh.append(dict(seg, end=round(at, 3)))
                if b > until:                    # y el de detras
                    fresh.append(dict(seg, start=round(until, 3)))
            edl[:] = [x for x in fresh if float(x["end"]) - float(x["start"]) >= MIN_KEEP_S]
        elif kind == "zoom":
            until = float(act["until"])
            for seg in edl:
                if float(seg["start"]) < until and float(seg["end"]) > at:
                    seg["zoom"] = max(float(seg.get("zoom", 1.0)), 1.06)
                    done["zoom"] += 1
        elif kind == "marker":
            for seg in edl:
                if float(seg["start"]) <= at <= float(seg["end"]):
                    seg["note"] = act["text"]
                    # Y CUANTO despues de empezar el tramo. Sin esto la marca
                    # caia siempre al principio del tramo que la contiene:
                    # pedirla en el segundo 6 la dejaba en el 0, porque el tramo
                    # empezaba ahi. Las del preset de podcast no traen este
                    # campo y siguen marcando el tramo entero, que es lo suyo:
                    # ahi lo que se marca es la pregunta, no un instante.
                    seg["note_at"] = round(at - float(seg["start"]), 3)
                    done["marker"] += 1
                    break
        elif kind == "title":
            titles.append(act)
        elif kind == "voice":
            spoken.append(act)
    done["title"] = len(titles)
    done["voice"] = len(spoken)
    if log:
        log(", ".join("%d %s" % (n, k) for k, n in done.items() if n) or
            "nada que aplicar")
    return titles, spoken, done


# Como se llama cada cosa cuando se cuenta en la conversacion. Singular y plural,
# porque "1 zooms" delata que lo ha escrito una maquina.
DEED_WORDS = {
    "es": {"cut": ("trozo quitado", "trozos quitados"), "zoom": ("zoom", "zooms"),
           "marker": ("marca", "marcas"), "title": ("cartel", "carteles"),
           "voice": ("voz", "voces")},
    "en": {"cut": ("bit dropped", "bits dropped"), "zoom": ("zoom", "zooms"),
           "marker": ("marker", "markers"), "title": ("card", "cards"),
           "voice": ("voice line", "voice lines")},
}


def said_deeds(done, lang="es"):
    """Lo que se hizo en momentos concretos, contado."""
    words = DEED_WORDS.get(lang, DEED_WORDS["es"])
    out = []
    for key, n in (done or {}).items():
        if not n:
            continue
        one, many = words.get(key, (key, key))
        out.append("%d %s" % (n, one if n == 1 else many))
    return out


def titles_into(chunks, titles, edl):
    """Put the asked-for cards into the caption list, in edited time.

    They join the captions instead of becoming a separate mechanism, so a title
    gets the same look, the same renderer and the same treatment in both
    backends for free. Overlapping captions are pushed out of the way rather
    than stacked, because two lines in the same place is unreadable.
    """
    out = list(chunks or [])
    for t in titles:
        at = to_edited(float(t["at"]), edl)
        if at is None:
            continue
        end = at + float(t.get("secs", 2.0))
        out = [c for c in out
               if float(c["end"]) <= at + 0.05 or float(c["start"]) >= end - 0.05]
        words = t["text"].split()
        step = (end - at) / max(1, len(words))
        out.append({"start": round(at, 3), "end": round(end, 3), "text": t["text"],
                    "words": [{"w": w, "s": round(at + i * step, 3),
                               "e": round(at + (i + 1) * step, 3)}
                              for i, w in enumerate(words)]})
    out.sort(key=lambda c: float(c["start"]))
    return out


def retime_transcript(transcript, edl):
    """Move the words from source time into edited time.

    Once the dead air is gone every word sits earlier than it did in the source,
    by the total length of everything cut before it. Words inside a cut are
    dropped: they are not in the edit any more.
    """
    keeps, offset = [], 0.0
    for seg in edl:
        s, e = float(seg["start"]), float(seg["end"])
        keeps.append((s, e, s - offset))
        offset += e - s
    # Un grupo por tramo del montaje Y frase de la transcripcion, y luego el
    # orden del MONTAJE. Antes se recorria la transcripcion, que va en el orden
    # del ORIGINAL, y los dos ordenes eran el mismo mientras no se pudieran
    # mover los tramos de sitio. Ya no lo son.
    #
    # De paso arregla algo que estaba mal desde antes: una frase partida por un
    # corte salia como UNA sola, con el principio de un lado del corte y el
    # final del otro. Un subtitulo no puede cruzar un corte.
    grupos = {}
    for si, seg in enumerate(transcript.get("segments", [])):
        for w in seg.get("words", []):
            for ki, (s, e, shift) in enumerate(keeps):
                if s <= float(w["s"]) < e:
                    grupos.setdefault((ki, si), []).append(
                        {"w": w["w"], "s": float(w["s"]) - shift,
                         "e": min(float(w["e"]), e) - shift})
                    break
    segments = []
    for clave in sorted(grupos):
        words = grupos[clave]
        segments.append({"start": words[0]["s"], "end": words[-1]["e"],
                         "text": " ".join(x["w"].strip() for x in words),
                         "words": words})
    return {"duration": offset, "segments": segments}


def ai_choice(req=None):
    """Which model answers a prompt, and the key for it.

    Kept in one place because three call sites need the same answer and a second
    copy of this would drift. The request may override the saved settings, so a
    user can try a provider without committing to it.

    The key is looked up per provider: swapping from OpenRouter to Gemini and
    back must not lose either key, and it must not send one vendor's secret to
    another. Never logged, never returned by /config.
    """
    req = req or {}
    cfg = load_config()
    provider = req.get("aiProvider") or cfg.get("aiProvider") or providers.DEFAULT_PROVIDER
    if provider not in providers.PROVIDERS:
        provider = providers.DEFAULT_PROVIDER
    keys = cfg.get("keys") or {}
    # The old single-key config predates the picker; honour it so an upgrade does
    # not silently log the user out of the provider they were already using.
    if not keys.get("anthropic") and cfg.get("anthropicKey"):
        keys["anthropic"] = cfg["anthropicKey"]
    if not keys.get("openai") and cfg.get("openaiKey"):
        keys["openai"] = cfg["openaiKey"]
    if not keys.get("gemini") and cfg.get("geminiKey"):
        keys["gemini"] = cfg["geminiKey"]
    return {"provider": provider,
            "model": req.get("aiModel") or cfg.get("aiModel") or "",
            "key": req.get("aiKey") or keys.get(provider, ""),
            "baseUrl": req.get("aiBaseUrl") or cfg.get("aiBaseUrl") or ""}


def packed_text(transcript):
    """Las frases en el formato que lee el director, sin pasar por disco."""
    return "\n".join(
        "[%07.2f-%07.2f] %s" % (float(x["start"]), float(x["end"]),
                                str(x.get("text", "")).strip())
        for x in transcript.get("segments", []))


def packed_view(workdir, transcript, video):
    """The compact phrase view the director reads, rebuilt if it went missing.

    transcribe.py writes it next to transcript.json, but the engine reuses a
    cached transcript by looking only for transcript.json. A workdir that kept
    one file and lost the other used to take the edit down at this line, and the
    error named a markdown file, which explains nothing to anyone. It is only
    the transcript in fewer characters, so it can simply be written again.
    """
    path = Path(workdir) / "takes_packed.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        pass
    segs = transcript.get("segments", [])
    text = ("# Transcripcion empaquetada\n\nVideo: %s\nDuracion: %.1fs | "
            "Frases: %d | Idioma: %s\n\n" % (video, float(transcript.get("duration", 0)),
                                             len(segs), transcript.get("language", "")))
    text += "\n".join("[%07.2f-%07.2f] %s" % (float(s["start"]), float(s["end"]),
                                              str(s.get("text", "")).strip())
                      for s in segs)
    try:
        path.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return text


# --------------------------------------------------------------------------- #
# The job
# --------------------------------------------------------------------------- #
TRANSCRIBE_RE = re.compile(r"^PROGRESO: (\d+)/(\d+)s")


def run_transcribe(cmd, out_file, timeout=7200):
    """Run the transcriber and relay its progress instead of swallowing it.

    This is the longest step and it used to run under capture_output, so every
    PROGRESO line it printed died inside the pipe and the bar sat at 10% for
    minutes. A progress bar that does not move is worse than no bar: it is the
    only evidence the user has that the program is alive.
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            creationflags=NO_WINDOW)
    killer = threading.Timer(timeout, proc.kill)
    killer.start()
    track(proc)
    tail = deque(maxlen=20)
    how = ""
    try:
        for line in proc.stdout:
            line = line.strip()
            m = TRANSCRIBE_RE.match(line)
            if m:
                done, total = int(m.group(1)), max(1, int(m.group(2)))
                set_progress(tr("transcribing"),
                             min(32, 10 + int(22 * done / total)),
                             "%s%d de %d segundos" % (how, done, total))
            elif line.startswith("CARGANDO_MODELO:"):
                how = line.split(":", 1)[1].strip() + " | "
                set_progress(tr("transcribing"), 10, how.rstrip(" |"))
            elif line.startswith("SIN_GPU:"):
                # Worth showing once: it is the difference between one minute
                # and ten, and the user can act on it.
                set_progress(tr("transcribing"), 10, tr("no_gpu"))
            elif line:
                tail.append(line)
        proc.wait(timeout=120)
    finally:
        killer.cancel()
        untrack(proc)
    # Al parar se le mata, asi que sale con codigo de error: eso no es un fallo
    # de la transcripcion, es lo que se le pidio.
    if _stop.is_set():
        raise Stopped()
    if proc.returncode != 0 or not out_file.exists():
        raise RuntimeError("Fallo transcribiendo: " + "\n".join(tail)[-400:])


def run_render(cmd, out_file, timeout=7200):
    """Run the renderer relaying its PROGRESS lines to /progress in real time."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            creationflags=NO_WINDOW)
    killer = threading.Timer(timeout, proc.kill)
    killer.start()
    track(proc)
    tail = deque(maxlen=25)
    try:
        for line in proc.stdout:
            m = PROGRESS_RE.match(line)
            if m:
                done, total = int(m.group(1)), max(1, int(m.group(2)))
                set_progress(tr("rendering"),
                             min(98, 65 + int(33 * done / total)),
                             f"frame {done} de {total}")
            elif line.strip():
                tail.append(line.strip())
        proc.wait(timeout=60)
    finally:
        killer.cancel()
        untrack(proc)
    if _stop.is_set():
        raise Stopped()
    if proc.returncode != 0 or not out_file.exists():
        raise RuntimeError("Fallo renderizando: " + "\n".join(tail)[-400:])


SESSION = "sesion.json"


def seek_to(at):
    """Mueve el cabezal de Resolve al segundo `at` del timeline que hay delante.

    El segundo es del MONTAJE, que es justo lo que el timeline abierto ES. Un
    timeline no empieza en el frame cero sino en su timecode de inicio (Resolve
    usa 01:00:00:00 casi siempre), asi que hay que sumarselo o el cabezal cae
    una hora antes de donde toca.

    Si no hay Resolve, no es un error del que haya que quejarse: es que se esta
    usando el MP4, donde no hay cabezal que mover.
    """
    tl = bridge_get("/timeline") or {}
    if not tl.get("name"):
        return {"ok": False, "why": "no_resolve"}
    fps = resolve_captions.timeline_fps(tl, 30.0)
    start = int(tl.get("startFrame", 0))
    total = max(0, int(tl.get("endFrame", 0)) - start)
    f = min(max(0, int(round(max(0.0, at) * fps))), max(0, total - 1))
    frame = start + f
    h, resto = divmod(int(frame // fps), 3600)
    m, sec = divmod(resto, 60)
    tc = "%02d:%02d:%02d:%02d" % (h, m, sec, int(frame % fps))
    got = bridge_post("/playhead", {"timecode": tc})
    return {"ok": bool(got.get("success", True)), "timecode": tc,
            "timeline": tl.get("name")}


def words_of(video):
    """Las palabras de un video, si ya se transcribio alguna vez.

    Solo lee del cache. La transcripcion tarda minutos y este endpoint lo llama
    la interfaz al abrir un panel: arrancarla aqui seria colgar la ventana sin
    avisar. Cuando no hay, se dice cual es la razon en una frase, que es lo que
    la interfaz puede enseñar.
    """
    if not video or not Path(video).is_file():
        return {"ok": False, "words": [], "why": "no_video"}
    path = workdir_for(video) / "transcript.json"
    if not path.exists():
        return {"ok": False, "words": [], "why": "no_transcript"}
    data = json.loads(path.read_text(encoding="utf-8"))
    # El reloj del MONTAJE, si ya hay uno. Importa y no es un detalle: una frase
    # con segundos se lee como tiempo del montaje en cuanto hay una edicion
    # hecha (`actions_to_original`), asi que mandar el segundo del ORIGINAL
    # apuntaria a otro sitio, y cuanto mas se haya cortado antes, mas lejos.
    edl = []
    edl_path = workdir_for(video) / "edl.json"
    if edl_path.exists():
        try:
            edl = json.loads(edl_path.read_text(encoding="utf-8")).get("segments") or []
        except Exception:
            edl = []
    out = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            texto = str(w.get("w", "")).strip()
            if not texto:
                continue
            s0 = round(float(w.get("s", 0)), 3)
            # `t` es None cuando esa palabra ya no esta en el montaje. Se manda
            # igual, porque enseñar tachado lo que ya se quito dice mas que
            # esconderlo: asi se ve QUE se llevo el corte automatico.
            t = to_edited(s0, edl) if edl else s0
            out.append({"w": texto, "s": s0, "e": round(float(w.get("e", 0)), 3),
                        "t": round(t, 3) if t is not None else None})
    return {"ok": True, "words": out, "lang": data.get("language", ""),
            "edited": bool(edl),
            "duration": round(float(data.get("duration", 0)), 2)}


def tramos_of(video):
    """El montaje partido en tramos, con lo que se dice en cada uno.

    Es la otra mitad de editar leyendo. Las palabras sueltas sirven para quitar
    un trozo; para MOVER algo de sitio hace falta la unidad que ya existe, que
    es el tramo del montaje. Reordenar palabras sueltas seria inventarse cortes
    que nadie ha pedido.

    `start`/`end` son del ORIGINAL (es lo que el EDL guarda) y `from`/`to` del
    MONTAJE (es lo que se ve). Los dos, porque la interfaz enseña el segundo del
    montaje y el motor razona con el del original.
    """
    if not video or not Path(video).is_file():
        return {"ok": False, "tramos": [], "why": "no_video"}
    path = workdir_for(video) / "transcript.json"
    if not path.exists():
        return {"ok": False, "tramos": [], "why": "no_transcript"}
    st, _ = session_for(video)
    edl = st.get("edl") or []
    if not edl:
        return {"ok": False, "tramos": [], "why": "no_edit"}
    return tramos_de(json.loads(path.read_text(encoding="utf-8")), edl)


def tramos_de(transcript, edl):
    """Lo mismo, ya con la transcripcion y el montaje en la mano.

    Aparte del de arriba para poder fijarlo con casos: el otro lee de disco y
    pregunta al puente en que proyecto estas, y eso no cabe en una prueba que
    tiene que correr sin nada delante.
    """
    palabras = []
    for seg in (transcript or {}).get("segments", []):
        for w in seg.get("words", []):
            texto = str(w.get("w", "")).strip()
            if texto:
                palabras.append((float(w.get("s", 0)), texto))
    out, at = [], 0.0
    for i, seg in enumerate(edl):
        a, b = float(seg["start"]), float(seg["end"])
        # Las palabras de ESTE tramo, en el orden en que se dicen. El orden es
        # el del original y no el del montaje a proposito: dentro de un tramo
        # son la misma cosa, y entre tramos manda el bucle de fuera, que ya va
        # en el orden del montaje aunque el montaje este reordenado.
        dice = " ".join(t for s0, t in palabras if a <= s0 < b)
        out.append({"i": i, "start": round(a, 3), "end": round(b, 3),
                    "from": round(at, 3), "to": round(at + (b - a), 3),
                    "text": dice})
        at += b - a
    return {"ok": True, "tramos": out, "total": round(at, 2)}


def session_save(workdir, state):
    """What a second round of prompts needs to know, next to the transcript."""
    try:
        # La carpeta del proyecto puede no existir todavia: es la primera vez que
        # se habla de este video EN ESTE proyecto.
        Path(workdir).mkdir(parents=True, exist_ok=True)
        (Path(workdir) / SESSION).write_text(
            json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        # Losing the ability to refine is a smaller failure than losing the
        # edit that was just made, so this never raises.
        traceback.print_exc()


def session_for(video, scope=None):
    """La conversacion de ESTE proyecto sobre este video.

    Hay un caso de compatibilidad y solo uno. Las sesiones de antes de esto vivian
    sueltas en la carpeta del video, sin saber de que proyecto eran. Se siguen
    leyendo, pero **solo cuando no hay un proyecto de Resolve abierto**: si lo
    hay, esa conversacion vieja no se sabe si es suya, y enseñarsela es
    justamente el fallo que se esta arreglando.
    """
    scope = scope or scope_now()
    mia = session_dir(video, scope)
    if (Path(mia) / SESSION).exists():
        return session_load(mia), mia
    suelta = workdir_for(video)
    try:
        sin_resolve = not (bridge_status() or {}).get("project")
    except Exception:
        sin_resolve = True
    if sin_resolve and (Path(suelta) / SESSION).exists():
        return session_load(suelta), mia
    return {}, mia


def session_load(workdir):
    try:
        return json.loads((Path(workdir) / SESSION).read_text(encoding="utf-8"))
    except Exception:
        return {}


def workdir_for(video):
    """Donde vive lo que es del ARCHIVO: la transcripcion, sobre todo.

    Transcribir diez minutos cuesta minutos y el resultado no depende de en que
    proyecto estes, asi que esto se comparte a proposito.
    """
    return Path(video).parent / "edit" / Path(video).stem[:40]


def scope_now():
    """En que proyecto estamos, para no mezclar conversaciones.

    El proyecto abierto de Resolve si lo hay, y si no el workspace de Vidorq.
    Sin Resolve y sin nada, "suelto": ahi no hay proyecto que separar.
    """
    try:
        name = (bridge_status() or {}).get("project")
    except Exception:
        name = None
    if not name:
        try:
            name = ws_list()["active"]
        except Exception:
            name = ""
    return _safe_name(name or "suelto")[:40] or "suelto"


def session_dir(video, scope=None):
    """Donde vive lo que es del PROYECTO: la conversacion y el montaje."""
    return workdir_for(video) / "p" / (scope or scope_now())


# --------------------------------------------------------------------------- #
# Historial de ediciones
# --------------------------------------------------------------------------- #
# Vive en la carpeta de configuracion y NO junto al video, a proposito: el
# historial es de la persona, no del archivo. La pregunta que responde es "que
# hice el martes" cuando ya no se recuerda ni como se llamaba aquel video, y
# esa pregunta no se puede contestar desde una carpeta que hay que encontrar
# antes. La sesion de al lado (`sesion.json`) sigue siendo lo otro: la
# conversacion de ESE video en ESE proyecto, para poder retocarlo.
# Lo que se deja escribir en el campo de la ruta. No es la lista de lo que
# ffmpeg sabe abrir, que es enorme: es la de lo que alguien arrastra a un
# editor. Vale para decir "esto no es un video" antes de empezar, no para
# prometer que ese archivo esta sano.
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mpg",
             ".mpeg", ".wmv", ".flv", ".mts", ".m2ts", ".braw", ".r3d"}

LEDGER = CONFIG_DIR / "ediciones.json"
LEDGER_MAX = 200


def ledger_read():
    try:
        got = json.loads(LEDGER.read_text(encoding="utf-8"))
        return got if isinstance(got, list) else []
    except Exception:
        return []


def ledger_add(entry):
    """Anota una edicion. Nunca revienta el turno que acaba de hacerla."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        rows = ledger_read()
        rows.append(entry)
        LEDGER.write_text(
            json.dumps(rows[-LEDGER_MAX:], ensure_ascii=False, indent=1),
            encoding="utf-8")
    except Exception:
        # Perder la anotacion es menos grave que perder la edicion, igual que en
        # session_save: se cuenta por consola y se sigue.
        traceback.print_exc()


def ledger_entry(video, prompt, output, scope, started, **more):
    """La forma de una fila, en un solo sitio.

    Hay tres finales posibles para una edicion (terminada, parada por ti, y
    fallida) y las tres se anotan. Una que solo guardara las que salieron bien
    contaria una historia falsa del dia.
    """
    row = {"at": time.time(),
           "seconds": round(max(0.0, time.time() - started), 1),
           "video": video or "",
           "name": Path(video).name if video else "",
           "prompt": prompt or "",
           "output": output or "",
           "scope": scope or "",
           "did": [],
           "cuts": 0,
           "result": "",
           "ok": True,
           "stopped": False,
           "error": ""}
    row.update(more)
    return row


# Que sabe hacer cada salida. Una sola tabla, porque antes esto vivia como una
# condicion suelta en el render (la transicion solo se pasaba al MP4) y en la
# salida a Resolve se caia sin decir nada: pediste transiciones, no pasaron, y
# nadie te lo conto.
#
# El valor es False (no puede), True (puede entero), o una tupla con lo que
# puede de esa cosa.
CAPABILITIES = {
    "resolve": {
        # La API no tiene transiciones, pero una capa animada encima de cada
        # corte hace las que solo tapan: fundido a negro, a blanco y destello.
        # La disolvencia, el barrido y el deslizamiento necesitan mezclar los
        # DOS planos a la vez y por ahi no se puede pasar.
        "transition": tuple(overlays.AS_OVERLAY),
        "voice": False,     # tampoco admite meter audio
        "shake": False,     # ni keyframes de encuadre por llamada
    },
    "mp4": {
        "transition": tuple(director.TRANSITIONS),
        "voice": True,
        "shake": True,
    },
}


def can_do(output, what, value=None):
    """True si esta salida sabe hacer eso. Con `value`, si sabe hacer ESO."""
    got = (CAPABILITIES.get(output) or {}).get(what, True)
    if isinstance(got, tuple):
        return (value in got) if value is not None else bool(got)
    return bool(got)


# Como se le explica a una persona lo que no cabe en su salida, y que hacer.
CANNOT_WHY = {
    "es": {
        "transition": "Esa transición necesita mezclar los dos planos, y eso Resolve "
                      "no lo hace por API. En Resolve puedo poner fundido a negro o a "
                      "blanco; las demas salen en el MP4.",
        "voice": "Resolve no admite meter audio por su API, la voz solo sale en el MP4.",
        "shake": "El temblor necesita keyframes de encuadre, que Resolve no da por API.",
    },
    "en": {
        "transition": "That transition has to blend both shots, which Resolve will "
                      "not do over its API. In Resolve it can dip to black or dip to "
                      "white; the rest come out in the MP4.",
        "voice": "Resolve takes no audio over its API; the voice only comes out in "
                 "the MP4.",
        "shake": "The shake needs framing keyframes, which Resolve will not set over "
                 "its API.",
    },
}


# Como se le llama a cada ajuste cuando hay que contarselo a una persona. Sin
# esto la respuesta seria "captionPreset: neon", que es el nombre de la variable
# y no el de la cosa.
SETTING_WORDS = {
    "es": {"ratio": "formato", "transition": "transición", "captions": "subtítulos",
           "captionPreset": "estilo", "captionAnim": "entrada", "cuts": "corte",
           "look": "color", "shake": "temblor", "output": "salida"},
    "en": {"ratio": "frame", "transition": "transition", "captions": "captions",
           "captionPreset": "look", "captionAnim": "entrance", "cuts": "cut",
           "look": "colour", "shake": "shake", "output": "output"},
}

# La salida no sale de ningun catalogo, porque no es una eleccion de estilo:
# son los dos sitios a los que puede salir el video.
OUTPUT_WORDS = {"mp4": "MP4", "resolve": "Resolve", "timeline": "Resolve"}


def said_it(changed, settings):
    """Los ajustes que cambiaron, escritos como se los dirias a alguien."""
    words = SETTING_WORDS.get(_lang, SETTING_WORDS["es"])
    out = []
    for key in changed:
        value = settings.get(key)
        # Un si o un no se dice con palabras. "temblor: True" es como habla una
        # base de datos, y esto lo lee una persona en su pantalla.
        if isinstance(value, bool):
            name = words.get(key, key)
            out.append(name if value else
                       ("sin " + name if _lang == "es" else "no " + name))
            continue
        if key in ("cuts",):
            # El criterio con su nombre: "corte: montage" era el id interno.
            for opt in choices_for(key, _lang):
                if opt["id"] == value:
                    value = opt["label"]
                    break
        if key == "transition":
            value = (TRANSITION_LABELS.get(_lang, TRANSITION_LABELS["es"])
                     .get(value, value))
        elif key == "ratio":
            value = RATIO_LABELS.get(_lang, RATIO_LABELS["es"]).get(value, value)
        elif key == "output":
            # "salida: mp4" es el id; lo que se lee es "salida: MP4".
            value = OUTPUT_WORDS.get(value, value)
        elif key in ("look", "captionPreset", "captionAnim"):
            # El nombre de la cosa, no su id. "color: bn" es como se llama la
            # clave por dentro; lo que hay que leer es "Blanco y negro".
            for opt in choices_for(key, _lang):
                if opt["id"] == value:
                    value = opt["label"]
                    break
        out.append("%s: %s" % (words.get(key, key), value))
    return out


def blocked_by_output(output, settings, asked, want_voice=False, want_shake=False):
    """Lo que se ha pedido EN ESTE TURNO y esta salida no puede dar, explicado.

    `asked` son las claves que ha tocado esta frase, y filtra de verdad. Sin ese
    filtro, poner una transicion en el turno 2 hacia que el turno 5 siguiera
    diciendo "no puedo poner transiciones" por un ajuste que nadie habia vuelto
    a mencionar: el aviso se convierte en ruido y se deja de leer.

    Se calcula ANTES de trabajar. Enterarse al final de que la voz no estaba es
    lo mismo que no enterarse, porque el video ya parece terminado.
    """
    why = CANNOT_WHY.get(_lang, CANNOT_WHY["es"])
    out = []
    trans = settings.get("transition") or "none"
    if ("transition" in asked and trans != "none"
            and not can_do(output, "transition", trans)):
        out.append({"what": "transition", "value": trans, "why": why["transition"]})
    if want_voice and not can_do(output, "voice"):
        out.append({"what": "voice", "why": why["voice"]})
    if want_shake and not can_do(output, "shake"):
        out.append({"what": "shake", "why": why["shake"]})
    return out


# Que se ofrece cuando hay que preguntar por una categoria. Cada opcion es un
# id del catalogo de verdad, asi que pulsarla no vuelve a pasar por el modelo:
# se aplica y punto.
# Como viaja una eleccion pulsada. Es un prompt como cualquier otro para que
# entre por el mismo sitio que lo demas y no haya un segundo camino que mantener.
PICK = "pick:"


# Los tres cortes, con el nombre y el criterio de cada uno. En el motor y no en
# la ventana porque la pregunta se contesta aqui.
CUT_LABELS = {
    "es": {"clean": "Limpio (quita silencios)", "podcast": "Podcast (preguntas)",
           "montage": "Montaje (mejores momentos)"},
    "en": {"clean": "Clean (drops silences)", "podcast": "Podcast (questions)",
           "montage": "Montage (best bits)"},
}


def choices_for(key, lang="es", output=None):
    """Los botones de una pregunta, sabiendo en que salida estamos.

    Ofrecer una opcion y refunfunar despues de que la pulses es el peor de los
    dos mundos: parece que funciona, y encima te deja donde estabas. Aqui, lo
    que esta salida no sabe hacer se sigue enseñando (esconderlo seria fingir
    que no existe) pero dice que sale en el MP4 Y lo cambia al pulsarlo, asi que
    el boton hace lo que promete en un clic en vez de abrir un bucle.
    """
    if key == "cuts":
        words = CUT_LABELS.get(lang, CUT_LABELS["es"])
        return [{"id": c, "label": words.get(c, c)} for c in director.CUTS]
    if key == "transition":
        words = TRANSITION_LABELS.get(lang, TRANSITION_LABELS["es"])
        out = []
        for tval in director.TRANSITIONS:
            if tval == "none":
                continue
            opt = {"id": tval, "label": words.get(tval, tval)}
            if output and not can_do(output, "transition", tval):
                opt["note"] = tr_in(lang, "only_mp4")
                opt["send"] = "%stransition=%s&output=mp4" % (PICK, tval)
            out.append(opt)
        return out
    if key == "captionPreset":
        return [{"id": p["id"], "label": p["label"]} for p in cap.preset_list(lang)]
    if key == "captionAnim":
        return [{"id": a["id"], "label": a["label"]} for a in cap.anim_list(lang)]
    if key == "look":
        return [{"id": l["id"], "label": l["label"]} for l in looks.catalogue(lang)
                if l["id"] != "none"]
    if key == "ratio":
        words = RATIO_LABELS.get(lang, RATIO_LABELS["es"])
        return [{"id": r, "label": words.get(r, r)} for r in director.RATIOS]
    return []


def clock(seconds):
    """Segundos como los lee una persona: 1:07, no 67.0."""
    seconds = max(0, int(round(float(seconds))))
    return "%d:%02d" % (seconds // 60, seconds % 60)


def spans_ask(prompt, edl, transcript=None, lang="es"):
    """Los tramos del montaje, para poder señalar uno sin saberse el segundo.

    Cada opcion es la frase entera que se enviaria escribiendola, con el segundo
    ya dentro. Asi no hay un estado "accion pendiente" que mantener: se pulsa y
    entra por el mismo camino que el texto, que es el que esta probado.

    Los tiempos son los del MONTAJE, que es el reloj que el usuario esta viendo
    en la ventana, y no los del video original.
    """
    if not edl:
        return []
    dicho = {}
    for seg in (transcript or {}).get("segments") or []:
        dicho[round(float(seg.get("start", 0)), 1)] = (seg.get("text") or "").strip()
    opts, t = [], 0.0
    for i, seg in enumerate(edl[:12], 1):
        dur = float(seg["end"]) - float(seg["start"])
        texto = ""
        for start, words in dicho.items():
            if float(seg["start"]) - 0.6 <= start <= float(seg["end"]):
                texto = words[:38]
                break
        etiqueta = "%d · %s-%s" % (i, clock(t), clock(t + dur))
        if texto:
            etiqueta += " «%s»" % texto
        # La frase describe el TRAMO ENTERO, con su principio y su final, y no
        # un punto: "quita un trozo en el segundo 11" no dice cuanto hay que
        # quitar, y medido el 2026-08-19 el modelo de tiempos devolvia una lista
        # vacia y no se quitaba nada. Con los dos extremos contesta bien, y
        # ademas es lo que significa señalar un tramo: ese, entero.
        opts.append({"id": "%d" % i,
                     "label": etiqueta,
                     "send": "%s del segundo %d al %d" % (
                         prompt.strip().rstrip("."), int(t), int(round(t + dur)))})
        t += dur
    return [{"what": "at",
             "question": ("¿En qué parte?" if lang == "es" else "Which part?"),
             "options": opts}]


ASK_WORDS = {
    "es": {"transition": "¿Qué transición?", "captionPreset": "¿Qué estilo de subtítulo?",
           "captionAnim": "¿Cómo quieres que entren?", "look": "¿Qué filtro de color?",
           "ratio": "¿Qué formato?", "cuts": "¿Cómo quieres que lo corte?"},
    "en": {"transition": "Which transition?", "captionPreset": "Which caption look?",
           "captionAnim": "How should they come in?", "look": "Which colour filter?",
           "ratio": "Which frame?", "cuts": "How should I cut it?"},
}


def pick_pairs(prompt):
    """Lo que trae un boton pulsado, como diccionario.

    Un boton puede decidir mas de una cosa a la vez. El caso real es la
    transicion que Resolve no sabe hacer: el boton pone la transicion Y cambia
    la salida a MP4, porque ofrecerla y luego negarla es lo que dejaba al
    usuario dando vueltas entre la misma pregunta y la misma negativa.
    """
    pares = {}
    for trozo in prompt[len(PICK):].split("&"):
        key, _, value = trozo.partition("=")
        if key and value:
            pares[key] = value
    return pares


def said_pick(prompt, lang="es"):
    """Un boton pulsado, escrito como lo diria una persona.

    Lo que viaja es "pick:transition=dip" porque entra por el mismo sitio que
    todo lo demas, pero eso en la conversacion se lee como un error de la
    maquina. Se guarda ya traducido.
    """
    words = SETTING_WORDS.get(lang, SETTING_WORDS["es"])
    dichos = []
    for key, value in pick_pairs(prompt).items():
        etiqueta = OUTPUT_WORDS.get(value, value) if key == "output" else value
        for opt in choices_for(key, lang):
            if opt["id"] == value:
                etiqueta = opt["label"]
                break
        dichos.append("%s: %s" % (words.get(key, key), etiqueta))
    return ", ".join(dichos) or prompt


def shown(prompt, lang="es"):
    """Como se ve en la conversacion lo que se mando.

    Un boton viaja como "pick:transition=dip" y eso en pantalla se lee como un
    fallo del programa. Antes solo se traducia en el camino bueno; en los dos
    atajos (no se puede hacer / falta decidir algo) se guardaba crudo, que son
    justo los turnos en los que el usuario ya esta desconcertado.
    """
    if prompt.startswith(PICK):
        return said_pick(prompt, lang)
    return prompt


def ask_for(keys, lang="es", output=None):
    """Las preguntas pendientes, listas para pintarse como botones."""
    words = ASK_WORDS.get(lang, ASK_WORDS["es"])
    out = []
    for key in keys:
        options = choices_for(key, lang, output)
        if options:
            out.append({"what": key, "question": words.get(key, key),
                        "options": options})
    return out


def refine_settings(prompt, base, ai=None, model=None, log=None):
    """Que ajustes deja esta frase, sobre los que ya habia.

    Dos fuentes y un orden que importa. Primero el modelo, al que se le pide
    SOLO el delta (director.change), y encima las palabras literales, que ganan:
    son exactas, cuestan cero y ya esta medido que aciertan donde el modelo se
    despista. La version anterior usaba solo las palabras, y por eso una frase
    fuera del puñado de reglas no cambiaba nada y aun asi rehacia el video.

    Devuelve (ajustes, lo_que_cambio, lo_que_no_entendio).
    """
    out = dict(base)
    # Una eleccion pulsada en el chat llega ya decidida ("pick:transition=dip").
    # No pasa por el modelo: preguntarle que quiso decir alguien que acaba de
    # pulsar un boton es tirar diez segundos y arriesgarse a que conteste otra
    # cosa.
    if prompt.startswith(PICK):
        pares = pick_pairs(prompt)
        return dict(base, **pares), list(pares), []
    # Un retoque sin frase existe: mover un tramo de sitio se pide arrastrando,
    # no hablando. Preguntarle al modelo que quiso decir una frase vacia son
    # diez segundos y una respuesta inventada.
    if not prompt.strip():
        return dict(base), [], []
    delta, cannot, _why = director.change(prompt, base, ai, model, log)
    # El modelo de ajustes no manda sobre lo que pasa en un momento concreto:
    # eso lo lleva director.actions. Sin esta linea contestaba "esto no se
    # hacerlo: un zoom en el segundo 11" y acto seguido otra parte del programa
    # lo hacia, o sea que la respuesta era falsa.
    if director.wants_moments(prompt) or director.needs_where(prompt):
        cannot = []
    words = director.from_words(prompt)
    delta.update(words)
    # Lo que la frase nombra sin concretar se PREGUNTA, y por eso la suposicion
    # del modelo para esa clave se cae aqui. Que el modelo conteste "disolvencia"
    # a "pon transiciones" no significa que tu lo hayas dicho, y aplicarlo seria
    # volver a adivinar por otro camino.
    for key in director.vague(prompt, director.decided(prompt)):
        delta.pop(key, None)
    for key, value in delta.items():
        if key == "captionAnim" and value == "__any__":
            out["captionAnim"] = cap.PRESETS[
                out.get("captionPreset") or cap.DEFAULT_PRESET]["anim"]
            continue
        out[key] = value
    if delta.get("captions") is False:
        out["captionAnim"] = ""
    changed = sorted(k for k in delta if out.get(k) != base.get(k))
    # Un "no puedo" que habla de lo que SI se ha hecho, o de lo que se esta a
    # punto de preguntar, no es un limite: es una contradiccion. Medido contra un
    # video real: "hazme un resumen con los mejores momentos" cambiaba el corte a
    # montaje y en la misma respuesta decia que no sabia hacer un resumen.
    tocado = set(changed) | set(director.vague(prompt, director.decided(prompt)))
    if tocado:
        cannot = [c for c in cannot if not _echoes(c, tocado)]
    # Cada aviso sale de aqui siendo una frase entera. Antes eran trozos sueltos
    # ("musica de fondo") y la ventana les pegaba delante un "Esto no se
    # hacerlo:" para todos a la vez; desde que aqui tambien se cuentan cosas que
    # FALLARON, ese encabezado era mentira para la mitad de la lista.
    return out, changed, [tr("cannot_do", c) for c in cannot]


# Como se llama cada ajuste en la frase de alguien, para reconocer cuando un
# "no puedo" esta hablando de eso mismo.
ECHO_WORDS = {
    "ratio": ("vertical", "horizontal", "cuadrad", "formato", "tiktok", "short",
              "reel", "encuadre"),
    "transition": ("transicion", "transición", "transitions", "fundido",
                   "disolvencia", "corte a negro"),
    "captions": ("subtitul", "subtítul", "caption", "rotulo"),
    "captionPreset": ("subtitul", "subtítul", "caption", "estilo"),
    "captionAnim": ("animaci", "animad", "entrada", "aparec"),
    "cuts": ("corte", "cortar", "resumen", "mejores momentos", "montaje",
             "silencios", "podcast", "highlight"),
    "look": ("color", "filtro", "cinemato", "calid", "cálid", "frio", "frío",
             "blanco y negro", "vintage", "tono", "look"),
    "shake": ("temblor", "tiembl", "sacudid", "shake", "impacto", "golpe de camara"),
    "output": ("mp4", "resolve", "timeline"),
}


def _echoes(text, keys):
    """True si este 'no puedo' esta hablando de alguna de esas claves."""
    low = (text or "").lower()
    for key in keys:
        if any(w in low for w in ECHO_WORDS.get(key, ())):
            return True
    return False


def note_stopped(video, prompt):
    """Dejar el turno parado en la conversacion.

    Sin esto la ventana recarga el historial del motor, no encuentra tu frase y
    la hace desaparecer: parece que no la escribiste nunca.
    """
    if not video:
        return
    past, work = session_for(video)
    if not past.get("edl"):
        return  # No hay conversacion todavia: no habia nada que continuar.
    past["history"] = (past.get("history") or []) + [
        {"you": prompt, "cannot": [{"what": "stop", "why": tr("stopped_by_you")}],
         "ok": False}]
    session_save(work, past)


def run_job(req):
    global _busy
    # Se leen antes del try porque el except los necesita, y parar puede pasar
    # en la primera fase, antes de que el cuerpo haya definido nada.
    stop_video = req.get("video") or ""
    stop_prompt = (req.get("prompt") or "").strip()
    # Cuando empezo, para poder decir en el historial cuanto tardo. Fuera del
    # try por lo mismo que los dos de arriba: parar puede pasar antes. Y el
    # proyecto, para que una edicion parada se anote con el suyo en vez de
    # aparecer sin proyecto en una lista donde las demas si lo llevan.
    started = time.time()
    job_scope = ""
    try:
        video = req["video"]
        preset = req.get("preset", "clean")
        captions = bool(req.get("captions", True))
        output = req.get("output", "mp4")
        prompt = (req.get("prompt") or "").strip()
        ratio = req.get("ratio") or "source"
        transition = req.get("transition") or "none"
        # `colour` y no `look`: mas abajo `look` es lo que devuelve mirar el
        # video con vision.analyse, y llamar igual a dos cosas distintas hacia
        # que el filtro acabara guardado como {}.
        # El temblor nace de la casilla del panel, y a partir de ahi vive en la
        # sesion como cualquier otro ajuste: si en un turno lo pediste hablando,
        # en el siguiente sigue puesto sin tener que repetirlo.
        shake_on = bool(req.get("shake"))
        colour = req.get("look") or ""
        if colour not in looks.PRESETS:
            colour = ""
        # Los numeros del color automatico, si es que se ha pedido. Se calculan
        # una vez, mas abajo, cuando ya se sabe que el video existe.
        auto_cdl, auto_did = None, []
        # The look of the captions. An unknown name falls back to the default
        # instead of failing an edit that has already been transcribed.
        caption_preset = req.get("captionPreset") or profile_load().get(
            "captionPreset") or cap.DEFAULT_PRESET
        if caption_preset not in cap.PRESETS:
            caption_preset = cap.DEFAULT_PRESET
        # The movement is a separate choice from the look. Empty means "whatever
        # this look ships with", which is not the same as the global default.
        caption_anim = req.get("captionAnim") or profile_load().get("captionAnim") or ""
        if caption_anim not in cap.ANIMS:
            caption_anim = ""

        if not Path(video).is_file():
            raise ValueError(tr("no_video", video))

        # Second round and beyond. The user has watched the edit and is asking
        # for a change to THAT, so nothing is decided from scratch: the settings
        # carry over, the transcript is already on disk, and the cuts that are
        # there stay there unless this sentence says otherwise.
        # De que proyecto es esta conversacion. Se calcula UNA vez por turno:
        # preguntarselo al puente cuesta una llamada y el proyecto no cambia a
        # mitad de una edicion.
        scope = job_scope = scope_now()
        past0, sesdir = session_for(video, scope)
        again = bool(req.get("refine")) and bool(past0.get("edl"))
        keep_edl, history, turn = None, [], 1
        moved = False
        changed, not_understood = [], []
        # El montaje y los ajustes ANTES de este turno, copiados aqui porque de
        # aqui en adelante se tocan. Es todo lo que hace falta para poder volver
        # atras un paso.
        # Lo que trae un boton pulsado, si lo que llega es un boton. Se lee una
        # vez y se usa dos: para saber de que iba la pregunta, y para que la
        # salida que decide el boton gane sobre la del desplegable.
        pares = pick_pairs(prompt) if prompt.startswith(PICK) else {}
        prev_edl = [dict(x) for x in (past0.get("edl") or [])]
        prev_settings = dict(past0.get("settings") or {})
        undo = bool(req.get("undo")) and bool(past0.get("edl_prev"))
        if again:
            past = past0
            keep_edl = past["edl"]
            history = past.get("history") or []
            turn = len(history) + 1
            base = past.get("settings") or {}
            if undo:
                # Volver al montaje de antes es volver TAMBIEN a sus ajustes: si
                # el turno que se deshace puso subtitulos amarillos, deshacerlo y
                # dejarlos amarillos no es deshacer nada.
                keep_edl = past["edl_prev"]
                base = past.get("settings_prev") or base
            shake_on = bool(base.get("shake", shake_on))
            set_progress(tr("refining", turn), 6, tr("refine_reading"))
            fresh, changed, not_understood = refine_settings(
                prompt, base, ai_choice(req), req.get("directorModel") or None,
                log=lambda m: set_progress(tr("refining", turn), 7, m))
            ratio = fresh.get("ratio", ratio)
            preset = fresh.get("cuts", preset)
            transition = fresh.get("transition", transition)
            captions = fresh.get("captions", captions)
            shake_on = fresh.get("shake", shake_on)
            caption_preset = fresh.get("captionPreset") or caption_preset
            caption_anim = fresh.get("captionAnim", caption_anim)
            colour = fresh.get("look", colour)
            output = fresh.get("output") or output
            # El desplegable manda... salvo cuando el boton que acabas de pulsar
            # dice a donde va. El desplegable es lo que habia puesto antes; el
            # boton es la decision de ahora, y es la que abre la unica puerta
            # para una transicion que Resolve no sabe hacer.
            if req.get("output") and "output" not in pares:
                output = req["output"]
            set_progress(tr("refining", turn), 8,
                         tr("refine_kept", len(keep_edl),
                            ", ".join(changed) if changed
                            else tr("refine_nothing_said")))

        # El ritmo de tu marca, en los dos numeros que cortan. Se lee aqui y no
        # dentro de edl_from_speech porque el perfil es del workspace y esto es
        # una decision del turno.
        marca = profile_load()
        hueco, aire = pace_gap(marca.get("pace"))
        # El color de tu marca pinta la barra del rotulo. Era el tercer mando de
        # "Tu marca" y el unico que seguia siendo solo texto para el modelo.
        card_color = marca.get("color1") or ""

        # A prompt decides the whole edit, not just the cuts: the shape of the
        # frame, the caption look, its entrance, the joins. Before this the
        # prompt could ask for a vertical short and be handed a wide one.
        plan = None
        if prompt and not again:
            set_progress(tr("directing"), 6)
            # Lo que hay puesto en el panel entra como capa de abajo. Sin esto
            # `look` arrancaba desde sus propios valores de fabrica, asi que
            # elegir "Vertical" y escribir ademas una frase que no hablaba del
            # formato te devolvia un timeline horizontal.
            plan = director.look(prompt, ai_choice(req),
                                 req.get("directorModel") or None, _lang,
                                 log=lambda m: set_progress(tr("directing"), 7, m),
                                 base={"ratio": ratio, "captions": captions,
                                       "captionPreset": caption_preset,
                                       "captionAnim": caption_anim,
                                       "transition": transition, "cuts": preset})
            ratio = plan["ratio"]
            transition = plan["transition"]
            colour = plan.get("look") or colour
            captions = plan["captions"]
            caption_preset = plan["captionPreset"]
            caption_anim = plan["captionAnim"]
            preset = plan["cuts"]
            said = ("dicho por ti: " + ", ".join(plan["said"])) if plan["said"] else ""
            set_progress(tr("directed", plan["by"] or "el texto",
                            "%s, %s, %s/%s" % (ratio, "con subtitulos" if captions
                                               else "sin subtitulos",
                                               caption_preset, caption_anim or "propia")),
                         9, plan.get("why") or said)
            # Si nadie contesto, se DICE, y en el turno, no en una linea de
            # progreso que pasa de largo. Sin modelo local y sin clave, una
            # frase se lee solo con las reglas literales: hace bastante, pero no
            # lo mismo, y el usuario tiene que poder saber cual de las dos cosas
            # le acaba de pasar. La pantalla de ajustes le promete que "funciona
            # sin clave con el modelo local", asi que callarselo es peor.
            if not plan.get("by"):
                not_understood = list(not_understood) + [tr("no_brain")]

        workdir = Path(video).parent / "edit" / Path(video).stem[:40]
        workdir.mkdir(parents=True, exist_ok=True)
        tr_path = workdir / "transcript.json"

        # 1) Transcribe (reuse cached transcript if present)
        if not tr_path.exists():
            set_progress(tr("transcribing"), 10,
                         "La primera vez descarga el modelo; puede tardar unos minutos")
            run_transcribe([PYTHON, str(HELPERS / "transcribe.py"), video,
                            str(workdir)], tr_path)
        transcript = json.loads(tr_path.read_text(encoding="utf-8"))

        # 2) Look at the picture. Optional because it costs minutes on a long
        #    video, and the cuts still work without it - just deafer.
        look = {}
        if req.get("vision"):
            set_progress(tr("watching"), 35, "Los planos son aritmetica; describirlos "
                                             "usa un modelo local")
            try:
                look = vision.analyse(video, workdir,
                                      model=req.get("visionModel") or None,
                                      describe_shots=bool(req.get("visionDescribe", True)),
                                      log=lambda m: set_progress(tr("watching"), 40, m))
                set_progress(tr("watched", len(look.get("shots", [])),
                                " con %s" % look["model"] if look.get("model") else ""), 48)
            except Exception as e:
                # A missing model must not lose an edit that is already transcribed.
                traceback.print_exc()
                set_progress(tr("watching"), 48, "sin vista: %s" % str(e)[:120])

        # 3) Build the EDL
        set_progress(tr("deciding"), 50)
        # Impact shake on the beats. Off unless asked for: it is a look, not a
        # correction, and a podcast does not want its camera flinching.
        shake = shake_on
        report = {}
        # Cambiar el ESTILO de corte es lo unico de un retoque que obliga a
        # volver a cortar: los demas ajustes se pintan encima de la misma
        # edicion, pero "limpio" y "montaje" son dos ediciones distintas. Sin
        # esto la pregunta "como quieres que lo corte" tenia tres botones que no
        # hacian nada, que es peor que no preguntar.
        recut = again and bool({"cuts", "shake"} & set(changed))
        if again and not recut:
            # Los cortes que ya hay se respetan: esta frase es un retoque, no
            # una edicion nueva. Lo que la frase pida se aplica ENCIMA.
            edl = [dict(x) for x in keep_edl]
            # Y si vienen los tramos en otro orden, se ponen en ese orden. No
            # pasa por el modelo ni por una frase: mover el tercero al principio
            # no se puede decir con segundos sin que se preste a confusion, y
            # aqui no hay nada que interpretar, es una permutacion.
            edl = reordered(edl, req.get("order"))
            if len(edl) == len(keep_edl) and [dict(x) for x in keep_edl] != edl:
                moved = True
        elif prompt and not again:
            packed = packed_view(workdir, transcript, video)
            if look.get("shots"):
                # The model reads the video instead of watching it: the visual
                # track goes in next to the words, in the same shape.
                packed += "\n\nLO QUE SE VE (plano por plano):\n" + vision.packed(look)
            brand = profile_load()
            if brand:
                prompt += "\n\nPERFIL DE MARCA DEL USUARIO (respetalo): " + json.dumps(
                    brand, ensure_ascii=False)
            edl = director.segments(prompt, packed, ai_choice(req),
                                    req.get("directorModel") or None,
                                    log=lambda m: set_progress(tr("deciding"), 52, m))
            if not edl:
                # A model that could not produce a usable timeline must not cost
                # the edit: the deterministic engine is good, and the look the
                # prompt asked for still applies.
                set_progress(tr("deciding"), 54, "uso los cortes del motor")
                edl, report = edl_from_speech(transcript,
                                              transcript.get("language", _lang),
                                              max_gap=hueco, pad=aire,
                                              track=look.get("track"), shake=shake)
        elif preset == "montage":
            edl, report = edl_montage(video, transcript, track=look.get("track"),
                                      lang=transcript.get("language", _lang),
                                      max_gap=hueco, pad=aire)
        else:
            edl, report = edl_from_speech(transcript, transcript.get("language", _lang),
                                          max_gap=hueco, pad=aire,
                                          track=look.get("track"), shake=shake)
            if preset == "podcast":
                edl = mark_questions(transcript, edl)
        if not edl:
            # "El EDL salio vacio" es lo que le decia a quien arrastra un plano
            # de recurso o un videoclip: una palabra que no significa nada fuera
            # de aqui y ninguna salida. Los dos casos que lo provocan son
            # distintos y tienen respuestas distintas.
            hay_voz = any(seg.get("words")
                          for seg in (transcript or {}).get("segments", []))
            raise RuntimeError(tr("kept_nothing") if hay_voz else tr("no_speech"))

        # 3b) Which third of the width to keep. Only worth the decoding when the
        #     output is a different shape than the source, because a 16:9 out of
        #     a 16:9 crops nothing and there is nothing to aim. A user who moved
        #     the crop slider gets what they moved it to: a person who framed it
        #     by hand has already answered the question.
        hand_framed = abs(float(req.get("cropX", 0.5)) - 0.5) > 0.01
        hits = 0
        if ratio and ratio != "source" and not hand_framed and faces.available():
            set_progress(tr("framing"), 60, tr("framing_help"))
            try:
                hits = faces.frame_edl(video, edl,
                                       default=float(req.get("cropX", 0.5)),
                                       log=lambda m: set_progress(tr("framing"), 60, m))
                set_progress(tr("framing"), 61,
                             tr("framed", hits, len(edl)) if hits
                             else tr("framed_none"))
            except Exception as e:
                # A crop that centres is a worse crop, not a failed edit.
                traceback.print_exc()
                set_progress(tr("framing"), 61, "sin encuadrar: %s" % str(e)[:120])

        # 3b-bis) Un retoque que no cambio ningun ajuste y no pidio nada en
        #     ningun momento concreto NO se hace. Rehacer la misma edicion para
        #     entregar exactamente el mismo video es lo que hacia que "pon
        #     transiciones en cada corte" acabara en un rato mirando como se
        #     colocaban otra vez los mismos 751 subtitulos.
        #     Mover un tramo de sitio SI cambia el video, y no pasa por
        #     `changed` porque no es un ajuste: es el montaje.
        if again and not moved and not undo:
            # Lo que ha cambiado y esta salida SI sabe hacer. Cambiar la
            # transicion con salida a Resolve no cambia nada de lo que se ve,
            # asi que rehacer el montaje entero para entregar el mismo video es
            # exactamente lo que hacia que pedir transiciones acabara en un rato
            # mirando como se colocaban otra vez los mismos subtitulos.
            asked = set(changed)
            blocked = blocked_by_output(
                output, {"ratio": ratio, "transition": transition}, asked,
                want_voice=False, want_shake=shake_on and "shake" in asked)
            dead = {b["what"] for b in blocked}
            useful = [k for k in changed if k not in dead]
            # Categorias nombradas sin decir cual. "Pon transiciones" dice que
            # quieres transiciones, no cuales. Antes se adivinaba (disolvencia) o
            # se decia que no se entendia; las dos son peores que preguntar, y
            # preguntar es ademas la unica que ensena lo que hay.
            pending = ask_for(director.vague(prompt or "",
                                             director.decided(prompt or "")),
                              _lang, output)
            pide_sitio = prompt and (director.wants_moments(prompt)
                                     or director.needs_where(prompt))
            if pending and not pide_sitio:
                answer = {"you": shown(prompt, _lang), "did": [], "cannot": blocked,
                          "unknown": [], "ask": pending, "offer": {}, "ok": False}
                past["history"] = history + [answer]
                session_save(sesdir, past)
                set_progress(tr("done"), 100, result=pending[0]["question"])
                return
            if not useful and not pide_sitio:
                answer = {"you": shown(prompt, _lang), "did": [], "cannot": blocked,
                          "unknown": not_understood,
                          "offer": ({"kind": "mp4"} if blocked else {}),
                          "ok": False}
                # Sin frase y sin cambios no hay turno que recordar. Guardarlo
                # dejaba una burbuja VACIA en la conversacion, que se lee como
                # un mensaje que se perdio por el camino.
                if answer["you"]:
                    past["history"] = history + [answer]
                    session_save(sesdir, past)
                set_progress(tr("done"), 100,
                             result=(blocked[0]["why"] if blocked
                                     else tr("not_understood")))
                return

        # 3c) What the prompt asked for at particular moments. After the cuts
        #     are decided and before anything downstream reads the EDL, because
        #     a cut here moves every second that comes after it.
        want_titles, want_voice, deeds = [], [], {}
        # Pediste algo que pasa en un sitio y no dijiste en cual. Se enseñan los
        # tramos con su reloj y se elige uno, en vez de dejar que un modelo
        # adivine un segundo o no haga nada.
        if again and prompt and director.needs_where(prompt):
            ask_at = spans_ask(prompt, edl, transcript, _lang)
            if ask_at:
                answer = {"you": prompt, "did": [], "cannot": [], "unknown": [],
                          "ask": ask_at, "offer": {}, "ok": False}
                past["history"] = history + [answer]
                session_save(sesdir, past)
                set_progress(tr("done"), 100, result=ask_at[0]["question"])
                return
        if prompt:
            set_progress(tr("moments"), 59, tr("framing_help"))
            try:
                # En un retoque el reloj es el del MONTAJE, que es lo unico
                # que el usuario esta viendo. Asi que se le ensena la
                # transcripcion ya recortada y sus segundos se traducen despues
                # al video original, que es donde vive el EDL.
                if again:
                    packed_now = packed_text(retime_transcript(transcript, edl))
                    span = sum(float(x["end"]) - float(x["start"]) for x in edl)
                else:
                    packed_now = packed_view(workdir, transcript, video)
                    span = float(transcript.get("duration", 0))
                # Si la frase ya trae el verbo y los dos segundos, se hace y
                # ya: es aritmetica, no interpretacion. Ahorra los 11-15
                # segundos del modelo y quita el unico sitio donde un numero
                # que el usuario acaba de señalar podia leerse mal. Es ademas
                # la frase que escribe el propio programa desde los atajos y
                # desde el panel de texto, o sea la mas comun.
                acts = director.literal_actions(prompt, span)
                if acts:
                    set_progress(tr("moments"), 59, tr("literal"))
                else:
                    acts = director.actions(
                        prompt, packed_now, span, ai_choice(req),
                        req.get("directorModel") or None,
                        log=lambda m: set_progress(tr("moments"), 59, m))
                if again and acts:
                    acts = actions_to_original(acts, edl)
                if acts:
                    want_titles, want_voice, deeds = apply_actions(
                        edl, acts,
                        log=lambda m: set_progress(tr("decided"), 59,
                                                   tr("moments_done", m)))
            except Exception as e:
                # An instruction that could not be carried out must not cost the
                # edit: the rest of it is still exactly what was asked for.
                traceback.print_exc()
                set_progress(tr("moments"), 59, "sin momentos: %s" % str(e)[:120])
                not_understood = list(not_understood) + [
                    tr("failed_moments", str(e)[:100])]

        # 3d) El color automatico. Aqui y no antes porque hasta ahora el usuario
        #     podia haberlo cambiado con una frase, y porque mirar el video
        #     cuesta cuatro segundos que no hay que pagar si nadie lo pidio.
        if colour == "auto":
            try:
                set_progress(tr("colouring"), 62, tr("colouring_help"))
                auto_cdl, auto_did, _m = autocolor.analyse(
                    video, float(transcript.get("duration", 0)),
                    log=lambda m: set_progress(tr("colouring"), 62, m))
                if not auto_did:
                    # El video ya esta bien. Decirlo es mas util que aplicar una
                    # correccion de cero y cobrarla como si hubiera hecho algo.
                    set_progress(tr("colouring"), 63, tr("colour_ok"))
            except Exception as e:
                traceback.print_exc()
                set_progress(tr("colouring"), 63, "sin color automatico: %s" % str(e)[:90])
                not_understood = list(not_understood) + [
                    tr("failed_colour", str(e)[:100])]
                colour = ""

        edl_path = workdir / "edl.json"
        edl_path.write_text(json.dumps({"segments": edl}, indent=1), encoding="utf-8")
        kept = sum(s["end"] - s["start"] for s in edl)
        detail = f"{len(edl)} tramos, {kept:.0f}s conservados de {transcript['duration']:.0f}s"
        if report.get("fillers") or report.get("takes"):
            detail += " (" + tr("cut_report", len(edl), report.get("fillers", 0),
                                report.get("takes", 0)) + ")"
        if report.get("snapped"):
            detail += tr("snapped", report["snapped"])
        if report.get("beats"):
            detail += tr("beats", report["beats"])
        if report.get("jumps"):
            detail += tr("jumps", report["jumps"])
        set_progress(tr("decided"), 58, detail)

        # 4) Subtitle files. The edited-time transcript is the one that matches
        #    the cut video, so this is also what a translation must start from.
        srt_paths = []
        translated_chunks = None
        if captions:
            edited = retime_transcript(transcript, edl)
            # The line length depends on the frame the caption has to fit in, so
            # a vertical short gets shorter lines than the same edit in 16:9.
            _sw, _sh = video_shape(video)[1:]
            _ow, _oh = out_frame(ratio, _sw, _sh)
            base_chunks = cap.build_chunks(edited, caption_preset, _ow, _oh)
            if base_chunks:
                src_lang = transcript.get("language") or _lang
                p_src = workdir / ("subtitulos_%s.srt" % src_lang)
                p_src.write_text(tl.to_srt(base_chunks), encoding="utf-8")
                srt_paths.append(str(p_src))
                target = (req.get("translate") or "").strip().lower()
                if target and target != src_lang:
                    set_progress(tr("translating", tl.LANGS.get(target, target)), 60)
                    try:
                        # Sentences get translated, then re-chunked to the same
                        # preset. Translating the chunks themselves would hand
                        # the model two words with no sentence around them.
                        edited_tr = tl.translate_transcript(
                            edited, target, req.get("translateModel") or None,
                            ai=ai_choice(req),
                            log=lambda m: set_progress(
                                tr("translating", tl.LANGS.get(target, target)), 62, m))
                        done = cap.build_chunks(edited_tr, caption_preset)
                        p_dst = workdir / ("subtitulos_%s.srt" % target)
                        p_dst.write_text(tl.to_srt(done), encoding="utf-8")
                        srt_paths.append(str(p_dst))
                        if req.get("translateCaptions"):
                            # The captions on screen become the translation.
                            translated_chunks = done
                    except Exception as e:
                        traceback.print_exc()
                        set_progress(tr("translating", target), 62,
                                     "sin traducir: %s" % str(e)[:120])
                        not_understood = list(not_understood) + [
                            tr("failed_translate", str(e)[:100])]

        # 4b) The cards the prompt asked for join the captions, so they get the
        #     same look and the same renderer in both backends instead of a
        #     second mechanism that would have to be built twice.
        # Con que pinta se piden: lo decide la palabra que uso Munir. "Cartel"
        # es el de siempre; "rotulo" y "chapa" tienen su propia forma y no
        # pueden ir en la lista de subtitulos, que solo sabe de una pinta.
        # Solo en Resolve: el MP4 todavia no sabe dibujar la barra, y un rotulo
        # que se va por el camino de los overlays en el MP4 es un rotulo que no
        # aparece en ningun sitio. Alli sigue saliendo como un cartel, que es
        # peor que la barra pero infinitamente mejor que nada.
        card_style = director.title_style(prompt) if want_titles else ""
        cards = []
        if want_titles and card_style:
            for t in want_titles:
                at = to_edited(float(t["at"]), edl)
                if at is None:
                    continue          # cayo en un trozo que se ha cortado
                cards.append({"at": round(at, 3), "secs": float(t.get("secs", 2.0)),
                              "text": t.get("text", "")})
        elif want_titles:
            base = translated_chunks or cap.build_chunks(
                retime_transcript(transcript, edl), caption_preset,
                *out_frame(ratio, *video_shape(video)[1:]))
            translated_chunks = titles_into(base, want_titles, edl)
            captions = True

        # 4c) The spoken lines get made now, once the EDL is final, because a
        #     voice-over is placed by the clock of the EDITED video: every cut
        #     before it has already moved the second it belongs to.
        made_names = []
        voice_files = []
        if want_voice:
            engine_id = req.get("voiceEngine") or speech.DEFAULT_ENGINE
            cfg_keys = (load_config().get("keys") or {})
            e = speech.ENGINES.get(engine_id) or {}
            for i, act in enumerate(want_voice):
                at = to_edited(float(act["at"]), edl)
                if at is None:
                    continue          # cayo en un trozo que se ha cortado
                dest = workdir / ("voz_%02d%s" % (i, speech.ext(engine_id)))
                try:
                    set_progress(tr("rendering"), 63, tr("voice_making", i + 1,
                                                         len(want_voice)))
                    speech.say(act["text"], dest, engine_id,
                               req.get("voiceId") or "",
                               cfg_keys.get(e.get("key_id") or "", ""),
                               req.get("voiceBaseUrl") or "")
                    voice_files.append({"at": round(at, 3), "path": str(dest)})
                except Exception as ex:
                    # One line that could not be spoken must not cost the edit.
                    traceback.print_exc()
                    set_progress(tr("rendering"), 63,
                                 "sin voz en %.1fs: %s" % (at, str(ex)[:120]))
                    not_understood = list(not_understood) + [
                        tr("failed_voice", at, str(ex)[:100])]

        # 5) Execute on the chosen backend
        if output == "resolve":
            set_progress(tr("building"), 65,
                         "Necesita Resolve abierto con CursorBridge activo")
            if not bridge_status()["bridge"]:
                raise RuntimeError("No pude hablar con Resolve. Abre Resolve, un proyecto, "
                                   "y Workspace > Scripts > Vidorq")
            # En un retoque lo que hay que ver es la version nueva, no una
            # coleccion de versiones. Los nombres a borrar salen del estado de la
            # sesion, escritos por la ronda que los creo.
            result, made_names = output_resolve(
                video, edl, transcript, captions, caption_preset, workdir,
                caption_anim, translated_chunks, ratio,
                # Los timelines a borrar salen de la conversacion de ESTE
                # proyecto, no de la carpeta del archivo. Un timeline apuntado
                # por otro proyecto no es nuestro para borrarlo, y borrar el
                # timeline equivocado en Resolve ya se ha visto lo que hace.
                drop=(past0.get("timelines") or []) if again else [],
                look=colour, transition=transition, cdl=auto_cdl,
                cards=cards, card_style=card_style, card_color=card_color)
            if voice_files:
                # Said out loud instead of quietly skipped. The timeline would
                # come back looking finished and be missing the voice, which is
                # the worst way to find out.
                result += "  |  " + tr("voice_only_mp4", len(voice_files))
        else:
            set_progress(tr("rendering"), 65, "Cortes + zooms" + (" + captions" if captions else ""))
            out_file = workdir / f"{Path(video).stem[:40]}_vidorq.mp4"
            cmd = [PYTHON, str(HELPERS / "vidorq_render.py"), video, str(edl_path),
                   str(tr_path), str(out_file), "--preset", caption_preset]
            if transition and transition != "none":
                cmd += ["--transition", str(transition)]
            if ratio and ratio != "source":
                cmd += ["--ratio", str(ratio)]
                if abs(float(req.get("cropX", 0.5)) - 0.5) > 0.01:
                    cmd += ["--crop-x", str(float(req["cropX"]))]
            if caption_anim:
                cmd += ["--anim", caption_anim]
            if colour:
                cmd += ["--look", colour]
                if auto_cdl:
                    # Los numeros medidos van en un archivo, no en la linea de
                    # comandos: son doce decimales y ya hay bastante con la ruta.
                    cdl_path = workdir / "autocolor.json"
                    cdl_path.write_text(json.dumps(auto_cdl), encoding="utf-8")
                    cmd += ["--cdl", str(cdl_path)]
            if cards and card_style:
                cd_path = workdir / "rotulos.json"
                cd_path.write_text(
                    json.dumps([dict(c, kind=card_style, color=card_color)
                                for c in cards], ensure_ascii=False),
                    encoding="utf-8")
                cmd += ["--cards", str(cd_path)]
            if translated_chunks:
                ch_path = workdir / "chunks_traducidos.json"
                ch_path.write_text(json.dumps(translated_chunks, ensure_ascii=False),
                                   encoding="utf-8")
                cmd += ["--chunks", str(ch_path)]
            if voice_files:
                v_path = workdir / "voces.json"
                v_path.write_text(json.dumps(voice_files, ensure_ascii=False),
                                  encoding="utf-8")
                cmd += ["--voices", str(v_path)]
            if not captions:
                cmd.append("--no-captions")
            run_render(cmd, out_file)
            result = str(out_file)

        # Lo que hace falta para que la SIGUIENTE frase sea un retoque y no una
        # edicion desde cero. Se guarda al final, con el EDL ya definitivo.
        # Que se acaba de elegir con un boton, si fue eso. Sirve para encadenar:
        # elegido el estilo, la pregunta natural es como entran.
        # De que iba el boton. Con dos pares (transicion + salida) el que manda
        # es el que NO es la salida: la salida es como se hace, no que se pidio.
        picked = next((k for k in pares if k != "output"), "")
        settings_now = {"ratio": ratio, "transition": transition,
                        "captions": captions, "captionPreset": caption_preset,
                        "captionAnim": caption_anim, "cuts": preset,
                        "look": colour, "output": output, "shake": shake_on}
        # Lo que ha pasado en este turno, contado. Se guarda con la sesion para
        # que la conversacion siga estando ahi despues de cerrar la ventana.
        did = said_it(changed, settings_now) if again else []
        # Que arreglo el color automatico, con sus palabras. "color: Automatico"
        # no dice nada; "color: niveles, balance de blancos" si.
        if auto_did:
            did = [d for d in did if not d.startswith(("color:", "colour:"))]
            did.append(("color: " if _lang == "es" else "colour: ") + ", ".join(auto_did))
        # Mirar el video cuesta minutos y no dejaba ni una linea en la
        # conversacion: marcabas la casilla, esperabas, y el turno terminaba sin
        # mencionarlo. Y si no habia modelo de vision, los planos se encuentran
        # igual (eso es aritmetica) pero no se DESCRIBEN, que es justo la mitad
        # por la que se marca la casilla.
        if req.get("vision"):
            n_planos = len(look.get("shots") or [])
            if n_planos:
                did.append(tr("did_shots", n_planos))
                if not look.get("model"):
                    not_understood = list(not_understood) + [tr("no_eye")]
        # `hits` (encuadre por cara) tenia el mismo problema que `beats` mas
        # abajo: solo se contaba en una linea de progreso que el turno final
        # nunca repetia. Si no habia caras, tambien se dice, porque explica
        # por que el recorte salio centrado en vez de sobre alguien.
        if hits:
            did.append(tr("framed", hits, len(edl)))
        elif ratio and ratio != "source" and not hand_framed and faces.available():
            not_understood = list(not_understood) + [tr("framed_none")]
        did += said_deeds(deeds, _lang)
        # Pediste algo en un momento y no salio nada: se dice. Un turno que se
        # calla es indistinguible de uno que lo ha hecho, que es de donde sale el
        # "no se que ha hecho".
        if (prompt and not any(deeds.values())
                and (director.wants_moments(prompt) or director.needs_where(prompt))):
            not_understood = list(not_understood) + [tr("no_moment")]
        if undo:
            did.append(tr("did_undo"))
        elif moved:
            did.append(tr("did_order", len(edl)))
        did += [tr("did_cut" if len(edl) == 1 else "did_cuts", len(edl))]
        # `report["beats"]`, `report["snapped"]` y `report["jumps"]` tenian el
        # mismo problema: se contaban en la linea de progreso, que pasa de largo
        # en cuanto el render termina, y el turno final se quedaba callado.
        # Mismo patron que la vision o la traduccion antes de esto.
        if report.get("beats"):
            n = report["beats"]
            did.append(tr("did_beats_one" if n == 1 else "did_beats", n))
        if report.get("snapped"):
            n = report["snapped"]
            did.append(tr("did_snapped_one" if n == 1 else "did_snapped", n))
        if report.get("jumps"):
            n = report["jumps"]
            did.append(tr("did_jumps_one" if n == 1 else "did_jumps", n))
        # Solo cuando se sabe el numero aqui. Cuando los subtitulos los arma el
        # backend, el que los ha contado es el, y lo dice en `result`: repetirlo
        # aqui con un cero seria peor que no decirlo.
        if captions and translated_chunks:
            did.append(tr("did_caps", len(translated_chunks)))
        # Los carteles ya los ha contado `said_deeds` unas lineas mas arriba, y
        # los contaba bien ("1 cartel"). Esta linea los repetia y ademas los
        # decia en plural siempre, asi que un turno con uno solo terminaba en
        # "1 cartel - 1 carteles". Contarlo dos veces y una de ellas mal.
        # Las voces ya las conto `said_deeds` unas lineas mas arriba, igual que
        # pasaba con los carteles: "1 voz - 1 voz en off" es lo mismo dicho dos
        # veces. Lo que si aporta es cuando alguna se cayo por el camino porque
        # su segundo estaba en un trozo cortado. El `if voice_files` de antes
        # dejaba fuera el caso en que TODAS se caen: pedias una voz fuera del
        # tramo que quedo, el turno decia "1 voz" como si hubiera funcionado, y
        # `voces.json`/el WAV no se escribian nunca. Medido el 20-ago-2026.
        if want_voice and len(voice_files) < len(want_voice):
            if voice_files:
                did.append(tr("did_voice", len(voice_files)))
            elif len(want_voice) == 1:
                did.append(tr("did_voice_none"))
            else:
                did.append(tr("did_voice_none_many", len(want_voice)))
        blocked = blocked_by_output(output, settings_now, set(changed),
                                    want_voice=bool(want_voice),
                                    want_shake=bool(req.get("shake")))
        answer = {"you": (shown(prompt, _lang) or (tr("said_undo") if undo
                                                    else tr("said_order") if moved
                                                    else tr("history_first"))),
                  "did": [x for x in did if x],
                  "cannot": blocked,
                  "unknown": not_understood,
                  # Se ha hecho algo Y ademas queda algo por concretar: se hace
                  # lo que se entendio y se pregunta lo otro, en vez de parar el
                  # trabajo por una duda que no lo impedia.
                  "ask": (ask_for(director.NEXT_ASK[picked], _lang, output)
                          if picked in director.NEXT_ASK
                          else ask_for(director.vague(
                              prompt or "", director.decided(prompt or "")),
                              _lang, output))
                         if again else [],
                  "offer": ({"kind": "mp4"} if blocked else {}),
                  "result": result,
                  "ok": True}
        session_save(sesdir, {
            "video": video,
            "scope": scope,
            "edl": edl,
            "settings": settings_now,
            "history": (history if again else []) + [answer],
            "timelines": made_names,
            "result": result,
            # Y de donde se venia. Deshacer dos veces vuelve a donde estabas,
            # porque el paso anterior de un deshacer es lo que se acaba de
            # deshacer: un solo boton que va y vuelve.
            "edl_prev": prev_edl,
            "settings_prev": prev_settings,
        })
        # La misma frase que ve en el chat, no el prompt crudo: en la primera
        # edicion el prompt esta vacio y la frase dice "primera edicion".
        ledger_add(ledger_entry(video, answer["you"], output, scope, started,
                                did=answer["did"], cuts=len(edl), result=result,
                                timelines=made_names))

        if srt_paths:
            result += "  |  " + tr("srt_made", ", ".join(Path(p).name for p in srt_paths))
        set_progress(tr("done"), 100, result=result)
    except Stopped:
        # Lo que se hizo antes de parar se queda: los subtitulos ya colocados
        # estan en el timeline y borrarlos seria una sorpresa peor. Se dice lo
        # que quedo a medias y ya.
        note_stopped(stop_video, stop_prompt)
        ledger_add(ledger_entry(stop_video, stop_prompt, req.get("output") or "",
                                job_scope, started, ok=False, stopped=True))
        set_stopped(tr("stopped"), tr("stopped_help"))
    except Exception as e:
        traceback.print_exc()
        ledger_add(ledger_entry(stop_video, stop_prompt, req.get("output") or "",
                                job_scope, started, ok=False, error=str(e)[:200]))
        set_progress("", 0, error=str(e))
    finally:
        _busy = False


def de_casa(origin):
    """True si ese `Origin` es una ventana de Vidorq y no una web cualquiera.

    El motor escucha en 127.0.0.1, o sea que desde fuera del ordenador no se
    llega. Lo que si llega es cualquier PAGINA que el usuario tenga abierta en
    el navegador: una web puede hacerle peticiones a localhost, y con
    `Access-Control-Allow-Origin: *` ademas puede LEER lo que contesta. Ahi hay
    cosas suyas: `/history` lleva las rutas de sus videos y lo que le pidio a
    cada uno, `/words` la transcripcion entera, `/tramos` lo que dice en cada
    trozo, y `/shutdown` apaga el motor a mitad de una edicion.

    Vale cualquier cosa servida desde su propia maquina, que es donde vive la
    ventana: `http://localhost:1420` en desarrollo y `http://tauri.localhost`
    (o `tauri://localhost`) en la aplicacion compilada. La lista se deja ancha a
    proposito, porque Tauri cambia ese origen entre versiones y entre sistemas,
    y una ventana que no puede hablar con su motor es peor que el problema.

    Sin cabecera `Origin` no hay navegador detras: eso es curl, el skill de un
    agente o Python, y se deja pasar como siempre.
    """
    if not origin:
        return True
    try:
        from urllib.parse import urlparse
        u = urlparse(origin)
    except Exception:
        return False
    if u.scheme in ("tauri", "asset"):
        return True
    host = (u.hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")

# --------------------------------------------------------------------------- #
# HTTP plumbing
# --------------------------------------------------------------------------- #
_server = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send_bytes(self, data, content_type):
        """An image straight down the socket.

        Previews are files on disk, not JSON, and base64 in a JSON envelope would
        make every one of them a third bigger for no reason.

        Antes iban con `max-age=86400` y el comentario decia que eran inmutables
        porque la clave del cache lleva dentro todo lo que entro en la imagen.
        Eso es falso en un caso concreto y medido el 19-ago: la clave lleva lo
        que se le PIDE (video, estilo, formato, idioma) pero no la version del
        que dibuja. Al cambiar el texto de muestra y borrar el cache del disco,
        la ventana seguia enseñando la imagen de antes, porque ni preguntaba.
        Un dia entero viendo lo que ya no es.

        Ahora se revalida siempre y se contesta 304 cuando de verdad no ha
        cambiado nada. Es una peticion a localhost contra un archivo que ya
        esta en disco: cuesta menos que enseñar algo que no es verdad.
        """
        try:
            etag = '"%s"' % hashlib.md5(data).hexdigest()
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("ETag", etag)
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # The window closed or the poll timed out mid-answer. Normal, and the
            # user should not see a stack trace in the console for it.
            pass

    def _cors(self):
        """Las cabeceras de origen, solo para una ventana de esta maquina."""
        origin = self.headers.get("Origin")
        if not de_casa(origin):
            return
        self.send_header("Access-Control-Allow-Origin", origin or "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _ajeno(self):
        """Cierra la puerta a una pagina de fuera antes de hacerle nada.

        No basta con callarse la cabecera: sin ella el navegador impide LEER la
        respuesta, pero la peticion ya se ha hecho, y  o
         no necesitan que nadie lea nada para hacer dano.
        """
        if de_casa(self.headers.get("Origin")):
            return False
        self._send({"error": "origen no permitido"}, 403)
        return True

    def do_OPTIONS(self):
        self._send({})

    def do_GET(self):
        if self._ajeno():
            return
        if self.path == "/health":
            self._send({"ok": True, "version": VERSION, "busy": _busy,
                        "missing": missing_modules()})
        elif self.path == "/progress":
            with _lock:
                self._send(dict(_progress))
        elif self.path == "/workspaces":
            self._send(ws_list())
        elif self.path == "/profile":
            self._send(profile_load())
        elif self.path == "/resolve":
            self._send(bridge_status())
        elif self.path.startswith("/preview"):
            # A picture of what a choice actually does, made by the real
            # renderer. Slow the first time, free every time after, because the
            # cache key already contains everything that went into it.
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            one = lambda k, d="": (q.get(k) or [d])[0]  # noqa: E731
            video = one("video")
            try:
                w, h = 1920, 1080
                at = 1.0
                if video and Path(video).is_file():
                    _, w, h = video_shape(video)
                    at, _fx = previews.best_moment(video)
                kind = one("kind", "style")
                lang = one("lang", "es")
                ratio = one("ratio", "source")
                # The gallery asks for the close-up; the single preview under
                # the picker asks for the whole frame. Same renderer, two jobs.
                band = one("band") == "1"
                if kind == "look":
                    path = previews.look_still(one("id", looks.DEFAULT), ratio,
                                               video, w, h, at, band)
                elif kind == "card":
                    # Con el color de la marca: la baldosa tiene que enseñar el
                    # rotulo que va a salir, no uno neutro.
                    path = previews.card_still(one("id", "rotulo"), ratio,
                                               video, lang, w, h, at,
                                               profile_load().get("color1") or "")
                elif kind == "ratio":
                    path = previews.ratio_still(ratio, video, w, h, at)
                elif kind == "transition":
                    path = previews.transition_still(one("id", "dip"), ratio,
                                                     video, w, h, at)
                elif kind == "anim":
                    path = previews.anim_loop(one("id", "pop"),
                                              one("preset", cap.DEFAULT_PRESET),
                                              ratio, video, lang, w, h, at, band)
                else:
                    path = previews.style_still(one("id", cap.DEFAULT_PRESET),
                                                ratio, video, lang,
                                                one("anim") or None, w, h, at, band)
                mime = "image/webp" if str(path).endswith(".webp") else "image/png"
                self._send_bytes(Path(path).read_bytes(), mime)
            except Exception as e:
                traceback.print_exc()
                self._send({"error": str(e)[:300]}, 500)
        elif self.path.startswith("/session"):
            # Lo que se ha pedido hasta ahora sobre este video, para que la
            # ventana pueda seguir la conversacion despues de cerrarse.
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            video = (q.get("video") or [""])[0]
            if not video:
                self._send({"history": [], "can": False})
            else:
                st, _ = session_for(video)
                # Las sesiones viejas guardaban solo la frase del usuario. Se
                # leen igual, en vez de romper una conversacion que ya existia.
                turns = [({"you": h, "did": [], "cannot": [], "ok": True}
                          if isinstance(h, str) else h)
                         for h in (st.get("history") or [])]
                self._send({"history": turns,
                            "settings": st.get("settings") or {},
                            "result": st.get("result", ""),
                            "scope": st.get("scope") or scope_now(),
                            "can": bool(st.get("edl")),
                            # Si hay un paso atras al que volver. La ventana no
                            # puede saberlo sola: el montaje de antes vive aqui.
                            "canUndo": bool(st.get("edl_prev"))})
        elif self.path.startswith("/probe"):
            # Existe ese archivo? La ventana lo pregunta antes de aceptar una
            # ruta escrita a mano. Sin esto, una letra mal puesta se tragaba en
            # silencio: el nombre aparecia en su sitio, el boton de editar se
            # encendia, y el fallo no salia hasta la mitad de la edicion.
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            video = ((q.get("video") or [""])[0] or "").strip().strip('"')
            lang = (q.get("lang") or ["es"])[0]
            if not video:
                self._send({"ok": False, "why": ""})
            elif os.path.isdir(video):
                self._send({"ok": False, "why": (
                    "Eso es una carpeta, no un vídeo." if lang == "es"
                    else "That is a folder, not a video.")})
            elif not os.path.isfile(video):
                self._send({"ok": False, "why": (
                    "En esa ruta no hay ningún archivo. Míralo bien." if lang == "es"
                    else "There is no file at that path. Check it again.")})
            elif os.path.splitext(video)[1].lower() not in VIDEO_EXT:
                self._send({"ok": False, "why": (
                    "Ese archivo no es un vídeo de los que Vidorq abre." if lang == "es"
                    else "That file is not a video Vidorq can open.")})
            else:
                self._send({"ok": True, "why": "", "name": os.path.basename(video)})
        elif self.path.startswith("/tramos"):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            try:
                self._send(tramos_of((q.get("video") or [""])[0]))
            except Exception as e:
                traceback.print_exc()
                self._send({"ok": False, "tramos": [], "error": str(e)[:200]})
        elif self.path == "/history":
            # Al reves que en el archivo: lo ultimo arriba, que es lo que se
            # busca al abrir la pestaña.
            self._send({"edits": list(reversed(ledger_read()))})
        elif self.path.startswith("/words"):
            # Las palabras con su segundo, tal y como salieron de la
            # transcripcion. Se sirven planas (una lista, no segmentos) porque
            # quien las va a pintar es un parrafo, no un subtitulo.
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            video = (q.get("video") or [""])[0]
            try:
                self._send(words_of(video))
            except Exception as e:
                traceback.print_exc()
                self._send({"ok": False, "words": [], "error": str(e)[:200]})
        elif self.path == "/clips":
            # No bridge_status() gate on purpose. That check allows two seconds,
            # and the moment this gets asked is app startup, when Resolve is busy
            # opening a project and answers slower than that. The gate would time
            # out, report no bridge, and the clip list would stay empty forever
            # without a word. resolve_clips() already returns nothing when the
            # bridge is down, and a refused connection fails instantly anyway.
            try:
                self._send({"clips": resolve_clips()})
            except Exception as e:
                traceback.print_exc()
                self._send({"clips": [], "error": str(e)[:200]})
        elif self.path.startswith("/providers"):
            lang = "en" if "lang=en" in self.path else "es"
            cfg = load_config()
            chosen = ai_choice()
            # Which providers have a key, NOT the keys. A settings screen needs
            # to draw a filled-in field; it never needs the secret back, and an
            # endpoint that hands one out is one XSS away from leaking it.
            saved = set((cfg.get("keys") or {}).keys())
            for old, pid in (("anthropicKey", "anthropic"), ("openaiKey", "openai"),
                             ("geminiKey", "gemini")):
                if cfg.get(old):
                    saved.add(pid)
            self._send({"list": providers.catalogue(lang),
                        "provider": chosen["provider"],
                        "model": chosen["model"],
                        "baseUrl": chosen["baseUrl"],
                        "hasKey": sorted(saved)})
        elif self.path.startswith("/voices"):
            # Same rule as /providers: it says which engines have a key, never
            # what the key is.
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            one = lambda k, d="": (q.get(k) or [d])[0]  # noqa: E731
            lang = one("lang", "es")
            cfg = load_config()
            keys = cfg.get("keys") or {}
            engine_id = one("engine") or cfg.get("voiceEngine") or speech.DEFAULT_ENGINE
            e = speech.ENGINES.get(engine_id) or {}
            body = {"list": speech.catalogue(lang),
                    "engine": engine_id,
                    "voice": cfg.get("voiceId", ""),
                    "baseUrl": cfg.get("voiceBaseUrl", ""),
                    "hasKey": sorted(k for k in keys if keys[k])}
            try:
                body["voices"] = speech.voices(engine_id,
                                               keys.get(e.get("key_id") or "", ""),
                                               cfg.get("voiceBaseUrl", ""))
            except Exception as ex:
                # A bad key must not take the settings screen down with it: the
                # list of engines is still worth drawing.
                body["voices"] = []
                body["error"] = str(ex)[:200]
            self._send(body)
        elif self.path.startswith("/models"):
            # Asked live, so the list is whatever the provider has today rather
            # than whatever was true when this was written.
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            pid = (q.get("provider") or [""])[0]
            over = {"aiProvider": pid} if pid in providers.PROVIDERS else {}
            if q.get("key"):
                over["aiKey"] = q["key"][0]
            if q.get("baseUrl"):
                over["aiBaseUrl"] = q["baseUrl"][0]
            a = ai_choice(over)
            self._send({"provider": a["provider"],
                        "models": providers.models(a["provider"], a["key"],
                                                   a["baseUrl"])})
        elif self.path.startswith("/captions/presets"):
            lang = "en" if "lang=en" in self.path else "es"
            self._send({"default": cap.DEFAULT_PRESET, "list": cap.preset_list(lang),
                        "anims": cap.anim_list(lang),
                        "animOf": {k: v["anim"] for k, v in cap.PRESETS.items()},
                        "langs": tl.LANGS,
                        "looks": looks.catalogue(lang),
                        "cards": overlays.kind_list(lang, only=overlays.WITH_TEXT),
                        "transitions": TRANSITION_LABELS.get(lang, TRANSITION_LABELS["es"]),
                        # Cuales sabe hacer Resolve. Lo sabe la tabla
                        # CAPABILITIES y lo tenian copiado a mano DOS ficheros
                        # de la ventana, que ya se habian separado entre si: la
                        # galeria contaba el destello y el panel no.
                        "resolveTransitions": [
                            t for t in TRANSITION_LABELS.get(
                                lang, TRANSITION_LABELS["es"])
                            if t == "none" or can_do("resolve", "transition", t)],
                        "ratios": RATIO_LABELS.get(lang, RATIO_LABELS["es"])})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        global _busy
        if self._ajeno():
            return
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            return self._send({"error": "bad json"}, 400)
        if self.path == "/config":
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            cfg = load_config()
            # Keys arrive per provider and are merged, not replaced: the settings
            # screen only ever sends the one being edited, and overwriting the
            # whole map would wipe the others.
            incoming = dict(body)
            keys = dict(cfg.get("keys") or {})
            # The allowed ids are the AI providers PLUS the voice engines, and
            # missing the second half is how an ElevenLabs key gets accepted by
            # the screen, dropped on the floor here, and reported later as
            # "needs an API key" by an engine that was just given one.
            allowed = set(providers.PROVIDERS) | {
                e["key_id"] for e in speech.ENGINES.values() if e.get("key_id")}
            for pid, value in (incoming.pop("keys", None) or {}).items():
                if pid in allowed:
                    # An empty string is how the interface says "forget this one".
                    keys[pid] = value
            if keys:
                cfg["keys"] = {k: v for k, v in keys.items() if v}
            # Empty means "no preference" for these, and that has to be storable:
            # otherwise switching provider keeps the old provider's model id
            # forever and the interface offers no way to clear it. Everything
            # else keeps the old rule, where empty means "I am not sending this".
            for field in ("aiModel", "aiBaseUrl", "voiceId", "voiceBaseUrl"):
                if field in incoming:
                    cfg[field] = incoming.pop(field)
            cfg.update({k: v for k, v in incoming.items() if v != ""})
            CONFIG.write_text(json.dumps(cfg), encoding="utf-8")
            self._send({"ok": True})
        elif self.path == "/workspaces":
            created = None
            if body.get("create"):
                created = _new_ws_name(body["create"])
                (WORKSPACES / created).mkdir(parents=True, exist_ok=True)
            if body.get("activate"):
                # El flujo de "Nuevo workspace" manda `create` y `activate` con
                # el MISMO texto crudo: si `create` lo saneo a otro nombre para
                # no chocar con uno que ya existe, activar tiene que apuntar a
                # ese nombre ya resuelto, no volver a sanear el mismo texto por
                # su cuenta y acabar en un "Principal" distinto del que se creo.
                cfg = load_config()
                cfg["activeWorkspace"] = (created if body["activate"] == body.get("create")
                                          else _safe_name(body["activate"]))
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                CONFIG.write_text(json.dumps(cfg), encoding="utf-8")
            self._send(ws_list())
        elif self.path == "/profile":
            profile_save(body)
            self._send({"ok": True})
        elif self.path == "/edit":
            global _lang
            if body.get("lang") in TEXT:
                _lang = body["lang"]
            if _busy:
                return self._send({"error": tr("busy")}, 409)
            gone = missing_modules()
            if gone:
                return self._send({"error": tr("no_deps") % ", ".join(gone)}, 503)
            _busy = True
            # La bandera del turno anterior no puede matar a este.
            _stop.clear()
            set_progress(tr("preparing"), 3)
            threading.Thread(target=run_job, args=(body,), daemon=True).start()
            self._send({"ok": True})
        elif self.path == "/seek":
            # Llevar el cabezal de Resolve a un segundo del MONTAJE. Es lo unico
            # que Vidorq puede hacer y una pagina web no: corre DENTRO de
            # Resolve. Pulsar una palabra y ver el fotograma es la diferencia
            # entre leer la transcripcion y editar con ella.
            try:
                self._send(seek_to(float(body.get("at", 0.0))))
            except Exception as e:
                traceback.print_exc()
                self._send({"ok": False, "error": str(e)[:200]})
        elif self.path == "/history":
            # Borrar el historial es suyo, no mio: son sus ediciones y su disco.
            # Solo se borra la lista; los videos y los timelines no se tocan.
            try:
                LEDGER.unlink(missing_ok=True)
                self._send({"ok": True, "edits": []})
            except Exception as e:
                self._send({"ok": False, "error": str(e)[:200]})
        elif self.path == "/stop":
            # Parar el turno en marcha. Idempotente y sin cuerpo: se puede
            # pulsar dos veces sin que pase nada raro.
            if not _busy:
                return self._send({"ok": True, "idle": True})
            killed = stop_all()
            self._send({"ok": True, "killed": killed})
        elif self.path == "/shutdown":
            # Resolve starts the engine with no console window, so there has to be
            # a way to stop it that is not the task manager.
            self._send({"ok": True})
            if _server:
                threading.Thread(target=_server.shutdown, daemon=True).start()
        else:
            self._send({"error": "not found"}, 404)


def already_running():
    """True if a Vidorq engine is already answering on our port."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=1) as r:
            return bool(json.loads(r.read().decode()).get("ok"))
    except Exception:
        return False


if __name__ == "__main__":
    # Launching twice used to end in a stack trace and a console window stuck on
    # "press any key", which is how people pile up dead windows without knowing why.
    if already_running():
        print(f"[VidorqEngine] Ya hay un motor corriendo en http://{HOST}:{PORT}.")
        print("[VidorqEngine] No hace falta abrir otro. Puedes cerrar esta ventana.")
        sys.exit(0)
    print(f"[VidorqEngine] v{VERSION} en http://{HOST}:{PORT}  (Ctrl+C para parar)")
    try:
        # Threaded: /resolve asks the bridge three questions, and a single-threaded
        # server would freeze the app's health poll while it waits.
        _server = ThreadingHTTPServer((HOST, PORT), Handler)
        _server.serve_forever()
        print("[VidorqEngine] Parado.")
    except KeyboardInterrupt:
        print("[VidorqEngine] Parado.")
    except OSError as e:
        print(f"[VidorqEngine] No pude abrir el puerto {PORT}: {e}")
        print(f"[VidorqEngine] Mira que no haya otro programa usandolo.")
        sys.exit(1)
