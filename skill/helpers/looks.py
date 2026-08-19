"""Filtros de color, definidos una sola vez y aplicados en las dos salidas.

Un look aqui son cuatro numeros de CDL (ASC Color Decision List), que es el
formato que la industria usa para pasarse una correccion primaria entre
programas: pendiente, desplazamiento, potencia y saturacion. La formula es
publica y determinista:

    salida = ( entrada * slope + offset ) ^ power     y luego la saturacion

Que sea determinista es lo que permite lo importante: de los MISMOS numeros
salen las dos salidas de Vidorq.

  Resolve  ->  item.SetCDL(...) por clip. Nativo, exacto, sin archivos, y el
               usuario puede abrir la pagina de color y seguir tocandolo, que
               es el sentido de entregar un timeline en vez de un video.
  MP4      ->  un .cube generado con esa misma formula y aplicado con el
               filtro lut3d de ffmpeg.

Si cada salida tuviera su propia definicion del look, un dia dejarian de
parecerse y nadie sabria cual es el bueno. Con una sola fuente eso no puede
pasar, que es la misma regla que ya siguen los subtitulos.
"""
from __future__ import annotations

import os
from pathlib import Path

# Donde se cachean los .cube. Se generan una vez y valen para siempre, porque
# dependen solo de los numeros de aqui.
CACHE = Path(os.environ.get("APPDATA", ".")) / "Vidorq" / "luts"

# Cuantos puntos por lado tiene la rejilla del LUT. 33 es lo que exporta Resolve
# por defecto y lo que todo el mundo espera; 17 se nota en los degradados.
CUBE_SIZE = 33

# slope, offset y power van por canal (R, G, B). sat es un solo numero.
# Los valores son suaves a proposito: un filtro que se nota mas que el video es
# un filtro que se quita a los dos dias.
PRESETS = {
    "none": {
        "label": {"es": "Sin filtro", "en": "No filter"},
        "note": {"es": "El color tal y como salió de la cámara.",
                 "en": "The colour straight out of the camera."},
        "slope": (1.0, 1.0, 1.0), "offset": (0.0, 0.0, 0.0),
        "power": (1.0, 1.0, 1.0), "sat": 1.0,
    },
    # El unico que no trae numeros: se los calcula mirando el video. Aqui esta
    # con los neutros para que exista en el catalogo y se pueda elegir; los de
    # verdad los pone `autocolor` en cada edicion.
    "auto": {
        "label": {"es": "Automático", "en": "Auto"},
        "note": {"es": "Mira TU vídeo y le corrige los niveles, la dominante de "
                       "color y la saturación. No impone un look: arregla el que hay.",
                 "en": "Looks at YOUR video and fixes its levels, colour cast and "
                       "saturation. It imposes no look: it fixes the one you have."},
        "slope": (1.0, 1.0, 1.0), "offset": (0.0, 0.0, 0.0),
        "power": (1.0, 1.0, 1.0), "sat": 1.0,
    },
    "cine": {
        "label": {"es": "Cine", "en": "Cinema"},
        "note": {"es": "Sombras levantadas y algo desaturado. El look de pelicula "
                       "sin pasarse.",
                 "en": "Lifted shadows, slightly desaturated. The film look without "
                       "overdoing it."},
        "slope": (0.95, 0.96, 1.02), "offset": (0.012, 0.010, 0.020),
        "power": (1.05, 1.03, 0.98), "sat": 0.88,
    },
    "calido": {
        "label": {"es": "Cálido", "en": "Warm"},
        "note": {"es": "Más rojo y menos azul, como una tarde. Favorece la piel.",
                 "en": "More red, less blue, like late afternoon. Kind to skin."},
        "slope": (1.06, 1.01, 0.93), "offset": (0.008, 0.002, -0.006),
        "power": (0.98, 1.0, 1.03), "sat": 1.05,
    },
    "frio": {
        "label": {"es": "Frio", "en": "Cool"},
        "note": {"es": "Azulado y limpio. Para tecnologia y para interiores feos.",
                 "en": "Blue and clean. For tech, and for ugly interiors."},
        "slope": (0.93, 0.99, 1.08), "offset": (-0.004, 0.0, 0.010),
        "power": (1.03, 1.0, 0.96), "sat": 0.97,
    },
    "verano": {
        "label": {"es": "Verano", "en": "Summer"},
        "note": {"es": "Contraste y color subidos. Exteriores y viajes.",
                 "en": "Contrast and colour up. Outdoors and travel."},
        "slope": (1.08, 1.05, 1.0), "offset": (-0.010, -0.008, -0.006),
        "power": (0.94, 0.95, 0.97), "sat": 1.22,
    },
    "noche": {
        "label": {"es": "Noche", "en": "Night"},
        "note": {"es": "Oscuro y azulado, con las luces marcadas.",
                 "en": "Dark and blue, with the lights standing out."},
        "slope": (0.86, 0.90, 1.02), "offset": (-0.012, -0.008, 0.006),
        "power": (1.12, 1.10, 1.02), "sat": 0.92,
    },
    "bn": {
        "label": {"es": "Blanco y negro", "en": "Black and white"},
        "note": {"es": "Sin color y con algo más de contraste.",
                 "en": "No colour, and a little more contrast."},
        "slope": (1.04, 1.04, 1.04), "offset": (-0.006, -0.006, -0.006),
        "power": (0.97, 0.97, 0.97), "sat": 0.0,
    },
    "vintage": {
        "label": {"es": "Vintage", "en": "Vintage"},
        "note": {"es": "Negros lavados y tono amarillento, como cinta vieja.",
                 "en": "Washed blacks and a yellow cast, like old tape."},
        "slope": (0.93, 0.92, 0.86), "offset": (0.035, 0.028, 0.020),
        "power": (1.02, 1.02, 1.06), "sat": 0.80,
    },
}

