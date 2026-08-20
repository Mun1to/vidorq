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
    Ojo con --chunks: esos vienen en el reloj del MONTAJE, no en el del original.
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
import looks
import overlays

AUDIO_RATE = 48000
FADE_MS = 30

# Windows gives every child process its own console window when the parent has
# none, and the parent here has none: Resolve starts the engine with pythonw so
# nothing flashes. The result was the opposite, a console blinking on screen for
# every single ffmpeg, and there is one ffmpeg per segment. CREATE_NO_WINDOW is
# what stops it, and it does not exist off Windows, hence the getattr.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

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
                         encoding="utf-8", errors="replace",
                         creationflags=NO_WINDOW)
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


# Impact shake, in numbers. Fast and short is the whole trick: a shake that
# lasts is a wobble and reads as bad footage, while one that dies in a fifth of
# a second reads as something landing. Cut off entirely below a pixel, so the
# rest of the segment is not evaluating a sine wave for nothing.
SHAKE_SECONDS = 0.20
SHAKE_HZ = 17.0
# How far it moves, as a fraction of the headroom the zoom left. Never more,
# because past the headroom the crop walks off the edge of the frame and ffmpeg
# clamps it, which turns a shake into a lurch.
SHAKE_REACH = 0.75
# The least zoom a shaking segment gets, so there is a margin to move inside.
SHAKE_MIN_ZOOM = 1.05


def shake_crop(zw, zh, zx, zy, secs=SHAKE_SECONDS, hz=SHAKE_HZ):
    """A crop that jitters and settles, written as an ffmpeg expression.

    Done inside ffmpeg on purpose. The alternative is moving the crop frame by
    frame from Python, which is what v1 of this renderer did for everything and
    why it took fifty minutes to render ten minutes of video. An expression is
    evaluated in C, once per frame, and costs nothing measurable.

    Both axes decay together but at different frequencies, so the movement is
    not a diagonal line: 1.0 and 1.37 do not line up again for long enough that
    the eye never sees a pattern. `t` restarts at zero for every segment because
    each one is its own ffmpeg run, which is exactly the clock a shake wants.
    """
    ax = max(0.0, min(zx, zw * 0.05)) * SHAKE_REACH
    ay = max(0.0, min(zy, zh * 0.05)) * SHAKE_REACH
    if ax < 1 and ay < 1:
        return f"crop={zw}:{zh}:{zx}:{zy}"
    decay = f"exp(-t/{secs / 3.0:.4f})"
    x = f"{zx}+{ax:.1f}*{decay}*sin(t*{hz * 6.2832:.3f})"
    y = f"{zy}+{ay:.1f}*{decay}*cos(t*{hz * 1.37 * 6.2832:.3f})"
    # lt(t,secs) switches the whole thing off once it has decayed to nothing.
    return (f"crop={zw}:{zh}:x='if(lt(t,{secs}),{x},{zx})'"
            f":y='if(lt(t,{secs}),{y},{zy})'")


def _cards_by_kind(cards, desde, hasta):
    """Los rotulos que caen en este trozo, agrupados por tipo.

    Los segundos de `cards` son del MONTAJE, como los que manda el motor. Se
    devuelven con forma de chunk porque quien los va a escribir es to_ass, que
    solo sabe de chunks.
    """
    if not cards:
        return []
    # La clave lleva el COLOR ademas del tipo. Aqui se armaban dicts nuevos con
    # solo el texto y los segundos, asi que el color de la marca se quedaba por
    # el camino y la barra salia siempre del color de fabrica.
    por_tipo = {}
    for c in cards:
        a = float(c.get("at", 0.0))
        b = a + float(c.get("secs") or 3.0)
        if b <= desde or a >= hasta:
            continue
        texto = str(c.get("text") or "")
        clave = (c.get("kind") or "rotulo", c.get("color") or "")
        por_tipo.setdefault(clave, []).append(
            {"start": a, "end": b, "text": texto,
             "words": [{"w": texto, "s": a, "e": b}]})
    return [(k, color, trozo) for (k, color), trozo in sorted(por_tipo.items())]


