# -*- coding: utf-8 -*-
"""Las curvas de movimiento, fijadas donde se midieron.

El 2026-09-21 se midio, contando pixeles del texto fotograma a fotograma, que las
entradas de los subtitulos iban a VELOCIDAD CONSTANTE: el "pop" crecia +0.10,
+0.11, +0.10, +0.10 por fotograma y se paraba en seco. Es lo que hace que una
animacion se vea barata, y es facil de volver a meter sin darse cuenta: basta con
escribir tres claves a mano, como estaba.

Aqui se comprueba, en este orden:

  1. Las curvas son las de la industria: empiezan en 0, acaban en 1, y las que
     frenan FRENAN (velocidad al final cero o casi cero).
  2. El muelle se asienta de verdad. La primera version no lo hacia: sin rebote,
     en el 95% del tiempo aun le faltaba un 4%, y al acabar daba un salto.
  3. Ninguna entrada que sale de un tamaño a otro lleva claves a mano: todas
     tienen su curva. Una que vuelva a claves a mano vuelve a la velocidad fija.
  4. El MP4 y Fusion sacan las claves de la MISMA curva.
  5. En el archivo de subtitulos NO hay velocidad constante: el cambio de tamaño
     entre tramos seguidos varia, que es lo que significa acelerar y frenar.
  6. La chapa aterriza en el MP4, que hasta este dia solo hacia un fundido
     mientras en Resolve si aterrizaba.

Son cuentas y un archivo de texto: no necesita ffmpeg, ni red, ni modelos.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skill" / "helpers"))
import captions as cap  # noqa: E402
import curvas as cv  # noqa: E402
import overlays as ov  # noqa: E402


def _vel(f, a, b, n=200):
    """Velocidad media de la curva entre a y b."""
    return (f(b) - f(a)) / (b - a)


def casos():
    out = []

    # 1. Las curvas empiezan y acaban donde deben.
    for cid in cv.CURVAS:
        f = cv.curva(cid)
        out.append(("la curva %s empieza en 0" % cid, round(f(0.0), 6), 0.0))
        out.append(("la curva %s acaba en 1" % cid, round(f(1.0), 6), 1.0))

    # Las de frenar frenan: al final casi no se mueven, y al principio si.
    for cid in ("suave", "rapida", "muelle"):
        f = cv.curva(cid)
        out.append(("%s arranca rapido" % cid, _vel(f, 0.0, 0.05) > 0.7, True))
        out.append(("%s frena al final" % cid, abs(_vel(f, 0.95, 1.0)) < 0.25, True))

    # Las que rebotan se pasan, y las que no, no.
    out.append(("atras se pasa del final",
                max(cv.atras(i / 200) for i in range(201)) > 1.05, True))
    out.append(("suave nunca se pasa",
                max(cv.suave(i / 200) for i in range(201)) <= 1.0 + 1e-9, True))
    out.append(("rebote nunca se pasa (rebota hacia atras)",
                max(cv.rebote(i / 200) for i in range(201)) <= 1.0 + 1e-9, True))

    # 2. El muelle se asienta, con cualquier rebote.
    for r in (0.0, 0.2, 0.35, 0.55, 0.7):
        out.append(("el muelle con rebote %.2f esta quieto al acabar" % r,
                    abs(cv.muelle(0.95, r) - 1.0) < 0.01, True))

    # 3. Toda entrada de un tamaño a otro tiene su curva.
    for aid, a in cap.ANIMS.items():
        if a.get("desde") is None:
            continue
        out.append(("la animacion %s tiene curva" % aid,
                    cv.conocida(a.get("curva")), True))
        out.append(("y no lleva claves a mano", "scale" in a, False))

    # 4. Los dos caminos, de la misma curva: las claves del MP4 y las de Fusion
    #    acaban en el mismo sitio y salen de la misma funcion.
    pop = cap.ANIMS["pop"]
    mp4 = cap.escala_de(pop, 20)
    fus = cap.escala_de(pop, 6)
    out.append(("MP4 y Fusion arrancan igual", round(mp4[0][1], 4), round(fus[0][1], 4)))
    out.append(("y acaban igual", round(mp4[-1][1], 4), round(fus[-1][1], 4)))
    out.append(("y acaban en su tamaño", round(mp4[-1][1], 4), 1.0))

    # Elegir otra curva cambia el movimiento, no de donde sale ni a donde llega.
    lin = cap.escala_de(pop, 20, "lineal")
    out.append(("otra curva sale del mismo tamaño", round(lin[0][1], 4), round(mp4[0][1], 4)))
    out.append(("pero se mueve distinto",
                any(abs(a[1] - b[1]) > 0.01 for a, b in zip(lin, mp4)), True))

    # Una curva inventada no rompe nada: cae a la propia.
    out.append(("una curva que no existe no rompe",
                round(cap.escala_de(pop, 20, "inventada")[-1][1], 4), 1.0))

    # 5. En el archivo de subtitulos no hay velocidad constante.
    d = Path(tempfile.mkdtemp(prefix="vidorq_curvas_"))
    ass = d / "p.ass"
    chunks = [{"start": 0.0, "end": 1.0, "text": "HOLA",
               "words": [{"w": "HOLA", "s": 0.0, "e": 1.0}]}]
    cap.to_ass(ass, chunks, 0.0, 1.0, 1080, 1920, "pop", "pop")
    texto = ass.read_text(encoding="utf-8-sig")
    tamaños = [float(x) for x in re.findall(r"\\fscx([\d.]+)", texto)]
    pasos = [round(b - a, 2) for a, b in zip(tamaños, tamaños[1:])]
    out.append(("la entrada tiene muchos tramos (una curva, no tres rectas)",
                len(tamaños) >= 6, True))
    out.append(("y la velocidad CAMBIA entre tramos (no es constante)",
                len(set(pasos)) > 2, True))

    # 6. La chapa aterriza en el MP4.
    chapa = ov.as_preset("chapa", None)
    out.append(("la chapa aterriza, no solo funde",
                isinstance(chapa["anim"], dict), True))
    out.append(("y sale mas grande de lo que acaba",
                isinstance(chapa["anim"], dict) and chapa["anim"]["desde"] > 1.0, True))
    out.append(("el rotulo sigue sobrio, solo fundido",
                ov.as_preset("rotulo", None)["anim"], "fade"))

    # El catalogo que ve la ventana, en los dos idiomas.
    for lang in ("es", "en"):
        cat = cv.catalogo(lang)
        out.append(("el catalogo %s trae las %d curvas" % (lang, len(cv.CURVAS)),
                    len(cat), len(cv.CURVAS)))
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
    print("%d casos, el texto entra con curva y no a ritmo fijo." % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
