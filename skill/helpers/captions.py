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
# anim        : "pop" | "rise" | "fade" | None
# panel       : (r, g, b, alpha, padding) plate behind the line, or None
# word_fx     : None | "karaoke" (the MP4 paints the word being said)
# accent      : colour the word_fx paints with
# tracking    : letter spacing, in em
PRESETS = {
    "pop": {
        "label": {"es": "Pop", "en": "Pop"},
        "note": {"es": "Dos palabras en mayusculas, muy gordas, con contorno negro. "
                       "El clasico de retencion.",
                 "en": "Two words in caps, very bold, black outline. The retention classic."},
        "words": 2, "max_chars": 22, "upper": True,
        "font": "Arial", "style": "Black", "size": 0.115,
        "fill": (1.0, 1.0, 1.0), "outline": (0, 0, 0, 0.22),
        "shadow": (0, 0, 0, 0.7, 0.004, -0.006),
        "y": 0.20, "anim": "pop", "panel": None,
        "word_fx": None, "accent": (1.0, 0.84, 0.0), "tracking": 0.0,
    },
    "punch": {
        "label": {"es": "Punch", "en": "Punch"},
        "note": {"es": "Una palabra a la vez, amarilla sobre negro. Para cortes rapidos.",
                 "en": "One word at a time, yellow on black. For fast cuts."},
        "words": 1, "max_chars": 16, "upper": True,
        "font": "Arial", "style": "Black", "size": 0.145,
        "fill": (1.0, 0.84, 0.0), "outline": (0, 0, 0, 0.26),
        "shadow": (0, 0, 0, 0.75, 0.005, -0.007),
        "y": 0.22, "anim": "pop", "panel": None,
        "word_fx": None, "accent": (1.0, 1.0, 1.0), "tracking": 0.02,
    },
    "marker": {
        "label": {"es": "Marcador", "en": "Marker"},
        "note": {"es": "Cada palabra sobre un trazo de rotulador que se ajusta a ella. "
                       "En el MP4 pinta ademas la palabra que suena.",
                 "en": "Each word on a marker stroke that fits it. The MP4 also "
                       "paints the word being said."},
        "words": 2, "max_chars": 20, "upper": True,
        "font": "Arial", "style": "Black", "size": 0.088,
        "fill": (1.0, 1.0, 1.0), "outline": None, "shadow": None,
        "y": 0.19, "anim": "pop",
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
        "panel": (0.02, 0.02, 0.04, 0.60, 0.62),
        "word_fx": None, "accent": (0.45, 0.78, 1.0), "tracking": 0.0,
    },
    "minimal": {
        "label": {"es": "Minimal", "en": "Minimal"},
        "note": {"es": "Frase completa, fina y discreta. Para contenido mas serio.",
                 "en": "Full sentence, thin and discreet. For more serious content."},
        "words": 0, "max_chars": 42, "upper": False,
        "font": "Arial", "style": "Regular", "size": 0.048,
        "fill": (1.0, 1.0, 1.0), "outline": None,
        "shadow": (0, 0, 0, 0.8, 0.002, -0.003),
        "y": 0.12, "anim": "fade", "panel": None,
        "word_fx": None, "accent": (1.0, 1.0, 1.0), "tracking": 0.0,
    },
    "neon": {
        "label": {"es": "Neon", "en": "Neon"},
        "note": {"es": "Contorno de color encendido sobre texto blanco. Llama la atencion.",
                 "en": "Lit colour outline around white text. Loud on purpose."},
        "words": 2, "max_chars": 20, "upper": True,
        "font": "Arial", "style": "Black", "size": 0.105,
        "fill": (1.0, 1.0, 1.0), "outline": (0.65, 0.15, 1.0, 0.20),
        "shadow": (0.4, 0.0, 0.9, 0.85, 0.0, 0.0),
        "y": 0.21, "anim": "pop", "panel": None,
        "word_fx": None, "accent": (0.2, 1.0, 0.9), "tracking": 0.01,
    },
    # No typewriter here, and not for lack of trying: Text+ ignores its own
    # WriteOnStart/WriteOnEnd when a comp is imported, and libass renders a \k
    # span whatever its secondary colour says, so neither renderer can reveal a
    # line character by character. Both were measured, not assumed. What is left
    # is a good monospaced caption, so that is what this preset promises.
    "mono": {
        "label": {"es": "Mono", "en": "Mono"},
        "note": {"es": "Monoespaciada, sobria y con contorno fino. Para tutoriales "
                       "y cualquier cosa con codigo.",
                 "en": "Monospaced, sober, thin outline. For tutorials and anything "
                       "with code in it."},
        "words": 0, "max_chars": 40, "upper": False,
        "font": "Courier New", "style": "Bold", "size": 0.050,
        "fill": (1.0, 1.0, 1.0), "outline": (0, 0, 0, 0.14), "shadow": None,
        "y": 0.14, "anim": "fade", "panel": None,
        "word_fx": None, "accent": (1.0, 0.84, 0.0), "tracking": 0.0,
    },
}

