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


# --------------------------------------------------------------------------- #
# Como ENTRA un subtitulo
# --------------------------------------------------------------------------- #
# Cuanto tiene que cambiar de alto la mancha de texto para llamarlo "entra
# creciendo", y cuanto tiene que subirle el contraste para llamarlo "entra
# apareciendo". Medido renderizando LAS NUEVE entradas de la casa y midiendolas
# como si vinieran de fuera:
#
#   creciendo    bounce 0,641   pop 0,415   ignite 0,275   zoom 0,170
#   apareciendo  focus  0,690   fade 0,655  rise   0,631
#   de golpe     throb  0,071   none 0,000
#
# El margen entre `zoom` (0,170), que es la que menos crece de las que crecen,
# y `throb` (0,071), que es la que mas de las que no, es de mas del doble.
CRECE = 0.12
ACLARA = 0.45
# Fotogramas seguidos que se miran desde que aparece el texto. La entrada mas
# larga de la casa cabe de sobra en ocho, y pedir mas cuesta descodificar mas.
ENTRADA_FRAMES = 8


def _mancha(f, umbral=60, color=None):
    """(ancho, alto, centro_y, contraste) del texto dentro del cuadro.

    Con `color`, la mancha son los pixeles que se parecen al RELLENO que ya se
    midio, y `f` viene en RGB. Sin el, son los que pasan un umbral de brillo.

    El umbral de brillo solo vale sobre un fondo oscuro de laboratorio: sobre
    metraje de pelicula lo pasa casi todo el cuadro, la mancha nunca
    desaparece y entonces no hay forma de ver DONDE empieza el texto. Medido
    con un Short real, donde devolvia None por eso mismo.
    """
    import numpy as np

    if color is not None:
        obj = np.array(color, dtype="float32") * 255.0
        d = np.abs(f.astype("float32") - obj).sum(axis=2)
        m = d < 110
        fuerza = f.mean(axis=2)
    else:
        m = f > umbral
        fuerza = f
    if m.sum() < 20:
        return None
    filas = np.where(m.any(axis=1))[0]
    cols = np.where(m.any(axis=0))[0]
    return (int(cols[-1] - cols[0] + 1), int(filas[-1] - filas[0] + 1),
            float(filas.mean()), float(fuerza[m].std()))


def entrada(video, at, banda=None, antes=0.35, despues=0.65, color=None):
    """Como entra el subtitulo que aparece cerca del segundo `at`.

    `banda` es (y0, y1) en fraccion del alto, para mirar solo donde esta el
    texto y no el video entero. Devuelve None si no se pudo ver.

    Los fotogramas se piden SEGUIDOS y no muestreados a proposito: una entrada
    dura tres o cuatro fotogramas, y el muestreo normal de la casa (40 por
    video) se la salta entera. Por eso esto es una pasada aparte y solo se
    hace sobre el trozo que interesa.

    Devuelve tres familias y no nueve nombres:

      "creciendo"    la letra cambia de tamaño al entrar
      "apareciendo"  aparece sin cambiar de tamaño
      "de golpe"     ya esta ahi entera en el primer fotograma

    Dentro de cada familia NO se distingue cual es, y se dice: un pop, un
    rebote y un zoom crecen los tres, y ponerle nombre a cual seria una
    respuesta segura y a medias equivocada.

    DA POR HECHO que en ese instante hay texto, porque quien la llama viene de
    `leer.py`, que ya lo ha encontrado. No sabe distinguir una letra de un
    cartel ni de un logo: si se le apunta a un sitio donde no hay subtitulo,
    describira como entra lo que sea que haya ahi.
    """
    import subprocess

    import numpy as np

    import aprende

    w, h, dur = aprende.medidas(video)
    if not (w and h and dur > 0):
        return None
    desde, hasta = max(0.0, at - antes), min(dur, at + despues)
    if hasta <= desde:
        return None
    # A un alto manejable, en gris: aqui solo importa la FORMA de la mancha.
    ALTO = 360
    ancho = int(round(w * ALTO / h))
    ancho -= ancho % 2
    if ancho < 2:
        return None
    filtros = ["select='between(t,%.3f,%.3f)'" % (desde, hasta),
               "setpts=N/FRAME_RATE/TB",
               "scale=%d:%d" % (ancho, ALTO)]
    alto = ALTO
    if banda:
        # El recorte va DESPUES del escalado, para que la banda se mida contra
        # el mismo alto en el que viene expresada.
        y0 = max(0, int(banda[0] * ALTO))
        y1 = min(ALTO, int(banda[1] * ALTO))
        y1 -= (y1 - y0) % 2
        if y1 - y0 >= 8:
            filtros.append("crop=%d:%d:0:%d" % (ancho, y1 - y0, y0))
            alto = y1 - y0
    # En color solo cuando hace falta: si se sabe de que color es el relleno,
    # la mancha se busca por color y no por brillo, que es lo unico que
    # funciona sobre metraje.
    canales = 3 if color is not None else 1
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", ",".join(filtros),
         "-vsync", "0", "-f", "rawvideo",
         "-pix_fmt", "rgb24" if color is not None else "gray", "-"],
        capture_output=True, creationflags=getattr(subprocess,
                                                   "CREATE_NO_WINDOW", 0))
    paso = ancho * alto * canales
    if not r.stdout or len(r.stdout) < paso * 3:
        return None
    forma = (alto, ancho, 3) if canales == 3 else (alto, ancho)
    fs = [np.frombuffer(r.stdout[i * paso:(i + 1) * paso],
                        dtype="uint8").reshape(forma)
          for i in range(len(r.stdout) // paso)]
    medidas = [_mancha(f, color=color) for f in fs]
    # Hay que VER el hueco antes del texto. Si el primer fotograma de la
    # ventana ya tiene texto, no se sabe cuando empezo ni cuanto llevaba ahi,
    # y lo que se mediria seria el final de una entrada anterior o nada. Se
    # devuelve None, que es la respuesta honesta.
    #
    # Importa porque quien llama viene de leer.py, y el instante que da es
    # donde se MUESTREO la linea, no donde entro: puede caer a mitad de frase.
    vacios = [i for i, m in enumerate(medidas) if m is None]
    if not vacios or vacios[0] >= len(medidas) - 3:
        return None
    empieza = next((i for i in range(vacios[0], len(medidas))
                    if medidas[i] is not None), None)
    if empieza is None:
        return None
    vivos = [m for m in medidas[empieza:] if m][:ENTRADA_FRAMES]
    if len(vivos) < 3:
        return None
    altos = [v[1] for v in vivos]
    anchos = [v[0] for v in vivos]
    contrastes = [v[3] for v in vivos]
    fin = max(altos) or 1
    # El RANGO y no el cambio desde el primero: una entrada que empieza grande
    # y se encoge daba cero midiendo desde el primero, siendo la que mas
    # cambia de tamaño de todas.
    crece = (max(altos) - min(altos)) / fin
    aclara = ((max(contrastes) - min(contrastes)) / (max(contrastes) or 1))
    if crece >= CRECE:
        como = "creciendo"
    elif aclara >= ACLARA:
        como = "apareciendo"
    else:
        como = "de golpe"
    return {"como": como, "crece": round(crece, 3),
            "aclara": round(aclara, 3),
            "crece_ancho": round((max(anchos) - min(anchos))
                                 / (max(anchos) or 1), 3),
            "frames": len(vivos)}


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
