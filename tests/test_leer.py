"""Vidorq lee los subtitulos QUEMADOS de un video y de que color va cada palabra.

La vara de medir es un circulo cerrado, como en test_aprende: se pinta una
linea de texto con colores CONOCIDOS, se le da la imagen al lector como si
viniera de fuera, y se mira si recupera cada palabra con su color. No hay
forma de hacer trampa, porque el lector solo ve pixeles.

Lo que se comprueba y por que cada cosa:

  - la linea se parte en tantas palabras como tiene. El reparto por letras
    entro justo por aqui: repartir por huecos de contraste ponia el corte de
    'CADA' encima de la E de 'DE', y entonces el color medido era el de otra
    palabra. Ninguna formula de color arregla un corte mal puesto.
  - cada palabra recupera SU color. Es el punto 2 entero: una palabra de un
    color entre otras de otro es lo que hace que estos subtitulos se vean
    como se ven.
  - funciona con letra rellena Y con letra HUECA. El video real trae las dos,
    y con la hueca todo lo que mire "el interior" devuelve el fondo.
  - el fondo NUNCA es liso. Un fondo liso esconde justo los fallos que
    importan, y aqui ya paso una vez.

Necesita el detector de texto (`rapidocr-onnxruntime`), que trae consigo cv2.
Si no esta, se salta DICIENDOLO: una prueba que se salta en silencio es peor
que no tenerla.

Se lanza:  python tests/test_leer.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))

# Los colores con los que se pinta, y como se llaman al mirarlos. Son los tres
# medidos en el Short que abrio esto, no inventados.
BLANCO = (242, 240, 245)
AMARILLO = (235, 217, 28)
CIAN = (18, 212, 240)


def _fondo(w, h):
    """Un fondo con textura, nunca liso.

    Rayas diagonales de colores medios mas ruido: se parece a metraje en lo
    unico que importa aqui, que es que hay detalle en todas partes y ninguna
    fila destaca sola.
    """
    import numpy as np

    y, x = np.mgrid[0:h, 0:w]
    base = (np.sin((x + y) / 7.0) * 40 + np.cos(x / 11.0) * 30 + 90)
    ruido = np.random.RandomState(7).randint(-18, 18, (h, w))
    g = np.clip(base + ruido, 0, 255).astype("uint8")
    return np.dstack([g, np.roll(g, 3, axis=1), np.roll(g, 7, axis=0)])


def _pinta(palabras, hueca=False, w=760, h=90):
    """Una linea de subtitulo, con cada palabra de su color. (imagen, texto)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    img = Image.fromarray(_fondo(w, h))
    d = ImageDraw.Draw(img)
    try:
        fuente = ImageFont.truetype("arialbd.ttf", 52)
    except OSError:
        return None, ""
    texto = " ".join(p[0] for p in palabras)
    ancho = d.textlength(texto, font=fuente)
    x = (w - ancho) / 2
    for pal, color in palabras:
        if hueca:
            # Letra hueca: solo el contorno, y por dentro se ve el fondo. Es
            # como estan la mitad de los subtitulos del video real.
            d.text((x, 14), pal, font=fuente, fill=None,
                   stroke_width=3, stroke_fill=color)
        else:
            d.text((x, 14), pal, font=fuente, fill=color,
                   stroke_width=3, stroke_fill=(0, 0, 0))
        x += d.textlength(pal + " ", font=fuente)
    # Recortado a las letras, que es como llega en el producto: el trozo que
    # se mide es la caja que devuelve el detector, y esa viene ceñida al
    # texto. Dejar el margen de la imagen aqui probaria otra cosa distinta de
    # la que hace el programa, y de hecho fallaba por eso.
    izq = int((w - ancho) / 2)
    return np.array(img)[:, izq:izq + int(ancho)], texto


def _cerca(uno, otro, margen=0.22):
    """Dos colores 0-1 que son el mismo a ojo."""
    if not uno:
        return False
    return all(abs(a - b / 255.0) <= margen for a, b in zip(uno, otro))


def casos():
    import leer

    # Cada caso: como se llama, que palabras, y si la letra va hueca.
    pruebas = [
        ("una amarilla entre blancas",
         [("Y", BLANCO), ("HAY", BLANCO), ("OTRA", AMARILLO), ("PERSONA", BLANCO)],
         False),
        ("una amarilla entre blancas, letra hueca",
         [("UNA", BLANCO), ("DE", BLANCO), ("CADA", AMARILLO), ("CINCO", BLANCO)],
         True),
        ("tres colores distintos",
         [("BLANCA", BLANCO), ("AMARILLA", AMARILLO), ("CIAN", CIAN)], False),
        ("dos palabras", [("TODOS", AMARILLO), ("USTEDES", AMARILLO)], False),
        ("una sola palabra", [("JARVIS", AMARILLO)], False),
        ("todas del mismo color",
         [("CUANDO", CIAN), ("QUIERAS", CIAN)], False),
    ]
    for nombre, palabras, hueca in pruebas:
        img, texto = _pinta(palabras, hueca)
        if img is None:
            yield ("hay tipografia para pintar la prueba", False, True)
            return
        tramos = leer._tramos(img, texto)
        yield ("%s: se parte en %d" % (nombre, len(palabras)),
               len(tramos), len(palabras))
        # Los tramos van en orden y no se pisan: si se solapan, el color de una
        # palabra se esta midiendo encima de la de al lado.
        yield ("%s: los tramos no se pisan" % nombre,
               all(tramos[i][1] < tramos[i + 1][0] for i in range(len(tramos) - 1)),
               True)
        for (pal, color), (a, b) in zip(palabras, tramos):
            medido, px = leer._color(img, a, b)
            yield ("%s: %s sale de su color" % (nombre, pal),
                   _cerca(medido, color), True)
            yield ("%s: %s se mide sobre pixeles de verdad" % (nombre, pal),
                   px >= 12, True)

    # Y el que de verdad importa: que la palabra distinta se DISTINGA de sus
    # vecinas. Un lector que devuelve el mismo color para todas no sirve,
    # aunque cada color por separado caiga dentro del margen.
    img, texto = _pinta(
        [("Y", BLANCO), ("HAY", BLANCO), ("OTRA", AMARILLO), ("PERSONA", BLANCO)])
    tramos = leer._tramos(img, texto)
    medidos = [leer._color(img, a, b)[0] for a, b in tramos]
    if all(medidos):
        # El azul es lo que separa el blanco del amarillo, y es la unica
        # comparacion que no depende de que tan brillante salga la letra.
        azules = [c[2] for c in medidos]
        yield ("la amarilla se distingue de las blancas",
               azules[2] < min(azules[0], azules[1], azules[3]) - 0.25, True)


def main():
    try:
        import leer
    except Exception as e:
        print("(no pude importar leer.py: %s)" % e)
        return 0
    if not leer.hay_motor():
        print("(salto: falta rapidocr-onnxruntime, que es quien trae cv2)")
        return 0
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception:
        print("(salto: faltan numpy o Pillow)")
        return 0

    bad, total = [], 0
    for nombre, got, want in casos():
        total += 1
        if got != want:
            bad.append("%s: esperaba %r y devolvio %r" % (nombre, want, got))
    if bad:
        print("%d de %d casos MAL:\n" % (len(bad), total))
        for line in bad:
            print("  - %s" % line)
        return 1
    print("%d casos, lee el subtitulo y el color de cada palabra." % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
