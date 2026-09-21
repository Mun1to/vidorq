"""Vidorq caption engine: one preset library, two renderers.

A caption preset is plain data. The same definition drives both outputs, so a
look chosen in the app is the same look in either backend:

  to_ass()   burned-in captions for the MP4 path (ffmpeg/libass)
  to_comp()  a Fusion composition for the DaVinci Resolve path

The Resolve path exists because of a workaround worth writing down. The
scripting API cannot set keyframes and cannot edit the inside of a Fusion node,
but a .comp file is just text, and `TimelineItem.ImportFusionComp()` swallows
whatever is in it - splines included. So Vidorq writes the animation into the
file instead of asking the API for it. Verified on Resolve 21.0.4.5 FREE:
imported splines come back out of ExportFusionComp intact and render.

Text+ parameters used here, measured against Resolve 21 by rendering them and
looking at the frame, not guessed from a forum:
    StyledText, Font, Style, Size            the text and its face
    Center {x, y}                            0-1, y counted from the bottom
    VerticalJustificationNew / Horizontal..  3 = centred
    TrackingSpacing                          letter spacing, 1.0 = normal
    ElementShape<n>                          what shading element n draws:
                                               0 = a copy of the glyphs
                                                   (+ Offset/Softness = shadow)
                                               1 = an outline hugging the glyphs
                                               2 = a box per character
                                               3 = a rounded plate per character,
                                                   which only welds into one plate
                                                   per line above ~0.5 thickness
    Red<n>/Green<n>/Blue<n>/Alpha<n>         its colour, Softness<n> 0-1 only
Element 1 draws in front, so the order here is fill, outline, shadow, plate.
"""
from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------------- #
# Presets
# --------------------------------------------------------------------------- #
# words       : how many words per caption chunk (0 = one chunk per sentence)
# max_chars   : split a chunk that would grow past this, even mid-count
# upper       : shout it
# font/style  : family plus face name as Fusion spells it
# size        : cap height as a fraction of frame height
# fill        : (r, g, b) 0-1
# outline     : (r, g, b, thickness) or None
# shadow      : (r, g, b, alpha, dx, dy) or None
# y           : 0-1 from the bottom of the frame
# anim        : the entrance this look ships with, an id from ANIMS below. The
#               app can override it, because a look and a movement are two
#               choices and bundling them was hiding half the options.
# glow        : (r, g, b, size, gain) halo behind the text, or None
# panel       : (r, g, b, alpha, padding) plate behind the line, or None
# word_fx     : None | "karaoke" (the MP4 paints the word being said)
# accent      : colour the word_fx paints with
# tracking    : letter spacing, in em
PRESETS = {
    "pop": {
        "label": {"es": "Pop", "en": "Pop"},
        "note": {"es": "Dos palabras en mayúsculas, muy gordas, con contorno negro. "
                       "El clásico de retención.",
                 "en": "Two words in caps, very bold, black outline. The retention classic."},
        "words": 2, "max_chars": 22, "upper": True,
        "font": "Arial", "style": "Black", "size": 0.115,
        "fill": (1.0, 1.0, 1.0), "outline": (0, 0, 0, 0.22),
        "shadow": (0, 0, 0, 0.7, 0.004, -0.006),
        "y": 0.20, "anim": "pop", "glow": None, "panel": None,
        "word_fx": None, "accent": (1.0, 0.84, 0.0), "tracking": 0.0,
    },
    "punch": {
        "label": {"es": "Punch", "en": "Punch"},
        "note": {"es": "Una palabra a la vez, amarilla sobre negro. Para cortes rápidos.",
                 "en": "One word at a time, yellow on black. For fast cuts."},
        "words": 1, "max_chars": 16, "upper": True,
        "font": "Arial", "style": "Black", "size": 0.145,
        "fill": (1.0, 0.84, 0.0), "outline": (0, 0, 0, 0.26),
        "shadow": (0, 0, 0, 0.75, 0.005, -0.007),
        "y": 0.22, "anim": "pop", "glow": None, "panel": None,
        "word_fx": None, "accent": (1.0, 1.0, 1.0), "tracking": 0.02,
    },
    "marker": {
        "label": {"es": "Marcador", "en": "Marker"},
        "note": {"es": "Cada palabra sobre un trazo de rotulador que se ajusta a ella. "
                       "En el MP4 pinta además la palabra que suena.",
                 "en": "Each word on a marker stroke that fits it. The MP4 also "
                       "paints the word being said."},
        "words": 2, "max_chars": 20, "upper": True,
        "font": "Arial", "style": "Black", "size": 0.088,
        "fill": (1.0, 1.0, 1.0), "outline": None, "shadow": None,
        "y": 0.19, "anim": "pop",
        "glow": None,
        "panel": (0.13, 0.80, 0.45, 1.0, 0.55),
        "word_fx": "karaoke", "accent": (1.0, 0.95, 0.30), "tracking": 0.0,
    },
    "bar": {
        "label": {"es": "Barra", "en": "Bar"},
        "note": {"es": "Texto sobre una barra de color que entra desde la izquierda.",
                 "en": "Text over a colour bar that slides in from the left."},
        "words": 3, "max_chars": 30, "upper": True,
        "font": "Arial", "style": "Bold", "size": 0.062,
        "fill": (1.0, 1.0, 1.0), "outline": None, "shadow": None,
        "y": 0.16, "anim": "rise",
        "glow": None,
        "panel": (0.86, 0.16, 0.10, 1.0, 0.55),
        "word_fx": None, "accent": (1.0, 1.0, 1.0), "tracking": 0.01,
    },
    "glass": {
        "label": {"es": "Cristal", "en": "Glass"},
        "note": {"es": "Panel oscuro translucido con esquinas redondeadas. Discreto y limpio.",
                 "en": "Translucent dark panel with rounded corners. Quiet and clean."},
        "words": 5, "max_chars": 38, "upper": False,
        "font": "Arial", "style": "Bold", "size": 0.052,
        "fill": (1.0, 1.0, 1.0), "outline": None,
        "shadow": (0, 0, 0, 0.45, 0.002, -0.003),
        "y": 0.15, "anim": "rise",
        "glow": None,
        "panel": (0.02, 0.02, 0.04, 0.60, 0.62),
        "word_fx": None, "accent": (0.45, 0.78, 1.0), "tracking": 0.0,
    },
    "minimal": {
        "label": {"es": "Minimal", "en": "Minimal"},
        "note": {"es": "Frase completa, fina y discreta. Para contenido más serio.",
                 "en": "Full sentence, thin and discreet. For more serious content."},
        "words": 0, "max_chars": 42, "upper": False,
        "font": "Arial", "style": "Regular", "size": 0.048,
        "fill": (1.0, 1.0, 1.0), "outline": None,
        "shadow": (0, 0, 0, 0.8, 0.002, -0.003),
        "y": 0.12, "anim": "fade", "glow": None, "panel": None,
        "word_fx": None, "accent": (1.0, 1.0, 1.0), "tracking": 0.0,
    },
    # Real halo, not a fat coloured outline pretending to be one: a Fusion Glow
    # node sits behind the text and gets tinted. Measured working in Free.
    "neon": {
        "label": {"es": "Neon", "en": "Neon"},
        "note": {"es": "Halo de verdad alrededor del texto, con el nodo Glow de Fusion. "
                       "Cian encendido sobre blanco.",
                 "en": "A real halo around the text, from Fusion's Glow node. Lit cyan "
                       "on white."},
        "words": 2, "max_chars": 20, "upper": True,
        "font": "Arial", "style": "Black", "size": 0.108,
        "fill": (1.0, 1.0, 1.0), "outline": (0, 0.35, 0.45, 0.10),
        "shadow": None,
        "y": 0.21, "anim": "ignite",
        "glow": (0.30, 0.90, 1.0, 20.0, 2.1),
        "panel": None,
        "word_fx": None, "accent": (0.2, 1.0, 0.9), "tracking": 0.01,
    },
    "ember": {
        "label": {"es": "Brasa", "en": "Ember"},
        "note": {"es": "Halo naranja cálido, como una luz detrás del texto. Menos grito "
                       "que el neón.",
                 "en": "Warm orange halo, like a light behind the text. Less shouty than "
                       "neon."},
        "words": 2, "max_chars": 22, "upper": True,
        "font": "Arial", "style": "Black", "size": 0.112,
        "fill": (1.0, 0.98, 0.94), "outline": (0.25, 0.08, 0.0, 0.12),
        "shadow": None,
        "y": 0.20, "anim": "pop",
        "glow": (1.0, 0.42, 0.08, 16.0, 1.5),
        "panel": None,
        "word_fx": None, "accent": (1.0, 0.8, 0.3), "tracking": 0.0,
    },
    "halo": {
        "label": {"es": "Halo", "en": "Halo"},
        "note": {"es": "Frase entera con un resplandor cálido detrás. Elegante, y entra "
                       "enfocándose.",
                 "en": "Full line with a warm bloom behind it. Elegant, and it focuses in."},
        "words": 0, "max_chars": 36, "upper": False,
        "font": "Arial", "style": "Bold", "size": 0.056,
        "fill": (1.0, 1.0, 1.0), "outline": None,
        # A white bloom around white text eats the letters, so this one leans on
        # a warm tint and a heavier shadow to stay readable at line length.
        "shadow": (0, 0, 0, 0.85, 0.003, -0.004),
        "y": 0.13, "anim": "focus",
        "glow": (1.0, 0.86, 0.52, 6.0, 1.2),
        "panel": None,
        "word_fx": None, "accent": (1.0, 1.0, 1.0), "tracking": 0.005,
    },
    # No typewriter here, and not for lack of trying: Text+ ignores its own
    # WriteOnStart/WriteOnEnd when a comp is imported, and libass renders a \k
    # span whatever its secondary colour says, so neither renderer can reveal a
    # line character by character. Both were measured, not assumed. What is left
    # is a good monospaced caption, so that is what this preset promises.
    "mono": {
        "label": {"es": "Mono", "en": "Mono"},
        "note": {"es": "Monoespaciada, sobria y con contorno fino. Para tutoriales "
                       "y cualquier cosa con código.",
                 "en": "Monospaced, sober, thin outline. For tutorials and anything "
                       "with code in it."},
        "words": 0, "max_chars": 40, "upper": False,
        "font": "Courier New", "style": "Bold", "size": 0.050,
        "fill": (1.0, 1.0, 1.0), "outline": (0, 0, 0, 0.14), "shadow": None,
        "y": 0.14, "anim": "fade", "glow": None, "panel": None,
        "word_fx": None, "accent": (1.0, 0.84, 0.0), "tracking": 0.0,
    },
}

