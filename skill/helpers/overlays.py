"""Cosas animadas que Vidorq escribe desde cero y pone encima del vídeo.

Un overlay aqui es una composicion de Fusion generada por plantilla, igual que
los subtitulos (captions.to_comp), con sus curvas escritas dentro del archivo.
Ese es el truco de toda la casa: la API de Resolve no pone keyframes, pero un
.comp los trae puestos y ImportFusionComp los respeta.

Lo que cambia respecto a los subtitulos es DONDE cae. Un titulo aterriza siempre
en V1 y descoloca la edicion; estos se colocan con /media/insert en una pista de
arriba, en su frame exacto y con su duracion exacta, que es el mismo mecanismo
con el que los subtitulos pasaron de 518 ms a 52 ms cada uno.

  ¿Y por que se puede poner una comp sobre un clip de video cualquiera?
  Porque estas composiciones no tienen MediaIn: son Background o Text+ hacia el
  Saver, asi que el clip de debajo no entra en el grafico y lo que sale es el
  overlay sobre transparencia. Medido con un soporte rojo: el clip sin comp se
  exporta (255, 24, 0) y el clip con comp se exporta (0, 0, 0). El rojo no
  llega.

El vocabulario es CERRADO a proposito. La IA elige de esta lista y rellena
parametros; nunca escribe Fusion. La frase que la IA esta leyendo sale de la
transcripcion de un video ajeno (regla AL), y un modelo al que se le deja
escribir codigo de nodos es un modelo al que se le deja escribir cualquier cosa.
"""
from __future__ import annotations

import re
from pathlib import Path

import captions as cap

# id -> como se llama y que hace, para la interfaz y para el prompt del director.
KINDS = {
    "dip": {
        "label": {"es": "Fundido a negro", "en": "Dip to black"},
        "note": {"es": "El vídeo se va a negro y vuelve. Para separar bloques.",
                 "en": "The video goes to black and comes back. To separate blocks."},
        "rgb": (0.0, 0.0, 0.0), "peak": 1.0, "shape": "solid",
    },
    "white": {
        "label": {"es": "Fundido a blanco", "en": "Dip to white"},
        "note": {"es": "Igual pero en blanco. Más alegre y menos definitivo.",
                 "en": "The same in white. Brighter and less final."},
        "rgb": (1.0, 1.0, 1.0), "peak": 1.0, "shape": "solid",
    },
    "flash": {
        "label": {"es": "Destello", "en": "Flash"},
        "note": {"es": "Un golpe de luz corto en el corte. El de los montajes rápidos.",
                 "en": "A short punch of light on the cut. The fast-montage one."},
        "rgb": (1.0, 1.0, 1.0), "peak": 0.75, "shape": "solid",
    },
}

# Los que llevan texto. No son una transicion: no van en el corte, van donde el
# usuario diga y duran lo que el diga. Comparten catalogo con las de arriba para
# que la interfaz y el prompt del director tengan una sola lista que leer.
#
# Las medidas (`size`, `y`) siguen la escala de captions.py, que es fraccion del
# ANCHO del cuadro y no del alto. Eso ya esta medido alli y no se rediscute.
KINDS.update({
    "rotulo": {
        "label": {"es": "Rótulo", "en": "Lower third"},
        "note": {"es": "Una barra abajo con tu texto encima. El de las entrevistas.",
                 "en": "A bar at the bottom with your text on it. The interview one."},
        # ENCIMA de los subtitulos, no debajo. Debajo no cabe, y esto se midio
        # el 19-ago sobre un cuadro de 1080 con la caja del rotulo aislada
        # contra un fondo plano:
        #
        #   los subtitulos ocupan de la fila 842 (punch, el mas alto) a la 1033
        #   (marker, el mas hondo), y la caja del rotulo mide 52 px.
        #
        # O sea que entre el subtitulo mas hondo y el borde de abajo quedan 46
        # px para una caja de 52: no entra. Bajarlo a 0.06 quitaba el solape
        # pero lo sacaba del cuadro, y el texto se cortaba contra la fila 1079.
        # Y hay que mirar las DOS salidas, porque la misma barra no mide lo
        # mismo en cada una. Medido el 19-ago restando fotogramas (el mismo
        # montaje con y sin rotulo, y el de solo subtitulos contra el crudo):
        #
        #   en el MP4 (libass)    la caja mide  52 px
        #   en Resolve (Fusion)   la caja mide 203 px
        #
        # No es un fallo suelto: en Fusion la placa se dibuja por letra y solo
        # se cierra en una barra continua a partir de Thickness 0.80, que ya se
        # midio ayer. A esa gruesura la caja es cuatro veces mas alta, y a 0.30
        # se comia 76 px del subtitulo de Resolve aunque en el MP4 sobraran 22.
        # A 0.40 la caja de Resolve va de la 532 a la 735 y el subtitulo empieza
        # en la 785: 50 px de hueco. En el MP4 sobran 130.
        "shape": "text", "y": 0.40, "size": 0.052,
        "font": "Arial", "style": "Bold",
        "fill": (1.0, 1.0, 1.0),
        # r, g, b, alpha, grosor: el panel del Text+, que es la barra.
        "panel": (0.06, 0.07, 0.10, 0.88, 0.80),
        "tracking": 0.0, "pop": 0.0,
    },
    "chapa": {
        "label": {"es": "Chapa", "en": "Badge"},
        "note": {"es": "Una etiqueta pequeña arriba, en amarillo. Para avisos cortos.",
                 "en": "A small tag at the top, in yellow. For short notices."},
        "shape": "text", "y": 0.86, "size": 0.040,
        "font": "Arial", "style": "Black",
        "fill": (0.08, 0.08, 0.08),
        "panel": (1.0, 0.84, 0.0, 1.0, 0.90),
        "tracking": 0.02, "pop": 0.18,
    },
})

