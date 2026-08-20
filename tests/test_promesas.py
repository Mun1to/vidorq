# -*- coding: utf-8 -*-
"""Que lo que se promete en publico sea lo que hay en el codigo.

El 20-ago-2026 salieron tres promesas que el programa no cumplia, y las tres
eran texto que alguien lee antes de decidir si se fia:

  - la ventana sugeria "Los mejores momentos, con musica de fondo" y Vidorq no
    sabe poner musica: la edicion salia sin decir ni una palabra de ella;
  - la tarjeta Podcast decia "cada pregunta o cambio de tema" y no hay nada que
    mire los temas;
  - el README contaba "nine entrance animations" cuando una de las nueve es
    "ninguna".

Las dos primeras se arreglaron a mano. Esta prueba es para la tercera clase: las
CIFRAS, que envejecen solas cuando alguien anade un preset y no se acuerda del
README. El mismo dia se encontraron otras dos ya viejas (el README decia 98 s
donde hoy son 26, y un doc decia 53 casos donde hay 155).

No comprueba prosa ni promesas de calidad: solo lo que se puede contar.

Se lanza:  python tests/test_promesas.py
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))

NUMEROS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


NUMEROS_ES = {
    "un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
}


def cifra_es(texto):
    """Lo mismo en castellano, que es como habla la landing."""
    t = (texto or "").strip().lower()
    return NUMEROS_ES.get(t, int(t) if t.isdigit() else None)


def cifra(texto):
    """El numero que hay en esa palabra, escrito con letra o con digito."""
    t = (texto or "").strip().lower()
    return NUMEROS.get(t, int(t) if t.isdigit() else None)


def leer(nombre):
    ruta = RAIZ / nombre
    return io.open(ruta, encoding="utf-8").read() if ruta.exists() else ""


def casos():
    """Cada caso devuelve (nombre, lo que salio, lo que tenia que salir)."""
    import captions as cap

    readme = leer("README.md")
    yield ("el README existe", bool(readme), True)
    if not readme:
        return

    estilos = len(cap.PRESETS)
    con_halo = sum(1 for p in cap.PRESETS.values() if p.get("glow"))
    # "none" no es una animacion, es no poner ninguna.
    anims = len([a for a in cap.ANIMS if a != "none"])

    # "Ten styles and eight entrance animations (plus none)"
    m = re.search(r"\*\*Subtitles\.\*\*\s+(\w+)\s+styles?\s+and\s+(\w+)\s+entrance",
                  readme)
    yield ("el README cuenta los estilos y las entradas", bool(m), True)
    if m:
        yield ("estilos que promete el README", cifra(m.group(1)), estilos)
        yield ("entradas que promete el README", cifra(m.group(2)), anims)

    # "Three styles carry a real halo from Fusion's Glow node"
    m = re.search(r"(\w+)\s+styles?\s+carry\s+a\s+real\s+halo", readme)
    yield ("el README cuenta los halos", bool(m), True)
    if m:
        yield ("halos que promete el README", cifra(m.group(1)), con_halo)

    # "a 227 KB detector". El archivo esta en el repo, asi que se pesa.
    modelo = RAIZ / "skill" / "models" / "face_detection_yunet_2023mar.onnx"
    m = re.search(r"(\d+)\s*KB\s+detector", readme)
    yield ("el README cuenta lo que pesa el detector", bool(m), True)
    if m and modelo.exists():
        real = round(modelo.stat().st_size / 1024)
        yield ("el detector pesa lo que dice el README",
               abs(real - int(m.group(1))) <= 1, True)

    # La landing dice lo mismo con otras palabras, y envejece igual. Ahi la
    # frase es "diez estilos y ocho entradas", con los numeros escritos con
    # letra porque es prosa y no una tabla.
    landing = leer("web/index.html")
    m = re.search(r"(\w+)\s+estilos\s+y\s+(\w+)\s+entradas", landing)
    yield ("la landing cuenta los estilos y las entradas", bool(m), True)
    if m:
        yield ("estilos que promete la landing", cifra_es(m.group(1)), estilos)
        yield ("entradas que promete la landing", cifra_es(m.group(2)), anims)

    # Y lo que NO se puede prometer: la ventana no vuelve a sugerir musica.
    i18n = leer("app/src/i18n.tsx")
    ejemplos = re.findall(r'"say\.eg\d+":\s*"([^"]*)"', i18n)
    yield ("hay frases de ejemplo en la ventana", len(ejemplos) >= 3, True)
    con_musica = [e for e in ejemplos
                  if re.search(r"m[uú]sic|banda sonora|soundtrack", e, re.I)]
    yield ("ninguna frase de ejemplo promete musica", con_musica, [])


def main():
    mal, n = [], 0
    for nombre, got, want in casos():
        n += 1
        if got != want:
            mal.append("%s: esperaba %r y salio %r" % (nombre, want, got))
    if mal:
        print("%d de %d promesas MAL:\n" % (len(mal), n))
        for linea in mal:
            print("  - %s" % linea)
        return 1
    print("%d promesas, todas cuadran con el codigo." % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