DEFAULT_PRESET = "pop"

# --------------------------------------------------------------------------- #
# Animations
# --------------------------------------------------------------------------- #
# A look and a movement are two separate choices, the way CapCut splits style
# from animation, so any preset can be asked for with any of these.
#
# desde : the size the entrance starts at, as a multiple of the final size.
# curva : HOW it gets from there to 1.0, by name from curvas.CURVAS. This is the
#         part that decides whether it looks expensive or cheap. Before
#         2026-09-21 every entrance was three hand-placed keyframes joined by
#         straight lines, which is constant speed and a dead stop at each one:
#         measured frame by frame, the "pop" grew at +0.10 per frame four frames
#         running and then stopped cold. A curve accelerates and eases in.
# rebote: only for curva "muelle", how much it overshoots (0 = none).
# dur   : how long the entrance lasts, in beats (one beat is ~70 ms in the MP4).
# scale : hand keyframes, (fraction_of_the_entrance, multiplier). Only for moves
#         that are NOT an entrance from one size to another, like the throb,
#         which goes out and comes back. Everything else is generated from its
#         curve by `escala_de`, so the MP4 and Fusion can never disagree.
#
# Everything here is still a spline on a NUMBER input, which is the only kind of
# animation both renderers can deliver: a point input needs a path tool and Text+
# ignores its own WriteOn, so no slide and no typing in the Resolve path.
# fade  : True to bring every shading element up from transparent.
# blur  : starting blur in pixels, focused to 0 (Fusion Blur node / libass \blur).
# glow  : starting glow size multiplier, for looks that carry a halo.
ANIMS = {
    "pop": {
        "label": {"es": "Pop", "en": "Pop"},
        "note": {"es": "Entra pequeña, se pasa un poco y se asienta.",
                 "en": "Comes in small, overshoots a little, settles."},
        # Muelle con poco rebote: se pasa un 5% y vuelve, como algo que salta.
        "desde": 0.62, "curva": "muelle", "rebote": 0.30, "dur": 1.6,
        "fade": False, "blur": 0.0, "glow": 0.0,
    },
    "bounce": {
        "label": {"es": "Rebote", "en": "Bounce"},
        "note": {"es": "Muelle de tres tiempos, la de CapCut. La más enérgica.",
                 "en": "Three-beat spring, the CapCut one. The most energetic."},
        # El mismo muelle con mas rebote. Antes eran cuatro claves a mano que
        # llegaban al 114%; este llega al 110% pero oscila de verdad, con la
        # proporcion de un objeto fisico, en vez de tres rectas.
        "desde": 0.35, "curva": "muelle", "rebote": 0.55, "dur": 2.2,
        "fade": False, "blur": 0.0, "glow": 0.0,
    },
    "zoom": {
        "label": {"es": "Zoom", "en": "Zoom"},
        "note": {"es": "Entra grande y se cierra hasta su tamaño. Cinematográfica.",
                 "en": "Starts big and closes down to size. Cinematic."},
        "desde": 1.38, "curva": "suave", "dur": 1.4,
        "fade": True, "blur": 0.0, "glow": 0.0,
    },
    "rise": {
        "label": {"es": "Subida", "en": "Rise"},
        "note": {"es": "Crece un poco mientras aparece. Discreta.",
                 "en": "Grows slightly as it appears. Discreet."},
        "desde": 0.93, "curva": "suave", "dur": 1.4,
        "fade": True, "blur": 0.0, "glow": 0.0,
    },
    "fade": {
        "label": {"es": "Fundido", "en": "Fade"},
        "note": {"es": "Solo aparece, sin moverse. La más sobria.",
                 "en": "It just appears, no movement. The soberest."},
        "scale": [], "fade": True, "blur": 0.0, "glow": 0.0,
    },
    "throb": {
        "label": {"es": "Latido", "en": "Throb"},
        "note": {"es": "Da un golpe de tamaño en cada palabra, como un énfasis.",
                 "en": "Punches its size on every word, like an emphasis."},
        "scale": [(0.0, 1.0), (0.5, 1.09), (1.0, 0.99), (1.5, 1.04), (2.0, 1.0)],
        "fade": False, "blur": 0.0, "glow": 0.0,
    },
    "focus": {
        "label": {"es": "Enfoque", "en": "Focus"},
        "note": {"es": "Llega desenfocada y entra en foco. Es el efecto que la tienda "
                       "vende como premium.",
                 "en": "Arrives out of focus and snaps sharp. The effect the shop sells "
                       "as premium."},
        "desde": 1.04, "curva": "suave", "dur": 1.5,
        "fade": True, "blur": 15.0, "glow": 0.0,
    },
    "ignite": {
        "label": {"es": "Encendido", "en": "Ignite"},
        "note": {"es": "El halo se enciende de golpe y baja. Solo se nota en los estilos "
                       "con glow.",
                 "en": "The halo flares up and settles. Only shows on looks with a glow."},
        "desde": 0.72, "curva": "muelle", "rebote": 0.30, "dur": 1.6,
        "fade": False, "blur": 0.0, "glow": 2.4,
    },
    "none": {
        "label": {"es": "Ninguna", "en": "None"},
        "note": {"es": "Sin animación. El subtítulo está y ya.",
                 "en": "No animation. The caption is just there."},
        "scale": [], "fade": False, "blur": 0.0, "glow": 0.0,
    },
}

