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
import resolve_captions  # noqa: E402

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
        "deciding": "Decidiendo los cortes...",
        "decided": "Cortes decididos",
        "rendering": "Renderizando (GPU)...",
        "building": "Montando timeline en Resolve...",
        "done": "Listo",
        "timeline_made": "Timeline 'Vidorq_%s' creado en Resolve",
        "captioning": "Poniendo los subtitulos en Resolve...",
        "captioning_n": "%d subtitulos, uno a uno",
        "captions_made": "con %d subtitulos editables",
        "cut_report": "%d cortes, %d muletillas fuera, %d tomas repetidas",
    },
    "en": {
        "busy": "There is already an edit running",
        "no_video": "Cannot find the video: %s",
        "preparing": "Getting ready...",
        "transcribing": "Transcribing (local Whisper)...",
        "deciding": "Deciding the cuts...",
        "decided": "Cuts decided",
        "rendering": "Rendering (GPU)...",
        "building": "Building the timeline in Resolve...",
        "done": "Done",
        "timeline_made": "Timeline 'Vidorq_%s' created in Resolve",
        "captioning": "Putting the captions into Resolve...",
        "captioning_n": "%d captions, one by one",
        "captions_made": "with %d editable captions",
        "cut_report": "%d cuts, %d filler words out, %d repeated takes",
    },
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


def edl_from_speech(transcript, lang="es", max_gap=0.6, pad=0.15, drop_takes=True):
    """Keep the speech, drop the dead air, the fillers and the retries.

    Built from word timings rather than whole phrases, which is what makes it
    possible to cut an 'eh' out of a pause without touching the words around it.
    Returns (edl, report) where report is what the app tells the user it did.
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
    return merged, {"takes": dropped, "fillers": fillers, "cuts": len(merged)}


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


def edl_montage(video, transcript):
    """Beta: keep the highest audio-energy chunks (~top third), min 3s each."""
    import av
    import numpy as np
    c = av.open(video)
    a = c.streams.audio[0]
    sr = a.codec_context.sample_rate or 48000
    energy = {}
    for frame in c.decode(a):
        t = int(float(frame.pts * a.time_base))
        arr = frame.to_ndarray().astype("float64")
        energy[t] = energy.get(t, 0.0) + float((arr ** 2).mean())
    c.close()
    if not energy:
        return edl_from_speech(transcript)[0]
    times = sorted(energy)
    vals = sorted(energy.values(), reverse=True)
    thr = vals[max(0, len(vals) // 3 - 1)]
    keep, cur = [], None
    for t in times:
        if energy[t] >= thr:
            if cur and t - cur["end"] <= 2:
                cur["end"] = t + 1
            else:
                if cur:
                    keep.append(cur)
                cur = {"start": float(t), "end": float(t + 1)}
    if cur:
        keep.append(cur)
    keep = [k for k in keep if k["end"] - k["start"] >= 3]
    for k in keep:
        k["zoom"] = 1.0
        k["note"] = "pico de energia"
    return keep or edl_from_speech(transcript)[0]


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
    """
    if bridge_get("/status") is None:
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


def output_resolve(video, edl, transcript, captions=False, preset=cap.DEFAULT_PRESET,
                   workdir=None, anim=""):
    name = Path(video).stem[:40]
    fps, width, height = video_shape(video)
    timeline = f"Vidorq_{name}"
    # import media (idempotent) + timeline + inserts
    bridge_post("/media/import", {"filePaths": [video]})
    bridge_post("/timeline/create", {"name": timeline})
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
    for i, seg in enumerate(edl):
        z = float(seg.get("zoom", 1.0))
        if z > 1.001:
            bridge_post("/clip/properties", {"trackType": "video", "trackIndex": 1,
                                             "clipIndex": i, "properties": {"ZoomX": z, "ZoomY": z}})

    made = tr("timeline_made", name)
    if captions:
        # Caption times have to follow the CUT video, not the original, so the
        # transcript is folded onto the edit before the chunks are built.
        chunks = cap.build_chunks(retime_transcript(transcript, edl), preset)
        if chunks:
            set_progress(tr("captioning"), 85, tr("captioning_n", len(chunks)))
            out = resolve_captions.build(bridge_post, bridge_get, timeline, chunks,
                                         preset, workdir or Path(video).parent,
                                         width, height, fps, anim=anim)
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

        # 2) Build the EDL
        set_progress(tr("deciding"), 50)
        report = {}
        if prompt:
            key = load_config().get("anthropicKey", "")
            if not key:
                raise ValueError("El Modo Pro necesita tu API key de Anthropic (Ajustes)")
            packed = (workdir / "takes_packed.md").read_text(encoding="utf-8")
            brand = profile_load()
            if brand:
                prompt += "\n\nPERFIL DE MARCA DEL USUARIO (respetalo): " + json.dumps(
                    brand, ensure_ascii=False)
            edl = edl_from_prompt(prompt, packed, key)
        elif preset == "montage":
            edl = edl_montage(video, transcript)
        else:
            edl, report = edl_from_speech(transcript, transcript.get("language", _lang))
            if preset == "podcast":
                edl = mark_questions(transcript, edl)
        if not edl:
            raise RuntimeError("El EDL salio vacio; no hay nada que conservar")
        edl_path = workdir / "edl.json"
        edl_path.write_text(json.dumps({"segments": edl}, indent=1), encoding="utf-8")
        kept = sum(s["end"] - s["start"] for s in edl)
        detail = f"{len(edl)} tramos, {kept:.0f}s conservados de {transcript['duration']:.0f}s"
        if report.get("fillers") or report.get("takes"):
            detail += " (" + tr("cut_report", len(edl), report.get("fillers", 0),
                                report.get("takes", 0)) + ")"
        set_progress(tr("decided"), 58, detail)

        # 3) Execute on the chosen backend
        if output == "resolve":
            set_progress(tr("building"), 65,
                         "Necesita Resolve abierto con CursorBridge activo")
            if not bridge_status()["bridge"]:
                raise RuntimeError("No pude hablar con Resolve. Abre Resolve, un proyecto, "
                                   "y Workspace > Scripts > Vidorq")
            result = output_resolve(video, edl, transcript, captions, caption_preset,
                                    workdir, caption_anim)
        else:
            set_progress(tr("rendering"), 65, "Cortes + zooms" + (" + captions" if captions else ""))
            out_file = workdir / f"{Path(video).stem[:40]}_vidorq.mp4"
            cmd = [PYTHON, str(HELPERS / "vidorq_render.py"), video, str(edl_path),
                   str(tr_path), str(out_file), "--preset", caption_preset]
            if caption_anim:
                cmd += ["--anim", caption_anim]
            if not captions:
                cmd.append("--no-captions")
            run_render(cmd, out_file)
            result = str(out_file)

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
            self._send({"ok": True, "version": VERSION, "busy": _busy})
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
                        "animOf": {k: v["anim"] for k, v in cap.PRESETS.items()}})
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
