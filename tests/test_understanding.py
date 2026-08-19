"""What Vidorq understands from a sentence, pinned down.

No model, no network, no video: this is the layer that reads the words literally
(`director.from_words`) and the one that decides what to ask about
(`director.vague`, `director.needs_where`). It runs in milliseconds, which is the
point - it can run on every change.

Why this file exists at all: every one of these lines is a bug that shipped. The
rules are regular expressions over Spanish, they overlap, and the order between
them matters, so a rule added for one sentence quietly breaks another. Twice the
same class of bug came back:

  "quita los subtitulos"      turned captions ON, because the negative rule only
                              knew "sin" and "no" and the positive one just
                              looked for the word.
  "haz un zoom"               set the caption ENTRANCE to zoom instead of moving
                              the camera, because "zoom" is the same word for two
                              different things.

Run it:  python tests/test_understanding.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skill" / "helpers"))

import director  # noqa: E402

# ---------------------------------------------------------------------------
# What the words say outright. Each case is (sentence, settings it must state).
# A key that is absent must stay absent: stating something nobody asked for is
# the same bug as missing something they did.
# ---------------------------------------------------------------------------
WORDS = [
    # The frame
    ("ponlo en vertical", {"ratio": "vertical"}),
    ("hazlo para tiktok", {"ratio": "vertical"}),
    ("ponlo cuadrado", {"ratio": "square"}),
    ("en 16:9", {"ratio": "wide"}),
    ("recortalo a vertical", {"ratio": "vertical"}),

    # Captions on, and OFF. The off case is the one that shipped broken.
    ("ponle subtitulos", {"captions": True}),
    ("quita los subtitulos", {"captions": False}),
    ("quitar los subtitulos", {"captions": False}),
    ("sin subtitulos", {"captions": False}),
    ("fuera los subtitulos", {"captions": False}),
    ("borra los subtitulos", {"captions": False}),
    ("elimina los captions", {"captions": False}),

    # The camera zoom is NOT the caption entrance, even though it is the same
    # word. It only counts as an entrance when the sentence talks about text.
    ("haz un zoom", {}),
    ("haz un zoom en el segundo 11", {}),
    ("acercate en el segundo 5", {}),
    ("subtitulos con zoom", {"captions": True, "captionAnim": "zoom"}),
    ("pon la animacion de zoom en los subtitulos",
     {"captions": True, "captionAnim": "zoom"}),

    # The impact shake, and its negative, which has to win over the positive.
    ("ponle temblor de impacto", {"shake": True}),
    ("ponle un golpe de camara", {"shake": True}),
    ("que tiemble en los cortes", {"shake": True}),
    ("quita el temblor", {"shake": False}),
    ("sin temblor", {"shake": False}),

    # How to cut
    ("haz un montaje de los mejores momentos", {"cuts": "montage"}),
    ("es un podcast, marca las preguntas", {"cuts": "podcast"}),
    ("quita los silencios", {"cuts": "clean"}),

    # Two things at once, because that is how people talk
    ("ponle temblor y ponlo en vertical", {"ratio": "vertical", "shake": True}),

    # And the colour filter, which must not eat "blanco y negro" as a dip
    ("ponlo en blanco y negro", {"look": "bn"}),
]

# ---------------------------------------------------------------------------
# Naming a category without saying which one. These have to be ASKED, not
# guessed: guessing is how "pon transiciones en cada corte" silently became a
# dissolve nobody chose.
# ---------------------------------------------------------------------------
VAGUE = [
    ("pon transiciones en cada corte", ["transition"]),
    ("ponle un filtro de color", ["look"]),
    ("ponle subtitulos", ["captionPreset"]),
    ("cambia la animacion de los subtitulos", ["captionAnim"]),
    ("cortar el video", ["cuts"]),
    ("cut the video", ["cuts"]),
    ("cambia los cortes", ["cuts"]),
    # Removing something is not a choice: it is already said.
    ("quita los subtitulos", []),
    ("quita las transiciones", []),
    # A button already pressed is the answer, not a new question. Without this
    # the same question came back forever, because "pick:transition=dip" has the
    # word "transition" in it.
    ("pick:transition=dip", []),
    ("pick:cuts=montage", []),
    # Stated outright: nothing to ask.
    ("ponlo en vertical", []),
    ("ponlo en blanco y negro", []),
    # "en los cortes" is WHERE something happens, not a request to change how it
    # cuts. Measured against a real video: this asked which cutting criterion
    # you wanted, which nobody had mentioned.
    ("ponle temblor en los cortes", []),
    ("pon un fundido en el corte", []),
    ("pon transiciones en cada corte", ["transition"]),
]

# ---------------------------------------------------------------------------
# A "cannot" that talks about something that WAS done, or about something that
# is being asked, is not a limit - it is a contradiction. Measured on a real
# 10.7 minute video: "hazme un resumen con los mejores momentos" switched the
# cut to montage and in the same breath said it could not make a summary.
# ---------------------------------------------------------------------------
ECHO = [
    ("hacer un resumen con los mejores momentos", {"cuts"}, True),
    ("ha pedido un filtro de color pero no dice cual", {"look"}, True),
    ("hacer un zoom en un momento concreto", {"cuts"}, False),
    ("subir el video a YouTube", {"cuts", "look"}, False),
    ("anadir musica epica", {"captions", "ratio"}, False),
    ("ponerlo en vertical", {"ratio"}, True),
    ("el temblor de impacto", {"shake"}, True),
]

# ---------------------------------------------------------------------------
# Asking for something that happens SOMEWHERE, without saying where. The answer
# is the list of spans, so the user points at one instead of reciting a second.
# ---------------------------------------------------------------------------
WHERE = [
    ("haz un zoom", True),
    ("acerca la camara", True),
    ("quita un trozo", True),
    ("quita un cacho", True),
    ("pon un cartel", True),
    # Already said where: do not ask.
    ("haz un zoom en el segundo 12", False),
    ("quita el trozo del minuto 3", False),
    ("pon un cartel al final", False),
    ("pon un rotulo cuando dice hola", False),
    ("quita un trozo del segundo 7 al 14", False),
    # Not about a place at all.
    ("ponlo en vertical", False),
    ("ponle temblor", False),
    ("pick:at=2", False),
]


def main():
    bad = []

    for sentence, want in WORDS:
        got = director.from_words(sentence)
        if got != want:
            bad.append("from_words(%r)\n     esperaba %s\n     devolvio %s"
                       % (sentence, want, got))

    for sentence, want in VAGUE:
        got = director.vague(sentence, director.decided(sentence))
        if sorted(got) != sorted(want):
            bad.append("vague(%r)\n     esperaba %s\n     devolvio %s"
                       % (sentence, want, got))

    for sentence, want in WHERE:
        got = director.needs_where(sentence)
        if got != want:
            bad.append("needs_where(%r) esperaba %s y devolvio %s"
                       % (sentence, want, got))

    # `_echoes` vive en el motor, que importa muchas mas cosas. Si no se puede
    # cargar (falta una dependencia del render, por ejemplo), se dice y se sigue
    # en vez de tumbar las otras 60 comprobaciones, que no dependen de el.
    echo_n = 0
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
        saved, sys.argv = sys.argv, ["test"]
        import server  # noqa: E402
        sys.argv = saved
        for text, keys, want in ECHO:
            echo_n += 1
            got = server._echoes(text, keys)
            if got != want:
                bad.append("_echoes(%r, %s) esperaba %s y devolvio %s"
                           % (text, keys, want, got))
    except Exception as e:
        print("(no pude probar _echoes: %s)" % str(e)[:70])

    total = len(WORDS) + len(VAGUE) + len(WHERE) + echo_n
    if bad:
        print("%d de %d casos MAL:\n" % (len(bad), total))
        for line in bad:
            print("  - %s" % line)
        return 1
    print("%d casos, todos bien." % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
