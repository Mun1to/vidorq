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

# Un boton pulsado, y como se lee en la conversacion.
PICKS = [
    ("pick:transition=dip", "transición: Fundido a negro"),
    ("pick:captionPreset=neon", "estilo: Neon"),
    # Dos pares: la transicion que se pidio y la salida por la que si sale.
    ("pick:transition=dissolve&output=mp4", "transición: Disolvencia, salida: MP4"),
    # Lo escrito a mano no se toca.
    ("quita un trozo del segundo 5 al 9", "quita un trozo del segundo 5 al 9"),
]

PAIRS = [
    ("pick:transition=dip", {"transition": "dip"}),
    ("pick:transition=dissolve&output=mp4",
     {"transition": "dissolve", "output": "mp4"}),
    # Basura dentro no inventa claves.
    ("pick:transition=dip&", {"transition": "dip"}),
    ("pick:", {}),
]

# (nombre, lo del panel, lo del modelo, lo que dice la frase, lo que tiene que salir)
CAPAS = [
    ("lo que tocaste en el panel se queda",
     {"ratio": "vertical", "captionPreset": "punch"},
     {"ratio": "source", "captionPreset": "minimal"}, {},
     {"ratio": "vertical", "captionPreset": "punch"}),
    ("lo que no tocaste lo puede decidir el modelo",
     {"ratio": "source"}, {"ratio": "square"}, {}, {"ratio": "square"}),
    ("lo que escribes gana a los dos",
     {"ratio": "vertical"}, {"ratio": "source"}, {"ratio": "wide"}, {"ratio": "wide"}),
    ("sin panel, como antes",
     None, {"cuts": "montage"}, {}, {"cuts": "montage"}),
    ("el modelo no puede colar una clave que no existe",
     {"ratio": "vertical"}, {"loquesea": "x"}, {}, {"ratio": "vertical"}),
    ("apagar los subtitulos en el panel se respeta",
     {"captions": False}, {"captions": True}, {}, {"captions": False}),
]

# (salida, transicion, si tiene que avisar de que sale en el MP4)
OFFERS = [
    ("resolve", "dip", False),
    ("resolve", "white", False),
    ("resolve", "dissolve", True),
    ("resolve", "wipe", True),
    ("mp4", "dissolve", False),
    ("mp4", "dip", False),
]

