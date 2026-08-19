"""Los dos relojes de Vidorq, fijados.

En este programa un segundo no significa nada hasta que se dice de que reloj es:

  el del ORIGINAL   el archivo que arrastro el usuario. Es donde vive el EDL,
                    donde estan los tiempos de la transcripcion y con lo que
                    ffmpeg busca en el archivo.
  el del MONTAJE    lo que se ve despues de cortar. Es lo unico que el usuario
                    puede mirar en un retoque, asi que es lo que quiere decir
                    cuando dice "el segundo 12".

Los dos empiezan igual y se separan un poco mas con cada corte, asi que un fallo
aqui no revienta: desplaza. Y un subtitulo diez segundos tarde no parece un
error de reloj, parece que el programa es malo.

Esto ya paso dos veces:

  el cartel en el MP4       se armaba en reloj de montaje y el renderizador lo
                            filtraba con el del original. No salia desplazado:
                            no salia. Cero lineas de Dialogue.
  editar leyendo            el panel mandaba el segundo del ORIGINAL y el motor
                            lo leia como del montaje. En el video de prueba eran
                            once segundos de diferencia a los treinta de
                            metraje, y mas cuanto mas avanzado el video.

Sin modelo, sin red y sin video: son cuentas.

Se lanza:  python tests/test_relojes.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))
sys.path.insert(0, str(RAIZ / "engine"))

import captions as cap  # noqa: E402

_argv, sys.argv = sys.argv, ["test"]
import server  # noqa: E402
sys.argv = _argv

# Un EDL que tira los cinco primeros segundos y otros cinco por el medio, que es
# exactamente lo que hace el corte de silencios.
EDL = [{"start": 5.0, "end": 15.0}, {"start": 20.0, "end": 30.0}]


def casos():
    """Cada caso devuelve (nombre, lo que salio, lo que tenia que salir)."""
    # --- ida y vuelta entre los dos relojes ---------------------------------
    yield "to_edited(5) = principio del montaje", server.to_edited(5.0, EDL), 0.0
    yield "to_edited(14) = 9 del montaje", server.to_edited(14.0, EDL), 9.0
    # El primer segundo del segundo trozo va detras de los diez del primero.
    yield "to_edited(20) = 10 del montaje", server.to_edited(20.0, EDL), 10.0
    yield "to_edited(25) = 15 del montaje", server.to_edited(25.0, EDL), 15.0
    # Un segundo que cayo DENTRO de un corte no existe en el montaje. Devolver
    # el mas cercano seria peor: colocaria la cosa en un sitio plausible y
    # equivocado, que es el fallo que no se ve.
    yield "to_edited(17) esta cortado", server.to_edited(17.0, EDL), None
    yield "to_edited(2) esta cortado", server.to_edited(2.0, EDL), None

    yield "to_original(0) = 5 del original", server.to_original(0.0, EDL), 5.0
    yield "to_original(9) = 14 del original", server.to_original(9.0, EDL), 14.0
    yield "to_original(15) = 25 del original", server.to_original(15.0, EDL), 25.0
    # El borde entre dos trozos es UN segundo del montaje y dos del original: el
    # final del que se va y el principio del que entra. Lo que se ve ahi es el
    # que entra, asi que se resuelve al de entrar. Con el otro criterio caia en
    # material cortado, o sea en un fotograma que ya no existe.
    yield "el borde cae en el plano que entra", server.to_original(10.0, EDL), 20.0
    # Y el final del montaje si es el final del ultimo trozo, porque ahi no hay
    # siguiente al que pasarle el segundo.
    yield "el final del montaje es el del ultimo trozo", server.to_original(20.0, EDL), 30.0
    yield "to_original(99) se sale", server.to_original(99.0, EDL), None

    # Ida y vuelta: lo que sobrevive al corte tiene que volver a su sitio.
    for t in (5.0, 9.5, 14.9, 20.0, 26.25, 29.9):
        ida = server.to_edited(t, EDL)
        yield ("ida y vuelta del segundo %.2f" % t,
               round(server.to_original(ida, EDL), 3), t)

    # --- un cartel se escribe en el reloj del MONTAJE -----------------------
    # `titles_into` recibe el segundo del ORIGINAL (ya traducido por el motor) y
    # devuelve el del montaje, porque lo que arma es la lista de subtitulos.
    chunks = server.titles_into([], [{"do": "title", "at": 6.0, "secs": 2.0,
                                      "text": "HOLA"}], EDL)
    yield "el cartel del segundo 6 cae en el 1 del montaje", chunks[0]["start"], 1.0
    yield "y dura los 2 segundos pedidos", chunks[0]["end"], 3.0

    # --- y el renderizador tiene que leerlo en ese mismo reloj --------------
    # Esta es la que fallaba. Se cuenta cuantas lineas de Dialogue salen con
    # cada reloj: con el del original salian CERO, o sea que el cartel no
    # aparecia en el MP4 y nadie decia nada.
    d = Path(tempfile.mkdtemp())
    yield ("con el reloj del original el cartel no se dibuja",
           _dialogos(d / "mal.ass", chunks, EDL[0]["start"], EDL[0]["end"]), 0)
    yield ("con el del montaje se dibuja una vez",
           _dialogos(d / "bien.ass", chunks, 0.0, EDL[0]["end"] - EDL[0]["start"]), 1)
    yield ("y no se repite en el segundo trozo",
           _dialogos(d / "bien2.ass", chunks, 10.0, 20.0), 0)


def _dialogos(path, chunks, desde, hasta):
    cap.to_ass(path, chunks, desde, hasta, 1920, 1080)
    return sum(1 for line in path.read_text(encoding="utf-8-sig").splitlines()
               if line.startswith("Dialogue"))


def main():
    mal, n = [], 0
    for nombre, got, want in casos():
        n += 1
        if got != want:
            mal.append("%s: esperaba %r y devolvio %r" % (nombre, want, got))
    if mal:
        print("%d de %d casos MAL:\n" % (len(mal), n))
        for line in mal:
            print("  - %s" % line)
        return 1
    print("%d casos, todos bien." % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
