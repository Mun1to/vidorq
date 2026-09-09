# -*- coding: utf-8 -*-
"""Los presets de exportacion, fijados con los numeros que se midieron.

Aqui no se comprueba "que devuelva algo": se comprueban las TRES decisiones que
costaron una medicion cada una, porque las tres se pueden deshacer sin querer al
tocar la tabla y las tres fallan en silencio (el video sale, solo que mal).

  1. El caudal va por SUPERFICIE, no por altura. Un vertical de 1080x1920 y un
     horizontal de 1920x1080 tienen los mismos pixeles y tienen que pedir lo
     mismo. Indexando por altura, el vertical caia en el escalon de 1440p y
     pedia 20 Mbps para hacer lo que el horizontal hace con 8.
  2. El tamaño solo BAJA. Pedir "YouTube 4K" desde un 1080p no puede inventar
     pixeles, y pedir WhatsApp desde un 4K tiene que encoger.
  3. El caudal sigue al tamaño REAL de salida, no al del preset. Un 1080p
     exportado como 4K se llevaba el caudal de 4K: cinco veces lo que necesita.

Y dos que son de seguridad, no de calidad: un nombre de preset que viene de
fuera no puede tumbar una exportacion, y NVENC no puede recibir caudal y calidad
constante a la vez (es la forma clasica de que no mande ninguno de los dos).

No necesita ffmpeg, ni red, ni modelos: son cuentas.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skill" / "helpers"))
import exportar as ex  # noqa: E402


def casos():
    """(nombre, lo que salio, lo que tenia que salir)."""
    out = []

    # 1. Misma superficie, mismo caudal.
    hor = ex.salida("youtube", 1920, 1080, 30)
    ver = ex.salida("youtube", 1080, 1920, 30)
    out.append(("vertical y horizontal piden el mismo caudal",
                hor["kbps"], ver["kbps"]))
    out.append(("y el de 1080p es el de YouTube", hor["kbps"], 8000))

    # A 50 fps o mas, YouTube sube su propio numero.
    out.append(("a 60 fps sube a 12000",
                ex.salida("youtube", 1920, 1080, 60)["kbps"], 12000))

    # 2. El tamaño solo baja.
    sube = ex.salida("youtube4k", 1280, 720, 30)
    out.append(("pedir 4K desde un 720p NO agranda", (sube["ancho"], sube["alto"]),
                (1280, 720)))
    baja = ex.salida("mensajeria", 3840, 2160, 30)
    out.append(("pedir WhatsApp desde un 4K encoge a 720 de lado corto",
                min(baja["ancho"], baja["alto"]), 720))
    # El lado corto, no la altura: un vertical de 1080x1920 YA es 1080p.
    vert = ex.salida("youtube", 1080, 1920, 30)
    out.append(("un vertical 1080x1920 no se toca",
                (vert["ancho"], vert["alto"]), (1080, 1920)))

    # 3. El caudal sigue al tamaño real, no al del preset.
    out.append(("4K pedido sobre un 1080p cobra caudal de 1080p",
                ex.salida("youtube4k", 1920, 1080, 30)["kbps"], 8000))
    out.append(("y sobre un 4K de verdad si cobra el de 4K",
                ex.salida("youtube4k", 3840, 2160, 30)["kbps"], 40000))

    # Seguridad: lo que viene de fuera no tumba nada.
    for malo in ("inventado", "", None, 123, "../../etc/passwd"):
        out.append(("un preset invalido (%r) cae al de casa" % (malo,),
                    ex.salida(malo, 1920, 1080, 30)["preset"], ex.POR_DEFECTO))

    # NVENC: caudal y calidad constante a la vez, nunca.
    args = ex.args_video(ex.salida("youtube", 1920, 1080, 30), "h264_nvenc")
    out.append(("con caudal, NVENC no lleva -cq", "-cq" in args, False))
    out.append(("y si lleva el caudal pedido", "8000k" in args, True))
    solo_calidad = ex.args_video(ex.salida("master", 1920, 1080, 30), "h264_nvenc")
    out.append(("el master va por calidad, sin -b:v", "-b:v" in solo_calidad, False))

    # El volumen: se toca donde se dijo y NO donde se dijo que no.
    out.append(("YouTube sale normalizado a -14 LUFS",
                ex.salida("youtube", 1920, 1080, 30)["lufs"], -14.0))
    out.append(("el master no se toca el volumen",
                ex.salida("master", 1920, 1080, 30)["lufs"], None))
    out.append(("y por eso no lleva filtro de volumen",
                ex.filtro_volumen(ex.salida("master", 1920, 1080, 30)), []))

    # El catalogo que ve la ventana: completo y en los dos idiomas.
    for lang in ("es", "en"):
        cat = ex.catalogo(lang)
        out.append(("el catalogo %s trae los %d destinos" % (lang, len(ex.PRESETS)),
                    len(cat), len(ex.PRESETS)))
        out.append(("y todos con etiqueta y pista en %s" % lang,
                    all(c["label"] and c["hint"] for c in cat), True))

    # Los lados pares: H.264 rechaza los impares y falla sin decir por que.
    raro = ex.salida("mensajeria", 1287, 723, 30)
    out.append(("los lados salen pares aunque entren impares",
                (raro["ancho"] % 2, raro["alto"] % 2), (0, 0)))
    return out


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
    print("%d casos, los destinos dan los numeros medidos." % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