DEFAULT_ANIM = "pop"

# How wide one character of the caption font runs, as a fraction of the Text+
# Size. Measured off rendered frames: "MUCHISIMAS" came out 1076 px at Size
# 0.2440 in a 1080 wide frame, which is 0.41 per character. Used only as a
# ceiling, so being a little pessimistic is the safe direction.
CHAR_ADVANCE = 0.41
# How much of the frame width the longest line may take. The rest is breathing
# room for the glow, which is drawn outside the letters.
FIT = 0.94


def anim(name):
    """An animation by name, falling back to the preset's own rather than dying.

    Tambien acepta la animacion ya escrita, como diccionario. Es lo que usa la
    chapa: aterriza desde un tamaño que depende de cada tipo de rotulo, y crear
    un nombre en ANIMS por cada tamaño seria llenar el selector de animaciones
    que nadie puede elegir.
    """
    if isinstance(name, dict):
        return name
    return ANIMS.get(name)


def escala_de(a, pasos, curva=None):
    """Las claves de tamaño de una animacion, como `(momento_en_beats, tamaño)`.

    La UNICA fuente de las claves para los dos caminos de salida. Una entrada
    trae de donde sale (`desde`) y con que curva, y de ahi se generan tantas
    claves como pida quien las va a pintar: el MP4 una por fotograma, Fusion una
    por fotograma de la suya. Asi los dos se mueven con la misma curva y no puede
    pasar que uno se separe del otro, que es lo que pasa en cuanto hay dos listas
    de numeros para lo mismo.

    `curva` es la que ha elegido el usuario, si ha elegido: cambia COMO se mueve,
    no de donde sale. El rebote propio de la animacion solo se aplica con su
    propia curva, porque esta pensado para ella: el de "rebote" en otra curva no
    significa nada.

    Lo que no es una entrada de un tamaño a otro (el latido, que va y vuelve)
    sigue con sus claves a mano en `scale`, y se devuelven tal cual.
    """
    import curvas
    if a.get("desde") is not None:
        propia = a.get("curva") or curvas.POR_DEFECTO
        nombre = curva if curvas.conocida(curva) else propia
        rebote = a.get("rebote") if nombre == propia else None
        return curvas.claves(a["desde"], 1.0, nombre, a["dur"], pasos, rebote)
    return list(a.get("scale") or [])


def duracion_de(a):
    """Cuanto dura la entrada, en beats, sea de curva o de claves a mano."""
    if a.get("desde") is not None:
        return float(a.get("dur") or 1.0)
    esc = a.get("scale") or []
    return float(esc[-1][0]) if esc else 0.0


def anim_list(lang="es"):
    return [{"id": aid, "label": a["label"].get(lang, a["label"]["en"]),
             "note": a["note"].get(lang, a["note"]["en"])}
            for aid, a in ANIMS.items()]

# Enough of a chunk to read, but never a flash frame.
MIN_CHUNK_S = 0.30
# Room after the last word so the eye can finish the line.
CHUNK_TAIL_S = 0.12


def _propios():
    """Los estilos de subtitulo copiados de un video, o {} si no hay ninguno.

    Se importa aqui dentro y no arriba porque `galeria` necesita este modulo
    para construir uno, asi que arriba seria un import circular. Y no lanza
    nunca: una galeria rota no puede dejar sin subtitulos a quien solo usa los
    diez de la casa.
    """
    try:
        import galeria
        return galeria.de_tipo(galeria.CAPTION)
    except Exception:
        return {}


def known(name):
    """Si `name` es un estilo que se sabe pintar, sea de la casa o copiado.

    Existe porque media docena de sitios preguntaban `name in PRESETS`, y esa
    pregunta empezo a estar mal el dia que un estilo pudo no estar en PRESETS:
    un estilo copiado del video de alguien pasaba la comprobacion como falso y
    la edicion caia al de la casa sin decir nada.
    """
    return bool(name) and (name in PRESETS or name in _propios())


def preset(name):
    """A preset by name, falling back to the default rather than exploding.

    Un estilo copiado se guarda entero, asi que normalmente ya trae todos los
    campos. El relleno contra el de la casa es para los que se guardaron antes
    de que existiera algun campo nuevo: sin el, un estilo del mes pasado se
    queda sin `tracking` y el render revienta al buscarlo.
    """
    p = PRESETS.get(name)
    if p:
        return p
    propio = _propios().get(name)
    if propio:
        return {**PRESETS[DEFAULT_PRESET], **propio}
    return PRESETS[DEFAULT_PRESET]


def _ficha_de(pid, p, lang):
    return {"id": pid, "label": p["label"].get(lang, p["label"]["en"]),
            "note": p["note"].get(lang, p["note"]["en"]),
            "propio": bool(p.get("propio"))}


def preset_list(lang="es"):
    """What the app needs to draw the picker.

    Los copiados van DELANTE de los diez de la casa. Quien acaba de copiar un
    estilo de su video lo busca en el selector, y si sale el ultimo de trece da
    por hecho que no se guardo.
    """
    propios = [_ficha_de(pid, p, lang) for pid, p in _propios().items()]
    return propios + [_ficha_de(pid, p, lang) for pid, p in PRESETS.items()]


def anim_of():
    """La entrada que trae cada estilo, copiados incluidos.

    La ventana la necesita para enseñar "la suya" en el selector de animacion.
    Se arma de una sola lectura del disco: preguntarlo estilo por estilo abria
    el archivo trece veces para contestar una pantalla.
    """
    out = {pid: p["anim"] for pid, p in PRESETS.items()}
    for pid, p in _propios().items():
        out[pid] = p.get("anim") or PRESETS[DEFAULT_PRESET]["anim"]
    return out


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #
def _clean(word):
    return word.strip()


def line_ref(w, h):
    """The dimension a caption's size should be measured against.

    Sizes are written as a fraction of frame height, which silently assumes a
    wide frame: rotate to 9:16 and the same fraction runs off both edges.

    Two things share the correction, and getting the split wrong is visible. The
    line also gets fewer characters (see chars_for), so if the size took the
    whole correction as well the result is tiny text swimming in empty width -
    measured at 53 px on a 1080 wide frame, which is not a short caption, it is a
    footnote. Taking the square root leaves the text the same physical size it
    has in 16:9 and lets the shorter line do the rest, which is how a short
    actually looks. A 16:9 frame comes out exactly as it did before.
    """
    if not w or not h:
        return h
    return h * min(1.0, ((w / h) / (16.0 / 9.0)) ** 0.5)