DEFAULT_PRESET = "pop"

# Enough of a chunk to read, but never a flash frame.
MIN_CHUNK_S = 0.30
# Room after the last word so the eye can finish the line.
CHUNK_TAIL_S = 0.12


def preset(name):
    """A preset by name, falling back to the default rather than exploding."""
    return PRESETS.get(name) or PRESETS[DEFAULT_PRESET]


def preset_list(lang="es"):
    """What the app needs to draw the picker."""
    return [{"id": pid, "label": p["label"].get(lang, p["label"]["en"]),
             "note": p["note"].get(lang, p["note"]["en"])}
            for pid, p in PRESETS.items()]


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #
def _clean(word):
    return word.strip()


def build_chunks(transcript, name=DEFAULT_PRESET):
    """Group the transcript words into caption chunks in SOURCE time.

    Returns [{"start", "end", "text", "words": [{"w", "s", "e"}]}]. The word list
    survives the grouping because the karaoke look needs it; everything else
    just reads "text".
    """
    p = preset(name)
    per = int(p["words"])
    limit = int(p["max_chars"])
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


def to_ass(path, chunks, seg_start, seg_end, w, h, name=DEFAULT_PRESET):
    """Write one ASS file for one EDL segment, times shifted to segment-local.

    libass measures Fontsize as the GDI cell height, so the preset's cap-height
    fraction is scaled by 1.41 (Arial Black winAscent+winDescent / em) to land
    on the size the preset asks for.
    """
    p = preset(name)
    em = h * p["size"]
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
        move = _ass_anim(p, x, y, sh_x, sh_y, h)
        lines.append("Dialogue: 0,%s,%s,Vidorq,,0,0,0,,%s%s\n"
                     % (ass_time(s), ass_time(e), move, body))
    path.write_text("".join(lines), encoding="utf-8-sig")


def _ass_anim(p, x, y, sh_x, sh_y, h):
    """Override tags that place the line and give it its entrance."""
    tags = "\\pos(%d,%d)" % (x, y)
    if p["shadow"]:
        tags += "\\xshad%.1f\\yshad%.1f" % (sh_x * h, -sh_y * h)
    if p["anim"] == "pop":
        # 90 ms overshoot: 70 -> 106 -> 100 per cent.
        tags += "\\fscx70\\fscy70\\t(0,60,\\fscx106\\fscy106)\\t(60,110,\\fscx100\\fscy100)"
    elif p["anim"] == "rise":
        tags += "\\alpha&HFF&\\t(0,90,\\alpha&H00&)"
    elif p["anim"] == "fade":
        tags += "\\fad(80,60)"
    return "{%s}" % tags


