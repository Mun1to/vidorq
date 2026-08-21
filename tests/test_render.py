"""El render de verdad: un video entra, un MP4 sale, y se mira lo que sale.

Las demas pruebas son cuentas. Esta ejecuta el motor de render entero
(`vidorq_render.py`), con ffmpeg y todo, y luego ABRE el archivo resultante
para comprobar que lo que hay dentro es lo que se pidio. Es la unica que puede
decir que el producto entrega algo correcto, y no solo que el codigo es valido.

El truco para poder mirarlo sin ojos: el video de origen son cuatro bloques de
un color plano cada uno.

    rojo 0-5   verde 5-10   azul 10-15   amarillo 15-20

Un EDL que se queda con verde y amarillo tiene una consecuencia que se puede
LEER de un fotograma: en el resultado no puede haber ni un pixel rojo ni azul.
Si el corte se va medio segundo, sale otro color, y se ve.

Necesita ffmpeg en el PATH. Si no esta, se salta diciendolo, porque una prueba
que se salta en silencio es peor que no tenerla.

Se lanza:  python tests/test_render.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RENDER = RAIZ / "skill" / "helpers" / "vidorq_render.py"

# Los cuatro bloques del original, y el color que tiene cada uno. No se
# comparan exactos: el paso por h264 mueve un punto o dos.
COLORES = {"rojo": (255, 0, 0), "verde": (0, 128, 0),
           "azul": (0, 0, 255), "amarillo": (255, 255, 0)}

EDL = {"segments": [
    {"start": 6.0, "end": 9.0, "zoom": 1.0, "note": "verde"},
    {"start": 16.0, "end": 19.0, "zoom": 1.0, "note": "amarillo"},
]}


def _palabras(texto, desde):
    out, t = [], desde
    for w in texto.split():
        out.append({"w": w, "s": round(t, 2), "e": round(t + 0.35, 2)})
        t += 0.4
    return out


TRANSCRIPT = {
    "duration": 20.0, "language": "es",
    "segments": [
        {"text": "esto es rojo y se va", "start": 1.0, "end": 3.5,
         "words": _palabras("esto es rojo y se va", 1.0)},
        {"text": "esto es verde y se queda", "start": 6.0, "end": 8.6,
         "words": _palabras("esto es verde y se queda", 6.0)},
        {"text": "esto es azul y se va", "start": 11.0, "end": 13.5,
         "words": _palabras("esto es azul y se va", 11.0)},
        {"text": "esto es amarillo y se queda", "start": 16.0, "end": 18.8,
         "words": _palabras("esto es amarillo y se queda", 16.0)},
    ],
}


def _ffmpeg(*args):
    return subprocess.run(["ffmpeg", "-y", "-v", "error"] + list(args),
                          capture_output=True)


def _fuente(donde):
    """Los cuatro bloques de color, con un tono de fondo para que haya audio."""
    salida = donde / "fuente.mp4"
    trozos = []
    for i, color in enumerate(("red", "green", "blue", "yellow")):
        trozos += ["-f", "lavfi", "-i", "color=c=%s:s=320x180:r=25:d=5" % color]
    trozos += ["-f", "lavfi", "-i", "sine=frequency=440:duration=20:sample_rate=48000"]
    r = _ffmpeg(*(trozos + [
        "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]",
        "-map", "[v]", "-map", "4:a", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(salida)]))
    if r.returncode != 0 or not salida.exists():
        raise RuntimeError("no pude construir el video de prueba: %s"
                           % r.stderr.decode("utf-8", "replace")[-200:])
    return salida


def _color(video, segundo, alto=None):
    """El color de la esquina de arriba, que es donde no hay subtitulo."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(segundo), "-i", str(video),
         "-frames:v", "1", "-vf", "crop=20:20:0:0,scale=1:1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    b = r.stdout[:3]
    return (b[0], b[1], b[2]) if len(b) == 3 else None


def _cerca(uno, otro, margen=40):
    return uno is not None and all(abs(a - b) <= margen for a, b in zip(uno, otro))


def _duracion(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(video)],
                       capture_output=True)
    try:
        return float(r.stdout.decode().strip())
    except ValueError:
        return -1.0


def _forma(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of",
                        "csv=p=0", str(video)], capture_output=True)
    try:
        w, h = r.stdout.decode().strip().split(",")[:2]
        return int(w), int(h)
    except Exception:
        return (0, 0)