def render_video(ffmpeg, source, edl, chunks, seg_dir: Path, do_caps, do_zoom,
                 preset=cap.DEFAULT_PRESET, anim=None, ratio="source", crop_x=0.5,
                 look="", cdl=None, chunks_edited=False, cards=None):
    """`chunks_edited` dice en que reloj vienen los subtitulos.

    Los que se construyen aqui salen de la transcripcion, o sea del reloj del
    ORIGINAL, y cada trozo se filtra con sus propios segundos de origen. Los que
    llegan por `--chunks` ya vienen del MONTAJE (el motor los arma sobre la
    transcripcion recortada), y filtrarlos con el reloj del original los tira
    todos: un cartel pedido en el segundo 1 del montaje cae antes del principio
    del primer trozo y no se dibuja. Medido: cero lineas de Dialogue en los dos
    trozos de un EDL de prueba.
    """
    src = av.open(source)
    vs = src.streams.video[0]
    w, h = vs.codec_context.width, vs.codec_context.height
    fps = Fraction(vs.average_rate)
    src.close()
    out_w, out_h, crop_w, crop_h = frame_for(ratio, w, h)
    if (out_w, out_h) != (w, h):
        print("RATIO: %s -> recorte %dx%d, salida %dx%d" % (ratio, crop_w, crop_h,
                                                            out_w, out_h), flush=True)

    # La clave del .cube: con numeros propios hay uno por video, y sin ella dos
    # videos distintos compartirian la correccion del primero.
    key = ("%.4f_%.4f_%.4f_%.4f" % (cdl["slope"][0], cdl["slope"][1],
                                    cdl["slope"][2], cdl["sat"])) if cdl else ""
    look_vf = looks.ffmpeg_filter(look, cdl, key) if look else None
    if look_vf:
        print("LOOK: %s%s" % (look, " (medido en tu video)" if cdl else ""), flush=True)

    total = sum(max(1, round((float(s["end"]) - float(s["start"])) * fps))
                for s in edl)
    print(f"PROGRESS 0 {total}", flush=True)

    encoder = "h264_nvenc"
    seg_files = []
    done = 0
    # Donde empieza cada trozo en el MONTAJE: la suma de lo que dura todo lo
    # anterior. Es el reloj que ve el usuario y el de los chunks que llegan
    # hechos de fuera.
    ed_at = 0.0
    for i, seg in enumerate(edl):
        s, e = float(seg["start"]), float(seg["end"])
        zoom = float(seg.get("zoom", 1.0)) if do_zoom else 1.0
        # A shake needs somewhere to move. The crop can only slide inside the
        # margin the zoom left over, so a segment asked to shake at zoom 1.0 has
        # a margin of zero and renders perfectly still. Measured: half the beat
        # cuts came out with no shake at all until this line existed.
        if seg.get("shake") and zoom < SHAKE_MIN_ZOOM:
            zoom = SHAKE_MIN_ZOOM
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
            if seg.get("shake"):
                vf.append(shake_crop(zw, zh, zx, zy))
            else:
                vf.append(f"crop={zw}:{zh}:{zx}:{zy}")
        if vf:
            vf.append(f"scale={out_w}:{out_h}:flags=lanczos")
        # El color va DESPUES del reencuadre y ANTES de los subtitulos: despues,
        # porque asi se colorean menos pixeles; antes, porque un subtitulo
        # blanco tiene que seguir siendo blanco y no salir teñido del filtro.
        if look_vf:
            vf.append(look_vf)
        if do_caps:
            a0, b0 = (ed_at, ed_at + (e - s)) if chunks_edited else (s, e)
            cap.to_ass(seg_dir / f"seg_{i:04d}.ass", chunks, a0, b0, out_w, out_h,
                       preset, anim)
            vf.append(f"subtitles=seg_{i:04d}.ass")
        # Los rotulos y las chapas van en su PROPIO archivo .ass, uno por tipo:
        # un ASS lleva un estilo por nombre y aqui hacen falta dos pintas
        # distintas a la vez (la barra de abajo y la etiqueta de arriba). Van
        # despues de los subtitulos en la cadena de filtros, o sea encima.
        for j, (kind, color, trozo) in enumerate(_cards_by_kind(cards, ed_at,
                                                                ed_at + (e - s))):
            # El color de la marca viaja dentro de cada rotulo, en el mismo
            # JSON que ya trae su texto y su segundo: asi no hace falta otra
            # opcion en la linea de comandos para un dato que es del mismo sitio.
            p_ov = overlays.as_preset(kind, color)
            if not p_ov:
                continue
            name = f"seg_{i:04d}_c{j}.ass"
            cap.to_ass(seg_dir / name, trozo, ed_at, ed_at + (e - s),
                       out_w, out_h, p=p_ov)
            vf.append(f"subtitles={name}")
        ed_at += e - s
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
    # El destello es el mismo blanco pero corto: lo que lo hace un golpe de luz
    # y no un fundido es que dura 0,18 s, y eso lo dice overlays.seconds().
    "flash": "fadewhite",
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
    r = subprocess.run(cmd, capture_output=True, text=True,
                       creationflags=NO_WINDOW)
    if r.returncode != 0:
        print("xfade failed, falling back to hard cuts: %s" % (r.stderr or "")[-200:],
              flush=True)
        return False
    print("XFADE_OK: %s %.2fs x%d" % (kind, d, len(seg_files) - 1), flush=True)
    return True


