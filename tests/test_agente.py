"""Lo que Vidorq le cuenta a OTRO agente sobre un video.

Un agente que llega de fuera no quiere pintar una pantalla: quiere saber que
hay en el video y que puede hacer con ello. Este archivo comprueba que lo que
recibe sirve para decidir, y sobre todo que **dice lo que Vidorq NO sabe
hacer**, que es la parte que no suele estar y la que evita que un agente
prometa lo que no puede cumplir. Ese fue el fallo que abrio todo este trabajo:
la pantalla decia "copiar el estilo de un video" y elegia el mas parecido de
un cajon de diez.

Lo que se comprueba:

  - `capacidades()` dice lo que mide, lo que reconstruye y lo que NO, y la
    lista de lo que no puede no esta vacia. Una lista vacia ahi seria la
    mentira de siempre con otra forma.
  - los nombres de color se entienden. Un agente no deberia tener que
    interpretar tres decimales para saber que una palabra es amarilla, y un
    nombre equivocado es peor que ninguno: (0.94, 0.94, 0.69) salia "verde"
    por un empate entre el rojo y el verde, siendo un amarillo palido.
  - el informe de un video sin subtitulos lo dice, en vez de callarse.
  - el texto ajeno va marcado como ajeno.

No necesita ffmpeg, ni red, ni el detector de texto: lo que necesita video se
comprueba en test_leer.py.

Se lanza:  python tests/test_agente.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))

import agente        # noqa: E402

# Colores medidos de verdad en el Short de referencia, mas los del catalogo de
# la casa, mas los dos empates que rompian el nombre.
COLORES = [
    ((0.98, 0.97, 0.97), "blanco"),
    ((0.93, 0.98, 0.07), "amarillo"),
    ((0.92, 0.85, 0.11), "amarillo"),
    # El que fallaba: rojo y verde clavados, azul corto. Amarillo palido.
    ((0.938, 0.938, 0.688), "amarillo"),
    ((0.07, 0.83, 0.94), "cian"),
    ((0.30, 0.90, 1.00), "cian"),
    ((0.0, 0.0, 0.0), "negro"),
    ((0.05, 0.04, 0.06), "negro"),
    ((0.5, 0.5, 0.52), "gris"),
    ((0.86, 0.16, 0.10), "rojo"),
    ((0.13, 0.80, 0.45), "verde"),
    ((1.0, 0.42, 0.08), "naranja"),
    ((0.45, 0.20, 0.85), "morado"),
    ((0.15, 0.25, 0.85), "azul"),
]


def casos():
    c = agente.capacidades()
    yield ("dice lo que mide", bool(c["mide"]["subtitulos_quemados"]), True)
    yield ("dice lo que reconstruye", bool(c["reconstruye"]["mp4"]), True)
    # La que de verdad importa. Una lista vacia aqui seria volver a prometer
    # de mas, que es justo lo que este harness viene a evitar.
    yield ("y dice lo que NO sabe hacer", len(c["no"]) >= 5, True)
    yield ("la tipografia esta entre lo que no sabe",
           any("TIPOGRAFIA" in x for x in c["no"]), True)
    yield ("y lo de Resolve con dos colores tambien",
           any("Text+" in x for x in c["no"]), True)
    # Los numeros del puente no se inventan: son los que hay.
    yield ("cuenta los endpoints del puente",
           c["puente"]["en_uso"] < c["puente"]["endpoints_totales"], True)
    yield ("y lista los que sirven y no se usan",
           len(c["puente"]["sin_tocar_que_sirven"]) >= 3, True)

    for rgb, nombre in COLORES:
        yield ("%s se llama %s" % (str(rgb), nombre),
               agente._nombre_color(rgb), nombre)
    yield ("un color que no esta no revienta", agente._nombre_color(None), "?")
    yield ("ni una tupla corta", agente._nombre_color(()), "?")

    # El montaje, dicho en una frase que se entiende sin mirar la tabla.
    frase = agente._frase_montaje({
        "planos": 9, "plano_tipico_s": 2.7, "acelera": 0.7,
        "cortes": 8, "cortes_en_golpe": 7, "planos_quietos": 2})
    yield ("cuenta los planos", "9 planos" in frase, True)
    yield ("y cada cuanto corta", "cada 2.7 s" in frase, True)
    yield ("y que acelera", "acelera" in frase, True)
    yield ("y los cortes al golpe", "7 de sus 8" in frase, True)
    lento = agente._frase_montaje({
        "planos": 4, "plano_tipico_s": 6.0, "acelera": 1.4,
        "cortes": 3, "cortes_en_golpe": 0, "planos_quietos": 0})
    yield ("un video que se calma tambien se dice",
           "se calma" in lento, True)
    yield ("y sin cortes al golpe no se menciona",
           "golpe" in lento, False)
    yield ("sin montaje no se inventa una frase",
           agente._frase_montaje(None), None)


def main():
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
    print("%d casos, lo que le cuenta a un agente se entiende." % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
