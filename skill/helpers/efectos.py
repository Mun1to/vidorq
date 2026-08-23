"""Que hay entre un plano y el siguiente: un corte seco o una transicion.

Hasta ahora Vidorq no tenia ni un campo para esto. Sabia CUANTOS planos hay y
cada cuanto corta, pero no si el montaje corta a hueso o si funde, que es de
las primeras cosas que alguien ve de un video ajeno y de las que quiere copiar.

La medida sale de lo que `vision.shots()` ya calcula, sin una segunda pasada
por el archivo: el `track` trae cuanto cambia la imagen en cada muestra, y un
corte y una transicion se ven distintos ahi.

  corte        un pico solitario. El cambio entero cabe en una muestra.
  transicion   una meseta. El cambio se reparte en varias muestras seguidas.

Medido con transiciones fabricadas por ffmpeg, o sea de tipo CONOCIDO, y la
separacion no admite discusion:

    corte        ancho 1   (pico de 110 entre valores de 0,1)
    circleopen   ancho 3
    smoothleft   ancho 5
    fade         ancho 6
    dissolve     ancho 6
    wipeleft     ancho 6
    fadeblack    ancho 6   + el brillo toca 0,00
    fadewhite    ancho 6   + el brillo toca 1,00

  Lo que SI se distingue: corte, fundido a negro, fundido a blanco, y "hay una
  transicion aqui" con su duracion.

  Lo que NO, y se dice en vez de fingirlo: una disolvencia de un barrido de un
  circulo. Los tres dan la misma meseta, porque lo que cambia entre ellos es
  la FORMA de la mezcla y esta medida solo mira cuanto cambia, no donde. Para
  separarlos habria que mirar el reparto espacial del cambio, y eso es otra
  pasada mas cara que hoy no se paga.
"""
from __future__ import annotations

# Cada muestra de vision.shots() dura esto. Se calcula y no se escribe a mano,
# para que no se separen si alguien cambia el muestreo.
def _paso():
    import vision
    return 1.0 / float(vision.SAMPLE_FPS)


# Por encima de esto (veces la mediana del video) una muestra cuenta como
# "aqui esta pasando algo". El suelo de 2.0 es para un video tan quieto que su
# mediana es casi cero, donde cualquier cosa multiplicada sigue siendo nada.
#
# Va contra la MEDIANA y no contra el pico a proposito: contra el pico, un
# fundido a blanco (pico de 163 sobre una meseta de 40) contaba una sola
# muestra y salia clasificado como corte seco.
VIVO = 4.0
SUELO = 2.0
# Con una sola muestra por encima es un corte. Con dos ya se reparte, y todas
# las transiciones medidas dan tres o mas.
CORTE = 1
# El brillo por debajo o por encima del cual se llama fundido a negro o a
# blanco. Medido: fadeblack toca 0,00 y fadewhite toca 1,00, y un video normal
# se queda entre 0,18 y 0,54.
NEGRO, BLANCO = 0.06, 0.94


def transiciones(video, planos=None, track=None):
    """Los cambios de plano, cada uno con lo que hay entre los dos.

    Devuelve [] si no se pudo mirar, que no es lo mismo que "no hay ninguno":
    un video de un solo plano devuelve [] y tambien uno que no se pudo abrir,
    asi que quien llame mira `planos` para saber cual de las dos.
    """
    import numpy as np

    try:
        import vision
    except ImportError:
        return []
    if planos is None or track is None:
        try:
            planos, track = vision.shots(video)
        except Exception:
            return []
    if not track or len(track) < 4 or len(planos) < 2:
        return []

    d = np.array([p["diff"] for p in track], dtype="float32")
    br = np.array([p.get("brightness", 0.5) for p in track], dtype="float32")
    tiempos = np.array([p["t"] for p in track], dtype="float32")
    med = float(np.median(d[1:])) if len(d) > 1 else 0.0
    umbral = max(med * VIVO, SUELO)
    paso = _paso()

    out = []
    for p in planos[1:]:
        borde = float(p["start"])
        # La muestra donde cae ese limite de plano.
        i = int(np.argmin(np.abs(tiempos - borde)))
        # Y cuantas muestras SEGUIDAS a su alrededor estan por encima del
        # umbral. Se camina hacia los dos lados desde la mas alta de la zona,
        # porque el limite que da vision.shots() puede caer en el principio de
        # la meseta y no en su centro.
        zona = range(max(1, i - 6), min(len(d), i + 7))
        pico = max(zona, key=lambda k: float(d[k]))
        if float(d[pico]) < umbral:
            continue                       # aqui no cambia nada medible
        a = b = pico
        while a - 1 >= 1 and d[a - 1] >= umbral:
            a -= 1
        while b + 1 < len(d) and d[b + 1] >= umbral:
            b += 1
        ancho = b - a + 1
        # El brillo DENTRO de la transicion, que es lo que separa un fundido a
        # negro de una disolvencia cualquiera.
        dentro = br[a:b + 1]
        if ancho <= CORTE:
            tipo = "corte"
        elif float(dentro.min()) <= NEGRO:
            tipo = "fundido a negro"
        elif float(dentro.max()) >= BLANCO:
            tipo = "fundido a blanco"
        else:
            # Se dice "transicion" y no "disolvencia": esta medido que esta
            # cuenta no separa una disolvencia de un barrido, y ponerle nombre
            # seria una respuesta segura y a medias equivocada.
            tipo = "transicion"
        out.append({
            "t": round(float(tiempos[a]), 2),
            "tipo": tipo,
            "dura_s": round(ancho * paso, 2),
            "fuerza": round(float(d[pico]), 1),
        })
    return out


def resumen(trans):
    """Los cambios contados por tipo, para decirlo en una frase."""
    if not trans:
        return None
    cuenta = {}
    for t in trans:
        cuenta[t["tipo"]] = cuenta.get(t["tipo"], 0) + 1
    fundidos = [t for t in trans if t["tipo"] != "corte"]
    return {
        "total": len(trans),
        "por_tipo": cuenta,
        "corta_a_hueso": cuenta.get("corte", 0) == len(trans),
        "dura_media_s": (round(sum(t["dura_s"] for t in fundidos)
                               / len(fundidos), 2) if fundidos else 0.0),
    }
