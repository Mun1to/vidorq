# -*- coding: utf-8 -*-
"""Todas las pruebas de una vez.

Varios archivos y varios comandos es un comando que alguien se salta, y el que
se salta siempre es el ultimo que se anadio. Ninguna necesita modelo ni red, y
todas menos una son cuentas, palabras y tildes: caben en unos segundos y se
pueden lanzar en cada cambio.

La excepcion es `test_render.py`, que SI hace un video y lo renderiza de
verdad con ffmpeg (unos ocho segundos). Va la ultima a proposito: es la unica
que puede decir que el producto entrega un archivo correcto, y la unica que se
salta sola si no hay ffmpeg en el PATH.

Se lanza:  python tests/todas.py
Devuelve 0 si todo esta bien y 1 en cuanto falla algo, para poder engancharlo a
un hook sin pensarlo mucho.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
# En el orden en que conviene leerlas si algo se rompe: primero las cuentas,
# luego lo que entiende de una frase, despues como lo escribe (en castellano y
# en los dos idiomas a la vez), luego si lo que promete en publico es lo que de
# verdad tiene, y al final el render de verdad, que es lenta y va sola.
ARCHIVOS = ["test_relojes.py", "test_understanding.py", "test_castellano.py",
            "test_idiomas.py", "test_promesas.py", "test_render.py"]


def main():
    fallos = []
    for nombre in ARCHIVOS:
        ruta = AQUI / nombre
        if not ruta.exists():
            fallos.append((nombre, "no esta el archivo"))
            continue
        p = subprocess.run([sys.executable, str(ruta)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        salida = (p.stdout or "").strip().splitlines()
        print("%-24s %s" % (nombre, salida[-1] if salida else "(sin salida)"))
        if p.returncode:
            fallos.append((nombre, "\n".join(salida)))
    if fallos:
        print()
        for nombre, detalle in fallos:
            print("=== %s ===" % nombre)
            print(detalle)
        return 1
    print("\nTodo en verde.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
