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

# The caption presets and the filler-word lists live with the renderers that use
# them, so the engine borrows them instead of keeping a second copy.
sys.path.insert(0, str(HELPERS))
import captions as cap  # noqa: E402
import vision  # noqa: E402
import translate as tl  # noqa: E402
import director  # noqa: E402
import resolve_captions  # noqa: E402
import faces  # noqa: E402

_lock = threading.Lock()
_progress = {"step": "", "percent": 0, "detail": "", "result": "", "error": ""}
_busy = False

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
        "timeline_made": "Timeline '%s' creado en Resolve",
        "captioning": "Poniendo los subtitulos en Resolve...",
        "captioning_n": "%d subtitulos, uno a uno",
        "captions_made": "con %d subtitulos editables",
        "cut_report": "%d cortes, %d muletillas fuera, %d tomas repetidas",
        "snapped": ", %d cortes movidos a un momento quieto",
        "jumps": ", %d saltos tapados cambiando el encuadre",
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
        "timeline_made": "Timeline '%s' created in Resolve",
        "captioning": "Putting the captions into Resolve...",
        "captioning_n": "%d captions, one by one",
        "captions_made": "with %d editable captions",
        "cut_report": "%d cuts, %d filler words out, %d repeated takes",
        "snapped": ", %d cuts moved onto a still moment",
        "jumps": ", %d jump cuts hidden by changing the framing",
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
    with _lock:
        _progress.update(step=step, percent=percent, detail=detail, result=result, error=error)


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
    merged, hidden = hide_jump_cuts(merged, track)
    return merged, {"takes": dropped, "fillers": fillers, "cuts": len(merged),
                    "snapped": moved, "jumps": hidden}