def chars_for(limit, w, h):
    """How many characters actually fit on a line in this frame.

    A vertical frame is narrower, so it holds fewer of them even though the text
    is the same size relative to the picture.
    """
    if not w or not h:
        return limit
    return max(6, int(round(limit * min(1.0, (w / max(1.0, h)) / (16.0 / 9.0)) ** 0.5
                            * (1.0 if w >= h else 0.78))))


def build_chunks(transcript, name=DEFAULT_PRESET, w=0, h=0):
    """Group the transcript words into caption chunks in SOURCE time.

    Returns [{"start", "end", "text", "words": [{"w", "s", "e"}]}]. The word list
    survives the grouping because the karaoke look needs it; everything else
    just reads "text". Frame size is optional and only narrows the lines when the
    frame is not wide.
    """
    p = preset(name)
    per = int(p["words"])
    limit = chars_for(int(p["max_chars"]), w, h)
    out = []

    for seg in transcript.get("segments", []):
        words = [{"w": _clean(w["w"]), "s": float(w["s"]), "e": float(w["e"])}
                 for w in seg.get("words", []) if _clean(w["w"])]
        if not words:
            continue
        buf = []
        for w in words:
            nxt = " ".join(x["w"] for x in buf + [w])
            full = (per and len(buf) >= per) or len(nxt) > limit
            if full and buf:
                out.append(_chunk(buf, p))
                buf = []
            buf.append(w)
        if buf:
            out.append(_chunk(buf, p))

    # The tail added after the last word must not run into the next chunk, and a
    # chunk shorter than a blink is unreadable: it borrows from the gap in front
    # of it, never from its neighbour.
    for i, c in enumerate(out):
        ceiling = out[i + 1]["start"] if i + 1 < len(out) else None
        if ceiling is not None:
            c["end"] = min(c["end"], ceiling)
        if c["end"] - c["start"] < MIN_CHUNK_S:
            want = c["start"] + MIN_CHUNK_S
            c["end"] = want if ceiling is None else min(want, max(ceiling, c["end"]))
    return out


def _chunk(buf, p):
    text = " ".join(w["w"] for w in buf)
    return {
        "start": buf[0]["s"],
        "end": buf[-1]["e"] + CHUNK_TAIL_S,
        "text": text.upper() if p["upper"] else text,
        "words": [dict(w, w=(w["w"].upper() if p["upper"] else w["w"])) for w in buf],
    }


# --------------------------------------------------------------------------- #
# ASS output (burned-in MP4 path)
# --------------------------------------------------------------------------- #
def _ass_colour(rgb, alpha=1.0):
    """ASS wants &HAABBGGRR, and its alpha is inverted: 00 is opaque."""
    r, g, b = (max(0, min(255, int(round(c * 255)))) for c in rgb[:3])
    a = max(0, min(255, int(round((1.0 - alpha) * 255))))
    return "&H%02X%02X%02X%02X" % (a, b, g, r)


def ass_time(t):
    cs = max(0, int(round(t * 100)))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def to_ass(path, chunks, seg_start, seg_end, w, h, name=DEFAULT_PRESET,
           anim_name=None, still=False, p=None, curva=None):
    """Write one ASS file for one EDL segment, times shifted to segment-local.

    libass measures Fontsize as the GDI cell height, so the preset's cap-height
    fraction is scaled by 1.41 (Arial Black winAscent+winDescent / em) to land
    on the size the preset asks for.

    `p` takes a preset-shaped dict straight, for looks that are not caption
    styles and have no business in the gallery of caption styles - a lower
    third, say. Same trick and same reason as looks.cube(name, p=...).
    """
    p = p or preset(name)
    a = anim(anim_name) or anim(p["anim"]) or ANIMS[DEFAULT_ANIM]
    em = line_ref(w, h) * p["size"]
    fs = max(8, int(em * 1.411))
    x = w // 2
    y = int(h * (1.0 - p["y"]))
    fill = _ass_colour(p["fill"])
    bold = -1 if p["style"].lower() in ("black", "bold", "semibold", "heavy") else 0
    sh_x, sh_y, sh_depth = 0.0, 0.0, 0
    if p["shadow"]:
        _sr, _sg, _sb, _sa, dx, dy = p["shadow"]
        sh_depth = max(1, int(round(max(abs(dx), abs(dy)) * h)))
        sh_x, sh_y = dx, dy

    # In BorderStyle 3 libass fills the box with OutlineColour and treats Outline
    # as the padding, so the plate colour goes there - not in BackColour, which
    # is the shadow. Getting this backwards paints a black brick.
    if p["panel"]:
        pr, pg, pb, pa, pad = p["panel"]
        line_col = _ass_colour((pr, pg, pb), pa)
        out_w = max(2, int(em * pad * 0.5))
        border_style = 3
    else:
        line_col = _ass_colour(p["outline"]) if p["outline"] else _ass_colour((0, 0, 0))
        out_w = max(1, int(em * p["outline"][3])) if p["outline"] else 0
        border_style = 1
    # libass has no glow node, but a thick outline in the glow colour plus \blur
    # is the same picture. It replaces the outline rather than stacking on it,
    # because two borders cannot both be drawn.
    if p["glow"] and not p["panel"]:
        gr, gg, gb, gsize, _gain = p["glow"]
        line_col = _ass_colour((gr, gg, gb))
        out_w = max(out_w, int(round(em * 0.10 + gsize * 0.28)))
    back = _ass_colour(p["shadow"][:3], p["shadow"][3]) if p["shadow"] else _ass_colour((0, 0, 0))

    # The word looks come from libass itself: it sweeps a \k span from the
    # secondary colour to the primary one. So karaoke puts the accent in
    # primary and the base colour in secondary, and the typewriter makes
    # secondary invisible, which reveals each word as its span arrives.
    fx = p["word_fx"]
    if fx == "karaoke":
        primary, secondary = _ass_colour(p["accent"]), fill
    else:
        primary, secondary = fill, fill
    spacing = round(em * p["tracking"], 1)

    head = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: %d\nPlayResY: %d\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Vidorq,%s,%d,%s,%s,%s,%s,%d,0,0,0,100,100,%s,0,%d,%d,%d,8,0,0,0,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    ) % (w, h, p["font"], fs, primary, secondary, line_col, back, bold, spacing,
         border_style, out_w, sh_depth)

    lines = [head]
    for c in chunks:
        s = max(c["start"], seg_start) - seg_start
        e = min(c["end"], seg_end) - seg_start
        if e - s < 0.01:
            continue
        body = _ass_body(c, p)
        move = _ass_anim(p, a, x, y, sh_x, sh_y, h, still, curva)
        lines.append("Dialogue: 0,%s,%s,Vidorq,,0,0,0,,%s%s\n"
                     % (ass_time(s), ass_time(e), move, body))
    path.write_text("".join(lines), encoding="utf-8-sig")


def curvas_mod():
    """El modulo de curvas, cargado cuando hace falta y no al importar este.

    captions.py lo importa medio proyecto, muchas veces solo para leer un
    catalogo, y no hay por que cargar las curvas para eso.
    """
    import curvas
    return curvas