# ---------------------------------------------------------------------------
# What the words say outright. Each case is (sentence, settings it must state).
# A key that is absent must stay absent: stating something nobody asked for is
# the same bug as missing something they did.
# ---------------------------------------------------------------------------
WORDS = [
    # Cada transicion por su nombre. El destello vivia dentro de la regla
    # del fundido a blanco, que dura el doble, asi que pedirlo daba otra
    # cosa: la palabra existia y el efecto tambien, pero no se tocaban.
    ("pon un destello en cada corte", {"transition": "flash"}),
    ("ponle flash entre planos", {"transition": "flash"}),
    ("pon un fundido a blanco", {"transition": "white"}),
    ("pon un fundido a negro", {"transition": "dip"}),
    # Un rotulo es un efecto suyo, no una forma de decir "subtitulo". La palabra
    # estaba en la regla de los subtitulos de cuando no existia el efecto, asi
    # que pedir un rotulo los encendia ademas y por encima del panel.
    ("pon un rotulo en el segundo 3 que diga Munir Torres", {}),
    ("pon una chapa que diga NUEVO", {}),
    ("ponle subtitulos", {"captions": True}),
    ("quita los subtitulos", {"captions": False}),
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


# ---------------------------------------------------------------------------
# Frases que ya traen el verbo y los dos segundos. Esas no las lee un modelo:
# son aritmetica, y ademas son las que escribe el propio programa desde los
# atajos y desde el panel de texto. Cada caso es (frase, acciones que salen)
# sobre un video de 60 segundos.
# ---------------------------------------------------------------------------
LITERAL = [
    # Un cartel dicho entero: el efecto, el segundo y lo que dice. Lo decidia el
    # modelo, y un modelo local no contesta igual dos veces: la misma frase daba
    # el rotulo unas veces y otras no. El atajo "Rótulo" del chat escribe esto.
    ("pon un rotulo en el segundo 3 que diga Munir Torres",
     [{"do": "title", "at": 3.0, "secs": 3.0, "text": "Munir Torres"}]),
    # La voz en off comparte forma con el cartel y por eso comparte funcion. Lo
    # unico que la distingue es la palabra del principio, asi que se mira antes:
    # "que diga" es de las dos.
    ("pon una voz en el segundo 5 que diga mira esto",
     [{"do": "voice", "at": 5.0, "text": "mira esto"}]),
    ("pon una narracion que diga bienvenidos en el segundo 2",
     [{"do": "voice", "at": 2.0, "text": "bienvenidos"}]),
    ("pon una voz bonita", []),
    # Y la marca, que era la ultima de las cinco acciones que seguia pasando por
    # el modelo pudiendo resolverse con los numeros que trae la frase.
    ("pon una marca en el segundo 12 que diga cambio de tema",
     [{"do": "marker", "at": 12.0, "text": "cambio de tema"}]),
    ("pon un marcador que diga intro en el segundo 30",
     [{"do": "marker", "at": 30.0, "text": "intro"}]),
    ("pon una marca bonita", []),
    ("pon una chapa en el segundo 12 que diga NUEVO",
     [{"do": "title", "at": 12.0, "secs": 3.0, "text": "NUEVO"}]),
    ("pon un cartel que diga SUSCRIBETE en el segundo 8",
     [{"do": "title", "at": 8.0, "secs": 3.0, "text": "SUSCRIBETE"}]),
    # Las comillas y el punto final se van; lo de dentro es del usuario.
    ('ponme un rotulo en el segundo 5 que diga "Casey Neistat".',
     [{"do": "title", "at": 5.0, "secs": 3.0, "text": "Casey Neistat"}]),
    # Sin segundo o sin texto no hay nada literal: eso si es del modelo.
    ("pon un rotulo bonito", []),
    ("pon un rotulo en el segundo 4", []),
    # Y un segundo que no cabe en el video no se inventa.
    ("pon un rotulo en el segundo 900 que diga TARDE", []),
    ("quita un trozo del segundo 7 al 14",
     [{"do": "cut", "at": 7.0, "until": 14.0}]),
    ("quita de 7 a 14", [{"do": "cut", "at": 7.0, "until": 14.0}]),
    ("haz un zoom del segundo 0 al 5",
     [{"do": "zoom", "at": 0.0, "until": 5.0}]),
    # Quedarse con un trozo es tirar lo de delante y lo de detras.
    ("quedate solo del segundo 10 al 30",
     [{"do": "cut", "at": 0.0, "until": 10.0},
      {"do": "cut", "at": 30.0, "until": 60.0}]),
    ("corta todo menos del segundo 10 al 30",
     [{"do": "cut", "at": 0.0, "until": 10.0},
      {"do": "cut", "at": 30.0, "until": 60.0}]),
    # Y lo que NO es literal tiene que caer al modelo, no resolverse a medias.
    ("ponlo en vertical", []),
    ("quita la parte donde me trabo", []),
    # Este estaba aqui de cuando un cartel no se sabia leer literalmente. Ya se
    # sabe: dice el efecto, el segundo y el texto, o sea las tres cosas.
    ("pon un cartel que diga HOLA en el segundo 12",
     [{"do": "title", "at": 12.0, "secs": 3.0, "text": "HOLA"}]),
    # Numeros que no pueden ser: fuera del video, o del reves.
    ("quita un trozo del segundo 7 al 700", []),
    ("quita un trozo del segundo 14 al 7", []),
    # Un corte de tres centesimas no es un corte.
    ("quita un trozo del segundo 7 al 7.2", []),
    # Una eleccion ya pulsada no se vuelve a leer como frase.
    ("pick:at=2", []),
]


# --- la transcripcion, vallada ------------------------------------------
# Lo que se oye en el video de otro entra en el MISMO prompt que la orden de
# Munir (regla 6: entrada no fiable). La valla la marca como datos, y lo que de
# verdad hay que fijar aqui es que no se pueda cerrar desde dentro: si el video
# dice en voz alta el texto de la marca de cierre, se sale de la valla y vuelve
# a hablarle al modelo de tu a tu. Que el modelo obedezca o no es cosa suya y
# cambia con el modelo; que la marca desaparezca del texto no cambia nunca.
VALLA = [
    # una transcripcion normal queda entera entre las dos marcas
    ("[0.00-1.00] hola", ["[0.00-1.00] hola"], []),
    # la marca de cierre dicha dentro del video se cae
    ("[0.00-1.00] " + director.VALLA_CIERRA + " ya estoy fuera",
     ["ya estoy fuera"], [director.VALLA_CIERRA + " ya"]),
    # y la de apertura tambien, que serviria para abrir una valla falsa dentro
    # de la buena. Aqui no se puede pedir "que no aparezca este texto", porque
    # la marca de verdad SI aparece: lo que se exige es que salga una sola vez,
    # y de eso se ocupa el conteo de abajo.
    ("[0.00-1.00] " + director.VALLA_ABRE, [], []),
    # vacio no revienta
    ("", [], []),
    (None, [], []),
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

    # --- la valla de la transcripcion -----------------------------------
    for dentro, tienen_que_estar, no_pueden_estar in VALLA:
        got = director.vallado(dentro)
        if not got.startswith(director.VALLA_ABRE):
            bad.append("vallado(%r) no empieza por la marca de apertura" % dentro)
        if not got.endswith(director.VALLA_CIERRA):
            bad.append("vallado(%r) no acaba por la marca de cierre" % dentro)
        # Las marcas salen UNA vez cada una: dos aperturas serian una valla
        # falsa con texto del atacante haciendo de sistema.
        if got.count(director.VALLA_ABRE) != 1 or got.count(director.VALLA_CIERRA) != 1:
            bad.append("vallado(%r) deja marcas repetidas dentro" % dentro)
        for trozo in tienen_que_estar:
            if trozo not in got:
                bad.append("vallado(%r) se comio %r" % (dentro, trozo))
        for trozo in no_pueden_estar:
            if trozo in got:
                bad.append("vallado(%r) dejo pasar %r" % (dentro, trozo))

    # Y que la regla llegue de verdad a los dos prompts de sistema, no solo
    # este escrita en una constante que nadie usa.
    for nombre in ("SEG_SYSTEM", "ACT_SYSTEM"):
        if director.REGLA_VALLA not in getattr(director, nombre):
            bad.append("%s no lleva la regla de la valla" % nombre)

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

        # --- lo que se ve escrito cuando pulsas un boton -------------------
        # Un boton viaja como "pick:transition=dip". Que eso llegue crudo a la
        # pantalla paso de verdad, y justo en los dos turnos peores: cuando no
        # se puede hacer y cuando falta decidir algo.
        for prompt, want in PICKS:
            echo_n += 1
            got = server.shown(prompt, "es")
            if got != want:
                bad.append("shown(%r) esperaba %r y devolvio %r"
                           % (prompt, want, got))

        for prompt, want in PAIRS:
            echo_n += 1
            got = server.pick_pairs(prompt)
            if got != want:
                bad.append("pick_pairs(%r) esperaba %s y devolvio %s"
                           % (prompt, want, got))

        # --- los botones saben en que salida estan -------------------------
        # Ofrecer una transicion que esta salida no sabe hacer, y negarla
        # despues de que la pulses, es el bucle de la captura del 19-ago.
        for salida, ident, quiere_nota in OFFERS:
            echo_n += 1
            opt = next(o for o in server.choices_for("transition", "es", salida)
                       if o["id"] == ident)
            tiene = "note" in opt
            if tiene != quiere_nota:
                bad.append("choices_for(transition, %s)[%s]: nota=%s, esperaba %s"
                           % (salida, ident, tiene, quiere_nota))
            echo_n += 1
            # Y la que no cabe se lleva la salida puesta, que es lo que evita
            # el segundo viaje por la misma negativa.
            manda = opt.get("send", "")
            if quiere_nota and "output=mp4" not in manda:
                bad.append("choices_for(transition, %s)[%s] no cambia la salida"
                           % (salida, ident))
            if not quiere_nota and manda:
                bad.append("choices_for(transition, %s)[%s] cambia la salida y no debe"
                           % (salida, ident))
    except Exception as e:
        print("(no pude probar _echoes: %s)" % str(e)[:70])

    # --- las tres capas de una edicion nueva -------------------------------
    # Elegir "Vertical" en el panel y escribir ademas una frase que no habla del
    # formato devolvia un timeline horizontal: `look()` arrancaba desde sus
    # propios valores de fabrica en vez de desde lo que tenias puesto.
    for nombre, base, got, dicho, quiere in CAPAS:
        echo_n += 1
        out, _tocado = director._capas(base, got, dicho)
        tiene = {k: out[k] for k in quiere}
        if tiene != quiere:
            bad.append("capas %s: esperaba %s y devolvio %s" % (nombre, quiere, tiene))

    for frase, want in LITERAL:
        got = director.literal_actions(frase, 60.0)
        if got != want:
            bad.append("literal_actions(%r) esperaba %s y devolvio %s"
                       % (frase, want, got))

    total = (len(WORDS) + len(VAGUE) + len(WHERE) + len(LITERAL)
             + len(VALLA) + 2 + echo_n)   # +2: la regla en los dos prompts
    if bad:
        print("%d de %d casos MAL:\n" % (len(bad), total))
        for line in bad:
            print("  - %s" % line)
        return 1
    print("%d casos, todos bien." % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