def concat_and_mux(ffmpeg, seg_dir: Path, seg_files, audio_path, out_path,
                   transition="none", trans_dur=None):
    """Join the segments and marry the audio back on.

    With a transition the video has to be re-encoded, so it happens once into a
    temporary file and the audio is muxed onto that. Without one the segments
    are copied end to end, which is instant and lossless.
    """
    joined = None
    if transition and transition != "none":
        joined = seg_dir / "_xfade.mp4"
        # Cuanto dura, de la misma tabla que usa Resolve. Antes eran 0,30 s para
        # todas, asi que un fundido a negro duraba 0,50 en el timeline y 0,30 en
        # el MP4: el mismo nombre y dos cosas distintas segun por donde saliera.
        if trans_dur is None:
            try:
                import overlays
                trans_dur = overlays.seconds(transition)
            except Exception:
                trans_dur = 0.30
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
    r = subprocess.run(cmd, cwd=str(seg_dir), capture_output=True, text=True,
                       creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg concat failed: " + (r.stderr or "")[-300:])
    print(f"MUX_OK: {out_path}", flush=True)


# --------------------------------------------------------------------------- #
# Audio pass (concatenate segments with boundary fades, mux later)
# --------------------------------------------------------------------------- #
# How far the original drops while a voice-over is talking, and how long it
# takes to get there. A hard drop reads as a fault in the file; a slow one
# swallows the first word. A fifth of a second is the usual radio number.
DUCK_TO = 0.30
DUCK_RAMP_S = 0.20
# Room either side of the spoken line, so the bed is already down when the first
# syllable lands and does not jump back up on the last one.
DUCK_PAD_S = 0.15


def _read_pcm(path):
    """Any audio file as float32 stereo at AUDIO_RATE, shape (n, 2).

    Whatever the engine handed back: Windows writes a 16 bit mono wav, the paid
    ones write mp3 at whatever rate they like. The resampler flattens all of it
    so the mix does not have to care where the voice came from.
    """
    c = av.open(str(path))
    st = c.streams.audio[0]
    rs = av.AudioResampler(format="s16", layout="stereo", rate=AUDIO_RATE)
    buf = []
    for frame in c.decode(st):
        for rf in rs.resample(frame):
            buf.append(rf.to_ndarray())
    for rf in rs.resample(None):        # lo que quede en el resampler
        buf.append(rf.to_ndarray())
    c.close()
    if not buf:
        return np.zeros((0, 2), dtype=np.float32)
    return np.concatenate(buf, axis=1).reshape(-1, 2).astype(np.float32)


def _mix_voices(flat, voices):
    """Lay the spoken lines over the edited audio, ducking what is underneath.

    `flat` is float32 (n, 2) and the times are seconds of the EDITED video,
    because that is the only clock that still means anything once the cuts have
    been made. A line that starts past the end of the video is dropped rather
    than extending it: the user asked for a voice over the video, not for a
    video with a tail of talking over black.
    """
    for v in voices or []:
        try:
            speech_pcm = _read_pcm(v["path"])
        except Exception as e:
            print("VOZ: no pude leer %s (%s)" % (v.get("path"), str(e)[:80]), flush=True)
            continue
        if not len(speech_pcm):
            continue
        start = int(max(0.0, float(v.get("at", 0.0))) * AUDIO_RATE)
        if start >= len(flat):
            print("VOZ: el segundo %.1f cae fuera del video ya montado, la dejo"
                  % float(v.get("at", 0.0)), flush=True)
            continue
        n = min(len(speech_pcm), len(flat) - start)
        pad = int(DUCK_PAD_S * AUDIO_RATE)
        ramp_n = max(1, int(DUCK_RAMP_S * AUDIO_RATE))
        lo = max(0, start - pad)
        hi = min(len(flat), start + n + pad)
        # A gain curve for the bed: 1 down to DUCK_TO across the ramp, flat while
        # the line runs, back up after it. Built as an array so the whole thing
        # is one multiply instead of a loop over samples.
        gain = np.ones(hi - lo, dtype=np.float32)
        gain[:] = DUCK_TO
        up = np.linspace(1.0, DUCK_TO, min(ramp_n, len(gain)), dtype=np.float32)
        gain[:len(up)] = up
        down = np.linspace(DUCK_TO, 1.0, min(ramp_n, len(gain)), dtype=np.float32)
        gain[len(gain) - len(down):] = np.maximum(gain[len(gain) - len(down):], down)
        flat[lo:hi] *= gain[:, None]
        flat[start:start + n] += speech_pcm[:n]
        print("VOZ: %.1fs, %.1fs de linea" % (start / AUDIO_RATE, n / AUDIO_RATE),
              flush=True)
    return flat


def render_audio(source, edl, out_path, voices=None):
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

    # The clip to int16 waits until AFTER the voice is in: mixing on top of an
    # already clipped array would have the loud parts fold instead of duck.
    mixed = _mix_voices(np.concatenate(pieces, axis=0), voices)
    flat = np.clip(mixed, -32768, 32767).astype(np.int16)

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
    # [{"at": segundos del video YA MONTADO, "path": archivo de audio}]. Llega en
    # un archivo y no en la linea de comandos porque una ruta con espacios y un
    # acento es exactamente el tipo de cosa que se rompe una vez al ano.
    look = ""
    if "--look" in sys.argv:
        look = sys.argv[sys.argv.index("--look") + 1]
    # Los numeros del color automatico, que no salen del catalogo sino de mirar
    # ESTE video. Van en un archivo por lo mismo que el resto: una linea de
    # comandos con doce decimales es una linea de comandos que se rompe.
    cdl = None
    if "--cdl" in sys.argv:
        cdl = json.loads(
            Path(sys.argv[sys.argv.index("--cdl") + 1]).read_text(encoding="utf-8"))
        cdl = {k: (tuple(v) if isinstance(v, list) else v) for k, v in cdl.items()}
    # Los rotulos, en segundos del MONTAJE. Van en archivo por lo mismo que el
    # resto: un texto del usuario en la linea de comandos es una linea de
    # comandos que se rompe con la primera comilla.
    cards = None
    if "--cards" in sys.argv:
        cards = json.loads(
            Path(sys.argv[sys.argv.index("--cards") + 1]).read_text(encoding="utf-8"))
    voices = None
    if "--voices" in sys.argv:
        voices = json.loads(
            Path(sys.argv[sys.argv.index("--voices") + 1]).read_text(encoding="utf-8"))
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
          f"transicion={transition}, formato={ratio}, color={look or 'ninguno'}, "
          f"voces={len(voices or [])})", flush=True)
    seg_dir.mkdir(exist_ok=True)
    try:
        seg_files = render_video(ffmpeg, source, edl, chunks, seg_dir,
                                 do_caps, do_zoom, preset, anim, ratio, crop_x,
                                 look, cdl, chunks_edited=bool(given_chunks),
                                 cards=cards)
        render_audio(source, edl, tmp_a, voices)
        concat_and_mux(ffmpeg, seg_dir, seg_files, tmp_a, out, transition)
    finally:
        shutil.rmtree(seg_dir, ignore_errors=True)
        tmp_a.unlink(missing_ok=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