DEFAULT = "none"
# Coeficientes de luminancia de Rec.709, que es el espacio en el que trabaja
# todo esto. Usar los de Rec.601 aqui vuelve verdes los grises.
LUMA = (0.2126, 0.7152, 0.0722)


def catalogue(lang="es"):
    """Lo que la interfaz necesita para dibujar el selector."""
    return [{"id": lid, "label": p["label"].get(lang, p["label"]["en"]),
             "note": p["note"].get(lang, p["note"]["en"])}
            for lid, p in PRESETS.items()]


def preset(name):
    return PRESETS.get(name) or PRESETS[DEFAULT]


def apply_cdl(rgb, p):
    """La formula, sobre un color. Un solo sitio, para las dos salidas."""
    out = []
    for i, v in enumerate(rgb):
        x = v * p["slope"][i] + p["offset"][i]
        # Negativo elevado a una potencia no es un numero real; ffmpeg y Resolve
        # lo recortan a cero y aqui se hace lo mismo para no divergir de ellos.
        x = 0.0 if x <= 0.0 else x ** p["power"][i]
        out.append(x)
    sat = p["sat"]
    if sat != 1.0:
        grey = sum(c * k for c, k in zip(out, LUMA))
        out = [grey + (c - grey) * sat for c in out]
    return [min(1.0, max(0.0, c)) for c in out]


def cube(name, p=None, key=""):
    """El .cube de este look, generado una vez y cacheado.

    `p` permite pasar unos numeros calculados en vez de los del catalogo, que es
    lo que hace el color automatico: cada video tiene los suyos. En ese caso hace
    falta una `key` que los distinga, porque dos videos con el mismo nombre de
    look no comparten correccion.

    Texto plano: una cabecera y SIZE^3 lineas con el color de salida. Con 33
    puntos son 35.937 lineas, que se escriben en unas decimas y se leen desde
    disco para siempre.
    """
    p = p or preset(name)
    dest = CACHE / ("%s%s_%d.cube" % (name, ("_" + key) if key else "", CUBE_SIZE))
    if dest.exists():
        return dest
    CACHE.mkdir(parents=True, exist_ok=True)
    n = CUBE_SIZE
    step = 1.0 / (n - 1)
    lines = ['TITLE "Vidorq %s"' % name, "LUT_3D_SIZE %d" % n,
             "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0", ""]
    # El orden lo fija el formato: el rojo es el que corre mas rapido.
    for b in range(n):
        for g in range(n):
            for r in range(n):
                out = apply_cdl((r * step, g * step, b * step), p)
                lines.append("%.6f %.6f %.6f" % tuple(out))
    tmp = dest.with_suffix(".part%d.cube" % os.getpid())
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(dest)
    return dest


def ffmpeg_filter(name, p=None, key=""):
    """El trozo de -vf que aplica este look, o None si no hay nada que aplicar."""
    if not name or name == DEFAULT:
        return None
    if p and _is_neutral(p):
        # El automatico sobre un video que ya esta bien: no hay nada que aplicar
        # y meter un LUT identidad solo cuesta una pasada de mas.
        return None
    path = str(cube(name, p, key)).replace("\\", "/")
    # La ruta va entre comillas simples y con los dos puntos escapados con UNA
    # barra. En una cadena de filtros los dos puntos separan argumentos, asi que
    # "C:/..." sin escapar parte el filtro por la mitad y ffmpeg contesta "No
    # option name near '/Users/...'". Con dos barras tampoco vale. Probadas las
    # cuatro formas contra ffmpeg: esta y pasar el nombre pelado con el cwd en
    # la carpeta del .cube; se usa esta porque no obliga a copiar un mega por
    # render.
    return "lut3d=file='%s'" % path.replace(":", "\\:")


def _is_neutral(p):
    return (tuple(p["slope"]) == (1.0, 1.0, 1.0)
            and tuple(p["offset"]) == (0.0, 0.0, 0.0)
            and tuple(p["power"]) == (1.0, 1.0, 1.0)
            and p["sat"] == 1.0)


def resolve_cdl(name, node=1, p=None):
    """Lo que espera item.SetCDL: los mismos numeros, en su formato.

    Resolve los quiere como cadenas de tres numeros separados por espacios.
    """
    p = p or preset(name)
    return {"NodeIndex": str(node),
            "Slope": "%.4f %.4f %.4f" % p["slope"],
            "Offset": "%.4f %.4f %.4f" % p["offset"],
            "Power": "%.4f %.4f %.4f" % p["power"],
            "Saturation": "%.4f" % p["sat"]}
