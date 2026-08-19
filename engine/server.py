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
    POST /edit       -> {"video", "preset", "captions", "output", "prompt"} starts a job

Workspaces live in %APPDATA%/Vidorq/workspaces/<name>/ (brand.json + future memory);
each one is a brand/project with its own style profile.

Presets (no API key needed, fully local):
    clean    keep speech, drop silences/dead air
    podcast  clean + a marker/zoom on every question
    montage  keep the highest-energy chunks (beta)
Prompt mode (Modo Pro) uses the Anthropic API with the user's own key.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
import threading
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
        "busy": "Ya hay una edicion en marcha",
        "no_video": "No encuentro el video: %s",
        "preparing": "Preparando...",
        "transcribing": "Transcribiendo (Whisper local)...",
        "watching": "Mirando el video (planos y movimiento)...",
        "watched": "%d planos vistos%s",
        "deciding": "Decidiendo los cortes...",
        "decided": "Cortes decididos",
        "rendering": "Renderizando (GPU)...",
        "building": "Montando timeline en Resolve...",
        "done": "Listo",
        "stopped": "Parado",
        "stopped_help": "Lo que ya estaba puesto se queda en el timeline",
        "stopped_by_you": "Lo paraste tu a mitad. Lo que ya estaba hecho se queda.",
        "timeline_made": "Timeline '%s' creado en Resolve",
        "captioning": "Poniendo los subtitulos en Resolve...",
        "captioning_n": "%d subtitulos, uno a uno",
        "captions_made": "con %d subtitulos editables",
        "cut_report": "%d cortes, %d muletillas fuera, %d tomas repetidas",
        "snapped": ", %d cortes movidos a un momento quieto",
        "jumps": ", %d saltos tapados cambiando el encuadre",
        "beats": ", %d cortes sobre el movimiento",
        "translating": "Traduciendo los subtitulos a %s...",
        "srt_made": "Subtitulos guardados en %s",
        "directing": "Leyendo lo que has pedido...",
        "directed": "%s decidio: %s",
        "no_deps": ("Al motor le falta %s. Lo han arrancado con el Python "
                    "equivocado: cierralo y usa engine\\start_engine.bat"),
        "framing": "Buscando la cara para encuadrar...",
        "framing_help": "Detector local, milisegundos por fotograma",
        "framed": "Encuadre sobre la cara en %d de %d tramos",
        "framed_none": "Sin caras: recorte centrado",
        "no_gpu": "Sin GPU para transcribir, va por CPU y tarda mas",
        "moments": "Leyendo lo que pides en momentos concretos...",
        "moments_done": "En momentos concretos: %s",
        "refine_reading": "Se lo estoy preguntando a la IA...",
        "not_understood": "No he entendido que cambiar, asi que no he tocado nada.",
        "did_cuts": "%d tramos",
        "did_cut": "%d tramo",
        "did_caps": "%d subtitulos",
        "did_titles": "%d carteles",
        "did_voice": "%d voz en off",
        "painting": "Coloreando en Resolve...",
        "painting_help": "Una correccion primaria por clip, que puedes seguir tocando a mano",
        "painted": "%d clips con el filtro '%s'",
        "overlaying": "Poniendo las transiciones...",
        "overlaying_help": "Una capa animada en cada corte, en su propia pista",
        "overlaid": "%d transiciones '%s'",
        "refining": "Retoque %d: leyendo lo que pides...",
        "refine_kept": "Sigo sobre el montaje que ya hay (%d tramos). Cambias: %s",
        "refine_nothing_said": "solo lo de momentos concretos",
        "history_first": "primera edicion",
        "voice_making": "Poniendo voz a la linea %d de %d...",
        "voice_only_mp4": "%d voz(es) generadas, pero en Resolve no se pueden meter por API: salen solo en el MP4.",
        "nesting": "Poniendo los subtitulos encima de tu edicion...",
    },
    "en": {
        "busy": "There is already an edit running",
        "no_video": "Cannot find the video: %s",
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
        "did_caps": "%d captions",
        "did_titles": "%d cards",
        "did_voice": "%d voice line(s)",
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
           "white": "Fundido a blanco", "slide": "Deslizamiento", "wipe": "Barrido",
           "zoom": "Zoom"},
    "en": {"none": "Hard cut", "dissolve": "Dissolve", "dip": "Dip to black",
           "white": "Dip to white", "slide": "Slide", "wipe": "Wipe", "zoom": "Zoom"},
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


