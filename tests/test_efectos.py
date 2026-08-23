"""Vidorq distingue un corte seco de una transicion, y de que tipo.

Circulo cerrado, como en test_aprende: se fabrican videos con transiciones de
tipo CONOCIDO (las hace ffmpeg), se le dan al detector como si vinieran de
fuera, y se mira si acierta. No hay forma de hacer trampa, porque el detector
solo ve pixeles y no sabe con que se fabrico el archivo.

Lo que se comprueba y por que:

  - un CORTE seco sale como corte. Es el caso mayoritario de un video de
    redes, y confundirlo con una transicion le diria a un agente que copie
    fundidos donde no los hay.
  - una transicion sale como transicion, y se recorren TODAS las que ffmpeg
    sabe hacer de las que interesan, no dos elegidas a mano.
  - un fundido a NEGRO y uno a BLANCO se dicen por su nombre, porque son los
    dos que si se pueden distinguir mirando el brillo.
  - y lo que NO se distingue no se finge: una disolvencia, un barrido y un
    circulo dan los tres "transicion", que es la respuesta honesta.

Los planos se separan por LUMINANCIA y no por color: el detector mira en
escala de gris, y doce colores distintos pueden ser el mismo gris. Eso ya
costo una vez acusar al detector de un fallo que era del video de prueba.

Necesita ffmpeg. Si no esta, se salta DICIENDOLO.

Se lanza:  python tests/test_efectos.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Grises bien separados. Con textura encima, nunca planos lisos.
TONOS = [0x1a, 0x8c, 0x30, 0xd8]

# tipo de ffmpeg -> lo que Vidorq tiene que contestar.
ESPERADO = {
    "corte": "corte",
    "fade": "transicion",
    "dissolve": "transicion",
    "wipeleft": "transicion",
    "smoothleft": "transicion",
    "circleopen": "transicion",
    "fadeblack": "fundido a negro",
    "fadewhite": "fundido a blanco",
}


def _plano(i, seg, dst):
    v = TONOS[i % len(TONOS)]
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "color=c=0x%02x%02x%02x:s=320x180:d=%.2f:r=25" % (v, v, v, seg),
         "-vf", "noise=alls=12:allf=t+u,drawbox=x=%d:y=40:w=60:h=100:"
                "color=0x%02x%02x%02x:t=fill" % (30 + i * 60, 255 - v,
                                                 255 - v, 255 - v),
         "-pix_fmt", "yuv420p", str(dst)],
        capture_output=True, creationflags=NO_WINDOW)
    return dst


def _video(tipo, casa, dur_trans=0.8):
    a = _plano(0, 2.0, casa / "a.mp4")
    b = _plano(1, 2.0, casa / "b.mp4")
    if not (a.exists() and b.exists()):
        return None
    fuera = casa / ("t_%s.mp4" % tipo)
    if tipo == "corte":
        lista = casa / "l.txt"
        lista.write_text("file '%s'\nfile '%s'\n" % (a.name, b.name))
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat",
                        "-i", "l.txt", "-c", "copy", fuera.name],
                       capture_output=True, cwd=str(casa),
                       creationflags=NO_WINDOW)
    else:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(a), "-i", str(b),
             "-filter_complex",
             "xfade=transition=%s:duration=%.2f:offset=%.2f"
             % (tipo, dur_trans, 2.0 - dur_trans),
             "-pix_fmt", "yuv420p", str(fuera)],
            capture_output=True, creationflags=NO_WINDOW)
    return fuera if fuera.exists() else None


def casos(casa):
    import efectos

    for tipo, quiero in ESPERADO.items():
        v = _video(tipo, casa)
        if not v:
            yield ("ffmpeg sabe hacer %s" % tipo, False, True)
            continue
        t = efectos.transiciones(v)
        yield ("%s: se encuentra el cambio" % tipo, len(t) >= 1, True)
        if not t:
            continue
        # El mas fuerte es el de la union; puede salir alguno mas por el ruido.
        cambio = max(t, key=lambda x: x["fuerza"])
        yield ("%s: se llama %s" % (tipo, quiero), cambio["tipo"], quiero)
        if quiero == "corte":
            yield ("corte: no dura nada", cambio["dura_s"] <= 0.20, True)
        else:
            # La transicion fabricada dura 0,8 s. No se exige que clave el
            # numero, porque se mide a 6 muestras por segundo: se exige que
            # diga que dura ALGO, que es lo que la separa de un corte.
            yield ("%s: dura algo" % tipo, cambio["dura_s"] >= 0.30, True)

    # Y el resumen, que es lo que acaba en la frase que lee un agente.
    v = _video("corte", casa)
    if v:
        r = efectos.resumen(efectos.transiciones(v))
        yield ("un video que solo corta lo dice", r["corta_a_hueso"], True)
    v = _video("fade", casa)
    if v:
        r = efectos.resumen(efectos.transiciones(v))
        yield ("y uno que funde, tambien", r["corta_a_hueso"], False)
    yield ("sin cambios no se inventa un resumen", efectos.resumen([]), None)

    # Un video de UN SOLO plano no tiene transiciones que contar, y eso no es
    # un fallo: es que no hay ninguna.
    solo = _plano(2, 2.0, casa / "solo.mp4")
    if solo.exists():
        import efectos as e
        yield ("un solo plano no da transiciones", e.transiciones(solo), [])


def main():
    if not shutil.which("ffmpeg"):
        print("(salto: no hay ffmpeg en el PATH)")
        return 0
    casa = Path(tempfile.mkdtemp(prefix="vidorq_efectos_"))
    try:
        bad, total = [], 0
        for nombre, got, want in casos(casa):
            total += 1
            if got != want:
                bad.append("%s: esperaba %r y devolvio %r" % (nombre, want, got))
        if bad:
            print("%d de %d casos MAL:\n" % (len(bad), total))
            for line in bad:
                print("  - %s" % line)
            return 1
        print("%d casos, distingue un corte de una transicion." % total)
        return 0
    finally:
        # Los videos pesan y esta carpeta no la vacia nadie.
        shutil.rmtree(casa, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
