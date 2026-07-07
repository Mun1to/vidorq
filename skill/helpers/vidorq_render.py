"""Vidorq render engine v2 (Resolve-independent).

Reads a source video, an EDL (keep-segments with optional per-segment punch zoom),
and a caption plan, and produces a finished MP4:
  - smart cuts   : only the EDL keep-segments survive, in order
  - punch zoom   : static center zoom per segment (no keyframes) for emphasis
  - captions     : Hormozi-style 2-word UPPERCASE chunks, written as a per-segment
                   ASS track and burned in by ffmpeg/libass
  - clean audio  : 30 ms fades at every segment boundary so cuts never pop

v1 composited captions+zoom frame by frame with PIL/numpy in pure Python
(~170 ms/frame -> 50+ min for a 10-min video). v2 keeps the exact same edit
semantics but moves all per-frame work into ffmpeg filters (crop/scale/
subtitles, all C code) feeding NVENC, one ffmpeg process per EDL segment,
then a lossless concat. Progress is reported on stdout as
"PROGRESS <frames_done> <frames_total>" lines for the engine to relay.

Usage:
    python vidorq_render.py <source> <edl.json> <transcript.json> <out.mp4>
                            [--no-captions] [--no-zoom]
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections import deque
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

FONT_FAMILY = "Arial Black"  # bold, high retention
AUDIO_RATE = 48000
FADE_MS = 30

# keys ffmpeg -progress writes to stdout; anything else on the merged
# stdout/stderr stream is kept as the error tail
PROGRESS_KEYS = ("frame=", "fps=", "stream_", "bitrate=", "total_size=",
                 "out_time", "dup_frames=", "drop_frames=", "speed=", "progress=")


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH; install it (e.g. winget "
                           "install Gyan.FFmpeg) - Vidorq needs it to render")
    return exe


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


def ass_time(t: float) -> str:
    cs = max(0, int(round(t * 100)))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_segment_ass(path: Path, chunks, seg_start: float, seg_end: float,
                      w: int, h: int):
    """ASS subtitle file for one EDL segment, times shifted to segment-local.

    Two layers reproduce the v1 PIL look: layer 0 is a soft dark halo (text
    and thick outline at alpha 190, offset 3 px down), layer 1 is the white
    text with an opaque black stroke.
    """
    em = h * 0.062  # v1 used this as the PIL em size; keep the same visual size
    # libass (VSFilter-compatible) treats Fontsize as the GDI cell height;
    # for Arial Black that is 1.411 em (winAscent 2254 + winDescent 634 / 2048)
    fs = int(em * 1.411)
    outline = max(1, int(h * 0.006))
    halo = max(outline, int(h * 0.010))
    x = w // 2
    # \pos+an8 anchors at the ascender top; v1 put the ink (cap) top at 0.74h,
    # so pull up by winAscent-capHeight = (2254-1466)/2048 = 0.385 em
    y = int(h * 0.74 - em * 0.385)
    head = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Halo,{FONT_FAMILY},{fs},&H41000000,&H41000000,&H41000000,"
        "&H41000000,0,0,0,0,100,100,0,0,1," f"{halo},0,8,0,0,0,1\n"
        f"Style: Main,{FONT_FAMILY},{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,"
        "&H00000000,0,0,0,0,100,100,0,0,1," f"{outline},0,8,0,0,0,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    lines = [head]
    for cs_, ce_, text in chunks:
        s = max(cs_, seg_start) - seg_start
        e = min(ce_, seg_end) - seg_start
        if e - s < 0.01:
            continue
        text = text.replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Halo,,0,0,0,,"
                     f"{{\\pos({x},{y + 3})}}{text}\n")
        lines.append(f"Dialogue: 1,{ass_time(s)},{ass_time(e)},Main,,0,0,0,,"
                     f"{{\\pos({x},{y})}}{text}\n")
    path.write_text("".join(lines), encoding="utf-8-sig")


# --------------------------------------------------------------------------- #
# Video pass (one ffmpeg per EDL segment, then lossless concat)
# --------------------------------------------------------------------------- #
ENCODERS = {
    "h264_nvenc": ["-c:v", "h264_nvenc", "-rc", "vbr", "-cq", "21",
                   "-b:v", "12M", "-preset", "p5"],
    "libx264": ["-c:v", "libx264", "-crf", "21", "-preset", "veryfast"],
}


def run_ffmpeg_progress(cmd, cwd: Path, base: int, total: int):
    """Run ffmpeg relaying -progress frame counts as global PROGRESS lines."""
    p = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace")
    frames = 0
    tail = deque(maxlen=15)
    for line in p.stdout:
        if line.startswith("frame="):
            try:
                frames = int(line.split("=", 1)[1].strip())
            except ValueError:
                continue
            print(f"PROGRESS {min(base + frames, total)} {total}", flush=True)
        elif line.strip() and not line.startswith(PROGRESS_KEYS):
            tail.append(line.strip())
    p.wait()
    return frames, p.returncode, "\n".join(tail)


def render_video(ffmpeg, source, edl, chunks, seg_dir: Path, do_caps, do_zoom):
    src = av.open(source)
    vs = src.streams.video[0]
    w, h = vs.codec_context.width, vs.codec_context.height
    fps = Fraction(vs.average_rate)
    src.close()

    total = sum(max(1, round((float(s["end"]) - float(s["start"])) * fps))
                for s in edl)
    print(f"PROGRESS 0 {total}", flush=True)

    encoder = "h264_nvenc"
    seg_files = []
    done = 0
    for i, seg in enumerate(edl):
        s, e = float(seg["start"]), float(seg["end"])
        zoom = float(seg.get("zoom", 1.0)) if do_zoom else 1.0
        vf = []
        if zoom > 1.001:
            cw, ch = int(w / zoom) // 2 * 2, int(h / zoom) // 2 * 2
            x0, y0 = (w - cw) // 2 // 2 * 2, (h - ch) // 2 // 2 * 2
            vf.append(f"crop={cw}:{ch}:{x0}:{y0}")
            vf.append(f"scale={w}:{h}:flags=lanczos")
        if do_caps:
            write_segment_ass(seg_dir / f"seg_{i:04d}.ass", chunks, s, e, w, h)
            vf.append(f"subtitles=seg_{i:04d}.ass")
        seg_name = f"seg_{i:04d}.mp4"

        def cmd_for(enc):
            c = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                 "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", source,
                 "-an", "-sn"]
            if vf:
                c += ["-vf", ",".join(vf)]
            return c + ENCODERS[enc] + ["-pix_fmt", "yuv420p",
                                        "-progress", "pipe:1", "-y", seg_name]

        frames, rc, err = run_ffmpeg_progress(cmd_for(encoder), seg_dir, done, total)
        if rc != 0 and encoder == "h264_nvenc":
            print(f"NVENC failed ({err[-120:]}), falling back to libx264", flush=True)
            encoder = "libx264"
            frames, rc, err = run_ffmpeg_progress(cmd_for(encoder), seg_dir, done, total)
        if rc != 0:
            raise RuntimeError(f"ffmpeg failed on segment {i} [{s:.2f}-{e:.2f}]: {err[-300:]}")
        done += frames
        seg_files.append(seg_name)
    print(f"VIDEO_OK: {done} frames, {done / float(fps):.1f}s", flush=True)
    return seg_files


def concat_and_mux(ffmpeg, seg_dir: Path, seg_files, audio_path, out_path):
    (seg_dir / "concat.txt").write_text(
        "".join(f"file '{n}'\n" for n in seg_files), encoding="utf-8")
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
         "-f", "concat", "-safe", "0", "-i", "concat.txt", "-i", str(audio_path),
         "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
         "-movflags", "+faststart", "-y", str(out_path)],
        cwd=str(seg_dir), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg concat failed: " + (r.stderr or "")[-300:])
    print(f"MUX_OK: {out_path}", flush=True)


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


def main():
    source, edl_path, tr_path, out = sys.argv[1:5]
    do_caps = "--no-captions" not in sys.argv
    do_zoom = "--no-zoom" not in sys.argv
    edl = json.loads(Path(edl_path).read_text(encoding="utf-8"))["segments"]
    transcript = json.loads(Path(tr_path).read_text(encoding="utf-8"))
    chunks = build_caption_chunks(transcript) if do_caps else []

    ffmpeg = find_ffmpeg()
    out = Path(out)
    tmp_a = out.with_name("._a.m4a")
    seg_dir = out.with_name("._segs")
    keep = sum(float(s["end"]) - float(s["start"]) for s in edl)
    print(f"EDL: {len(edl)} segmentos, {keep:.1f}s de material conservado "
          f"(captions={do_caps}, zoom={do_zoom})", flush=True)
    seg_dir.mkdir(exist_ok=True)
    try:
        seg_files = render_video(ffmpeg, source, edl, chunks, seg_dir,
                                 do_caps, do_zoom)
        render_audio(source, edl, tmp_a)
        concat_and_mux(ffmpeg, seg_dir, seg_files, tmp_a, out)
    finally:
        shutil.rmtree(seg_dir, ignore_errors=True)
        tmp_a.unlink(missing_ok=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