# How much bigger the framing goes on the far side of a jump cut. Small on
# purpose: enough that the join stops reading as a glitch, not so much that it
# announces itself as an effect.
JUMP_ZOOM = 1.07


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
def bridge_post(path, body):
    req = urllib.request.Request(BRIDGE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def bridge_get(path, timeout=2):
    """One GET to the bridge, or None if it is down or has nothing to say."""
    try:
        with urllib.request.urlopen(BRIDGE + path, timeout=timeout) as r:
            data = json.loads(r.read().decode())
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


def output_resolve(video, edl, transcript, captions=False, preset=cap.DEFAULT_PRESET,
                   workdir=None, anim="", chunks=None, ratio="source"):
    name = Path(video).stem[:40]
    fps, width, height = video_shape(video)
    out_w, out_h = out_frame(ratio, width, height)
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
        if z > 1.001:
            bridge_post("/clip/properties", {"trackType": "video", "trackIndex": 1,
                                             "clipIndex": i, "properties": {"ZoomX": z, "ZoomY": z}})

    made = tr("timeline_made", timeline)
    if captions:
        # Caption times have to follow the CUT video, not the original, so the
        # transcript is folded onto the edit before the chunks are built.
        chunks = chunks or cap.build_chunks(retime_transcript(transcript, edl), preset,
                                            out_w, out_h)
        if chunks:
            set_progress(tr("captioning"), 85, tr("captioning_n", len(chunks)))
            out = resolve_captions.build(bridge_post, bridge_get, timeline, chunks,
                                         preset, workdir or Path(video).parent,
                                         out_w, out_h, fps, anim=anim)
            made += " " + tr("captions_made", out["captions"])
    bridge_post("/project/save", {})
    return made


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
def run_render(cmd, out_file, timeout=7200):
    """Run the renderer relaying its PROGRESS lines to /progress in real time."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    killer = threading.Timer(timeout, proc.kill)
    killer.start()
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
    if proc.returncode != 0 or not out_file.exists():
        raise RuntimeError("Fallo renderizando: " + "\n".join(tail)[-400:])


def run_job(req):
    global _busy
    try:
        video = req["video"]
        preset = req.get("preset", "clean")
        captions = bool(req.get("captions", True))
        output = req.get("output", "mp4")
        prompt = (req.get("prompt") or "").strip()
        ratio = req.get("ratio") or "source"
        transition = req.get("transition") or "none"
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

        # A prompt decides the whole edit, not just the cuts: the shape of the
        # frame, the caption look, its entrance, the joins. Before this the
        # prompt could ask for a vertical short and be handed a wide one.
        plan = None
        if prompt:
            set_progress(tr("directing"), 6)
            plan = director.look(prompt, load_config().get("anthropicKey", ""),
                                 req.get("directorModel") or None, _lang,
                                 log=lambda m: set_progress(tr("directing"), 7, m))
            ratio = plan["ratio"]
            transition = plan["transition"]
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
            r = subprocess.run([PYTHON, str(HELPERS / "transcribe.py"), video, str(workdir)],
                               capture_output=True, text=True, timeout=3600)
            if r.returncode != 0 or not tr_path.exists():
                raise RuntimeError("Fallo transcribiendo: " + (r.stderr or r.stdout)[-400:])
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
        report = {}
        if prompt:
            key = load_config().get("anthropicKey", "")
            packed = packed_view(workdir, transcript, video)
            if look.get("shots"):
                # The model reads the video instead of watching it: the visual
                # track goes in next to the words, in the same shape.
                packed += "\n\nLO QUE SE VE (plano por plano):\n" + vision.packed(look)
            brand = profile_load()
            if brand:
                prompt += "\n\nPERFIL DE MARCA DEL USUARIO (respetalo): " + json.dumps(
                    brand, ensure_ascii=False)
            edl = director.segments(prompt, packed, key,
                                    req.get("directorModel") or None,
                                    log=lambda m: set_progress(tr("deciding"), 52, m))
            if not edl:
                # A model that could not produce a usable timeline must not cost
                # the edit: the deterministic engine is good, and the look the
                # prompt asked for still applies.
                set_progress(tr("deciding"), 54, "uso los cortes del motor")
                edl, report = edl_from_speech(transcript,
                                              transcript.get("language", _lang),
                                              track=look.get("track"))
        elif preset == "montage":
            edl, report = edl_montage(video, transcript, track=look.get("track"),
                                      lang=transcript.get("language", _lang))
        else:
            edl, report = edl_from_speech(transcript, transcript.get("language", _lang),
                                          track=look.get("track"))
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

        edl_path = workdir / "edl.json"
        edl_path.write_text(json.dumps({"segments": edl}, indent=1), encoding="utf-8")
        kept = sum(s["end"] - s["start"] for s in edl)
        detail = f"{len(edl)} tramos, {kept:.0f}s conservados de {transcript['duration']:.0f}s"
        if report.get("fillers") or report.get("takes"):
            detail += " (" + tr("cut_report", len(edl), report.get("fillers", 0),
                                report.get("takes", 0)) + ")"
        if report.get("snapped"):
            detail += tr("snapped", report["snapped"])
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

        # 5) Execute on the chosen backend
        if output == "resolve":
            set_progress(tr("building"), 65,
                         "Necesita Resolve abierto con CursorBridge activo")
            if not bridge_status()["bridge"]:
                raise RuntimeError("No pude hablar con Resolve. Abre Resolve, un proyecto, "
                                   "y Workspace > Scripts > Vidorq")
            result = output_resolve(video, edl, transcript, captions, caption_preset,
                                    workdir, caption_anim, translated_chunks, ratio)
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
            if translated_chunks:
                ch_path = workdir / "chunks_traducidos.json"
                ch_path.write_text(json.dumps(translated_chunks, ensure_ascii=False),
                                   encoding="utf-8")
                cmd += ["--chunks", str(ch_path)]
            if not captions:
                cmd.append("--no-captions")
            run_render(cmd, out_file)
            result = str(out_file)

        if srt_paths:
            result += "  |  " + tr("srt_made", ", ".join(Path(p).name for p in srt_paths))
        set_progress(tr("done"), 100, result=result)
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
        elif self.path.startswith("/captions/presets"):
            lang = "en" if "lang=en" in self.path else "es"
            self._send({"default": cap.DEFAULT_PRESET, "list": cap.preset_list(lang),
                        "anims": cap.anim_list(lang),
                        "animOf": {k: v["anim"] for k, v in cap.PRESETS.items()},
                        "langs": tl.LANGS,
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
            cfg.update({k: v for k, v in body.items() if v})
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
            set_progress(tr("preparing"), 3)
            threading.Thread(target=run_job, args=(body,), daemon=True).start()
            self._send({"ok": True})
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