def edl_montage(video, transcript, keep_ratio=0.45, track=None, lang="es"):
    """Keep the best moments, chosen on what is said, how loud it is and how
    much the picture is doing.

    The first version scored one-second buckets of raw loudness, which is how a
    montage ends up starting mid-word: a bucket has no idea where a sentence
    begins. This scores whole spoken segments instead, so every kept moment is a
    complete thought, and it only ever picks from what survived the cleanup, so
    the fillers and the retries are already gone.
    """
    base, report = edl_from_speech(transcript, lang, track=track)
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


def edl_from_prompt(prompt, packed, key):
    """Modo Pro: ask Claude for an EDL over the packed transcript."""
    body = {
        "model": "claude-sonnet-5",
        "max_tokens": 4000,
        "system": (
            "Eres el editor de video de Vidorq. Recibes la transcripcion empaquetada de un video "
            "(lineas '[inicio-fin] texto' en segundos) y la instruccion del usuario. Devuelve SOLO un JSON: "
            '{"segments":[{"start":s,"end":s,"zoom":1.0-1.08,"note":"..."}]} con los tramos A CONSERVAR, '
            "en orden, cortando en limites de frase. Zoom >1 solo en momentos de enfasis."),
        "messages": [{"role": "user", "content": f"INSTRUCCION: {prompt}\n\nTRANSCRIPCION:\n{packed}"}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"},
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    text = "".join(b.get("text", "") for b in data.get("content", []))
    m = re.search(r"\{.*\}", text, re.S)
    edl = json.loads(m.group(0))["segments"]
    for seg in edl:
        seg.setdefault("zoom", 1.0)
        seg.setdefault("note", "")
    return edl


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


def paint_clips(look, n, log=None):
    """El filtro de color, clip a clip, con el CDL nativo de Resolve.

    Los mismos numeros que el .cube del MP4 (skill/helpers/looks.py), asi que
    las dos salidas se ven igual. Va por CDL y no por LUT a proposito: queda en
    la pagina de color como una correccion primaria normal, que se puede abrir y
    seguir tocando a mano. Un LUT seria una caja negra encima del plano.
    """
    if not look or look == looks.DEFAULT:
        return 0
    cdl = looks.resolve_cdl(look)
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
                   drop=None, look="", transition="none"):
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
    record = 0
    for seg in edl:
        sf = round(seg["start"] * fps)
        ef = max(sf, round(seg["end"] * fps) - 1)
        bridge_post("/media/insert", {"clipName": Path(video).name,
                                      "startFrame": sf, "endFrame": ef})
        if seg.get("note"):
            bridge_post("/marker/add", {"frameId": record, "color": "Yellow",
                                        "name": seg["note"][:40], "note": seg["note"]})
        record += ef - sf + 1
    fill = fill_zoom(width, height, out_w, out_h)
    for i, seg in enumerate(edl):
        z = float(seg.get("zoom", 1.0)) * fill
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
    if transition in overlays.AS_OVERLAY and len(edl) > 1:
        set_progress(tr("overlaying"), 78, tr("overlaying_help"))
        plan = overlays.at_cuts(edl, transition, tl_fps, start_frame)
        for ev in plan:
            ev["fps"] = tl_fps
        n = resolve_captions.place_overlays(bridge_post, bridge_get_slow, plan,
                                            workdir or Path(video).parent,
                                            out_w, out_h)
        made += " " + tr("overlaid", n, transition) if n else ""

    if look and look != looks.DEFAULT:
        set_progress(tr("painting"), 80, tr("painting_help"))
        paint_clips(look, len(edl),
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
        if t < a:
            return None                     # cayo en un hueco que se ha ido
        if t <= b:
            return offset + (t - a)
        offset += b - a
    return None


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
    for seg in edl:
        a, b = float(seg["start"]), float(seg["end"])
        span = b - a
        if left <= span:
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
    return titles, spoken


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
    segments = []
    for seg in transcript.get("segments", []):
        words = []
        for w in seg.get("words", []):
            for s, e, shift in keeps:
                if s <= float(w["s"]) < e:
                    words.append({"w": w["w"], "s": float(w["s"]) - shift,
                                  "e": min(float(w["e"]), e) - shift})
                    break
        if words:
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


def session_save(workdir, state):
    """What a second round of prompts needs to know, next to the transcript."""
    try:
        (Path(workdir) / SESSION).write_text(
            json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        # Losing the ability to refine is a smaller failure than losing the
        # edit that was just made, so this never raises.
        traceback.print_exc()


def session_load(workdir):
    try:
        return json.loads((Path(workdir) / SESSION).read_text(encoding="utf-8"))
    except Exception:
        return {}


def workdir_for(video):
    return Path(video).parent / "edit" / Path(video).stem[:40]


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
        "transition": "Esa transicion necesita mezclar los dos planos, y eso Resolve "
                      "no lo hace por API. En Resolve puedo poner fundido a negro, a "
                      "blanco o destello; las demas salen en el MP4.",
        "voice": "Resolve no admite meter audio por su API, la voz solo sale en el MP4.",
        "shake": "El temblor necesita keyframes de encuadre, que Resolve no da por API.",
    },
    "en": {
        "transition": "That transition has to blend both shots, which Resolve will "
                      "not do over its API. In Resolve it can dip to black, dip to "
                      "white or flash; the rest come out in the MP4.",
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
    "es": {"ratio": "formato", "transition": "transicion", "captions": "subtitulos",
           "captionPreset": "estilo", "captionAnim": "entrada", "cuts": "corte",
           "look": "color"},
    "en": {"ratio": "frame", "transition": "transition", "captions": "captions",
           "captionPreset": "look", "captionAnim": "entrance", "cuts": "cut",
           "look": "colour"},
}


def said_it(changed, settings):
    """Los ajustes que cambiaron, escritos como se los dirias a alguien."""
    words = SETTING_WORDS.get(_lang, SETTING_WORDS["es"])
    out = []
    for key in changed:
        value = settings.get(key)
        if key == "captions":
            out.append(("subtitulos" if value else "sin subtitulos") if _lang == "es"
                       else ("captions" if value else "no captions"))
            continue
        if key == "transition":
            value = (TRANSITION_LABELS.get(_lang, TRANSITION_LABELS["es"])
                     .get(value, value))
        elif key == "ratio":
            value = RATIO_LABELS.get(_lang, RATIO_LABELS["es"]).get(value, value)
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


def choices_for(key, lang="es"):
    if key == "cuts":
        words = CUT_LABELS.get(lang, CUT_LABELS["es"])
        return [{"id": c, "label": words.get(c, c)} for c in director.CUTS]
    if key == "transition":
        words = TRANSITION_LABELS.get(lang, TRANSITION_LABELS["es"])
        return [{"id": t, "label": words.get(t, t)}
                for t in director.TRANSITIONS if t != "none"]
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


ASK_WORDS = {
    "es": {"transition": "¿Que transicion?", "captionPreset": "¿Que estilo de subtitulo?",
           "captionAnim": "¿Como quieres que entren?", "look": "¿Que filtro de color?",
           "ratio": "¿Que formato?", "cuts": "¿Como quieres que lo corte?"},
    "en": {"transition": "Which transition?", "captionPreset": "Which caption look?",
           "captionAnim": "How should they come in?", "look": "Which colour filter?",
           "ratio": "Which frame?", "cuts": "How should I cut it?"},
}


def said_pick(prompt, lang="es"):
    """Un boton pulsado, escrito como lo diria una persona.

    Lo que viaja es "pick:transition=dip" porque entra por el mismo sitio que
    todo lo demas, pero eso en la conversacion se lee como un error de la
    maquina. Se guarda ya traducido.
    """
    key, _, value = prompt[len(PICK):].partition("=")
    words = SETTING_WORDS.get(lang, SETTING_WORDS["es"])
    for opt in choices_for(key, lang):
        if opt["id"] == value:
            return "%s: %s" % (words.get(key, key), opt["label"])
    return "%s: %s" % (words.get(key, key), value)


def ask_for(keys, lang="es"):
    """Las preguntas pendientes, listas para pintarse como botones."""
    words = ASK_WORDS.get(lang, ASK_WORDS["es"])
    out = []
    for key in keys:
        options = choices_for(key, lang)
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
        key, _, value = prompt[len(PICK):].partition("=")
        return dict(base, **{key: value}), [key], []
    delta, cannot, _why = director.change(prompt, base, ai, model, log)
    words = director.from_words(prompt)
    delta.update(words)
    # Lo que la frase nombra sin concretar se PREGUNTA, y por eso la suposicion
    # del modelo para esa clave se cae aqui. Que el modelo conteste "disolvencia"
    # a "pon transiciones" no significa que tu lo hayas dicho, y aplicarlo seria
    # volver a adivinar por otro camino.
    for key in director.vague(prompt, set(words)):
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
    return out, changed, cannot


def note_stopped(video, prompt):
    """Dejar el turno parado en la conversacion.

    Sin esto la ventana recarga el historial del motor, no encuentra tu frase y
    la hace desaparecer: parece que no la escribiste nunca.
    """
    if not video:
        return
    work = workdir_for(video)
    past = session_load(work)
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
        colour = req.get("look") or ""
        if colour not in looks.PRESETS:
            colour = ""
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
        again = bool(req.get("refine")) and bool(
            session_load(workdir_for(video)).get("edl"))
        keep_edl, history, turn = None, [], 1
        changed, not_understood = [], []
        if again:
            past = session_load(workdir_for(video))
            keep_edl = past["edl"]
            history = past.get("history") or []
            turn = len(history) + 1
            base = past.get("settings") or {}
            set_progress(tr("refining", turn), 6, tr("refine_reading"))
            fresh, changed, not_understood = refine_settings(
                prompt, base, ai_choice(req), req.get("directorModel") or None,
                log=lambda m: set_progress(tr("refining", turn), 7, m))
            ratio = fresh.get("ratio", ratio)
            preset = fresh.get("cuts", preset)
            transition = fresh.get("transition", transition)
            captions = fresh.get("captions", captions)
            caption_preset = fresh.get("captionPreset") or caption_preset
            caption_anim = fresh.get("captionAnim", caption_anim)
            colour = fresh.get("look", colour)
            output = fresh.get("output") or output
            if req.get("output"):
                output = req["output"]
            set_progress(tr("refining", turn), 8,
                         tr("refine_kept", len(keep_edl),
                            ", ".join(changed) if changed
                            else tr("refine_nothing_said")))

        # A prompt decides the whole edit, not just the cuts: the shape of the
        # frame, the caption look, its entrance, the joins. Before this the
        # prompt could ask for a vertical short and be handed a wide one.
        plan = None
        if prompt and not again:
            set_progress(tr("directing"), 6)
            plan = director.look(prompt, ai_choice(req),
                                 req.get("directorModel") or None, _lang,
                                 log=lambda m: set_progress(tr("directing"), 7, m))
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
        shake = bool(req.get("shake"))
        report = {}
        # Cambiar el ESTILO de corte es lo unico de un retoque que obliga a
        # volver a cortar: los demas ajustes se pintan encima de la misma
        # edicion, pero "limpio" y "montaje" son dos ediciones distintas. Sin
        # esto la pregunta "como quieres que lo corte" tenia tres botones que no
        # hacian nada, que es peor que no preguntar.
        recut = again and "cuts" in changed
        if again and not recut:
            # Los cortes que ya hay se respetan: esta frase es un retoque, no
            # una edicion nueva. Lo que la frase pida se aplica ENCIMA.
            edl = [dict(x) for x in keep_edl]
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
                                              track=look.get("track"), shake=shake)
        elif preset == "montage":
            edl, report = edl_montage(video, transcript, track=look.get("track"),
                                      lang=transcript.get("language", _lang))
        else:
            edl, report = edl_from_speech(transcript, transcript.get("language", _lang),
                                          track=look.get("track"), shake=shake)
            if preset == "podcast":
                edl = mark_questions(transcript, edl)
        if not edl:
            raise RuntimeError("El EDL salio vacio; no hay nada que conservar")

        # 3b) Which third of the width to keep. Only worth the decoding when the
        #     output is a different shape than the source, because a 16:9 out of
        #     a 16:9 crops nothing and there is nothing to aim. A user who moved
        #     the crop slider gets what they moved it to: a person who framed it
        #     by hand has already answered the question.
        hand_framed = abs(float(req.get("cropX", 0.5)) - 0.5) > 0.01
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
        if again:
            # Lo que ha cambiado y esta salida SI sabe hacer. Cambiar la
            # transicion con salida a Resolve no cambia nada de lo que se ve,
            # asi que rehacer el montaje entero para entregar el mismo video es
            # exactamente lo que hacia que pedir transiciones acabara en un rato
            # mirando como se colocaban otra vez los mismos subtitulos.
            asked = set(changed)
            blocked = blocked_by_output(
                output, {"ratio": ratio, "transition": transition}, asked,
                want_voice=False, want_shake=bool(req.get("shake")))
            dead = {b["what"] for b in blocked}
            useful = [k for k in changed if k not in dead]
            # Categorias nombradas sin decir cual. "Pon transiciones" dice que
            # quieres transiciones, no cuales. Antes se adivinaba (disolvencia) o
            # se decia que no se entendia; las dos son peores que preguntar, y
            # preguntar es ademas la unica que ensena lo que hay.
            pending = ask_for(director.vague(prompt or "",
                                             set(director.from_words(prompt or ""))),
                              _lang)
            if pending and not (prompt and director.wants_moments(prompt)):
                answer = {"you": prompt, "did": [], "cannot": blocked,
                          "unknown": [], "ask": pending, "offer": {}, "ok": False}
                past["history"] = history + [answer]
                session_save(workdir_for(video), past)
                set_progress(tr("done"), 100, result=pending[0]["question"])
                return
            if not useful and not (prompt and director.wants_moments(prompt)):
                answer = {"you": prompt, "did": [], "cannot": blocked,
                          "unknown": not_understood,
                          "offer": ({"kind": "mp4"} if blocked else {}),
                          "ok": False}
                past["history"] = history + [answer]
                session_save(workdir_for(video), past)
                set_progress(tr("done"), 100,
                             result=(blocked[0]["why"] if blocked
                                     else tr("not_understood")))
                return

        # 3c) What the prompt asked for at particular moments. After the cuts
        #     are decided and before anything downstream reads the EDL, because
        #     a cut here moves every second that comes after it.
        want_titles, want_voice = [], []
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
                acts = director.actions(
                    prompt, packed_now, span, ai_choice(req),
                    req.get("directorModel") or None,
                    log=lambda m: set_progress(tr("moments"), 59, m))
                if again and acts:
                    acts = actions_to_original(acts, edl)
                if acts:
                    want_titles, want_voice = apply_actions(
                        edl, acts,
                        log=lambda m: set_progress(tr("decided"), 59,
                                                   tr("moments_done", m)))
            except Exception as e:
                # An instruction that could not be carried out must not cost the
                # edit: the rest of it is still exactly what was asked for.
                traceback.print_exc()
                set_progress(tr("moments"), 59, "sin momentos: %s" % str(e)[:120])

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

        # 4b) The cards the prompt asked for join the captions, so they get the
        #     same look and the same renderer in both backends instead of a
        #     second mechanism that would have to be built twice.
        if want_titles:
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
                drop=(session_load(workdir).get("timelines") or []) if again else [],
                look=colour, transition=transition)
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
        picked = (prompt[len(PICK):].partition("=")[0]
                  if prompt.startswith(PICK) else "")
        settings_now = {"ratio": ratio, "transition": transition,
                        "captions": captions, "captionPreset": caption_preset,
                        "captionAnim": caption_anim, "cuts": preset,
                        "look": colour, "output": output}
        # Lo que ha pasado en este turno, contado. Se guarda con la sesion para
        # que la conversacion siga estando ahi despues de cerrar la ventana.
        did = said_it(changed, settings_now) if again else []
        did += [tr("did_cut" if len(edl) == 1 else "did_cuts", len(edl))]
        # Solo cuando se sabe el numero aqui. Cuando los subtitulos los arma el
        # backend, el que los ha contado es el, y lo dice en `result`: repetirlo
        # aqui con un cero seria peor que no decirlo.
        if captions and translated_chunks:
            did.append(tr("did_caps", len(translated_chunks)))
        if want_titles:
            did.append(tr("did_titles", len(want_titles)))
        if voice_files:
            did.append(tr("did_voice", len(voice_files)))
        blocked = blocked_by_output(output, settings_now, set(changed),
                                    want_voice=bool(want_voice),
                                    want_shake=bool(req.get("shake")))
        answer = {"you": (said_pick(prompt, _lang) if prompt.startswith(PICK)
                          else (prompt or tr("history_first"))),
                  "did": [x for x in did if x],
                  "cannot": blocked,
                  "unknown": not_understood,
                  # Se ha hecho algo Y ademas queda algo por concretar: se hace
                  # lo que se entendio y se pregunta lo otro, en vez de parar el
                  # trabajo por una duda que no lo impedia.
                  "ask": (ask_for(director.NEXT_ASK[picked], _lang)
                          if picked in director.NEXT_ASK
                          else ask_for(director.vague(
                              prompt or "", set(director.from_words(prompt or ""))),
                              _lang))
                         if again else [],
                  "offer": ({"kind": "mp4"} if blocked else {}),
                  "result": result,
                  "ok": True}
        session_save(workdir, {
            "video": video,
            "edl": edl,
            "settings": settings_now,
            "history": (history if again else []) + [answer],
            "timelines": made_names,
            "result": result,
        })

        if srt_paths:
            result += "  |  " + tr("srt_made", ", ".join(Path(p).name for p in srt_paths))
        set_progress(tr("done"), 100, result=result)
    except Stopped:
        # Lo que se hizo antes de parar se queda: los subtitulos ya colocados
        # estan en el timeline y borrarlos seria una sorpresa peor. Se dice lo
        # que quedo a medias y ya.
        note_stopped(stop_video, stop_prompt)
        set_stopped(tr("stopped"), tr("stopped_help"))
    except Exception as e:
        traceback.print_exc()
        set_progress("", 0, error=str(e))
    finally:
        _busy = False


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
        make every one of them a third bigger for no reason. They are immutable
        once written (the cache key contains everything that went into them), so
        they can be cached hard by the window.
        """
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # The window closed or the poll timed out mid-answer. Normal, and the
            # user should not see a stack trace in the console for it.
            pass

    def do_OPTIONS(self):
        self._send({})

    def do_GET(self):
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
                elif kind == "ratio":
                    path = previews.ratio_still(ratio, video, w, h, at)
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
                st = session_load(workdir_for(video))
                # Las sesiones viejas guardaban solo la frase del usuario. Se
                # leen igual, en vez de romper una conversacion que ya existia.
                turns = [({"you": h, "did": [], "cannot": [], "ok": True}
                          if isinstance(h, str) else h)
                         for h in (st.get("history") or [])]
                self._send({"history": turns,
                            "settings": st.get("settings") or {},
                            "result": st.get("result", ""),
                            "can": bool(st.get("edl"))})
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
                        "transitions": TRANSITION_LABELS.get(lang, TRANSITION_LABELS["es"]),
                        "ratios": RATIO_LABELS.get(lang, RATIO_LABELS["es"])})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        global _busy
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
            if body.get("create"):
                (WORKSPACES / _safe_name(body["create"])).mkdir(parents=True, exist_ok=True)
            if body.get("activate"):
                cfg = load_config()
                cfg["activeWorkspace"] = _safe_name(body["activate"])
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
