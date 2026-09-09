# -*- coding: utf-8 -*-
"""El seguimiento de mascara, contra una escena con la respuesta conocida.

La vara de medir es la misma que en `test_aprende.py`: se fabrica una escena
donde YA se sabe donde esta el sujeto, fotograma a fotograma, y se compara. No
hay forma de hacer trampa porque el que sigue la mascara solo ve pixeles.

Lo que se comprueba y por que:

  - **El ACIERTO (IoU)** contra la verdad. Es la medida estandar de una mascara:
    1.0 es clavada, 0.5 ya se puede usar. Medido el 2026-09-09 con U-2-Net sale
    0.989, asi que el suelo se pone en 0.80: por debajo de ahi ha pasado algo
    gordo, y por encima no se casa el test con un decimal que cambie al tocar el
    modelo.
  - **El TEMBLOR**, que es lo unico que se ve al reproducir. Una mascara puede
    acertar de media y aun asi parpadear, y eso en pantalla se lee como un
    error. Se mide como los pixeles que cambian de lado entre dos fotogramas.
  - **Que arrastrar entre fotogramas salteados no empeora nada.** `cada=3` es lo
    que hace esto usable (tres veces mas rapido), y si algun dia rompe la
    mascara hay que enterarse aqui y no exportando.
  - **Que el recorte con alfa es correcto**: el sujeto opaco, el fondo
    transparente, y el area parecida a la de verdad. Un `.mov` sin canal alfa
    sale con fondo negro, que es exactamente lo contrario del efecto.
  - **Que el contorno se simplifica**: un poligono de 3000 puntos no lo edita
    nadie.

Necesita OpenCV, que el motor ya lleva. Si no esta, se salta DICIENDOLO: una
prueba que se salta en silencio es peor que no tenerla.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skill" / "helpers"))

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None

W, H, N = 320, 240, 24


def escena(carpeta):
    """Un sujeto claro moviendose sobre un fondo con detalle, y su verdad.

    Pequeña y corta a proposito: la prueba tiene que caber en la tanda de
    `todas.py`, y lo que se comprueba aqui no mejora por durar mas.
    """
    path = carpeta / "escena.mp4"
    v = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (W, H))
    rng = np.random.default_rng(7)
    fondo = cv2.GaussianBlur(rng.integers(70, 150, (H, W, 3)).astype(np.uint8),
                             (0, 0), 7)
    verdad = []
    for i in range(N):
        f = fondo.copy()
        cx = int(W * 0.3 + (W * 0.4) * (i / (N - 1.0)))
        cy = int(H * 0.55 + 10 * np.sin(i / 5.0))
        m = np.zeros((H, W), np.uint8)
        cv2.ellipse(m, (cx, cy), (int(W * 0.15), int(H * 0.30)), 0, 0, 360, 255, -1)
        f[m > 0] = np.full((H, W, 3), (215, 195, 180), np.uint8)[m > 0]
        v.write(f)
        verdad.append(m > 0)
    v.release()
    return path, np.array(verdad)


def leer(path):
    cap = cv2.VideoCapture(str(path))
    while True:
        ok, f = cap.read()
        if not ok:
            break
        yield f
    cap.release()


def medir(path, verdad, cada):
    import mascara as mk
    import segmentador as sg
    ious, temblores, previa = [], [], None
    for i, m in enumerate(mk.seguir(leer(path), sg.elegir(), cada=cada)):
        b = m > mk.CORTE
        if i < len(verdad):
            union = np.logical_or(b, verdad[i]).sum()
            ious.append(float(np.logical_and(b, verdad[i]).sum()) / union if union else 0.0)
        if previa is not None:
            temblores.append(float(np.logical_xor(b, previa).mean()))
        previa = b
    return (float(np.mean(ious)), float(np.min(ious)),
            float(np.mean(temblores)) if temblores else 0.0)


def casos(carpeta):
    import mascara as mk
    import segmentador as sg
    out = []
    path, verdad = escena(carpeta)

    out.append(("el segmentador dice con que motor trabaja",
                sg.motor() in ("red", "recorte"), True))
    out.append(("y el modelo bueno viaja con el repo", sg.hay_red(), True))

    iou, peor, temblor = medir(path, verdad, cada=1)
    out.append(("acierta la mascara (IoU >= 0.80)", iou >= 0.80, True))
    out.append(("y no falla en ningun fotograma suelto (peor >= 0.60)",
                peor >= 0.60, True))
    out.append(("la mascara no parpadea (temblor <= 0.05)", temblor <= 0.05, True))

    iou3, _, temblor3 = medir(path, verdad, cada=3)
    # Saltear no puede costar acierto: si lo cuesta, deja de ser gratis y hay
    # que volver a decidirlo mirando numeros, no aqui.
    out.append(("preguntar 1 de cada 3 no empeora el acierto",
                iou3 >= iou - 0.10, True))
    out.append(("ni el temblor", temblor3 <= temblor + 0.01, True))

    # El recorte con alfa, que es lo que hace el efecto de texto por detras.
    mov = carpeta / "sujeto.mov"
    mk.recortar_sujeto("ffmpeg", path, mov, dur=0.4)
    out.append(("escribe el recorte con alfa", mov.exists() and mov.stat().st_size > 0, True))
    png = carpeta / "f.png"
    import subprocess
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(mov),
                    "-vframes", "1", "-y", str(png)], capture_output=True)
    if png.exists():
        img = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
        out.append(("el recorte lleva canal alfa de verdad",
                    img is not None and img.shape[2] == 4, True))
        if img is not None and img.shape[2] == 4:
            alfa = img[..., 3]
            opaco = (alfa > 200).mean()
            out.append(("hay sujeto opaco (entre el 3% y el 60% del cuadro)",
                        0.03 < opaco < 0.60, True))
            out.append(("y fondo transparente (mas del 30%)",
                        (alfa < 50).mean() > 0.30, True))

    # El contorno, para el dia que se pueda escribir un Polygon de Fusion.
    m0 = next(mk.seguir(leer(path), sg.elegir()))
    pts = mk.contorno(m0)
    out.append(("el contorno sale simplificado (3 a 200 puntos)",
                3 <= len(pts) <= 200, True))
    out.append(("y en coordenadas de 0 a 1",
                all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in pts), True))
    return out


def main():
    if cv2 is None:
        print("(sin OpenCV: esta prueba se salta, y lo digo en vez de callarme)")
        return 0
    if not shutil.which("ffmpeg"):
        print("(sin ffmpeg en el PATH: esta prueba se salta, y lo digo)")
        return 0
    carpeta = Path(tempfile.mkdtemp(prefix="vidorq_mascara_"))
    try:
        bad, total = [], 0
        for nombre, got, want in casos(carpeta):
            total += 1
            if got != want:
                bad.append("%s: esperaba %r y devolvio %r" % (nombre, want, got))
        if bad:
            print("%d de %d casos MAL:\n" % (len(bad), total))
            for line in bad:
                print("  - %s" % line)
            return 1
        print("%d casos, la mascara sigue al sujeto." % total)
        return 0
    finally:
        # Los videos pesan y esta carpeta no la vacia nadie.
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