# Los que llevan texto, para poder preguntar por ellos sin ensenar transiciones.
WITH_TEXT = ("rotulo", "chapa")

# Cuanto dura uno de texto si nadie dice nada. Tres segundos es lo que se tarda
# en leer un nombre y un cargo sin correr.
TEXT_SECONDS = 3.0

# Cuanto dura un overlay de transicion, en segundos. Corto: una transicion que
# se nota mas que el corte es una transicion que estorba.
SECONDS = {"dip": 0.5, "white": 0.4, "flash": 0.18}

# Que transiciones se pueden hacer asi. Las otras (disolvencia, barrido,
# deslizamiento) necesitan mezclar los DOS planos a la vez, y una capa por
# encima solo puede taparlos: no hay forma de hacerlas con este mecanismo.
AS_OVERLAY = {"dip": "dip", "white": "white", "flash": "flash"}


def kind_list(lang="es", only=None):
    """El catalogo para la interfaz y para el prompt. `only` filtra la familia."""
    return [{"id": k, "label": v["label"].get(lang, v["label"]["en"]),
             "note": v["note"].get(lang, v["note"]["en"])}
            for k, v in KINDS.items() if only is None or k in only]


def label_of(kind, lang="es", plural=False):
    """Como se llama ese efecto delante de una persona.

    El motor contaba los rotulos con el id crudo y en plural fijo: "1 de tipo
    rotulo puestos". Tres cosas mal en cinco palabras.
    """
    k = KINDS.get(kind)
    if not k:
        return kind
    nombre = k["label"].get(lang, k["label"]["en"])
    return (nombre + "s") if plural else nombre


def as_preset(kind):
    """El mismo overlay con la forma que espera captions.to_ass.

    libass sabe pintar la barra: en `BorderStyle 3` rellena la caja con el
    color del contorno y usa `Outline` de relleno alrededor del texto. O sea que
    lo unico que hace falta para tener la misma pinta en el MP4 es hablarle en
    su idioma, y ese idioma es un preset.

    Los campos que un overlay no usa van a None a proposito y no a un valor
    "por si acaso": un contorno que nadie pidio se ve.
    """
    k = KINDS.get(kind) or KINDS["rotulo"]
    if k.get("shape") != "text":
        return None
    return {"words": 12, "max_chars": 90, "upper": False,
            "font": k["font"], "style": k["style"], "size": k["size"],
            "fill": k["fill"], "outline": None, "shadow": None,
            "y": k["y"], "anim": "fade", "glow": None, "panel": k["panel"],
            "word_fx": None, "accent": k["fill"], "tracking": k["tracking"]}


def seconds(kind):
    return SECONDS.get(kind, 0.4)