def _pasos(dur_beats, beat_ms):
    """Cuantas claves para una entrada: una por fotograma a 60, y nunca menos de 4.

    Una por fotograma porque asi cada fotograma que se ve tiene el valor EXACTO de
    la curva, y entre dos claves seguidas de 17 ms no hay nada que ver. Menos de
    cuatro ya no dibuja una curva, dibuja una esquina.
    """
    import math
    return max(4, int(math.ceil(dur_beats * beat_ms / curvas_mod().PASO_MS)))


def _por_tramos(claves, beat, fmt, valor):
    """Las claves como etiquetas ASS: el valor de partida y un `\\t` por tramo.

    Cada `\\t` va de su momento al siguiente y deja la propiedad en el valor de la
    clave. libass los encadena, asi que con un tramo por fotograma la curva sale
    entera. Los momentos se redondean a milisegundos enteros y nunca se repiten:
    dos tramos con el mismo inicio se pisan y libass se queda con el ultimo.
    """
    def f(v):
        r = valor(v)
        return fmt % (r if isinstance(r, tuple) else (r,))
    out = f(claves[0][1])
    prev = 0
    for at, v in claves[1:]:
        ms = max(prev + 1, int(round(at * beat)))
        out += "\\t(%d,%d,%s)" % (prev, ms, f(v))
        prev = ms
    return out


def _ass_anim(p, a, x, y, sh_x, sh_y, h, still=False, curva=None):
    """Override tags that place the line and give it the chosen entrance.

    The scale keyframes are the same numbers the Fusion side uses, replayed as
    \\t transforms in milliseconds so a look moves the same way in both outputs.
    One beat is 70 ms, which is about the two frames Fusion gets.

    With `still` the entrance is skipped and the line is drawn where it ENDS up.
    A single frame cannot show a movement, and asking for frame zero of a fade
    gets you a picture of nothing: measured, five of the ten gallery tiles came
    back empty for exactly that reason.
    """
    beat = 70
    tags = "\\pos(%d,%d)" % (x, y)
    if p["shadow"]:
        tags += "\\xshad%.1f\\yshad%.1f" % (sh_x * h, -sh_y * h)

    # libass has no glow node, so the halo is a blurred edge. Its size follows
    # the preset's glow size, and ignite flares it before it settles.
    if p["glow"]:
        base = 2.0 + p["glow"][3] * 0.20
        if still:
            tags += "\\blur%.1f" % base
        elif a["glow"] > 0:
            tags += "\\blur%.1f\\t(0,%d,\\blur%.1f)\\t(%d,%d,\\blur%.1f)" % (
                base * 0.3, beat, base * min(a["glow"], 2.0), beat, beat * 2, base)
        else:
            tags += "\\blur%.1f" % base
    if a["blur"] > 0 and not still:
        # El enfoque tambien sigue su curva: con una recta el texto se aclara a
        # ritmo fijo, y lo que se ve caro es que se enfoque de golpe y afine
        # despacio al final.
        tags += _por_tramos(curvas_mod().claves(a["blur"] * 0.6, 0.0, curva or "suave",
                                                1.6, _pasos(1.6, beat)),
                            beat, "\\blur%.1f", lambda v: v)

    esc = escala_de(a, _pasos(duracion_de(a), beat), curva)
    if esc:
        if still:
            # El tamaño en el que acaba, no en el que empieza: "pop" arranca al
            # 62% y una foto de eso enseña unas letras mas pequeñas de lo que
            # este estilo es en realidad.
            last = esc[-1][1] * 100
            tags += "\\fscx%.0f\\fscy%.0f" % (last, last)
        else:
            tags += _por_tramos(esc, beat, "\\fscx%.1f\\fscy%.1f",
                                lambda v: (v * 100, v * 100))
    if a["fade"] and not still:
        tags += "\\fad(%d,60)" % int(beat * 1.2)
    return "{%s}" % tags


def _ass_text(text):
    """El texto de una linea, sin que pueda dar ordenes al renderizador.

    En ASS, `{...}` no es texto: es un bloque de etiquetas. libass lee lo de
    dentro como instrucciones y lo que no reconoce lo TIRA, asi que una linea
    que contenga llaves o se mueve o se come un trozo de si misma.

    Medido el 20-ago-2026 sobre un cuadro de 640x360, con la misma linea puesta
    de tres formas:

        HOLA                  el texto sale en las filas 280-315 (abajo)
        {\\an8}HOLA            sale en las filas  48-83  (arriba del todo)
        \\{\\an8\\}HOLA          sale en las filas 280-319, con las llaves a la vista

    O sea que `\\{` y `\\}` neutralizan la etiqueta y ademas dibujan la llave, que
    es exactamente lo que hace falta.

    De donde viene el texto y por que importa: de la transcripcion, que es un
    dato ajeno (regla AL), y de lo que el usuario escribe en un rotulo. El
    segundo caso es el que se nota a diario: escribir "Sección {beta}" hacia
    desaparecer media frase sin decir nada.

    El `\\N` de ASS (salto de linea) se deja pasar a proposito: no esconde texto,
    y escaparlo obligaria a inventar una forma de escribir una contrabarra
    literal que ASS no tiene.
    """
    return (text or "").replace("{", "\\{").replace("}", "\\}")


def _ass_body(c, p):
    """The line itself, cut into \\kf spans when the preset wants word timing.

    The colours are already in the style, so all the body has to say is how long
    each word lasts, in centiseconds, and libass sweeps that word from the
    secondary colour to the primary one. This is the per-word behaviour the
    Resolve path cannot match, and it is why the same preset is worth more here.
    """
    # Un color FIJO por palabra manda sobre todo lo demas. Es lo que hace el
    # video de referencia: tres palabras blancas y una amarilla, sin que el
    # amarillo se mueva con el audio. Karaoke no es eso: karaoke pinta la
    # palabra que SUENA y va cambiando, asi que no se pueden hacer los dos a
    # la vez y gana el que se copio del video.
    if any(wd.get("color") for wd in c["words"]):
        return " ".join(
            ("{\\1c%s}%s" % (_ass_colour(wd["color"]), _ass_text(wd["w"])))
            if wd.get("color") else _ass_text(wd["w"])
            for wd in c["words"])
    if p["word_fx"] != "karaoke" or len(c["words"]) < 2:
        return _ass_text(c["text"])
    return " ".join("{\\kf%d}%s" % (max(1, int(round((wd["e"] - wd["s"]) * 100))),
                                        _ass_text(wd["w"]))
                    for wd in c["words"])


# --------------------------------------------------------------------------- #
# Fusion output (DaVinci Resolve path)
# --------------------------------------------------------------------------- #
def _fu_str(text):
    """Fusion reads Lua-ish strings, so quotes and newlines have to be escaped."""
    return (text.replace("\\", "\\\\").replace('"', '\\"')
                .replace("\n", "\\n").replace("\r", ""))


def _spline(name, keys):
    """A BezierSpline tool. This is the whole trick: the API cannot make
    keyframes, but a comp file can carry them and the import keeps them."""
    rows = ",\n".join("\t\t\t\t[%d] = { %.4f, Flags = { Linear = true } }" % (f, v)
                      for f, v in keys)
    return ("\t\t%s = BezierSpline {\n"
            "\t\t\tSplineColor = { Red = 250, Green = 180, Blue = 40 },\n"
            "\t\t\tNameSet = true,\n"
            "\t\t\tKeyFrames = {\n%s\n\t\t\t}\n\t\t},\n" % (name, rows))


