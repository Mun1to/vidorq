"""Vidorq render engine v1 (Resolve-independent).

Reads a source video, an EDL (keep-segments with optional per-segment punch zoom),
and a caption plan, and produces a finished MP4:
  - smart cuts   : only the EDL keep-segments survive, in order
  - punch zoom   : static center zoom per segment (no keyframes) for emphasis
  - captions     : Hormozi-style 2-word UPPERCASE chunks, rendered with PIL and
                   composited as overlays (this PyAV build has no drawtext/libass)
  - clean audio  : 30 ms fades at every segment boundary so cuts never pop

This is the same edit logic that will later drive DaVinci Resolve through the
bridge; here it renders straight to a file with PyAV + NVENC.

Usage:
    python vidorq_render.py <source> <edl.json> <transcript.json> <out.mp4>
                            [--no-captions] [--no-zoom]
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = r"C:\Windows\Fonts\ariblk.ttf"  # Arial Black — bold, high retention
AUDIO_RATE = 48000
FADE_MS = 30


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #
def build_caption_chunks(transcript: dict, words_per_chunk: int = 2):
    """Flatten transcript words into (start, end, TEXT) chunks in SOURCE time."""
    chunks = []
    buf = []
    for seg in transcript["segments"]:
        for w in seg.get("words", []):
            token = w["w"].strip()
            if not token:
                continue
            buf.append(w)
            if len(buf) >= words_per_chunk:
                text = " ".join(x["w"].strip() for x in buf).upper()
                chunks.append((buf[0]["s"], buf[-1]["e"], text))
                buf = []
    if buf:
        text = " ".join(x["w"].strip() for x in buf).upper()
        chunks.append((buf[0]["s"], buf[-1]["e"], text))
    return chunks


class CaptionRenderer:
    """Renders and caches caption overlays as RGBA ndarrays."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.font = ImageFont.truetype(FONT_PATH, size=int(h * 0.062))
        self._cache: dict[str, np.ndarray] = {}

    def overlay(self, text: str) -> np.ndarray:
        if text in self._cache:
            return self._cache[text]
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        bbox = d.textbbox((0, 0), text, font=self.font, stroke_width=int(self.h * 0.006))
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (self.w - tw) // 2 - bbox[0]
        y = int(self.h * 0.74) - bbox[1]
        # drop shadow + heavy stroke for legibility over any footage
        d.text((x, y + 3), text, font=self.font, fill=(0, 0, 0, 190),
               stroke_width=int(self.h * 0.010), stroke_fill=(0, 0, 0, 190))
        d.text((x, y), text, font=self.font, fill=(255, 255, 255, 255),
               stroke_width=int(self.h * 0.006), stroke_fill=(0, 0, 0, 255))
        arr = np.asarray(img)
        self._cache[text] = arr
        return arr


def active_caption(chunks, t: float):
    for s, e, text in chunks:
        if s <= t < e:
            return text
    return None


def composite(frame_rgb: np.ndarray, overlay_rgba: np.ndarray) -> np.ndarray:
    a = overlay_rgba[:, :, 3:4].astype(np.float32) / 255.0
    return (frame_rgb.astype(np.float32) * (1 - a) +
            overlay_rgba[:, :, :3].astype(np.float32) * a).astype(np.uint8)


def apply_zoom(rgb: np.ndarray, zoom: float) -> np.ndarray:
    if zoom <= 1.001:
        return rgb
    h, w, _ = rgb.shape
    cw, ch = int(w / zoom), int(h / zoom)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    crop = rgb[y0:y0 + ch, x0:x0 + cw]
    return np.asarray(Image.fromarray(crop).resize((w, h), Image.LANCZOS))


# --------------------------------------------------------------------------- #
# Video pass
# --------------------------------------------------------------------------- #
def render_video(source, edl, chunks, out_path, do_caps, do_zoom):
    src = av.open(source)
    vs = src.streams.video[0]
    w = vs.codec_context.width
    h = vs.codec_context.height
    fps = Fraction(vs.average_rate)

    oc = av.open(str(out_path), "w")
    ov = oc.add_stream("h264_nvenc", rate=fps)
    ov.width, ov.height, ov.pix_fmt = w, h, "yuv420p"
    ov.codec_context.options = {"rc": "vbr", "cq": "21", "b:v": "12M", "preset": "p5"}

    caps = CaptionRenderer(w, h) if do_caps else None
    tb = Fraction(1, 1) / fps
    out_idx = 0
    frame_dur = 1.0 / float(fps)

    for seg in edl:
        s, e = float(seg["start"]), float(seg["end"])
        zoom = float(seg.get("zoom", 1.0)) if do_zoom else 1.0
        src.seek(int(s / vs.time_base), stream=vs, any_frame=False, backward=True)
        for frame in src.decode(vs):
            t = float(frame.pts * vs.time_base)
            if t < s - frame_dur:
                continue
            if t >= e:
                break
            rgb = frame.to_ndarray(format="rgb24")
            if zoom > 1.001:
                rgb = apply_zoom(rgb, zoom)
            if caps is not None:
                text = active_caption(chunks, t)
                if text:
                    rgb = composite(rgb, caps.overlay(text))
            of = av.VideoFrame.from_ndarray(rgb, format="rgb24").reformat(format="yuv420p")
            of.pts = out_idx
            of.time_base = tb
            out_idx += 1
            for pkt in ov.encode(of):
                oc.mux(pkt)
    for pkt in ov.encode():
        oc.mux(pkt)
    oc.close()
    src.close()
    total_s = out_idx / float(fps)
    print(f"VIDEO_OK: {out_idx} frames, {total_s:.1f}s", flush=True)
    return total_s