def _hay_subtitulo(video, segundo):
    """Un subtitulo quemado deja muchos colores donde antes habia uno solo."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(segundo), "-i", str(video),
         "-frames:v", "1", "-vf", "crop=320:55:0:120", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"], capture_output=True)
    crudo = r.stdout
    distintos = {crudo[i:i + 3] for i in range(0, len(crudo) - 2, 3)}
    return len(distintos) > 5


def _render(fuente, casa, nombre, *extra):
    salida = casa / nombre
    r = subprocess.run(
        [sys.executable, str(RENDER), str(fuente), str(casa / "edl.json"),
         str(casa / "transcript.json"), str(salida)] + list(extra),
        capture_output=True, cwd=str(RENDER.parent))
    texto = (r.stdout + r.stderr).decode("utf-8", "replace")
    return salida, texto


def casos(casa, fuente):
    # --- el corte se queda lo que se le pidio y NADA mas -------------------
    plano, log = _render(fuente, casa, "plano.mp4")
    yield "render: el archivo sale", plano.exists(), True
    yield "render: y lo dice", "DONE" in log, True
    if not plano.exists():
        return
    yield ("render: dura lo que suman los tramos (6 s)",
           abs(_duracion(plano) - 6.0) < 0.2, True)
    # Lo que de verdad importa: los dos colores que se pidieron, en su sitio,
    # y ni un fotograma de los otros dos.
    yield ("render: la primera mitad es el tramo verde",
           [t for t in (0.2, 1.0, 2.0, 2.8)
            if not _cerca(_color(plano, t), COLORES["verde"])], [])
    yield ("render: la segunda es el amarillo",
           [t for t in (3.2, 4.0, 5.0, 5.7)
            if not _cerca(_color(plano, t), COLORES["amarillo"])], [])
    yield ("render: no se cuela ni un fotograma de lo cortado",
           [t for t in (0.2, 1.0, 2.0, 2.8, 3.2, 4.0, 5.0, 5.7)
            if _cerca(_color(plano, t), COLORES["rojo"])
            or _cerca(_color(plano, t), COLORES["azul"])], [])
    # Y el subtitulo esta QUEMADO en la imagen, no prometido en un log.
    yield ("render: el subtitulo sale en la imagen", _hay_subtitulo(plano, 1.0), True)
    # Con el hueco donde nadie habla: entre 8.6 y 16.0 del original no se dice
    # nada, y ese silencio tiene que verse limpio en el montaje.
    yield ("render: donde nadie habla no hay subtitulo",
           _hay_subtitulo(plano, 2.85), False)

    # --- el vertical, que es otro camino entero ----------------------------
    # Ojo con lo que NO se comprueba aqui. Las bandas negras del vertical son
    # imposibles en el MP4 por construccion: el reencuadre se hace RECORTANDO
    # al formato destino y luego escalando, asi que no hay hueco que rellenar.
    # Medido el 21-ago-2026 metiendo a mano un `force_original_aspect_ratio=
    # decrease` con su `pad`: el resultado salio igual de lleno. `fill_zoom`,
    # que es la funcion que sí evita las bandas, es del camino de RESOLVE, y
    # esa se prueba aparte en test_relojes.py con la cuenta. Una comprobacion
    # de bandas negras aqui no podria fallar nunca, y una prueba que no puede
    # fallar es peor que no tenerla.
    vert, _ = _render(fuente, casa, "vertical.mp4", "--ratio", "vertical")
    yield "render: el vertical sale", vert.exists(), True
    if vert.exists():
        yield "render: y mide 1080x1920", _forma(vert), (1080, 1920)
        # Reencuadrar no puede mover el corte: los mismos colores, a la misma
        # hora, con otra forma de cuadro.
        yield ("render: el vertical conserva el corte",
               [t for t in (0.2, 2.0, 2.8)
                if not _cerca(_color(vert, t), COLORES["verde"])]
               + [t for t in (3.2, 5.0, 5.7)
                  if not _cerca(_color(vert, t), COLORES["amarillo"])], [])
        yield ("render: y sigue durando lo mismo",
               abs(_duracion(vert) - 6.0) < 0.2, True)
        # Y el subtitulo se quema DESPUES de reencuadrar: al reves saldria
        # recortado o estirado con la imagen.
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", "1.0", "-i", str(vert),
             "-frames:v", "1", "-vf", "scale=320:569,crop=320:120:0:430",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
        crudo = r.stdout
        yield ("render: el vertical tambien lleva el subtitulo quemado",
               len({crudo[i:i + 3] for i in range(0, len(crudo) - 2, 3)}) > 5, True)

    # --- la transicion mezcla los dos planos de verdad ---------------------
    dis, log2 = _render(fuente, casa, "dissolve.mp4", "--transition", "dissolve",
                        "--no-captions")
    yield "render: la disolvencia sale", dis.exists(), True
    if dis.exists():
        yield "render: y lo dice", "XFADE_OK" in log2, True
        # En mitad de la union no puede haber ni verde puro ni amarillo puro:
        # si lo hay, no ha mezclado nada y es un corte seco disfrazado.
        medio = _color(dis, 2.7)
        yield ("render: la union es una mezcla, no un corte seco",
               (not _cerca(medio, COLORES["verde"], 20)
                and not _cerca(medio, COLORES["amarillo"], 20)), True)
        # Y la mezcla va DE uno A otro: mas verde antes, mas amarillo despues.
        antes, despues = _color(dis, 2.55), _color(dis, 2.85)
        yield ("render: la mezcla avanza hacia el plano que entra",
               (antes is not None and despues is not None
                and despues[0] > antes[0]), True)
        # El xfade se come el solape, asi que el resultado dura menos. Si el
        # archivo siguiera durando 6 s, el solape no se habria aplicado.
        yield ("render: la transicion acorta el resultado",
               _duracion(dis) < 5.9, True)


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("(sin ffmpeg en el PATH: esta prueba no se puede hacer)")
        return 0
    casa = Path(tempfile.mkdtemp(prefix="vidorq_render_"))
    try:
        (casa / "edl.json").write_text(json.dumps(EDL, indent=1), encoding="utf-8")
        (casa / "transcript.json").write_text(
            json.dumps(TRANSCRIPT, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            fuente = _fuente(casa)
        except RuntimeError as e:
            print("(no pude preparar el video de prueba: %s)" % e)
            return 0

        bad, total = [], 0
        for nombre, got, want in casos(casa, fuente):
            total += 1
            if got != want:
                bad.append("%s: esperaba %s y devolvio %s" % (nombre, want, got))
        if bad:
            print("%d de %d casos MAL:\n" % (len(bad), total))
            for line in bad:
                print("  - %s" % line)
            return 1
        print("%d casos, el render entrega lo que promete." % total)
        return 0
    finally:
        # Los videos pesan, y esta carpeta no la vacia nadie.
        shutil.rmtree(casa, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