# Un color por palabra dentro de UN SOLO Text+. Lo que faltaba no era la
# sintaxis, era el OPERADOR: el estilo por caracteres no es un campo del Text+,
# es un modificador aparte, `StyledTextCLS`, colgado de su entrada `StyledText`.
# Escrito en el propio Text+ Resolve lo guarda y lo IGNORA al pintar, que es lo
# que se midio dos veces; colgado del modificador, pinta. Medido el 2026-08-24
# sacando el fotograma de Resolve: "ROJO VERDE AZUL BLANCO" salio rojo, verde,
# azul y blanco. Detalle y como se descifro, en `docs/FUSION.md`.
#
# Cada fila es `{ codigo, primerCaracter, ultimoCaracter, Index = elemento,
# Value = v }`, con los dos caracteres INCLUSIVE y contando desde 0.
CLS_CANALES = (2401, 2402, 2403)   # rojo, verde, azul del color de relleno
# `Index` es el elemento del Text+ empezando en 0, o sea que `Index = n` es el
# `Red<n+1>` del nodo: 0 relleno, 1 contorno, 2 sombra. Se omite para el 0.
CLS_RELLENO = 0
# El nombre del modificador dentro del comp. Aparte del Text+, que se llama
# `Template`, porque un grupo y su nodo no pueden compartir nombre.
CLS_NODO = "Letras"


def _tramos(chunk):
    """(primerCaracter, ultimoCaracter, (r, g, b)) por palabra con color propio.

    Los indices son sobre `chunk["text"]`. Si el texto no se reconstruye juntando
    las palabras con un espacio, devuelve vacio: pintar el tramo equivocado es
    peor que no pintar, porque sale un fotograma que parece bien y no lo esta.
    """
    words = chunk.get("words") or []
    if not any(wd.get("color") for wd in words):
        return []
    if " ".join(wd["w"] for wd in words) != chunk.get("text", ""):
        return []
    fuera, i = [], 0
    for wd in words:
        if wd.get("color"):
            fuera.append((i, i + len(wd["w"]) - 1, wd["color"]))
        i += len(wd["w"]) + 1
    return fuera


def _cls_tool(text, tramos):
    """El modificador `StyledTextCLS` que lleva el texto y sus colores.

    Los tres canales se escriben SIEMPRE, tambien los que valen cero: el color
    de partida es el del relleno del preset, asi que una fila que falta deja ese
    canal como estaba y el rojo puro sale rosa. Un cero se escribe omitiendo
    `Value`, que es como lo escribe Blackmagic en sus propias plantillas.
    """
    filas = []
    for ini, fin, rgb in tramos:
        for codigo, v in zip(CLS_CANALES, rgb[:3]):
            filas.append("\t\t\t\t\t\t{ %d, %d, %d }" % (codigo, ini, fin) if not v
                         else "\t\t\t\t\t\t{ %d, %d, %d, Value = %.4f }"
                              % (codigo, ini, fin, v))
    return ('\t\t%s = StyledTextCLS {\n'
            '\t\t\tCtrlWZoom = false,\n'
            '\t\t\tInputs = {\n'
            '\t\t\t\tText = Input { Value = "%s", },\n'
            '\t\t\t\tCharacterLevelStyling = Input {\n'
            '\t\t\t\t\tValue = StyledText {\n'
            '\t\t\t\t\t\tArray = {\n%s\n\t\t\t\t\t\t},\n'
            '\t\t\t\t\t\tValue = ""\n'
            '\t\t\t\t\t},\n'
            '\t\t\t\t}\n'
            '\t\t\t},\n'
            '\t\t},\n'
            % (CLS_NODO, _fu_str(text), ",\n".join(filas)))


def _elements(p):
    """Which shading elements this preset lights up, front to back.

    Returns [(index, shape, (r, g, b), alpha, extra_input_lines)].
    """
    els = [(1, 0, p["fill"], 1.0, [])]
    if p["outline"]:
        r, g, b, th = p["outline"]
        els.append((2, 1, (r, g, b), 1.0, ["Thickness%d = Input { Value = %.4f, }," % (2, th)]))
    if p["shadow"]:
        r, g, b, a, dx, dy = p["shadow"]
        i = len(els) + 1
        els.append((i, 0, (r, g, b), a, [
            "Offset%d = Input { Value = { %.4f, %.4f }, }," % (i, dx * 12, dy * 12),
            "Softness%d = Input { Value = 0.35, }," % i,
        ]))
    if p["panel"]:
        r, g, b, a, th = p["panel"]
        i = len(els) + 1
        els.append((i, 3, (r, g, b), a, [
            "Thickness%d = Input { Value = %.4f, }," % (i, th),
            "Softness%d = Input { Value = 0.02, }," % i,
        ]))
    return els


def _anim_splines(a, dur, size, els, curva=None):
    """The chosen animation as splines over the clip's own frames.

    Returns (spline_tool_text, {input_name: spline_name}, extra) where extra
    carries the blur and glow splines the node chain needs. Frames are clamped
    to the clip length so a six-frame caption still animates instead of freezing
    on its opening pose, and no two keys ever land on the same frame.
    """
    # One beat of the entrance. Short captions get a short one so it finishes.
    beat = max(2, min(int(round(dur * 0.24)), 6))
    tools, wires, extra = "", {}, {}

    def keys(pairs, scale=1.0):
        out = []
        for at, val in pairs:
            f = int(round(at * beat))
            if out and f <= out[-1][0]:
                f = out[-1][0] + 1
            if f > dur - 1:
                if out:
                    break
                f = dur - 1
            out.append((f, val * scale))
        return out

    # Las claves salen de la misma curva que las del MP4 (`escala_de`), con una
    # por fotograma de la entrada: asi los dos caminos se mueven igual. Mas de
    # una por fotograma no sirve aqui, porque `keys` empuja las que chocan al
    # fotograma siguiente y alargaria la entrada.
    esc = escala_de(a, max(2, int(round(duracion_de(a) * beat))), curva)
    if esc:
        k = keys(esc, size)
        if len(k) > 1:
            tools += _spline("AnimSize", k)
            wires["Size"] = "AnimSize"
    if a["fade"]:
        # El fundido va en un Merge detras del texto, NO en los `Alpha<n>` del
        # Text+. Asi estuvo y no se veia: medido en Resolve componiendo sobre un
        # clip rojo, el fotograma 0 (alfa 0, o sea invisible) daba 41.31% de
        # pixeles blancos y el 20 daba 41.41%. O sea, ninguno. Y no era que la
        # comp estuviera congelada: la curva del TAMAÑO del mismo clip movia las
        # letras de 538 px a 921 y las asentaba en 869, exactamente como dice.
        # El `Blend` de un Merge si anima, y ademas funde el grupo entero de una
        # vez, que es lo que se queria al fundir todos los elementos.
        k = keys([(0.0, 0.0), (0.9, 1.0)])
        if len(k) > 1:
            tools += _spline("Fundido", k)
            extra["fade"] = "Fundido"
    if a["blur"] > 0:
        k = keys([(0.0, a["blur"]), (1.5, 0.0)])
        if len(k) > 1:
            tools += _spline("Focus", k)
            extra["blur"] = "Focus"
    if a["glow"] > 0:
        k = keys([(0.0, 0.0), (0.9, a["glow"]), (1.8, 1.0)])
        if len(k) > 1:
            tools += _spline("Ignite", k)
            extra["glow"] = "Ignite"
    return tools, wires, extra


