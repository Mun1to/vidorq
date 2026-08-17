"""Vidorq's eyes: what the video looks like, so the cuts stop being deaf-blind.

Until now Vidorq only knew what was said. That is enough to drop dead air, and
not enough to cut well: a cut landing mid-gesture or mid-camera-move looks wrong
no matter how clean the audio is.

This reads the picture in two passes, cheap first:

  shots()     pure arithmetic over downscaled frames - where the image changes,
              how much it moves, how bright it is. No model, no GPU, seconds.
  describe()  a local vision model, but only on ONE frame per shot.

The order matters and it is the project's stated philosophy: the model does not
watch the video, it reads it. Feeding a model every frame would cost hours and
buy nothing, and on this machine it would also fight DaVinci for the 8 GB of
VRAM. So arithmetic finds the interesting moments and the model is asked about
those, which is a few dozen questions instead of tens of thousands.

Everything runs against a local Ollama. No key, no upload, works on a plane.
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

# Ollama's own default. OLLAMA_HOST overrides it, which is also how a second
# instance on another port gets used without touching the user's setup.
OLLAMA = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA

# Best first. Vidorq takes the first one the machine actually has, so it works
# on a laptop with one small model and gets better on a machine with more.
# moondream is last on purpose: measured on this footage it answered
# "!!!PASSABLE!!! PASSABLE!!!" to two frames out of three. It is only there so a
# machine that has nothing else still gets an eye.
VISION_MODELS = ("qwen3-vl:8b", "qwen3.5:9b", "granite3.2-vision:2b",
                 "qwen3.5:4b", "llama3.2-vision:11b", "qwen3.5:2b",
                 "moondream:1.8b", "moondream:latest")

# Analysis frame rate. Shot changes never need full rate to be found, and this
# keeps a ten minute video in the seconds range.
SAMPLE_FPS = 6.0
# Frames are compared this small. Enough to see a cut, cheap enough to be free.
THUMB_W, THUMB_H = 64, 36
# A shot has to last this long to be worth calling a shot.
MIN_SHOT_S = 0.45
# How many frames get sent to the model, whatever the video's length.
MAX_DESCRIBED = 40


# --------------------------------------------------------------------------- #
# Pass one: arithmetic
# --------------------------------------------------------------------------- #
def shots(video, sample_fps=SAMPLE_FPS, log=None):
    """Where the picture changes, and how alive it is in between.

    Returns (shots, track):
      shots  [{"start", "end", "motion", "brightness", "still"}]
      track  [{"t", "diff", "brightness"}] at the sampling rate, kept because
             the cut engine wants the detail between boundaries, not just the
             boundaries themselves.
    """
    import av
    import numpy as np

    container = av.open(video)
    stream = container.streams.video[0]
    stream.thread_type = "AUTO"
    fps = float(stream.average_rate or 30)
    step = max(1, int(round(fps / max(0.5, sample_fps))))

    prev = None
    track = []
    for i, frame in enumerate(container.decode(stream)):
        if i % step:
            continue
        small = frame.reformat(width=THUMB_W, height=THUMB_H,
                               format="gray").to_ndarray().astype("float32")
        t = float(frame.pts * stream.time_base) if frame.pts is not None else i / fps
        diff = 0.0 if prev is None else float(np.abs(small - prev).mean())
        track.append({"t": round(t, 3), "diff": round(diff, 3),
                      "brightness": round(float(small.mean()) / 255.0, 3)})
        prev = small
    container.close()
    if not track:
        return [], []

    # An adaptive threshold, because a threshold that works on a talking head
    # would cut a music video into confetti. A boundary is a spike well above
    # this video's own normal amount of change.
    import numpy as np
    diffs = np.array([p["diff"] for p in track[1:]], dtype="float32")
    if len(diffs) == 0:
        cut_at = []
    else:
        med = float(np.median(diffs))
        mad = float(np.median(np.abs(diffs - med))) or 1e-3
        thr = max(med + 6.0 * mad, 8.0)
        cut_at = [track[i + 1]["t"] for i, d in enumerate(diffs) if d >= thr]
    if log:
        log("%d muestras, %d cortes de plano detectados" % (len(track), len(cut_at)))

    bounds = [track[0]["t"]] + cut_at + [track[-1]["t"]]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        if b - a < MIN_SHOT_S and out:
            out[-1]["end"] = b          # too short to be a shot, fold it back
            continue
        inside = [p for p in track if a <= p["t"] < b]
        if not inside:
            continue
        motion = sum(p["diff"] for p in inside[1:]) / max(1, len(inside) - 1)
        bright = sum(p["brightness"] for p in inside) / len(inside)
        out.append({"start": round(a, 3), "end": round(b, 3),
                    "motion": round(motion, 3), "brightness": round(bright, 3),
                    "still": motion < 1.2})
    return out, track


def motion_at(track, t):
    """How much the picture is moving at a given second."""
    if not track:
        return 0.0
    best = min(track, key=lambda p: abs(p["t"] - t))
    return float(best["diff"])


def quiet_moment(track, t, window=0.35):
    """The calmest instant within `window` of t, for landing a cut on.

    Cutting while the camera whips or an arm crosses frame reads as a mistake
    even when the audio is perfect, so the cut gets nudged to the nearest moment
    where the picture is holding still.
    """
    if not track:
        return t
    near = [p for p in track if abs(p["t"] - t) <= window]
    if not near:
        return t
    return min(near, key=lambda p: p["diff"])["t"]


# --------------------------------------------------------------------------- #
# Pass two: the model, on a handful of frames
# --------------------------------------------------------------------------- #
def _ollama(path, body, timeout=180):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def available_models():
    """What this machine can actually run, or [] if Ollama is not listening."""
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=6) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return []
    return [m.get("name", "") for m in data.get("models", [])]


def pick_model(prefer=None):
    """The best vision model present, or None if there is no eye to use."""
    have = set(available_models())
    if prefer and prefer in have:
        return prefer
    for name in VISION_MODELS:
        if name in have:
            return name
    return None


def grab(video, times, width=512):
    """JPEG bytes for each requested second, decoded in one pass.

    One pass matters: seeking per frame on a long video is slower than simply
    reading it through once.
    """
    import av
    from PIL import Image

    want = sorted(set(round(float(t), 2) for t in times))
    out = {}
    container = av.open(video)
    stream = container.streams.video[0]
    stream.thread_type = "AUTO"
    idx = 0
    for frame in container.decode(stream):
        if idx >= len(want):
            break
        t = float(frame.pts * stream.time_base) if frame.pts is not None else 0.0
        if t + 1e-3 < want[idx]:
            continue
        img = frame.to_image()
        img.thumbnail((width, width))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=80)
        out[want[idx]] = buf.getvalue()
        idx += 1
    container.close()
    return out


PROMPT = ("Describe this video frame for a video editor in one short sentence. "
          "Say what is in shot, what the person is doing, and the setting. "
          "If there is readable text on screen, quote it. No preamble.")


def describe(video, times, model=None, prompt=PROMPT, log=None):
    """Ask the local model what is in each of these moments.

    Returns {time: description}. A frame the model chokes on is skipped rather
    than taking the whole analysis down with it.
    """
    model = model or pick_model()
    if not model:
        raise RuntimeError(
            "No hay modelo de vision en Ollama. Instala uno (por ejemplo "
            "'ollama pull moondream') o apunta OLLAMA_HOST a la instancia que "
            "tenga los modelos.")
    frames = grab(video, times)
    out = {}
    for n, (t, jpeg) in enumerate(sorted(frames.items()), 1):
        try:
            r = _ollama("/api/generate", {
                "model": model,
                "prompt": prompt,
                "images": [base64.b64encode(jpeg).decode()],
                "stream": False,
                # Room to think AND answer. A reasoning model spends its first
                # couple of hundred tokens reasoning, so a tight budget hands
                # back an empty answer with a perfect description stranded in
                # the thinking field. Measured on qwen3-vl:8b: blank at 120
                # tokens, a clean sentence in 10 s at 400. Asking Ollama for
                # think=false did NOT stop it; the budget is what fixed it.
                "options": {"temperature": 0.1, "num_predict": 400},
            })
            text = (r.get("response") or "").strip().replace("\n", " ")
            if not text:
                # Last resort for a model that reasoned past its budget.
                text = (r.get("thinking") or "").strip().replace("\n", " ")[:240]
            if text:
                out[t] = text
            elif log:
                log("frame %.1fs: el modelo no dijo nada" % t)
        except Exception as e:
            if log:
                log("frame %.1fs sin describir: %s" % (t, str(e)[:80]))
        if log and n % 5 == 0:
            log("descritos %d/%d fotogramas" % (n, len(frames)))
    return out


# --------------------------------------------------------------------------- #
# The whole thing
# --------------------------------------------------------------------------- #
def analyse(video, out_dir, model=None, describe_shots=True, log=None):
    """Shots, movement and a sentence per shot, cached next to the transcript.

    Re-running an edit on the same video reuses the file, because the expensive
    half of this is the model and the video has not changed.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / "vision.json"
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("shots"):
                if log:
                    log("analisis visual reutilizado (%d planos)" % len(data["shots"]))
                return data
        except Exception:
            pass

    if log:
        log("mirando el video...")
    shot_list, track = shots(video, log=log)
    data = {"video": str(video), "shots": shot_list, "track": track,
            "model": None, "descriptions": {}}

    if describe_shots and shot_list:
        chosen = pick_model(model)
        if not chosen:
            if log:
                log("sin modelo de vision, me quedo con el analisis de movimiento")
        else:
            # One frame per shot, from its middle, capped so a long video does
            # not turn into an afternoon.
            mids = [round((s["start"] + s["end"]) / 2, 2) for s in shot_list]
            if len(mids) > MAX_DESCRIBED:
                keep = len(mids) / MAX_DESCRIBED
                mids = [mids[int(i * keep)] for i in range(MAX_DESCRIBED)]
            if log:
                log("preguntando a %s por %d fotogramas" % (chosen, len(mids)))
            data["model"] = chosen
            data["descriptions"] = {str(k): v for k, v in
                                    describe(video, mids, chosen, log=log).items()}

    cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def packed(data, limit=60):
    """The visual track as lines an LLM can read next to the transcript."""
    lines = []
    desc = {float(k): v for k, v in (data.get("descriptions") or {}).items()}
    for s in (data.get("shots") or [])[:limit]:
        mid = round((s["start"] + s["end"]) / 2, 2)
        near = min(desc, key=lambda d: abs(d - mid)) if desc else None
        text = desc.get(near, "") if near is not None and abs(near - mid) < 1.5 else ""
        lines.append("[%07.2f-%07.2f] %s%s" % (
            s["start"], s["end"],
            "quieto, " if s["still"] else "",
            text or ("movimiento %.1f" % s["motion"])))
    return "\n".join(lines)
