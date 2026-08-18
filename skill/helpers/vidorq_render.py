"""Vidorq render engine v2 (Resolve-independent).

Reads a source video, an EDL (keep-segments with optional per-segment punch zoom),
and a caption plan, and produces a finished MP4:
  - smart cuts   : only the EDL keep-segments survive, in order
  - punch zoom   : static center zoom per segment (no keyframes) for emphasis
  - captions     : whichever preset from captions.py was asked for, written as a
                   per-segment ASS track and burned in by ffmpeg/libass
  - clean audio  : 30 ms fades at every segment boundary so cuts never pop

v1 composited captions+zoom frame by frame with PIL/numpy in pure Python
(~170 ms/frame -> 50+ min for a 10-min video). v2 keeps the exact same edit
semantics but moves all per-frame work into ffmpeg filters (crop/scale/
subtitles, all C code) feeding NVENC, one ffmpeg process per EDL segment,
then a lossless concat. Progress is reported on stdout as
"PROGRESS <frames_done> <frames_total>" lines for the engine to relay.

Usage:
    python vidorq_render.py <source> <edl.json> <transcript.json> <out.mp4>
                            [--no-captions] [--no-zoom] [--preset <name>]
                            [--anim <name>] [--chunks <ready.json>]
                            [--transition <none|dissolve|dip|white|slide|wipe|zoom>]
                            [--ratio <source|vertical|portrait|square|wide>]
                            [--crop-x <0..1>]   0 left, 0.5 centre, 1 right
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

import captions as cap

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


# Output shapes, as (ratio, width, height). The vertical one is what a short
# wants; 16:9 keeps whatever the source was.
RATIOS = {
    "source": None,
    "vertical": (9 / 16, 1080, 1920),
    "portrait": (4 / 5, 1080, 1350),
    "square": (1.0, 1080, 1080),
    "wide": (16 / 9, 1920, 1080),
}


def frame_for(ratio, w, h):
    """The output size for a chosen shape, and the crop that gets there.

    Returns (out_w, out_h, crop_w, crop_h). The crop is the biggest rectangle of
    the wanted shape that fits inside the source, so nothing is stretched and no
    bars are added: the picture is cut, which is what a short needs.
    """
    spec = RATIOS.get(ratio)
    if not spec:
        return w, h, w, h
    want, ow, oh = spec
    if abs((w / max(1, h)) - want) < 0.01:
        return w, h, w, h          # already that shape, leave it alone
    if (w / max(1, h)) > want:
        cw, ch = int(round(h * want)), h
    else:
        cw, ch = w, int(round(w / want))
    return ow, oh, cw // 2 * 2, ch // 2 * 2


def render_video(ffmpeg, source, edl, chunks, seg_dir: Path, do_caps, do_zoom,
                 preset=cap.DEFAULT_PRESET, anim=None, ratio="source", crop_x=0.5):
    src = av.open(source)
    vs = src.streams.video[0]
    w, h = vs.codec_context.width, vs.codec_context.height
    fps = Fraction(vs.average_rate)
    src.close()
    out_w, out_h, crop_w, crop_h = frame_for(ratio, w, h)
    if (out_w, out_h) != (w, h):
        print("RATIO: %s -> recorte %dx%d, salida %dx%d" % (ratio, crop_w, crop_h,
                                                            out_w, out_h), flush=True)

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
        # Shape first, then the emphasis zoom, then the captions. The order is
        # the point: reframing after the captions would crop the words, and
        # burning them before the resize would soften them.
        if (crop_w, crop_h) != (w, h):
            # Per segment if the EDL says so, otherwise whatever the user chose.
            # The engine fills frame_x with where the face actually is, using a
            # face detector rather than a guess; see skill/helpers/faces.py. One
            # value per cut and not per frame on purpose: a static crop reads as
            # a deliberate shot, while a crop that drifts needs easing or it
            # looks seasick. See docs/INTELIGENCIA.md.
            fx = float(seg.get("frame_x", crop_x))
            x0 = max(0, min(w - crop_w, int(round((w - crop_w) * fx)))) // 2 * 2
            y0 = (h - crop_h) // 2 // 2 * 2
            vf.append(f"crop={crop_w}:{crop_h}:{x0}:{y0}")
        if zoom > 1.001:
            zw, zh = int(crop_w / zoom) // 2 * 2, int(crop_h / zoom) // 2 * 2
            zx, zy = (crop_w - zw) // 2 // 2 * 2, (crop_h - zh) // 2 // 2 * 2
            vf.append(f"crop={zw}:{zh}:{zx}:{zy}")
        if vf:
            vf.append(f"scale={out_w}:{out_h}:flags=lanczos")
        if do_caps:
            cap.to_ass(seg_dir / f"seg_{i:04d}.ass", chunks, s, e, out_w, out_h,
                       preset, anim)
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


TRANSITIONS = {
    "none": None,
    "dissolve": "fade",
    "dip": "fadeblack",
    "white": "fadewhite",
    "slide": "slideleft",
    "wipe": "wiperight",
    "zoom": "zoomin",
}


def concat_with_transitions(ffmpeg, seg_dir: Path, seg_files, out_path, kind, dur_s):
    """Join the segments with a transition instead of a hard cut.

    ffmpeg's xfade takes exactly two inputs, so a chain of them is built, each
    one starting `dur_s` before its left side ends. A hard cut stays the default
    because on speech a dissolve smears the words; this is for the montage.
    """
    filt = TRANSITIONS.get(kind)
    if not filt or len(seg_files) < 2:
        return False
    lengths = []
    for name in seg_files:
        with av.open(str(seg_dir / name)) as c:
            lengths.append(float(c.duration or 0) / 1_000_000)
    # A transition cannot be longer than the shots it joins, or it eats them.
    d = max(0.12, min(dur_s, min(lengths) * 0.4))

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
    for name in seg_files:
        cmd += ["-i", str(seg_dir / name)]
    steps, last, offset = [], "0:v", 0.0
    for i in range(1, len(seg_files)):
        offset += lengths[i - 1] - d
        tag = "x%d" % i
        steps.append("[%s][%d:v]xfade=transition=%s:duration=%.3f:offset=%.3f[%s]"
                     % (last, i, filt, d, max(0.0, offset), tag))
        last = tag
    cmd += ["-filter_complex", ";".join(steps), "-map", "[%s]" % last,
            "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-an", "-y", str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("xfade failed, falling back to hard cuts: %s" % (r.stderr or "")[-200:],
              flush=True)
        return False
    print("XFADE_OK: %s %.2fs x%d" % (kind, d, len(seg_files) - 1), flush=True)
    return True


def concat_and_mux(ffmpeg, seg_dir: Path, seg_files, audio_path, out_path,
                   transition="none", trans_dur=0.30):
    """Join the segments and marry the audio back on.

    With a transition the video has to be re-encoded, so it happens once into a
    temporary file and the audio is muxed onto that. Without one the segments
    are copied end to end, which is instant and lossless.
    """
    joined = None
    if transition and transition != "none":
        joined = seg_dir / "_xfade.mp4"
        if not concat_with_transitions(ffmpeg, seg_dir, seg_files, joined,
                                       transition, trans_dur):
            joined = None

    if joined:
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-i", str(joined), "-i", str(audio_path),
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
               "-shortest", "-movflags", "+faststart", "-y", str(out_path)]
    else:
        (seg_dir / "concat.txt").write_text(
            "".join(f"file '{n}'\n" for n in seg_files), encoding="utf-8")
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-f", "concat", "-safe", "0", "-i", "concat.txt", "-i", str(audio_path),
               "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
               "-movflags", "+faststart", "-y", str(out_path)]
    r = subprocess.run(cmd, cwd=str(seg_dir), capture_output=True, text=True)
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
    preset = cap.DEFAULT_PRESET
    if "--preset" in sys.argv:
        preset = sys.argv[sys.argv.index("--preset") + 1]
    anim = None
    if "--anim" in sys.argv:
        anim = sys.argv[sys.argv.index("--anim") + 1]
    # Ready-made chunks win over the transcript: this is how a translation gets
    # burned in, since translated words have no per-word timings to rebuild from.
    ratio = "source"
    if "--ratio" in sys.argv:
        ratio = sys.argv[sys.argv.index("--ratio") + 1]
    crop_x = 0.5
    if "--crop-x" in sys.argv:
        crop_x = max(0.0, min(1.0, float(sys.argv[sys.argv.index("--crop-x") + 1])))
    transition = "none"
    if "--transition" in sys.argv:
        transition = sys.argv[sys.argv.index("--transition") + 1]
    given_chunks = None
    if "--chunks" in sys.argv:
        given_chunks = json.loads(
            Path(sys.argv[sys.argv.index("--chunks") + 1]).read_text(encoding="utf-8"))
    edl = json.loads(Path(edl_path).read_text(encoding="utf-8"))["segments"]
    transcript = json.loads(Path(tr_path).read_text(encoding="utf-8"))
    # The line length depends on the frame it has to fit in, so the output shape
    # has to be known before the words are grouped.
    with av.open(source) as _c:
        _v = _c.streams.video[0]
        _ow, _oh, _cw, _ch = frame_for(ratio, _v.codec_context.width,
                                       _v.codec_context.height)
    chunks = (given_chunks or cap.build_chunks(transcript, preset, _ow, _oh)) if do_caps else []

    ffmpeg = find_ffmpeg()
    out = Path(out)
    tmp_a = out.with_name("._a.m4a")
    seg_dir = out.with_name("._segs")
    keep = sum(float(s["end"]) - float(s["start"]) for s in edl)
    print(f"EDL: {len(edl)} segmentos, {keep:.1f}s de material conservado "
          f"(captions={do_caps}:{preset}/{anim or 'propia'}, zoom={do_zoom}, "
          f"transicion={transition}, formato={ratio})", flush=True)
    seg_dir.mkdir(exist_ok=True)
    try:
        seg_files = render_video(ffmpeg, source, edl, chunks, seg_dir,
                                 do_caps, do_zoom, preset, anim, ratio, crop_x)
        render_audio(source, edl, tmp_a)
        concat_and_mux(ffmpeg, seg_dir, seg_files, tmp_a, out, transition)
    finally:
        shutil.rmtree(seg_dir, ignore_errors=True)
        tmp_a.unlink(missing_ok=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
