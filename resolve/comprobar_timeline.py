"""Comprueba que Vidorq monta de verdad un timeline dentro de DaVinci Resolve.

Es el ultimo tramo del producto y el unico que no se puede probar sin Resolve
delante: todo lo demas (leer un video ajeno, proponer un estilo, aplicarlo,
renderizar un MP4) corre en las pruebas de `tests/`, y hasta el dialogo con el
puente esta probado contra un puente de mentira. Lo que falta es mirar la
pantalla de Resolve.

    ANTES DE LANZARLO
    1. Abre DaVinci Resolve y entra en un proyecto (vale uno nuevo vacio).
    2. Dentro de Resolve: Workspace > Scripts > Vidorq.
    3. Aqui:  python resolve/comprobar_timeline.py

Fabrica un video de prueba, lo edita con un estilo de subtitulos concreto y lo
monta en Resolve. Al terminar dice que mirar en pantalla, porque eso es lo
unico que un programa no puede comprobar por ti.

No toca ningun proyecto tuyo: crea sus propios timelines, con nombres que
empiezan por `PruebaVidorq_`, y te dice cuales son para que los borres.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ / "engine"))
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))

ESTILO = "punch"          # amarillo con contorno negro: se reconoce de lejos


def falta(que, arreglo):
    print("\n  FALTA: %s" % que)
    print("  %s\n" % arreglo)
    return 1


def main():
    import server

    print("Comprobando el ultimo tramo: el timeline dentro de Resolve.\n")

    estado = server.bridge_status() or {}
    if not estado.get("bridge"):
        if not estado.get("app"):
            return falta("DaVinci Resolve no esta abierto.",
                         "Abrelo y entra en un proyecto, aunque este vacio.")
        return falta("Resolve esta abierto pero el puente no.",
                     "Dentro de Resolve: Workspace > Scripts > Vidorq.")
    if not estado.get("project"):
        return falta("El puente responde pero no hay ningun proyecto abierto.",
                     "Entra en un proyecto de Resolve, aunque sea uno nuevo.")
    print("  puente: si    proyecto: %s" % estado.get("project"))

    casa = Path(tempfile.mkdtemp(prefix="vidorq_comprobar_"))
    try:
        video = casa / "PruebaVidorq.mp4"
        print("  preparando un video de prueba...")
        trozos = []
        for c in ("gray", "darkgreen", "navy"):
            trozos += ["-f", "lavfi", "-i",
                       "color=c=%s:s=720x1280:r=25:d=4" % c]
        trozos += ["-f", "lavfi", "-i",
                   "sine=frequency=440:duration=12:sample_rate=48000"]
        r = subprocess.run(["ffmpeg", "-y", "-v", "error"] + trozos + [
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
            "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-preset",
            "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            str(video)], capture_output=True)
        if r.returncode != 0 or not video.exists():
            return falta("no pude preparar el video de prueba",
                         "mira que `ffmpeg -version` conteste en una terminal")

        edl = [{"start": 0.5, "end": 5.0, "zoom": 1.0, "note": ""},
               {"start": 6.0, "end": 11.0, "zoom": 1.0, "note": ""}]

        def palabras(txt, desde):
            return [{"w": w, "s": round(desde + i * 0.42, 2),
                     "e": round(desde + i * 0.42 + 0.35, 2)}
                    for i, w in enumerate(txt.split())]

        transcript = {"duration": 12.0, "language": "es", "segments": [
            {"text": "esto lo monto vidorq", "start": 1.0, "end": 3.0,
             "words": palabras("esto lo monto vidorq", 1.0)},
            {"text": "dentro de resolve", "start": 6.5, "end": 8.5,
             "words": palabras("dentro de resolve", 6.5)}]}

        print("  montandolo en Resolve con el estilo '%s'..." % ESTILO)
        resultado, nombres = server.output_resolve(
            str(video), edl, transcript, captions=True, preset=ESTILO,
            workdir=casa, anim="", ratio="vertical")
    except Exception as e:
        print("\n  NO SE PUDO: %s: %s" % (type(e).__name__, e))
        print("\n  Copia este mensaje entero: dice exactamente donde se paro.")
        return 1
    finally:
        import shutil
        shutil.rmtree(casa, ignore_errors=True)

    print("\n  %s" % resultado)
    print("  timelines creados: %s" % ", ".join(nombres))
    print("""
  AHORA MIRA LA PANTALLA DE RESOLVE. Tiene que verse:

    1. Un timeline abierto llamado '%s', vertical (1080x1920).
    2. Dos trozos de video en la pista V1, no uno solo ni ninguno.
    3. Subtitulos AMARILLOS con contorno negro sobre el video, en V2.
    4. Si haces doble clic en la pista V2, cada subtitulo sigue siendo un
       Text+ que se puede editar a mano.

  Si las cuatro estan, el ultimo tramo funciona. Si falta alguna, di CUAL:
  cada una se rompe por un motivo distinto.

  Para dejarlo como estaba, borra los timelines '%s'.
""" % (nombres[0] if nombres else "?", "' y '".join(nombres)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