def _ass_body(c, p):
    """The line itself, cut into \\kf spans when the preset wants word timing.

    The colours are already in the style, so all the body has to say is how long
    each word lasts, in centiseconds, and libass sweeps that word from the
    secondary colour to the primary one. This is the per-word behaviour the
    Resolve path cannot match, and it is why the same preset is worth more here.
    """
    if p["word_fx"] != "karaoke" or len(c["words"]) < 2:
        return c["text"]
    return " ".join("{\\kf%d}%s" % (max(1, int(round((wd["e"] - wd["s"]) * 100))), wd["w"])
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


def _anim_splines(p, dur, size, els):
    """Entrance animation as splines over the clip's own frames.

    Returns (spline_tool_text, {input_name: spline_name}). The frames are
    clamped to the clip length so a six-frame caption still animates instead of
    freezing on its opening pose. A fade has to move every element's alpha, not
    just the fill, or the shadow stays behind while the text arrives.
    """
    fast = max(2, min(int(round(dur * 0.34)), 7))
    tools, wires = "", {}
    anim = p["anim"]

    if anim == "pop":
        tools += _spline("PopSize", [(0, size * 0.62), (fast, size * 1.06),
                                     (min(dur - 1, fast + 3), size)])
        wires["Size"] = "PopSize"
    elif anim == "rise":
        tools += _spline("RiseSize", [(0, size * 0.93), (fast + 2, size)])
        wires["Size"] = "RiseSize"
    if anim in ("rise", "fade"):
        # Every enabled element fades, not just the fill, or the shadow sits
        # there waiting while the text arrives.
        for idx, _shape, _rgb, alpha, _extra in els:
            sp = "Fade%d" % idx
            tools += _spline(sp, [(0, 0.0), (max(2, fast - 1), alpha)])
            wires["Alpha%d" % idx] = sp
    return tools, wires


def _text_inputs(p, chunk, w, h, dur, wires, size, y, els):
    """The Inputs block of the Text+ node: preset values plus the spline wires."""
    def wired(input_name, fallback):
        sp = wires.get(input_name)
        if sp:
            return '%s = Input { SourceOp = "%s", Source = "Value", },' % (input_name, sp)
        return fallback

    lines = [
        'GlobalOut = Input { Value = %d, },' % max(1, dur - 1),
        'Width = Input { Value = %d, },' % w,
        'Height = Input { Value = %d, },' % h,
        'UseFrameFormatSettings = Input { Value = 1, },',
        'StyledText = Input { Value = "%s", },' % _fu_str(chunk["text"]),
        'Font = Input { Value = "%s", },' % p["font"],
        'Style = Input { Value = "%s", },' % p["style"],
        'VerticalJustificationNew = Input { Value = 3, },',
        'HorizontalJustificationNew = Input { Value = 3, },',
        'Center = Input { Value = { 0.5, %.4f }, },' % y,
        wired("Size", 'Size = Input { Value = %.4f, },' % size),
    ]
    if p["tracking"]:
        lines.append('TrackingSpacing = Input { Value = %.4f, },' % (1.0 + p["tracking"] * 4))
    if "WriteOnEnd" in wires:
        lines.append('WriteOnStart = Input { Value = 0, },')
        lines.append(wired("WriteOnEnd", ""))

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


def to_comp(path, chunk, w, h, dur, name=DEFAULT_PRESET):
    """Write the Fusion composition for one caption chunk.

    `dur` is the clip length in frames; the entrance is authored against it so a
    short caption gets a short entrance instead of one that never finishes. The
    Saver named MediaOut1 is what makes the comp valid as a timeline title.
    """
    p = preset(name)
    size = float(p["size"]) * 1.40  # Text+ Size is a cell height, not a cap height
    y = float(p["y"])
    els = _elements(p)
    anim_tools, wires = _anim_splines(p, dur, size, els)

    comp = (
        'Composition {\n'
        '\tCurrentTime = 0,\n'
        '\tRenderRange = { 0, %d },\n'
        '\tGlobalRange = { 0, %d },\n'
        '\tCurrentID = 9,\n'
        '\tHiQ = true,\n'
        '\tCustomData = {\n'
        '\t\tTEMPLATE_ID = "Text+",\n'
        '\t\tVIDORQ_PRESET = "%s"\n'
        '\t},\n'
        '\tTools = {\n'
        '%s'
        '\t\tTemplate = TextPlus {\n'
        '\t\t\tInputs = {\n'
        '\t\t\t\t%s\n'
        '\t\t\t},\n'
        '\t\t\tViewInfo = OperatorInfo { Pos = { 220, 49.5 } },\n'
        '\t\t},\n'
        '\t\tMediaOut1 = Saver {\n'
        '\t\t\tInputs = {\n'
        '\t\t\t\tIndex = Input { Value = "0", },\n'
        '\t\t\t\tInput = Input { SourceOp = "Template", Source = "Output", },\n'
        '\t\t\t},\n'
        '\t\t\tViewInfo = OperatorInfo { Pos = { 440, 49.5 } },\n'
        '\t\t},\n'
        '\t},\n'
        '}\n'
        % (max(1, dur - 1), max(1, dur - 1), name, anim_tools,
           _text_inputs(p, chunk, w, h, dur, wires, size, y, els))
    )
    path.write_text(comp, encoding="utf-8")
    return path


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
