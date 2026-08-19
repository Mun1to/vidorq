"""Mirar el video y calcular la correccion que le hace falta.

Los ocho filtros de `looks.py` son decisiones de estilo: los mismos numeros para
todo el mundo, porque "cine" quiere decir lo mismo en cualquier metraje. Esto es
lo contrario: no impone un look, **arregla lo que este video tiene mal**, y por
eso los numeros salen de mirarlo.

Tres cosas, en este orden, que son las tres que hace a mano cualquiera que abra
la pagina de color antes de ponerse a estilizar:

  1. **Niveles.** Si el negro mas oscuro esta en 12 y el blanco mas claro en 230,
     el video sale lavado. Se estira hasta tocar los extremos, con margen.
  2. **Balance de blancos.** Lo que deberia ser gris se mide en los tonos ALTOS,
     que es donde una dominante canta, y se corrige por canal.
  3. **Saturacion.** Solo si de verdad esta apagado. Subir saturacion a algo que
     ya la tiene es como subirle el volumen a quien ya grita.

Y un techo en cada una. Un automatico que se pasa es peor que no tener ninguno,
porque el usuario no sabe si lo raro es su video o el programa. Todas las
correcciones estan limitadas a lo que un colorista llamaria "una mano suave", y
si el video ya esta bien la respuesta correcta es no tocar nada, que tambien se
devuelve.

La salida tiene la MISMA forma que un preset de `looks.py` (slope, offset,
power, sat), asi que viaja por los dos caminos que ya existen sin inventar
ninguno: `SetCDL` en Resolve y un `.cube` en el MP4.
"""
from __future__ import annotations

import os
import shutil
import subprocess

# Cuantos fotogramas se miran. Doce repartidos por todo el metraje: suficientes
# para que una escena rara no mande, y baratos (a 160 px son 12 x 76 KB).
SAMPLES = 12
SAMPLE_W = 160

# Los topes. Nada de esto es negociable a la baja: son lo que separa "una mano
# suave" de "le ha pasado algo a mi video".
MAX_GAIN = 1.35        # cuanto se puede estirar el contraste
MAX_LIFT = 0.06        # cuanto se puede mover el negro
MAX_WB = 0.12          # cuanto se puede corregir una dominante, por canal
MAX_SAT = 1.25         # cuanto se puede subir la saturacion

# Por debajo de esto no se toca: el video ya esta bien y la mejor correccion es
# ninguna.
DEAD_ZONE = 0.02

NEUTRAL = {"slope": (1.0, 1.0, 1.0), "offset": (0.0, 0.0, 0.0),
           "power": (1.0, 1.0, 1.0), "sat": 1.0}


