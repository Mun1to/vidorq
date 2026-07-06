"""Vidorq Engine — local HTTP server that powers the desktop apps.

Zero external dependencies beyond the Vidorq venv (faster-whisper, PyAV, Pillow).
Pattern borrowed from CursorBridge: stdlib http.server + a worker thread.

Endpoints:
    GET  /health    -> {"ok": true, "version": ...}
    GET  /progress  -> {"step", "percent", "detail", "result", "error"}
    POST /config    -> {"anthropicKey": "..."} saved to %APPDATA%/Vidorq/config.json
    POST /edit      -> {"video", "preset", "captions", "output", "prompt"} starts a job

Presets (no API key needed, fully local):
    clean    keep speech, drop silences/dead air
    podcast  clean + a marker/zoom on every question
    montage  keep the highest-energy chunks (beta)
Prompt mode (Modo Pro) uses the Anthropic API with the user's own key.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HOST, PORT = "127.0.0.1", 9877
VERSION = "0.1.0"
HELPERS = Path(__file__).resolve().parent.parent / "skill" / "helpers"
PYTHON = sys.executable
CONFIG_DIR = Path(os.environ.get("APPDATA", ".")) / "Vidorq"
CONFIG = CONFIG_DIR / "config.json"
BRIDGE = "http://127.0.0.1:9876"

_lock = threading.Lock()
_progress = {"step": "", "percent": 0, "detail": "", "result": "", "error": ""}
_busy = False

QUESTION_RE = re.compile(
    r"^\s*(qu[eé]|c[oó]mo|cu[aá]l|qui[eé]n|por qu[eé]|d[oó]nde|cu[aá]ndo|cu[aá]nt)", re.I)


def set_progress(step, percent, detail="", result="", error=""):
    with _lock:
        _progress.update(step=step, percent=percent, detail=detail, result=result, error=error)


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# EDL builders (deterministic presets — no LLM required)
# --------------------------------------------------------------------------- #
def edl_from_speech(transcript, max_gap=0.6, pad=0.15):
    """Keep spoken segments; merge when the gap is tiny; drop dead air."""
    segs = transcript["segments"]
    if not segs:
        return []
    out = []
    cur = {"start": max(0.0, segs[0]["start"] - pad), "end": segs[0]["end"]}
    for s in segs[1:]:
        if s["start"] - cur["end"] <= max_gap:
            cur["end"] = s["end"]
        else:
            out.append(cur)
            cur = {"start": max(0.0, s["start"] - pad), "end": s["end"]}
    out.append(cur)
    for seg in out:
        seg["end"] += pad
        seg["zoom"] = 1.0
        seg["note"] = ""
    return out


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
        return edl_from_speech(transcript)
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
    return keep or edl_from_speech(transcript)


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


def output_resolve(video, edl, fps):
    name = Path(video).stem[:40]
    # import media (idempotent) + timeline + inserts
    bridge_post("/media/import", {"filePaths": [video]})
    bridge_post("/timeline/create", {"name": f"Vidorq_{name}"})
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
    bridge_post("/project/save", {})
    return f"Timeline 'Vidorq_{name}' creado en Resolve"


# --------------------------------------------------------------------------- #
# The job
# --------------------------------------------------------------------------- #
def run_job(req):
    global _busy
    try:
        video = req["video"]
        preset = req.get("preset", "clean")
        captions = bool(req.get("captions", True))
        output = req.get("output", "mp4")
        prompt = (req.get("prompt") or "").strip()

        if not Path(video).is_file():
            raise ValueError(f"No encuentro el video: {video}")

        workdir = Path(video).parent / "edit" / Path(video).stem[:40]
        workdir.mkdir(parents=True, exist_ok=True)
        tr_path = workdir / "transcript.json"

        # 1) Transcribe (reuse cached transcript if present)
        if not tr_path.exists():
            set_progress("Transcribiendo (Whisper local)...", 10,
                         "La primera vez descarga el modelo; puede tardar unos minutos")
            r = subprocess.run([PYTHON, str(HELPERS / "transcribe.py"), video, str(workdir)],
                               capture_output=True, text=True, timeout=3600)
            if r.returncode != 0 or not tr_path.exists():
                raise RuntimeError("Fallo transcribiendo: " + (r.stderr or r.stdout)[-400:])
        transcript = json.loads(tr_path.read_text(encoding="utf-8"))

        # 2) Build the EDL
        set_progress("Decidiendo los cortes...", 50)
        if prompt:
            key = load_config().get("anthropicKey", "")
            if not key:
                raise ValueError("El Modo Pro necesita tu API key de Anthropic (Ajustes)")
            packed = (workdir / "takes_packed.md").read_text(encoding="utf-8")
            edl = edl_from_prompt(prompt, packed, key)
        elif preset == "montage":
            edl = edl_montage(video, transcript)
        else:
            edl = edl_from_speech(transcript)
            if preset == "podcast":
                edl = mark_questions(transcript, edl)
        if not edl:
            raise RuntimeError("El EDL salio vacio; no hay nada que conservar")
        edl_path = workdir / "edl.json"
        edl_path.write_text(json.dumps({"segments": edl}, indent=1), encoding="utf-8")
        kept = sum(s["end"] - s["start"] for s in edl)
        set_progress("Cortes decididos", 58,
                     f"{len(edl)} tramos, {kept:.0f}s conservados de {transcript['duration']:.0f}s")

        # 3) Execute on the chosen backend
        if output == "resolve":
            set_progress("Montando timeline en Resolve...", 65,
                         "Necesita Resolve abierto con CursorBridge activo")
            try:
                result = output_resolve(video, edl, 30000 / 1001)
            except Exception:
                raise RuntimeError("No pude hablar con Resolve. Abre Resolve, un proyecto, "
                                   "y Workspace > Scripts > CursorBridge")
        else:
            set_progress("Renderizando (GPU)...", 65, "Cortes + zooms" + (" + captions" if captions else ""))
            out_file = workdir / f"{Path(video).stem[:40]}_vidorq.mp4"
            cmd = [PYTHON, str(HELPERS / "vidorq_render.py"), video, str(edl_path),
                   str(tr_path), str(out_file)]
            if not captions:
                cmd.append("--no-captions")
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
            if r.returncode != 0 or not out_file.exists():
                raise RuntimeError("Fallo renderizando: " + (r.stderr or r.stdout)[-400:])
            result = str(out_file)

        set_progress("Listo", 100, result=result)
    except Exception as e:
        traceback.print_exc()
        set_progress("", 0, error=str(e))
    finally:
        _busy = False


# --------------------------------------------------------------------------- #
# HTTP plumbing
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._send({})

    def do_GET(self):
        if self.path == "/health":
            self._send({"ok": True, "version": VERSION, "busy": _busy})
        elif self.path == "/progress":
            with _lock:
                self._send(dict(_progress))
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
        elif self.path == "/edit":
            if _busy:
                return self._send({"error": "Ya hay una edicion en marcha"}, 409)
            _busy = True
            set_progress("Preparando...", 3)
            threading.Thread(target=run_job, args=(body,), daemon=True).start()
            self._send({"ok": True})
        else:
            self._send({"error": "not found"}, 404)


if __name__ == "__main__":
    print(f"[VidorqEngine] v{VERSION} en http://{HOST}:{PORT}  (Ctrl+C para parar)")
    HTTPServer((HOST, PORT), Handler).serve_forever()