# --------------------------------------------------------------------------- #
# Audio pass (concatenate segments with boundary fades, mux later)
# --------------------------------------------------------------------------- #
def render_audio(source, edl, out_path):
    src = av.open(source)
    a = src.streams.audio[0]
    rs = av.AudioResampler(format="s16", layout="stereo", rate=AUDIO_RATE)
    fade = int(AUDIO_RATE * FADE_MS / 1000)
    ramp = np.linspace(0, 1, fade, dtype=np.float32)[:, None]
    pieces = []
    for seg in edl:
        s, e = float(seg["start"]), float(seg["end"])
        src.seek(int(s / a.time_base), stream=a, any_frame=False, backward=True)
        buf = []
        for frame in src.decode(a):
            t = float(frame.pts * a.time_base)
            if t < s - 0.05:
                continue
            if t >= e:
                break
            for rf in rs.resample(frame):
                buf.append(rf.to_ndarray())  # packed s16 -> shape (1, n*2)
        if not buf:
            continue
        piece = np.concatenate(buf, axis=1).reshape(-1, 2).astype(np.float32)  # (n, 2)
        if len(piece) > 2 * fade:  # 30 ms fade at each segment boundary -> no pops
            piece[:fade] *= ramp
            piece[-fade:] *= ramp[::-1]
        pieces.append(piece)
    src.close()

    flat = np.clip(np.concatenate(pieces, axis=0), -32768, 32767).astype(np.int16)

    oc = av.open(str(out_path), "w")
    oa = oc.add_stream("aac", rate=AUDIO_RATE)
    oa.codec_context.layout = "stereo"
    chunk = 1024
    pts = 0
    for i in range(0, len(flat), chunk):
        block = flat[i:i + chunk].reshape(1, -1).copy()  # packed: (1, n*2)
        af = av.AudioFrame.from_ndarray(block, format="s16", layout="stereo")
        af.sample_rate = AUDIO_RATE
        af.pts = pts
        af.time_base = Fraction(1, AUDIO_RATE)
        pts += (i + chunk <= len(flat)) and chunk or (len(flat) - i)
        for pkt in oa.encode(af):
            oc.mux(pkt)
    for pkt in oa.encode():
        oc.mux(pkt)
    oc.close()
    print(f"AUDIO_OK: {len(flat) / AUDIO_RATE:.1f}s", flush=True)


def mux(video_path, audio_path, out_path):
    vin = av.open(str(video_path))
    ain = av.open(str(audio_path))
    oc = av.open(str(out_path), "w")
    ov = oc.add_stream_from_template(vin.streams.video[0])
    oa = oc.add_stream_from_template(ain.streams.audio[0])
    for pkt in vin.demux(vin.streams.video[0]):
        if pkt.dts is None:
            continue
        pkt.stream = ov
        oc.mux(pkt)
    for pkt in ain.demux(ain.streams.audio[0]):
        if pkt.dts is None:
            continue
        pkt.stream = oa
        oc.mux(pkt)
    oc.close(); vin.close(); ain.close()
    print(f"MUX_OK: {out_path}", flush=True)


def main():
    source, edl_path, tr_path, out = sys.argv[1:5]
    do_caps = "--no-captions" not in sys.argv
    do_zoom = "--no-zoom" not in sys.argv
    edl = json.loads(Path(edl_path).read_text(encoding="utf-8"))["segments"]
    transcript = json.loads(Path(tr_path).read_text(encoding="utf-8"))
    chunks = build_caption_chunks(transcript) if do_caps else []

    out = Path(out)
    tmp_v = out.with_name("._v.mp4")
    tmp_a = out.with_name("._a.m4a")
    keep = sum(float(s["end"]) - float(s["start"]) for s in edl)
    print(f"EDL: {len(edl)} segmentos, {keep:.1f}s de material conservado "
          f"(captions={do_caps}, zoom={do_zoom})", flush=True)
    render_video(source, edl, chunks, tmp_v, do_caps, do_zoom)
    render_audio(source, edl, tmp_a)
    mux(tmp_v, tmp_a, out)
    tmp_v.unlink(missing_ok=True)
    tmp_a.unlink(missing_ok=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
