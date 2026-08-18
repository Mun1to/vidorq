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

from pathlib import Path

import captions as cap

# id -> como se llama y que hace, para la interfaz y para el prompt del director.
KINDS = {
    "dip": {
        "label": {"es": "Fundido a negro", "en": "Dip to black"},
        "note": {"es": "El video se va a negro y vuelve. Para separar bloques.",
                 "en": "The video goes to black and comes back. To separate blocks."},
        "rgb": (0.0, 0.0, 0.0), "peak": 1.0, "shape": "solid",
    },
    "white": {
        "label": {"es": "Fundido a blanco", "en": "Dip to white"},
        "note": {"es": "Igual pero en blanco. Mas alegre y menos definitivo.",
                 "en": "The same in white. Brighter and less final."},
        "rgb": (1.0, 1.0, 1.0), "peak": 1.0, "shape": "solid",
    },
    "flash": {
        "label": {"es": "Destello", "en": "Flash"},
        "note": {"es": "Un golpe de luz corto en el corte. El de los montajes rapidos.",
                 "en": "A short punch of light on the cut. The fast-montage one."},
        "rgb": (1.0, 1.0, 1.0), "peak": 0.75, "shape": "solid",
    },
}

# Cuanto dura un overlay de transicion, en segundos. Corto: una transicion que
# se nota mas que el corte es una transicion que estorba.
SECONDS = {"dip": 0.5, "white": 0.4, "flash": 0.18}

# Que transiciones se pueden hacer asi. Las otras (disolvencia, barrido,
# deslizamiento) necesitan mezclar los DOS planos a la vez, y una capa por
# encima solo puede taparlos: no hay forma de hacerlas con este mecanismo.
AS_OVERLAY = {"dip": "dip", "white": "white", "flash": "flash"}


def kind_list(lang="es"):
    return [{"id": k, "label": v["label"].get(lang, v["label"]["en"]),
             "note": v["note"].get(lang, v["note"]["en"])}
            for k, v in KINDS.items()]


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


def to_comp(path, kind, w, h, dur):
    """Escribe el .comp de este overlay. Devuelve la ruta.

    Mismo esqueleto que captions.to_comp y la misma BezierSpline, que se reusa
    de alli para no tener dos formas distintas de escribir un keyframe en el
    mismo programa.
    """
    k = KINDS.get(kind) or KINDS["dip"]
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