# Arial no trae glifos chinos ni japoneses, y a diferencia de libass (el
# renderizador del MP4, que hace fallback de fuente solo cuando falta un
# glifo) el Text+ de Fusion NO sustituye nada: dibuja un simple trazo vacio.
# Medido el 20-ago-2026 en un timeline real: un subtitulo en chino salia como
# una rayita azul en vez del caracter. Windows trae estas dos de fabrica, asi
# que se cambia la fuente SOLO cuando el texto de ese trozo las necesita; el
# resto de idiomas sigue viendo la fuente de siempre.
#
# Cambiar solo la fuente no basta: los presets piden "Black" (Punch, Pop...) y
# ninguna de las dos CJK trae ese grosor instalado (medido con
# `FontFamily.IsStyleAvailable`: solo Regular y Bold). Pedirle a Fusion una
# combinacion fuente+grosor que no existe no cae al grosor mas cercano, tira
# la composicion entera: el render fallaba con "The Fusion composition...
# could not be processed successfully" desde el primerisimo cartel.
_KANA_RE = re.compile(r"[぀-ヿ]")
_HAN_RE = re.compile(r"[一-鿿㐀-䶿]")


def _font_for(text, fallback_font, fallback_style):
    """(fuente, grosor) a usar para este trozo de texto."""
    if _KANA_RE.search(text):
        return "Yu Gothic", ("Regular" if fallback_style == "Regular" else "Bold")
    if _HAN_RE.search(text):
        return "Microsoft YaHei", ("Regular" if fallback_style == "Regular" else "Bold")
    return fallback_font, fallback_style


def _text_inputs(p, chunk, w, h, dur, wires, size, y, els, tramos=()):
    """The Inputs block of the Text+ node: preset values plus the spline wires.

    Con `tramos`, el texto deja de estar en el nodo y pasa al modificador que lo
    colorea: la entrada `StyledText` se cablea a el en vez de llevar valor.
    """
    def wired(input_name, fallback):
        sp = wires.get(input_name)
        if sp:
            return '%s = Input { SourceOp = "%s", Source = "Value", },' % (input_name, sp)
        return fallback

    font, style = _font_for(chunk["text"], p["font"], p["style"])
    lines = [
        'GlobalOut = Input { Value = %d, },' % max(1, dur - 1),
        'Width = Input { Value = %d, },' % w,
        'Height = Input { Value = %d, },' % h,
        'UseFrameFormatSettings = Input { Value = 1, },',
        ('StyledText = Input { SourceOp = "%s", Source = "StyledText", },' % CLS_NODO
         if tramos else
         'StyledText = Input { Value = "%s", },' % _fu_str(chunk["text"])),
        'Font = Input { Value = "%s", },' % font,
        'Style = Input { Value = "%s", },' % style,
        'VerticalJustificationNew = Input { Value = 3, },',
        'HorizontalJustificationNew = Input { Value = 3, },',
        'Center = Input { Value = { 0.5, %.4f }, },' % y,
        wired("Size", 'Size = Input { Value = %.4f, },' % size),
    ]
    if p["tracking"]:
        lines.append('TrackingSpacing = Input { Value = %.4f, },' % (1.0 + p["tracking"] * 4))

    for idx, shape, (r, g, b), alpha, extra in els:
        if idx > 1:
            lines.append('Enabled%d = Input { Value = 1, },' % idx)
        lines.append('ElementShape%d = Input { Value = %d, },' % (idx, shape))
        lines.append('Red%d = Input { Value = %.4f, },' % (idx, r))
        lines.append('Green%d = Input { Value = %.4f, },' % (idx, g))
        lines.append('Blue%d = Input { Value = %.4f, },' % (idx, b))
        lines.append(wired("Alpha%d" % idx,
                           'Alpha%d = Input { Value = %.4f, },' % (idx, alpha)))
        lines += extra
    return "\n\t\t\t\t".join(x for x in lines if x)


def _fade_tool(src, spline, w, h, x):
    """Un Merge sobre nada, con el Blend animado: asi se funde el grupo entero.

    El fondo es un Background transparente, no el video: la comp no lleva
    MediaIn a proposito (asi se puede anidar encima de cualquier plano), y
    fundir contra transparencia es exactamente lo que hace falta.
    """
    return (
        '\t\tVacio = Background {\n'
        '\t\t\tInputs = {\n'
        '\t\t\t\tGlobalOut = Input { Value = 1000, },\n'
        '\t\t\t\tWidth = Input { Value = %d, },\n'
        '\t\t\t\tHeight = Input { Value = %d, },\n'
        '\t\t\t\tUseFrameFormatSettings = Input { Value = 1, },\n'
        '\t\t\t\tTopLeftAlpha = Input { Value = 0, },\n'
        '\t\t\t},\n'
        '\t\t\tViewInfo = OperatorInfo { Pos = { %d, 115 } },\n'
        '\t\t},\n'
        '\t\tMezcla = Merge {\n'
        '\t\t\tInputs = {\n'
        '\t\t\t\tBackground = Input { SourceOp = "Vacio", Source = "Output", },\n'
        '\t\t\t\tForeground = Input { SourceOp = "%s", Source = "Output", },\n'
        '\t\t\t\tBlend = Input { SourceOp = "%s", Source = "Value", },\n'
        '\t\t\t},\n'
        '\t\t\tViewInfo = OperatorInfo { Pos = { %d, 49.5 } },\n'
        '\t\t},\n'
        % (w, h, x, src, spline, x))


def _blur_tool(src, spline, x):
    """A Blur whose size is driven by a spline, so the text focuses in.

    LockXY keeps the two axes together, which is what reads as an out-of-focus
    lens rather than a smear.
    """
    return ('\t\tSoft = Blur {\n\t\t\tInputs = {\n'
            '\t\t\t\tInput = Input { SourceOp = "%s", Source = "Output", },\n'
            '\t\t\t\tLockXY = Input { Value = 1, },\n'
            '\t\t\t\tXBlurSize = Input { SourceOp = "%s", Source = "Value", },\n'
            '\t\t\t},\n'
            '\t\t\tViewInfo = OperatorInfo { Pos = { %d, 49.5 } },\n\t\t},\n'
            % (src, spline, x))


def _glow_tool(src, glow, spline, x, keep_edge=False):
    """A tinted Fusion Glow behind the text.

    Threshold keeps the halo off the darker parts so the glyphs stay crisp; a
    Gain much over 2 blows the letters out and the caption stops being readable.
    When a spline drives GlowSize it is a multiplier of the preset's size.

    `keep_edge` mixes the un-glowed image back in through Blend. A preset whose
    only edge is the glyph itself has nothing left once its own halo blooms over
    it: `halo` came out of Resolve as three white smudges, unreadable, and the
    node responsible was measured by rendering it without the Blur (still a
    smudge) and then without the Glow (sharp). Blend 0.35 was picked the same
    way, against 1.0 and 0.6, and it is the one that keeps the halo AND the
    letters. Presets with an outline do not need it: the dark rim survives the
    bloom, which is why `neon` and `ember` always read.
    """
    r, g, b, size, gain = glow
    lines = [
        'Input = Input { SourceOp = "%s", Source = "Output", },' % src,
        'Gain = Input { Value = %.3f, },' % gain,
        'Threshold = Input { Value = 0.15, },',
        'Blend = Input { Value = %.2f, },' % (0.35 if keep_edge else 1.0),
        'Red = Input { Value = %.4f, },' % r,
        'Green = Input { Value = %.4f, },' % g,
        'Blue = Input { Value = %.4f, },' % b,
    ]
    if spline:
        lines.append('GlowSize = Input { SourceOp = "%s", Source = "Value", },' % spline)
    else:
        lines.append('GlowSize = Input { Value = %.2f, },' % size)
    return ('\t\tShine = Glow {\n\t\t\tInputs = {\n\t\t\t\t%s\n\t\t\t},\n'
            '\t\t\tViewInfo = OperatorInfo { Pos = { %d, 49.5 } },\n\t\t},\n'
            % ("\n\t\t\t\t".join(lines), x))


