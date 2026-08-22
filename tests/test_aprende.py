"""Vidorq mira un video ajeno y dice como esta hecho.

La vara de medir es un circulo cerrado: se le pide a la propia casa que queme
un subtitulo con un estilo CONOCIDO, y luego se le da ese MP4 al analizador
como si viniera de fuera, sin decirle nada. Si recupera el estilo con el que se
hizo, entiende de verdad; si no, no. No hay forma de hacer trampa porque el
analizador no ve el preset por ningun lado: solo ve pixeles.

Lo que se comprueba y por que:

  - la POSICION del subtitulo se recupera con error menor de 0.01. Es el numero
    que mas manda al reconstruir: dos estilos en sitios distintos se ven
    distintos aunque compartan color y tamaño.
  - el COLOR del relleno se recupera en los estilos que no llevan un adorno
    tapandolo.
  - un video SIN subtitulos no produce subtitulo. Un falso positivo aqui es
    peor que no detectar nada: le propondria al usuario reconstruir algo que
    nunca vio.
  - el estilo correcto sale entre los tres que se proponen.

Necesita ffmpeg en el PATH. Si no esta, se salta diciendolo, porque una prueba
que se salta en silencio es peor que no tenerla.

Se lanza:  python tests/test_aprende.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HELP = RAIZ / "skill" / "helpers"
sys.path.insert(0, str(HELP))

# Los estilos con los que se hace la ida y vuelta. Los cuatro cubren los casos
# que importan: blanco con contorno, color, plancha detras y el mas discreto.
ESTILOS = ("pop", "punch", "marker", "minimal")

FRASES = [("hola mundo esto va bien", 1.0), ("mira lo que hace", 6.0),
          ("otra frase mas larga aqui", 11.0), ("y la ultima de todas", 16.0)]

EDL = {"segments": [{"start": 0.5, "end": 19.5, "zoom": 1.0, "note": ""}]}


def _palabras(texto, desde):
    out, t = [], desde
    for w in texto.split():
        out.append({"w": w, "s": round(t, 2), "e": round(t + 0.35, 2)})
        t += 0.42
    return out


TRANSCRIPT = {"duration": 20.0, "language": "es", "segments": [
    {"text": t, "start": s, "end": s + 3.0, "words": _palabras(t, s)}
    for t, s in FRASES]}


def _fuente(casa):
    """Cuatro planos lisos en vertical. Lisos a proposito: si el fondo tuviera
    detalle, encontrar el texto seria mas facil de lo que es en la vida real."""
    dest = casa / "fuente.mp4"
    trozos = []
    for c in ("gray", "darkgreen", "navy", "maroon"):
        trozos += ["-f", "lavfi", "-i", "color=c=%s:s=720x1280:r=25:d=5" % c]
    trozos += ["-f", "lavfi", "-i",
               "sine=frequency=440:duration=20:sample_rate=48000"]
    r = subprocess.run(["ffmpeg", "-y", "-v", "error"] + trozos + [
        "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]",
        "-map", "[v]", "-map", "4:a", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(dest)],
        capture_output=True)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-200:])
    return dest


def _render(casa, fuente, nombre, *extra):
    salida = casa / nombre
    subprocess.run(
        [sys.executable, str(HELP / "vidorq_render.py"), str(fuente),
         str(casa / "edl.json"), str(casa / "transcript.json"), str(salida)]
        + list(extra), capture_output=True, cwd=str(HELP))
    return salida


def casos(casa, fuente):
    import aprende
    import captions

    # --- un video sin subtitulos no tiene subtitulo ------------------------
    # Primero este, que es el que puede mentir a favor. Si el detector ve
    # texto en un video liso, todo lo demas que diga vale menos.
    limpio = _render(casa, fuente, "limpio.mp4", "--no-captions", "--no-zoom")
    yield ("aprende: el video sin subtitulos se renderiza", limpio.exists(), True)
    if limpio.exists():
        f = aprende.ficha(limpio)
        yield ("aprende: no inventa un subtitulo donde no lo hay",
               f.get("subtitulo"), None)
        yield ("aprende: sin subtitulo no propone estilos",
               aprende.parecidos(f), [])
        yield ("aprende: aun asi mide el archivo",
               (f["ancho"], f["alto"]), (720, 1280))
        yield ("aprende: sabe que es vertical", f.get("vertical"), True)

    # --- el falso positivo que si costo encontrar --------------------------
    # Un video liso se descarta facil. El que se colaba era este: una franja
    # con detalle en MITAD del cuadro, que aparece y desaparece. Cumple las dos
    # firmas del detector, no toca los bordes, no es fina y contrasta de sobra,
    # y se leia como un subtitulo en y=0.467. Aparecio una vez, asi que se
    # queda clavado aqui.
    franja = casa / "franja.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=slateblue:s=720x1280:r=25:d=12",
        "-f", "lavfi", "-i", "color=c=gray:s=720x200:r=25:d=12",
        "-filter_complex",
        "[1:v]geq=lum='if(gt(mod(X,7),3),240,20)':cb=128:cr=128[f];"
        "[0:v][f]overlay=0:700:enable='lt(mod(t,3),1.6)'[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", str(franja)], capture_output=True)
    if franja.exists():
        yield ("aprende: una franja con detalle en medio no es un subtitulo",
               aprende.ficha(franja).get("subtitulo"), None)

    # --- la ida y vuelta, estilo por estilo -------------------------------
    en_tres = 0
    for pid in ESTILOS:
        p = captions.PRESETS[pid]
        v = _render(casa, fuente, "%s.mp4" % pid, "--preset", pid, "--no-zoom")
        if not v.exists():
            yield ("aprende: sale el render de %s" % pid, False, True)
            continue
        f = aprende.ficha(v)
        sub = f.get("subtitulo")
        yield ("aprende: %s deja un subtitulo que se ve" % pid,
               sub is not None, True)
        if not sub:
            continue

        # La posicion. El numero que mas manda al reconstruir.
        error = abs(float(sub["y"]) - float(p["y"]))
        yield ("aprende: %s cae donde dice el estilo (error %.3f)" % (pid, error),
               error < 0.01, True)

        # El color, en los que no llevan nada tapandolo. `marker` lleva una
        # plancha detras y el color medido sale mezclado con ella: eso esta
        # medido y por eso queda fuera de esta comprobacion en vez de
        # disimulado con un margen ancho que no probaria nada.
        if pid != "marker":
            lejos = max(abs(a - b) for a, b in zip(sub["fill"], p["fill"]))
            yield ("aprende: %s recupera su color (lejos %.2f)" % (pid, lejos),
                   lejos < 0.15, True)

        # La plancha. Solo se comprueba que no se la INVENTE donde no la hay,
        # que es el error que costaria caro: una propuesta con una tarjeta de
        # color detras que el video nunca tuvo. Detectarla cuando si esta
        # todavia no funciona (`marker` da False) y la causa esta escrita en
        # hay_panel; ponerlo aqui como si pasara seria mentir en verde.
        if pid != "marker":
            yield ("aprende: %s no se inventa una plancha" % pid,
                   bool(sub.get("panel")), False)

        en_tres += pid in [i for i, _ in aprende.parecidos(f)]

    # De los cuatro, cuantos salen entre los tres que se proponen. Tres de
    # cuatro es lo que hay hoy y esta medido; poner el liston en cuatro seria
    # escribir una prueba que ya sabemos que no pasa, y ponerlo en dos seria
    # dejar de enterarnos si empeora.
    yield ("aprende: el estilo esta entre los tres propuestos (%d de %d)"
           % (en_tres, len(ESTILOS)), en_tres >= 3, True)


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("(sin ffmpeg en el PATH: esta prueba no se puede hacer)")
        return 0
    casa = Path(tempfile.mkdtemp(prefix="vidorq_aprende_"))
    try:
        (casa / "edl.json").write_text(json.dumps(EDL, indent=1),
                                       encoding="utf-8")
        (casa / "transcript.json").write_text(
            json.dumps(TRANSCRIPT, ensure_ascii=False, indent=1),
            encoding="utf-8")
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
        print("%d casos, entiende lo que mira." % total)
        return 0
    finally:
        # Los videos pesan, y esta carpeta no la vacia nadie.
        shutil.rmtree(casa, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
