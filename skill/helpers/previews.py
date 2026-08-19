"""Pictures of what each choice actually does, made with the real renderer.

A row of names is not a choice. "Ember" and "Halo" mean nothing until you see
them, and neither does "Vertical 9:16" until you see YOUR shot inside it with
the sides gone. So every preview here comes out of the same code that produces
the final video: the same ASS from captions.py, the same crop, the same face
detector. Drawing these by hand in CSS would be faster and would lie, and a
preview that lies is worse than no preview at all.

Three kinds, because the three things being chosen are different:

  style   a still. A look is a look, and one frame shows it.
  anim    a short animated loop. Motion cannot be shown in a still, and
          pretending otherwise is how somebody picks "Bounce" and is surprised.
  ratio   a still of the REAL crop, face detector included, so "will this cut my
          head off" is answered by looking instead of by promising.

Everything is cached on disk under a key made of what went into it, so the first
open costs a few seconds of ffmpeg and every one after that costs nothing.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import captions as cap  # noqa: E402
import looks  # noqa: E402

CACHE = Path(os.environ.get("APPDATA", ".")) / "Vidorq" / "previews"
# What the sample caption says. Short enough to fit one vertical line, long
# enough to show letter spacing, the outline and the plate of a style.
SAMPLE = {"es": "ASÍ SE VE", "en": "LIKE THIS"}
# How wide a preview comes out. Small enough to be quick, big enough that a thin
# look like Minimal does not turn to mush.
PREVIEW_LONG = 480
# The entrance is caught mid-flight on purpose: the resting frame of "Bounce"
# looks exactly like the resting frame of "None".
ANIM_STILL_AT = 0.12
LOOP_SECONDS = 1.1
LOOP_FPS = 20
# A flat card the colour of the app's panel, for previews asked for before a
# video is chosen.
BLANK = "0x14141a"

# The gallery tile is a close-up, not the whole frame, and it has to be.
# Measured on the wall of ten looks: a Minimal caption is 3.4% of the frame
# width tall, so in a 198 px tile it came out at under seven pixels and five of
# the ten looks were an unreadable smudge. A gallery that cannot show you the
# difference between Minimal and Mono is a list of names with decoration.
#
# Showing less of the frame is the only lever: the caption is a fixed fraction
# of the frame, so the only way to make it bigger in a fixed tile is to crop
# the frame around it. The whole frame is still what the big preview shows,
# which is the one that answers "how will this look".
#
# Width first: the sample line is short and centred, and even Pop, the fattest
# look, runs to about 42% of the width. 62% clears it with room for the glow,
# which is drawn outside the letters.
BAND_W = 0.62
# Height measured from the bottom. Captions sit between 0.12 and 0.22 of the
# height off the floor and stand about 0.06 tall, so everything is inside the
# bottom 28%, and half the frame would already be plenty. It is set higher than
# it needs to be on purpose: the height costs nothing in legibility, because a
# tile is limited by its WIDTH and the letters only grow when the band gets
# narrower. Cropped to the bottom half, ten tiles of a talking video all showed
# the same pair of jeans. Two thirds gets the person back in the picture for
# free.
BAND_H = 0.70


# Windows gives every child process its own console window when the parent has
# none, and the parent here has none: Resolve starts the engine with pythonw so
# nothing flashes. The result was the opposite, a console blinking on screen for
# every single ffmpeg, and with one ffmpeg per preview that is a blink on every
# button press. CREATE_NO_WINDOW is what stops it, and it does not exist off
# Windows, hence the getattr.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def ffmpeg():
    return shutil.which("ffmpeg")


def _key(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _shape(ratio, w, h):
    from vidorq_render import frame_for
    return frame_for(ratio, w, h)


def _chunk(lang, seconds):
    """One fake caption chunk, shaped exactly like build_chunks would make it."""
    text = SAMPLE.get(lang, SAMPLE["es"])
    words = text.split()
    step = seconds / max(1, len(words))
    return {"start": 0.0, "end": seconds, "text": text,
            "words": [{"w": word, "s": i * step, "e": (i + 1) * step}
                      for i, word in enumerate(words)]}


def _crop_chain(w, h, out_w, out_h, crop_w, crop_h, fx):
    """The same crop the renderer would apply, so the preview cannot drift."""
    if (crop_w, crop_h) == (w, h):
        return []
    x0 = max(0, min(w - crop_w, int(round((w - crop_w) * fx)))) // 2 * 2
    y0 = (h - crop_h) // 2 // 2 * 2
    return ["crop=%d:%d:%d:%d" % (crop_w, crop_h, x0, y0),
            "scale=%d:%d:flags=lanczos" % (out_w, out_h)]


def _band_key(band):
    """What the band contributes to a cache key.

    The fractions themselves, not a yes/no. Tuning BAND_H and still being
    served yesterday's crop is a preview that lies, which is the one thing this
    module is not allowed to do.
    """
    return ("band%.2fx%.2f" % (BAND_W, BAND_H)) if band else ""


def _band(out_w, out_h):
    """Crop to where the caption lives: centre of the width, bottom half."""
    bw = int(out_w * BAND_W) // 2 * 2
    bh = int(out_h * BAND_H) // 2 * 2
    return "crop=%d:%d:%d:%d" % (bw, bh, (out_w - bw) // 2 // 2 * 2, out_h - bh)


def _fit(out_w, out_h):
    """Scale the finished frame down to preview size, keeping its shape."""
    if out_w >= out_h:
        return "scale=%d:-2" % PREVIEW_LONG
    return "scale=-2:%d" % PREVIEW_LONG


def _source_args(video, at, out_w, out_h, seconds=0.0):
    if video and os.path.isfile(video):
        args = ["-ss", "%.2f" % at]
        if seconds:
            args += ["-t", "%.2f" % seconds]
        return args + ["-i", video], True
    spec = "color=c=%s:s=%dx%d:d=%.2f" % (BLANK, out_w, out_h, seconds or 1.0)
    return ["-f", "lavfi", "-i", spec], False


# Where in the video to take the preview frame from. Sampled across the middle
# of the film, skipping the very start and end, which are the two places most
# likely to be a black frame or a title card.
MOMENTS = (0.12, 0.24, 0.36, 0.48, 0.60, 0.72, 0.84)
# {video: (second, face centre 0-1)}. Worked out once per file.
_best = {}
# The engine answers every preview on its own thread, and a gallery asks for
# eighteen at once. Without this they all miss the cache in the same instant and
# each runs its own seven face detections on the same file: measured at roughly
# four seconds of work, times eighteen, for one answer. The lock makes the first
# one do the pass and the other seventeen wait a moment and read it.
_best_lock = threading.Lock()


def _grab_fast(video, at, width=640):
    """One frame as JPEG bytes, seeking instead of decoding up to it.

    vision.grab() reads the file through from the start on purpose, because that
    is faster when a job needs dozens of frames. Here exactly one frame is wanted
    and it can be nine minutes in, and reading nine minutes of video to draw a
    thumbnail took 38 seconds per preview when this was measured. Putting -ss in
    front of -i makes ffmpeg jump to the nearest keyframe instead, which is a
    tenth of a second and plenty accurate for a preview.
    """
    exe = ffmpeg()
    if not exe:
        return None
    p = subprocess.run(
        [exe, "-hide_banner", "-loglevel", "error", "-nostdin",
         "-ss", "%.2f" % at, "-i", video, "-frames:v", "1",
         "-vf", "scale=%d:-2" % width, "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
        creationflags=NO_WINDOW, capture_output=True, timeout=60)
    return p.stdout or None


def _duration(video):
    try:
        import av
        c = av.open(video)
        d = float(c.duration or 0) / 1000000.0
        c.close()
        return d
    except Exception:
        return 0.0


def best_moment(video):
    """(second, face centre) of the frame that best shows a person.

    Without this a preview is whatever sits at a fixed timestamp, and on real
    footage that is a pair of shoes as often as it is the speaker. Both answers
    come out of the same pass and are cached per file, because the crop preview
    needs the horizontal position and asking for it separately meant decoding the
    video a second time.
    """
    if not (video and os.path.isfile(video)):
        return 1.0, 0.5
    if video in _best:
        return _best[video]
    with _best_lock:
        if video in _best:          # otro hilo lo calculo mientras esperabamos
            return _best[video]
        return _scan_moments(video)


def _scan_moments(video):
    """The pass itself. Only ever called with _best_lock held."""
    at, fx = 1.0, 0.5
    try:
        import faces
        import io as _io
        from PIL import Image
        dur = _duration(video)
        if dur > 0 and faces.available():
            times = [round(dur * f, 2) for f in MOMENTS]
            best_area = 0.0
            for t in times:
                jpeg = _grab_fast(video, t, width=faces.SIDE)
                if not jpeg:
                    continue
                face = faces.main_face(faces.detect(Image.open(_io.BytesIO(jpeg))))
                if face and face["w"] * face["h"] > best_area:
                    best_area = face["w"] * face["h"]
                    at, fx = t, face["x"] + face["w"] / 2
            if not best_area and times:
                at = times[len(times) // 2]   # sin caras, al menos no el segundo 1
    except Exception:
        pass
    _best[video] = (at, fx)
    return at, fx


def _face_x(video, at):
    """Where the crop would be aimed for this frame, without decoding it twice."""
    if not (video and os.path.isfile(video)):
        return 0.5
    cached_at, cached_fx = best_moment(video)
    if abs(cached_at - at) < 0.05:
        return cached_fx
    try:
        import faces
        import io as _io
        from PIL import Image
        jpeg = _grab_fast(video, at, width=faces.SIDE)
        if not jpeg:
            return 0.5
        face = faces.main_face(faces.detect(Image.open(_io.BytesIO(jpeg))))
        return (face["x"] + face["w"] / 2) if face else 0.5
    except Exception:
        return 0.5


# --------------------------------------------------------------------------- #
# The three kinds
# --------------------------------------------------------------------------- #
def card_still(kind, ratio="source", video="", lang="es",
               width=1920, height=1080, at=1.0):
    """Una foto de un rotulo o una chapa, hecha por el renderizador de verdad.

    Sin recorte a la banda del subtitulo a proposito: lo que hay que ver de un
    rotulo es DONDE se pone en el cuadro, y la banda esconde justo eso.
    """
    import overlays
    p = overlays.as_preset(kind)
    if not p:
        raise ValueError("'%s' no es un efecto con texto" % kind)
    muestra = {"es": {"rotulo": "Munir Torres", "chapa": "NUEVO"},
               "en": {"rotulo": "Your name here", "chapa": "NEW"}}
    texto = muestra.get(lang, muestra["es"]).get(kind, "Vidorq")
    return style_still(kind, ratio, video, lang, None, width, height, at,
                       band=False, p=p, text=texto)


def style_still(preset, ratio="source", video="", lang="es", anim=None,
                width=1920, height=1080, at=1.0, band=False, p=None, text=None):
    """A PNG of one caption look, burned in by the real subtitle renderer.

    `p` y `text` son para lo que NO es un estilo de subtitulo (un rotulo, una
    chapa): el mismo renderizador, otro preset y otra frase de muestra. El resto
    del camino es identico, que es justo la razon de no escribir una segunda
    funcion casi igual.
    """
    out_w, out_h, crop_w, crop_h = _shape(ratio, width, height)
    dest = CACHE / ("style_%s.png" % _key(preset, anim or "", ratio, video, lang,
                                          at, out_w, out_h, PREVIEW_LONG,
                                          _band_key(band), text or "", "still2"))
    if dest.exists():
        return dest
    exe = ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg no esta instalado")
    CACHE.mkdir(parents=True, exist_ok=True)
    # Unique per call, not per output. Two threads asked for the same preview
    # at the same time would otherwise share one scratch folder, and the first
    # to finish would delete it from under the second.
    work = CACHE / ("tmp_%s_%s" % (dest.stem[:24], uuid.uuid4().hex[:8]))
    work.mkdir(parents=True, exist_ok=True)
    try:
        # Named s.ass and run from its own folder: libass resolves the path
        # relative to the working directory and a Windows path with a colon in
        # it inside a filter chain is a fight nobody wins.
        # `still=True`: sin entrada. Es una foto, y el fotograma que se saca es
        # el primero, que en un estilo con fundido de entrada es justo el
        # instante en el que no se ve nada. Medido: cinco de diez baldosas
        # salian vacias.
        trozo = _chunk(lang, 2.0)
        if text:
            trozo = {"start": 0.0, "end": 2.0, "text": text,
                     "words": [{"w": text, "s": 0.0, "e": 2.0}]}
        cap.to_ass(work / "s.ass", [trozo], 0.0, 2.0,
                   out_w, out_h, preset, anim, still=True, p=p)
        src, real = _source_args(video, at, out_w, out_h)
        vf = _crop_chain(width, height, out_w, out_h, crop_w, crop_h,
                         _face_x(video, at)) if real else []
        # The band crop goes AFTER the subtitles filter, never before: libass
        # places a caption relative to the frame it is handed, so cropping first
        # would move the caption instead of framing it.
        vf += ["subtitles=s.ass"]
        if band:
            vf.append(_band(out_w, out_h))
        vf.append(_fit(out_w, out_h))
        # ffmpeg runs inside `work` so that s.ass resolves; the output is written
        # there too and then moved, because a half written PNG in the cache would
        # be served forever.
        tmp_out = work / "out.png"
        subprocess.run(
            [exe, "-hide_banner", "-loglevel", "error", "-nostdin"] + src +
            ["-frames:v", "1", "-vf", ",".join(vf), "-y", "out.png"],
            cwd=str(work), creationflags=NO_WINDOW, capture_output=True, timeout=90, check=True)
        shutil.move(str(tmp_out), str(dest))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return dest


def anim_loop(anim, preset=cap.DEFAULT_PRESET, ratio="source", video="",
              lang="es", width=1920, height=1080, at=1.0, band=False):
    """An animated WebP of one entrance, because motion needs motion."""
    out_w, out_h, crop_w, crop_h = _shape(ratio, width, height)
    dest = CACHE / ("anim_%s.webp" % _key(anim, preset, ratio, video, lang, at,
                                          out_w, out_h, PREVIEW_LONG,
                                          _band_key(band)))
    if dest.exists():
        return dest
    exe = ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg no esta instalado")
    CACHE.mkdir(parents=True, exist_ok=True)
    # Unique per call, not per output. Two threads asked for the same preview
    # at the same time would otherwise share one scratch folder, and the first
    # to finish would delete it from under the second.
    work = CACHE / ("tmp_%s_%s" % (dest.stem[:24], uuid.uuid4().hex[:8]))
    work.mkdir(parents=True, exist_ok=True)
    try:
        cap.to_ass(work / "s.ass", [_chunk(lang, LOOP_SECONDS)], 0.0,
                   LOOP_SECONDS, out_w, out_h, preset, anim)
        src, real = _source_args(video, at, out_w, out_h, LOOP_SECONDS)
        vf = _crop_chain(width, height, out_w, out_h, crop_w, crop_h,
                         _face_x(video, at)) if real else []
        vf += ["subtitles=s.ass", "fps=%d" % LOOP_FPS]
        if band:
            vf.append(_band(out_w, out_h))
        vf.append(_fit(out_w, out_h))
        subprocess.run(
            [exe, "-hide_banner", "-loglevel", "error", "-nostdin"] + src +
            ["-t", "%.2f" % LOOP_SECONDS, "-vf", ",".join(vf),
             "-loop", "0", "-quality", "70", "-y", "out.webp"],
            cwd=str(work), creationflags=NO_WINDOW, capture_output=True, timeout=120, check=True)
        shutil.move(str(work / "out.webp"), str(dest))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return dest


def look_still(name, ratio="source", video="", width=1920, height=1080, at=1.0,
               band=False):
    """Un fotograma con el filtro de color puesto, hecho con el mismo LUT.

    Sin subtitulos encima a proposito: aqui se juzga el color, y una linea de
    texto blanca en medio es justo lo que impide ver que le ha pasado a la piel.
    """
    out_w, out_h, crop_w, crop_h = _shape(ratio, width, height)
    dest = CACHE / ("look_%s.png" % _key(name, ratio, video, at, out_w, out_h,
                                         PREVIEW_LONG, _band_key(band)))
    if dest.exists():
        return dest
    exe = ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg no esta instalado")
    CACHE.mkdir(parents=True, exist_ok=True)
    src, real = _source_args(video, at, out_w, out_h)
    vf = _crop_chain(width, height, out_w, out_h, crop_w, crop_h,
                     _face_x(video, at)) if real else []
    look_vf = looks.ffmpeg_filter(name)
    if look_vf:
        vf.append(look_vf)
    if band:
        vf.append(_band(out_w, out_h))
    vf.append(_fit(out_w, out_h))
    tmp = dest.with_suffix(".part%s.png" % uuid.uuid4().hex[:8])
    subprocess.run(
        [exe, "-hide_banner", "-loglevel", "error", "-nostdin"] + src +
        ["-frames:v", "1", "-vf", ",".join(vf), "-y", str(tmp)],
        creationflags=NO_WINDOW, capture_output=True, timeout=90, check=True)
    shutil.move(str(tmp), str(dest))
    return dest


def ratio_still(ratio, video="", width=1920, height=1080, at=1.0):
    """A PNG of the real crop for one output shape, aimed by the face detector."""
    out_w, out_h, crop_w, crop_h = _shape(ratio, width, height)
    fx = _face_x(video, at)
    dest = CACHE / ("ratio_%s.png" % _key(ratio, video, at, out_w, out_h,
                                          round(fx, 3), PREVIEW_LONG))
    if dest.exists():
        return dest
    exe = ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg no esta instalado")
    CACHE.mkdir(parents=True, exist_ok=True)
    src, real = _source_args(video, at, out_w, out_h)
    vf = _crop_chain(width, height, out_w, out_h, crop_w, crop_h, fx) if real else []
    vf.append(_fit(out_w, out_h))
    tmp = dest.with_suffix(".part%s.png" % uuid.uuid4().hex[:8])
    subprocess.run(
        [exe, "-hide_banner", "-loglevel", "error", "-nostdin"] + src +
        ["-frames:v", "1", "-vf", ",".join(vf), "-y", str(tmp)],
        creationflags=NO_WINDOW, capture_output=True, timeout=90, check=True)
    shutil.move(str(tmp), str(dest))
    return dest


# Los dos momentos del video con los que se arma una transicion: el plano que
# se va y el que entra. Separados de verdad, porque dos fotogramas contiguos se
# parecen tanto que una disolvencia entre ellos no se ve.
# Lo mas separados que se puede sin caer en la cabecera ni en el cierre, que
# son los dos sitios donde es mas probable encontrar un negro o una careta. Y
# cuanto mas separados, mas probable es que sean dos PLANOS distintos, que es
# lo unico que hace legible el borde de un barrido: entre dos fotogramas del
# mismo plano continuo, la union del barrido no se ve, y no porque este mal.
TRANS_AT = (0.18, 0.82)


def transition_still(kind, ratio="source", video="", width=1920, height=1080,
                     at=1.0):
    """Una transicion congelada por la mitad, sobre TU metraje.

    La pestaña enseñaba seis rectangulos vacios con una etiqueta flotando en
    medio, que es justo lo que esta galeria existe para no hacer: un nombre no
    es una eleccion. Una transicion es movimiento y no cabe entera en una foto,
    pero su MITAD si dice lo que hace, que es lo que hay que decidir: si mezcla
    los dos planos, si pasa por negro, o si uno empuja al otro.

    Se hace con ffmpeg y con el mismo recorte que el render, como todo lo demas
    de este modulo, para que la foto no pueda mentir sobre el resultado.
    """
    out_w, out_h, crop_w, crop_h = _shape(ratio, width, height)
    dest = CACHE / ("tr_%s.png" % _key(kind, ratio, video, out_w, out_h,
                                       PREVIEW_LONG, TRANS_AT))
    if dest.exists():
        return dest
    exe = ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg no esta instalado")
    CACHE.mkdir(parents=True, exist_ok=True)

    dur = _duration(video) if video else 0.0
    fx = _face_x(video, at) if video else 0.5
    recorte = _crop_chain(width, height, out_w, out_h, crop_w, crop_h, fx)

    def entrada(frac):
        cuando = round(dur * frac, 2) if dur > 2 else at
        return _source_args(video, cuando, out_w, out_h)

    src_a, real = entrada(TRANS_AT[0])
    cadena = (recorte if real else []) + [_fit(out_w, out_h)]
    dos = kind in ("dissolve", "wipe", "slide")
    args = list(src_a)
    if dos:
        args += list(entrada(TRANS_AT[1])[0])

    def rama(indice, nombre):
        # La etiqueta va PEGADA al primer filtro. Con una coma en medio ffmpeg
        # lee un filtro vacio y contesta "No such filter: ''".
        return "[%d:v]%s[%s]" % (indice, ",".join(cadena) or "null", nombre)

    filtro = [rama(0, "a")]
    if dos:
        filtro.append(rama(1, "b"))

    # La mitad de cada transicion, dicha en filtros.
    if kind == "dissolve":
        filtro.append("[a][b]blend=all_mode=average[out]")
    elif kind == "dip":
        # A oscuras pero no negro del todo: el negro puro no enseña nada, y lo
        # que hay que entender es que el plano se APAGA.
        filtro.append("[a]drawbox=color=black@0.62:t=fill[out]")
    elif kind == "white":
        filtro.append("[a]drawbox=color=white@0.62:t=fill[out]")
    elif kind == "zoom":
        filtro.append("[a]scale=iw*1.35:ih*1.35,crop=iw/1.35:ih/1.35[out]")
    elif kind == "wipe":
        # Corte limpio por el medio: cada plano enseña su propio centro.
        filtro.append("[b]crop=iw/2:ih:iw/2:0[br]")
        filtro.append("[a][br]overlay=W/2:0[out]")
    elif kind == "slide":
        # Uno empuja al otro, asi que lo que se ve de cada uno es el borde por
        # el que se tocan, no su centro. Por eso no es la misma foto que wipe.
        filtro.append("[a]crop=iw/2:ih:iw/2:0[ar]")
        filtro.append("[b]crop=iw/2:ih:0:0[bl]")
        filtro.append("[ar][bl]hstack=inputs=2[out]")
    else:
        filtro.append("[a]null[out]")

    tmp = dest.with_suffix(".part%s.png" % uuid.uuid4().hex[:8])
    subprocess.run(
        [exe, "-hide_banner", "-loglevel", "error", "-nostdin"] + args +
        ["-filter_complex", ";".join(filtro), "-map", "[out]",
         "-frames:v", "1", "-y", str(tmp)],
        creationflags=NO_WINDOW, capture_output=True, timeout=90, check=True)
    shutil.move(str(tmp), str(dest))
    return dest


def clear():
    """Throw the cache away. The previews rebuild themselves on demand."""
    shutil.rmtree(CACHE, ignore_errors=True)