def _fade_keys(dur, peak):
    """De transparente a `peak` y de vuelta, dentro del clip.

    El pico va en el medio, que en una transicion es donde cae el corte: asi el
    cambio de plano ocurre cuando la pantalla esta tapada del todo, que es
    exactamente para lo que sirve un fundido.
    """
    mid = max(1, dur // 2)
    end = max(mid + 1, dur - 1)
    return [(0, 0.0), (mid, float(peak)), (end, 0.0)]


def to_comp(path, kind, w, h, dur, text=""):
    """Escribe el .comp de este overlay. Devuelve la ruta.

    Dos formas: un color solido con la opacidad animada (las transiciones) y un
    Text+ con su barra (el rotulo y la chapa). Decide el propio tipo, no quien
    llama, para que anadir uno nuevo sea anadir una entrada a KINDS.
    """
    k = KINDS.get(kind) or KINDS["dip"]
    if k.get("shape") == "text":
        return _text_comp(path, k, kind, w, h, dur, text)
    return _solid_comp(path, k, kind, w, h, dur)


def _text_comp(path, k, kind, w, h, dur, text):
    """Un Text+ con panel, que entra y sale con su curva.

    El texto viene de lo que ESCRIBIO el usuario en el chat, que es la unica
    fuente de ordenes de la casa, o de la transcripcion, que es un dato y se
    dibuja tal cual sin obedecerlo. En los dos casos se escapa antes de entrar
    en el archivo: una comilla suelta convierte el .comp en algo que Fusion no
    abre, y ese escapado ya vive en captions._fu_str.
    """
    import captions as _cap
    # Los espacios seguidos dejan una muesca en la barra, porque cada caracter
    # trae su propio recuadro y el del espacio es estrecho. Se ve en el borde de
    # arriba y de abajo, y se arregla en el texto, no subiendo mas el grosor.
    text = re.sub(r"\s+", " ", (text or "")).strip()
    # El tamano no puede pasarse de ancho: un Text+ NO parte la linea, se sale
    # del cuadro por los dos lados. El tope es el mismo que usan los subtitulos.
    size = float(k["size"]) * 2.259 * (_cap.line_ref(w, h) / max(1.0, float(w)))
    size = min(size, _cap.FIT / (_cap.CHAR_ADVANCE * max(1, len(text or "x"))))

    # Entrada y salida. Aqui no hay eleccion de animacion a proposito: un rotulo
    # que entra distinto cada vez distrae del video en vez de rotularlo.
    beat = max(2, min(int(round(dur * 0.18)), 8))
    last = max(1, dur - 1)
    fade = [(0, 0.0), (beat, 1.0)]
    if last > beat + 2:
        fade += [(max(beat + 1, last - beat), 1.0), (last, 0.0)]
    tools = _cap._spline("Entra", fade)
    wires = {"Alpha1": "Entra"}
    if k.get("pop"):
        # La chapa aterriza: empieza mas grande y se asienta. El valor final es
        # el de arriba y no uno mayor, para que no se salga del cuadro al entrar.
        tools += _cap._spline("Salta", [(0, size * (1.0 + float(k["pop"]))),
                                        (beat, size)])
        wires["Size"] = "Salta"

    els = [(1, 0, k["fill"], 1.0, [])]
    r, g, b, a, th = k["panel"]
    els.append((2, 3, (r, g, b), a, [
        "Thickness2 = Input { Value = %.4f, }," % th,
        "Softness2 = Input { Value = 0.01, },",
    ]))
    # El panel se funde con la misma curva, o la barra aparece de golpe y el
    # texto entra despues encima, que se ve mal y se vio.
    wires["Alpha2"] = "Entra"

    inputs = _cap._text_inputs(k, {"text": text or ""}, w, h, dur, wires,
                               size, float(k["y"]), els)
    comp = (
        'Composition {\n'
        '\tCurrentTime = 0,\n'
        '\tRenderRange = { 0, %d },\n'
        '\tGlobalRange = { 0, %d },\n'
        '\tCurrentID = 9,\n'
        '\tHiQ = true,\n'
        '\tCustomData = {\n'
        '\t\tTEMPLATE_ID = "Text+",\n'
        '\t\tVIDORQ_OVERLAY = "%s"\n'
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
        '\t\t\tViewInfo = OperatorInfo { Pos = { 385, 49.5 } },\n'
        '\t\t},\n'
        '\t},\n'
        '}\n'
        % (last, last, kind, tools, inputs)
    )
    Path(path).write_text(comp, encoding="utf-8")
    return Path(path)


def _solid_comp(path, k, kind, w, h, dur):
    """Un color plano que se funde. Es toda la transicion.

    Mismo esqueleto que captions.to_comp y la misma BezierSpline, que se reusa
    de alli para no tener dos formas distintas de escribir un keyframe en el
    mismo programa.
    """
    r, g, b = k["rgb"]
    spline = cap._spline("Fundido", _fade_keys(dur, k["peak"]))
    last = max(1, dur - 1)
    comp = (
        'Composition {\n'
        '\tCurrentTime = 0,\n'
        '\tRenderRange = { 0, %d },\n'
        '\tGlobalRange = { 0, %d },\n'
        '\tCurrentID = 9,\n'
        '\tHiQ = true,\n'
        '\tCustomData = {\n'
        '\t\tTEMPLATE_ID = "Text+",\n'
        '\t\tVIDORQ_OVERLAY = "%s"\n'
        '\t},\n'
        '\tTools = {\n'
        '%s'
        '\t\tCapa = Background {\n'
        '\t\t\tInputs = {\n'
        '\t\t\t\tGlobalOut = Input { Value = %d, },\n'
        '\t\t\t\tWidth = Input { Value = %d, },\n'
        '\t\t\t\tHeight = Input { Value = %d, },\n'
        '\t\t\t\tUseFrameFormatSettings = Input { Value = 1, },\n'
        '\t\t\t\tTopLeftRed = Input { Value = %.4f, },\n'
        '\t\t\t\tTopLeftGreen = Input { Value = %.4f, },\n'
        '\t\t\t\tTopLeftBlue = Input { Value = %.4f, },\n'
        '\t\t\t\tTopLeftAlpha = Input { SourceOp = "Fundido", Source = "Value", },\n'
        '\t\t\t},\n'
        '\t\t\tViewInfo = OperatorInfo { Pos = { 220, 49.5 } },\n'
        '\t\t},\n'
        '\t\tMediaOut1 = Saver {\n'
        '\t\t\tInputs = {\n'
        '\t\t\t\tIndex = Input { Value = "0", },\n'
        '\t\t\t\tInput = Input { SourceOp = "Capa", Source = "Output", },\n'
        '\t\t\t},\n'
        '\t\t\tViewInfo = OperatorInfo { Pos = { 385, 49.5 } },\n'
        '\t\t},\n'
        '\t},\n'
        '}\n'
        % (last, last, kind, spline, last, w, h, r, g, b)
    )
    Path(path).write_text(comp, encoding="utf-8")
    return Path(path)


def at_times(items, fps, start_frame, span=None):
    """Donde va cada overlay de texto: en su segundo, con su duracion.

    Los segundos de `items` son YA de tiempo de montaje, que es lo unico que
    significa algo una vez los cortes estan hechos. El que no cabe se cae en
    silencio: colocarlo fuera del timeline no da error, deja un hueco al final.
    """
    out = []
    for it in items or []:
        kind = it.get("kind") or "rotulo"
        if KINDS.get(kind, {}).get("shape") != "text":
            continue
        dur = max(2, int(round(float(it.get("secs") or TEXT_SECONDS) * fps)))
        frame = start_frame + int(round(float(it.get("at", 0.0)) * fps))
        if frame < start_frame:
            frame = start_frame
        if span is not None and frame + dur > start_frame + span:
            continue
        out.append({"frame": frame, "dur": dur, "kind": kind,
                    "text": str(it.get("text") or "")[:90]})
    return out


def at_cuts(edl, kind, fps, start_frame, span=None):
    """Donde va un overlay de transicion: uno centrado en cada corte.

    En el primer corte no va nada, porque ahi no se cambia de plano: se empieza.
    Cada capa se centra en la union para que el cambio quede tapado, y se
    recorta si el trozo de al lado es mas corto que el propio fundido.
    """
    secs = seconds(kind)
    dur = max(2, int(round(secs * fps)))
    out, at = [], 0.0
    for i, seg in enumerate(edl[:-1]):
        at += float(seg["end"]) - float(seg["start"])
        # No mas largo que la mitad de sus vecinos, o se comeria el plano corto.
        vecino = min(float(seg["end"]) - float(seg["start"]),
                     float(edl[i + 1]["end"]) - float(edl[i + 1]["start"]))
        largo = max(2, min(dur, int(round(vecino * fps))))
        frame = start_frame + int(round(at * fps)) - largo // 2
        if frame < start_frame:
            frame = start_frame
        if span is not None and frame + largo > start_frame + span:
            continue
        out.append({"frame": frame, "dur": largo, "kind": kind})
    return out