def _ffmpeg():
    return shutil.which("ffmpeg")


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def sample(video, seconds=0.0, n=SAMPLES, log=None):
    """Los pixeles de unos cuantos fotogramas repartidos por el video.

    Se decodifica a RGB pequeño y se lee en crudo por la tuberia: sin PNG, sin
    disco y sin depender de que el formato de salida conserve el color.
    """
    exe = _ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg no esta instalado")
    if not seconds or seconds <= 0:
        seconds = _duration(video) or 60.0
    # Se saltan el primer y el ultimo 5%: fundidos de entrada y de salida, y
    # cartelas negras, que son justo lo que no representa al video.
    a, b = seconds * 0.05, seconds * 0.95
    step = max(0.1, (b - a) / max(1, n - 1))
    frames = []
    for i in range(n):
        at = a + step * i
        r = subprocess.run(
            [exe, "-hide_banner", "-loglevel", "error", "-nostdin",
             "-ss", "%.2f" % at, "-i", video, "-frames:v", "1",
             "-vf", "scale=%d:-2" % SAMPLE_W, "-pix_fmt", "rgb24",
             "-f", "rawvideo", "-"],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0 and len(r.stdout) >= 3:
            frames.append(r.stdout)
        if log and i == 0:
            log("mirando el color del video...")
    if not frames:
        raise RuntimeError("no pude leer ni un fotograma para medir el color")
    return frames


def _duration(video):
    probe = shutil.which("ffprobe")
    if not probe:
        return 0.0
    r = subprocess.run([probe, "-v", "0", "-show_entries", "format=duration",
                        "-of", "csv=p=0", video], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def stats(frames):
    """Histograma por canal y de luma, sobre todos los fotogramas juntos."""
    hist = [[0] * 256, [0] * 256, [0] * 256]
    luma = [0] * 256
    total = 0
    for buf in frames:
        # De tres en tres: R, G, B. Se recorre entero y se cuenta; con 160 px de
        # ancho son unos 14.000 pixeles por fotograma, que en Python es
        # instantaneo y no justifica traerse numpy.
        for i in range(0, len(buf) - 2, 3):
            r, g, b = buf[i], buf[i + 1], buf[i + 2]
            hist[0][r] += 1
            hist[1][g] += 1
            hist[2][b] += 1
            luma[(r * 54 + g * 183 + b * 19) >> 8] += 1
            total += 1
    return hist, luma, total


def _pct(counts, total, p):
    """El valor por debajo del cual queda el p por ciento de los pixeles."""
    want = total * p
    run = 0
    for v, n in enumerate(counts):
        run += n
        if run >= want:
            return v
    return 255


def _mean(counts, total):
    return sum(v * n for v, n in enumerate(counts)) / max(1, total)


def measure(video, seconds=0.0, log=None):
    """Que le pasa al color de este video, en numeros que se pueden enseñar."""
    frames = sample(video, seconds, log=log)
    hist, luma, total = stats(frames)
    negro = _pct(luma, total, 0.005) / 255.0
    blanco = _pct(luma, total, 0.995) / 255.0
    medio = _mean(luma, total) / 255.0
    # El blanco se mide en los tonos ALTOS, no en la media: una dominante de
    # color canta en lo claro, y la media la ensucia cualquier objeto de color
    # que ocupe medio cuadro.
    altos = [_pct(hist[c], total, 0.90) / 255.0 for c in range(3)]
    medias = [_mean(hist[c], total) / 255.0 for c in range(3)]
    # Saturacion aproximada: cuanto se separan los canales entre si, de media.
    spread = sum(abs(medias[c] - sum(medias) / 3) for c in range(3)) / 3
    return {"negro": negro, "blanco": blanco, "medio": medio,
            "altos": altos, "medias": medias, "spread": spread}


def correction(m):
    """De la medida a los cuatro numeros del CDL, con sus topes.

    Devuelve (preset, que_hizo). `que_hizo` es la lista de cosas que ha tocado,
    en lenguaje de persona, porque un automatico que no dice lo que hace es
    indistinguible de uno que no hace nada.
    """
    hecho = []
    negro, blanco = m["negro"], m["blanco"]

    # 1. Niveles. Se estira lo que falta para llegar a los extremos, dejando un
    #    pelin de margen para no recortar detalle que si estaba ahi.
    rango = max(0.05, blanco - negro)
    gain = _clamp(0.98 / rango, 1.0, MAX_GAIN)
    lift = _clamp(-negro * gain, -MAX_LIFT, MAX_LIFT)
    if gain > 1.0 + DEAD_ZONE or abs(lift) > DEAD_ZONE:
        hecho.append("niveles")
    else:
        gain, lift = 1.0, 0.0

    # 2. Balance de blancos. El canal de referencia es el verde, que es el que
    #    lleva casi toda la luminancia y por eso es el que menos miente.
    altos = m["altos"]
    ref = altos[1] or 0.5
    wb = []
    for c in range(3):
        if altos[c] <= 0.01:
            wb.append(1.0)
            continue
        wb.append(_clamp(ref / altos[c], 1.0 - MAX_WB, 1.0 + MAX_WB))
    if max(abs(x - 1.0) for x in wb) > DEAD_ZONE:
        hecho.append("balance de blancos")
    else:
        wb = [1.0, 1.0, 1.0]

    # 3. Saturacion. Solo hacia arriba y solo si esta plano de verdad.
    sat = 1.0
    if m["spread"] < 0.045:
        sat = _clamp(1.0 + (0.045 - m["spread"]) * 4.0, 1.0, MAX_SAT)
        if sat > 1.0 + DEAD_ZONE:
            hecho.append("saturacion")
        else:
            sat = 1.0

    p = {"slope": tuple(gain * wb[c] for c in range(3)),
         "offset": (lift, lift, lift),
         "power": (1.0, 1.0, 1.0),
         "sat": sat}
    return p, hecho


def analyse(video, seconds=0.0, log=None):
    """Mirar el video y devolver (preset, que_hizo, medida).

    Si no hay nada que arreglar devuelve el preset neutro y una lista vacia, que
    es una respuesta correcta y no un fallo: hay videos que salen bien de camara.
    """
    m = measure(video, seconds, log=log)
    p, hecho = correction(m)
    if log:
        log("color: negro %.2f, blanco %.2f, %s"
            % (m["negro"], m["blanco"], ", ".join(hecho) or "no hace falta tocar nada"))
    return p, hecho, m
