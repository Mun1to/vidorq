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

import re
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
# En el orden en que conviene leerlas si algo se rompe: primero las cuentas,
# luego lo que entiende de una frase, despues como lo escribe (en castellano y
# en los dos idiomas a la vez), luego si lo que promete en publico es lo que de
# verdad tiene, y al final el render de verdad, que es lenta y va sola.
ARCHIVOS = ["test_relojes.py", "test_understanding.py", "test_castellano.py",
            "test_idiomas.py", "test_promesas.py", "test_render.py",
            "test_aprende.py"]


def cuadra_el_readme(cuentas):
    """El README enseña cuantos casos tiene cada archivo. Que sea verdad.

    Un README que miente sobre sus propias pruebas es peor que uno que no las
    menciona, y esta es la clase de numero que se queda viejo solo: nadie se
    acuerda de subirlo al anadir un caso. Aqui sale gratis, porque el runner ya
    ha ejecutado los seis y ya tiene el numero de cada uno delante.

    Devuelve la lista de lo que no cuadra, vacia si todo bien.
    """
    readme = AQUI.parent / "README.md"
    if not readme.exists():
        return []
    texto = readme.read_text(encoding="utf-8")
    mal = []
    for nombre, cuantos in cuentas.items():
        if cuantos is None:
            continue
        fila = re.search(r"^%s\s+(\d+)\s" % re.escape(nombre), texto, re.M)
        if not fila:
            continue
        dice = int(fila.group(1))
        if dice != cuantos:
            mal.append("el README dice %d casos en %s y son %d"
                       % (dice, nombre, cuantos))
    total = sum(c for c in cuentas.values() if c is not None)
    badge = re.search(r"tests-(\d+)%20checks", texto)
    if badge and int(badge.group(1)) != total:
        mal.append("el badge dice %s comprobaciones y son %d"
                   % (badge.group(1), total))
    return mal


def main():
    fallos = []
    cuentas = {}
    for nombre in ARCHIVOS:
        ruta = AQUI / nombre
        if not ruta.exists():
            fallos.append((nombre, "no esta el archivo"))
            continue
        p = subprocess.run([sys.executable, str(ruta)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        salida = (p.stdout or "").strip().splitlines()
        ultima = salida[-1] if salida else "(sin salida)"
        print("%-24s %s" % (nombre, ultima))
        # El numero con el que cada archivo se presenta ("409 casos, todos
        # bien"), para poder contrastarlo con lo que promete el README.
        n = re.match(r"(\d+)\s", ultima)
        cuentas[nombre] = int(n.group(1)) if n and not p.returncode else None
        if p.returncode:
            fallos.append((nombre, "\n".join(salida)))
    if not fallos:
        for linea in cuadra_el_readme(cuentas):
            fallos.append(("README.md", linea))
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