def to_comp(path, chunk, w, h, dur, name=DEFAULT_PRESET, anim_name=None, curva=None):
    """Write the Fusion composition for one caption chunk.

    `dur` is the clip length in frames; the entrance is authored against it so a
    short caption gets a short entrance instead of one that never finishes.
    `anim_name` overrides the preset's own movement. The Saver named MediaOut1 is
    what makes the comp valid as a timeline title.
    """
    p = preset(name)
    a = anim(anim_name) or anim(p["anim"]) or ANIMS[DEFAULT_ANIM]
    # Text+ Size is a cell height, not a cap height, and it is a fraction of the
    # frame WIDTH, not of the height. That is not a guess: the same caption was
    # rendered in both shapes and measured, and it came out 0.0573 of the width
    # in a 16:9 frame and 0.0574 in a 9:16 one. The same number twice settles it.
    # Dividing by the height instead made every vertical caption 56% of its size,
    # which on a phone reads as a footnote under a video.
    # The constant makes a comp match the MP4 renderer, which is the reference
    # because libass wraps a long line and a Text+ does not: it just walks off
    # both edges. Same preset, same caption, both shapes, glyphs measured:
    # "VER TODOS" came out 895 px wide burned into the MP4 and 986 px in Fusion,
    # so Fusion draws 10.2% wider for the same nominal size, and 2.489/1.102
    # brings them together. Before this, a ten character line lost a letter off
    # each end of a vertical short.
    size = float(p["size"]) * 2.259 * (line_ref(w, h) / max(1.0, float(w)))
    # And a ceiling, because a Text+ still cannot wrap: the chunker caps a line
    # by CHARACTER count, and ten narrow letters are not ten wide ones. Measured
    # on the rendered frames, one character of this font advances about 0.41 of
    # the Size, so the longest line sets the largest size that fits. FIT leaves
    # a margin for the glow, which is drawn outside the glyphs.
    longest = max((len(line) for line in str(chunk["text"]).splitlines()), default=1)
    size = min(size, FIT / (CHAR_ADVANCE * max(1, longest)))
    y = float(p["y"])
    els = _elements(p)
    anim_tools, wires, extra = _anim_splines(a, dur, size, els, curva)
    tramos = _tramos(chunk)
    if tramos:
        anim_tools += _cls_tool(chunk["text"], tramos)

    # Text+ -> optional Blur -> optional Glow -> Saver. Kept as a chain so a
    # preset that wants neither ends up with exactly the two nodes it needs.
    chain, out, x = "", "Template", 220
    if extra.get("blur"):
        x += 165
        chain += _blur_tool(out, extra["blur"], x)
        out = "Soft"
    if p["glow"]:
        x += 165
        if extra.get("glow"):
            # The ignite spline is written as a multiplier, so it gets baked
            # against this preset's own glow size here.
            anim_tools = _rescale_spline(anim_tools, extra["glow"], p["glow"][3])
        chain += _glow_tool(out, p["glow"], extra.get("glow"), x,
                            keep_edge=not p["outline"])
        out = "Shine"
    if extra.get("fade"):
        x += 165
        chain += _fade_tool(out, extra["fade"], w, h, x)
        out = "Mezcla"

    comp = (
        'Composition {\n'
        '\tCurrentTime = 0,\n'
        '\tRenderRange = { 0, %d },\n'
        '\tGlobalRange = { 0, %d },\n'
        '\tCurrentID = 9,\n'
        '\tHiQ = true,\n'
        '\tCustomData = {\n'
        '\t\tTEMPLATE_ID = "Text+",\n'
        '\t\tVIDORQ_PRESET = "%s",\n'
        '\t\tVIDORQ_ANIM = "%s"\n'
        '\t},\n'
        '\tTools = {\n'
        '%s'
        '\t\tTemplate = TextPlus {\n'
        '\t\t\tInputs = {\n'
        '\t\t\t\t%s\n'
        '\t\t\t},\n'
        '\t\t\tViewInfo = OperatorInfo { Pos = { 220, 49.5 } },\n'
        '\t\t},\n'
        '%s'
        '\t\tMediaOut1 = Saver {\n'
        '\t\t\tInputs = {\n'
        '\t\t\t\tIndex = Input { Value = "0", },\n'
        '\t\t\t\tInput = Input { SourceOp = "%s", Source = "Output", },\n'
        '\t\t\t},\n'
        '\t\t\tViewInfo = OperatorInfo { Pos = { %d, 49.5 } },\n'
        '\t\t},\n'
        '\t},\n'
        '}\n'
        % (max(1, dur - 1), max(1, dur - 1), name,
           anim_name or p["anim"], anim_tools,
           _text_inputs(p, chunk, w, h, dur, wires, size, y, els, tramos),
           chain, out, x + 165)
    )
    path.write_text(comp, encoding="utf-8")
    return path


def _rescale_spline(tools, spline_name, factor):
    """Multiply one spline's values in place, for the glow-size multiplier."""
    out, inside = [], False
    for line in tools.splitlines(True):
        if line.strip().startswith("%s = BezierSpline" % spline_name):
            inside = True
        elif inside and line.strip() == "},":
            inside = False
        elif inside and "] = {" in line:
            head, rest = line.split("] = {", 1)
            val, tail = rest.split(",", 1)
            line = "%s] = { %.4f,%s" % (head, float(val) * factor, tail)
        out.append(line)
    return "".join(out)


# --------------------------------------------------------------------------- #
# Filler words (used by the cut engine, kept here with the language data)
# --------------------------------------------------------------------------- #
# Hesitation sounds only, on purpose. The tempting additions - bueno, pues, vale,
# entonces, esto, nada, tipo, like, so, actually - are ordinary words that happen
# to get used as filler, and cutting them by spelling alone butchers real
# sentences: "esto es lo que nadie te cuenta" would lose its subject. Deciding
# whether one of those is filler needs to read the sentence, which is the Pro
# mode's job, not a word list's. Multi-word filler ("o sea") is out for the same
# reason: it is only filler sometimes.
FILLERS = {
    "es": ("eh", "ehh", "ehhh", "em", "emm", "ehm", "mm", "mmm", "mmmm", "aha", "ajam"),
    "en": ("uh", "uhh", "uhhh", "um", "umm", "erm", "er", "mm", "mmm", "hmm", "uhm"),
}


def strip_accents(text):
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def is_filler(word, lang="es"):
    """True for a word that is noise on its own. Punctuation and case ignored."""
    bare = strip_accents(re.sub(r"[^\w\s]", "", word or "").strip().lower())
    return bool(bare) and bare in FILLERS.get(lang, FILLERS["es"])
