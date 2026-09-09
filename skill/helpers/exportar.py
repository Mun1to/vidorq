"""Presets de exportacion: un destino elegido, no cuatro mandos que adivinar.

La forma de este modulo copia a proposito la de `looks.py` y `captions.py`: UNA
tabla con los datos, y los dos caminos de salida (el MP4 por ffmpeg y el render
por Resolve) leyendo de ella. Es la misma decision que sostiene los subtitulos:
si el MP4 y Resolve sacan sus numeros de sitios distintos, se separan solos a la
tercera sesion y nadie se entera hasta que alguien compara los dos archivos.

Que decide un preset, y que NO:

- **La forma NO la decide.** Eso ya tiene dueño desde hace tiempo, el selector de
  forma de la ventana (`vidorq_render.RATIOS`), y meter aqui un segundo mando
  para lo mismo termina con los dos diciendo cosas distintas. Cada preset trae un
  `sugiere` que la ventana pone en ese selector al elegirlo, a la vista y
  cambiable.
- **El tamaño solo lo BAJA** (`alto`): un destino no puede pedir mas pixeles de
  los que hay, pero si menos. Mandar un 4K por WhatsApp no lo mejora, lo parte.
- **El caudal de video** (`kbps`): los numeros de YouTube son los suyos, no los
  mios, comprobados el 2026-09-09 en support.google.com/youtube/answer/1722171:
  8 Mbps para 1080p normal, 12 para 1080p a 50 fps o mas, 35-45 para 4K. Pasarse
  no da mas calidad porque la plataforma recomprime igual; quedarse corto si se
  ve.
- **El audio** (`audio_kbps`): 384 kbps en estereo es lo que YouTube pide. Para
  mandar por mensajeria sobra con 128.
- **El volumen** (`lufs`): las plataformas normalizan el volumen a alrededor de
  -14 LUFS. Si el video sale mas alto, LO BAJAN ellas, y bajarlo despues de
  comprimir suena peor que entregarlo ya en su sitio. Un master no se toca, por
  eso su `lufs` es None.

`fps` a None quiere decir "el del original". Cambiar los fotogramas por segundo
sin necesidad obliga a inventar o tirar fotogramas, y eso se ve en un plano con
movimiento.
"""
from __future__ import annotations

# El orden importa: es el que ve el usuario en el desplegable, y el primero es
# el que sale marcado.
PRESETS = {
    "youtube": {
        "sugiere": "wide", "alto": 1080, "fps": None,
        "audio_kbps": 384, "lufs": -14.0,
        "formato": "mp4", "codec": "h264",
        "es": ("YouTube 1080p", "Horizontal, 8 Mbps, el número que ellos piden"),
        "en": ("YouTube 1080p", "Wide, 8 Mbps, the number they ask for"),
    },
    "youtube4k": {
        "sugiere": "wide", "alto": 2160, "fps": None,
        "audio_kbps": 384, "lufs": -14.0,
        "formato": "mp4", "codec": "h264",
        "es": ("YouTube 4K", "2160p a 40 Mbps; si el original no es 4K, baja lo que haga falta"),
        "en": ("YouTube 4K", "2160p at 40 Mbps; drops by itself if the source is smaller"),
    },
    "shorts": {
        "sugiere": "vertical", "alto": 1920, "fps": None,
        "audio_kbps": 256, "lufs": -14.0,
        "formato": "mp4", "codec": "h264",
        "es": ("TikTok, Reels y Shorts", "Vertical 1080x1920, el mismo archivo vale para los tres"),
        "en": ("TikTok, Reels and Shorts", "Vertical 1080x1920, one file for all three"),
    },
    "instagram": {
        "sugiere": "portrait", "alto": 1350, "fps": None,
        "audio_kbps": 256, "lufs": -14.0,
        "formato": "mp4", "codec": "h264",
        "es": ("Instagram, publicación", "Retrato 4:5, que es lo que más alto ocupa en el feed"),
        "en": ("Instagram post", "4:5 portrait, the tallest shape the feed allows"),
    },
    "x": {
        "sugiere": "wide", "alto": 1080, "fps": None,
        "audio_kbps": 192, "lufs": -14.0,
        "formato": "mp4", "codec": "h264",
        "es": ("X (Twitter)", "1080p, y con menos caudal porque recomprime fuerte igual"),
        "en": ("X (Twitter)", "1080p, at a lower rate because it recompresses hard anyway"),
    },
    "mensajeria": {
        "sugiere": "source", "alto": 720, "fps": None,
        "audio_kbps": 128, "lufs": None,
        "formato": "mp4", "codec": "h264",
        "es": ("Mandar por WhatsApp", "720p ligero, para que entre sin que lo destroce"),
        "en": ("Send over WhatsApp", "Light 720p, small enough to survive the app"),
    },
    "master": {
        "sugiere": "source", "alto": 0, "fps": None,
        "cq": 16, "sin_caudal": True,      # por calidad, no por caudal
        "audio_kbps": 320, "lufs": None,
        "formato": "mp4", "codec": "h264",
        "es": ("Master (guardar)", "El tamaño del original y la máxima calidad; el audio no se toca"),
        "en": ("Master (keep)", "Source size at top quality; the audio is left alone"),
    },
}

POR_DEFECTO = "youtube"

# El caudal se sube cuando el video va a 50 fps o mas, que es donde YouTube
# separa sus dos columnas. Por debajo de eso el numero normal ya sobra.
FPS_ALTO = 50

# Caudal de video por SUPERFICIE de salida, como (pixeles, normal, alto fps) en
# kbps. Son los numeros de YouTube, comprobados el 2026-09-09 en
# support.google.com/youtube/answer/1722171, con su tamaño 16:9 pasado a pixeles.
#
# Por pixeles y no por altura, que es lo que parecia y esta mal: un vertical de
# 1080x1920 y un horizontal de 1920x1080 tienen EXACTAMENTE la misma superficie,
# 2,07 millones de pixeles, y necesitan el mismo caudal. Indexando por altura, el
# vertical caia en el escalon de 1440p y pedia 20 Mbps para la misma imagen que
# el horizontal resuelve con 8. Medido con la tabla anterior antes de cambiarla.
#
# Por preset tampoco: pedir "YouTube 4K" con un original de 1080p daba un 1080p
# a 40 Mbps, cinco veces lo que ese tamaño necesita. Eso no es mas calidad, es un
# archivo enorme que tarda cinco veces mas en subir.
CAUDAL = (
    (1280 * 720,   5000,  7500),
    (1920 * 1080,  8000, 12000),
    (2560 * 1440, 16000, 24000),
    (3840 * 2160, 40000, 60000),
)

# Cuanto se aparta el caudal del de YouTube segun el destino. X recomprime
# fuerte pase lo que pase, y en vertical el archivo es mas alto que ancho, que
# es mas superficie en movimiento por la misma altura.
FACTOR = {"x": 0.75, "shorts": 1.25, "instagram": 1.1, "mensajeria": 0.5}


def conocido(nombre):
    """True si ese preset existe. La entrada de fuera se comprueba, no se cree."""
    return isinstance(nombre, str) and nombre in PRESETS


def preset(nombre):
    """El preset pedido, o el de por defecto si el nombre no vale."""
    return PRESETS[nombre if conocido(nombre) else POR_DEFECTO]


def catalogo(lang="es"):
    """La lista para el desplegable, en el orden de la tabla.

    Misma forma que `looks.catalogue` y `captions.preset_list`: la ventana no
    tiene que saber nada del preset salvo su id y como se llama en la pantalla.
    """
    lang = lang if lang in ("es", "en") else "es"
    fuera = []
    for pid, p in PRESETS.items():
        etiqueta, pie = p[lang]
        fuera.append({"id": pid, "label": etiqueta, "hint": pie,
                      "sugiere": p["sugiere"], "alto": p["alto"]})
    return fuera


def caudal(pid, ancho, alto, fps):
    """Los kbps de video para ese tamaño de salida, ese destino y esos fps.

    Devuelve 0 cuando el preset va por calidad y no por caudal (el master), que
    es el caso en el que fijar un numero seria peor: un plano quieto no necesita
    40 Mbps y uno con lluvia no le llega.
    """
    p = preset(pid)
    if p.get("sin_caudal"):
        return 0
    try:
        rapido = float(fps or 0) >= FPS_ALTO
    except (TypeError, ValueError):
        rapido = False
    col = 2 if rapido else 1
    px = max(1, int(ancho or 0) * int(alto or 0))
    base = _entre(px, col)
    return int(round(base * FACTOR.get(pid, 1.0)))


def _entre(px, col):
    """El caudal para esa superficie, interpolado entre los puntos de YouTube.

    Interpolado y no "el escalon de abajo" porque los tamaños reales caen casi
    siempre entre dos: un 1080x1350 de Instagram tiene 1,46 millones de pixeles,
    justo en medio de 720p y 1080p, y redondear hacia abajo le quitaba un tercio
    del caudal que le toca. Fuera de la tabla se usa el extremo tal cual, sin
    extrapolar: por debajo de 720p el archivo ya es pequeño, y por encima de 4K
    no hay dato de ellos que respaldara inventar un numero.
    """
    if px <= CAUDAL[0][0]:
        return CAUDAL[0][col]
    if px >= CAUDAL[-1][0]:
        return CAUDAL[-1][col]
    for (p0, *v0), (p1, *v1) in zip(CAUDAL, CAUDAL[1:]):
        if p0 <= px <= p1:
            t = (px - p0) / float(p1 - p0)
            return v0[col - 1] + t * (v1[col - 1] - v0[col - 1])
    return CAUDAL[1][col]


def salida(nombre, ancho, alto, fps):
    """Todo lo que los dos caminos necesitan saber, ya resuelto.

    Recibe el tamaño que la forma elegida YA decidio (`vidorq_render.frame_for`)
    y solo lo limita si el destino pide menos. A proposito: la forma tiene su
    propio selector en la ventana desde hace tiempo y funciona, asi que un preset
    que decidiera tambien la forma seria un segundo mando para lo mismo, y a la
    tercera edicion los dos dirian cosas distintas. Aqui el preset se ocupa de lo
    que NO tenia dueño: el caudal, el audio y el volumen.

    Lo unico que toca del tamaño es bajarlo. Un destino no puede pedir mas
    pixeles de los que hay, pero si puede pedir menos: mandar un 4K por WhatsApp
    no lo mejora, y a YouTube no le sirve de nada un 1440p si se pidio 1080.
    """
    pid = nombre if conocido(nombre) else POR_DEFECTO
    p = preset(pid)
    ow, oh = _limitar(ancho, alto, p["alto"])
    salida_fps = p["fps"] or fps
    return {
        "preset": pid,
        "ancho": ow, "alto": oh,
        "fps": salida_fps,
        "kbps": caudal(pid, ow, oh, salida_fps),
        "cq": p.get("cq", 21),
        "audio_kbps": int(p["audio_kbps"]),
        "lufs": p["lufs"],
        "formato": p["formato"], "codec": p["codec"],
        # Lo que la ventana pone en el selector de forma al elegir este destino.
        # Es una sugerencia que se ve y se puede cambiar, no una imposicion.
        "sugiere": p["sugiere"],
    }


def _limitar(ancho, alto, tope):
    """El mismo tamaño, o encogido si el destino pide menos altura.

    Encoge por el lado CORTO en vertical, que es lo que la gente quiere decir
    con "1080p": un vertical de 1080x1920 ya es 1080p, y tratarlo por su altura
    lo habria dejado en 607x1080. Se compara la medida menor de las dos contra el
    tope, que es lo mismo que hacen las plataformas.
    """
    ancho, alto = int(ancho or 0), int(alto or 0)
    if not (ancho and alto):
        return 1920, 1080
    if not tope:
        return _par(ancho), _par(alto)            # master: lo que venga
    corto = min(ancho, alto)
    if corto <= tope:
        return _par(ancho), _par(alto)            # ya cabe, no se agranda
    k = tope / float(corto)
    return _par(ancho * k), _par(alto * k)


def _par(n):
    """H.264 no admite lados impares, y ffmpeg falla sin decir por que."""
    n = int(round(n))
    return n if n % 2 == 0 else n + 1


# --------------------------------------------------------------------------- #
# Camino 1: el MP4 por ffmpeg
# --------------------------------------------------------------------------- #

def args_video(sal, encoder):
    """Los argumentos de codec para un segmento, segun el preset y el encoder.

    NVENC y libx264 no llaman igual a lo mismo: uno usa `-cq` y `-b:v`, el otro
    `-crf`. Traducirlo aqui es lo que deja que el resto del renderizador no sepa
    cual de los dos le toco.
    """
    kbps, cq = sal["kbps"], sal["cq"]
    if encoder == "h264_nvenc":
        if kbps:
            # Sin `-cq` a proposito. Mezclar caudal y calidad constante es el
            # error clasico de NVENC y esta MEDIDO aqui: con `-cq 21 -b:v 8000k
            # -maxrate 12000k`, un clip dificil salio a 12884 kbps, o sea que se
            # salto el objetivo Y el techo, porque con `-cq` puesto el caudal
            # pasa a ser una sugerencia. O se manda el caudal, o se manda la
            # calidad; las dos a la vez no mandan ninguna.
            return ["-c:v", "h264_nvenc", "-rc", "vbr",
                    "-b:v", "%dk" % kbps, "-maxrate", "%dk" % int(kbps * 1.25),
                    "-bufsize", "%dk" % (kbps * 2), "-preset", "p5"]
        return ["-c:v", "h264_nvenc", "-rc", "constqp", "-qp", str(cq),
                "-preset", "p5"]
    if kbps:
        return ["-c:v", "libx264", "-b:v", "%dk" % kbps,
                "-maxrate", "%dk" % int(kbps * 1.25),
                "-bufsize", "%dk" % (kbps * 2), "-preset", "veryfast"]
    return ["-c:v", "libx264", "-crf", str(cq), "-preset", "veryfast"]


def filtro_volumen(sal):
    """El filtro de ffmpeg que deja el audio al volumen de las plataformas.

    Una sola pasada a proposito. La de dos mide primero y corrige despues, y
    afina mas, pero cuesta leer el audio entero otra vez y la diferencia no se
    oye en un video hablado. `TP=-1` deja un decibelio de aire para que la
    recompresion de la plataforma no llegue a recortar picos.
    """
    if sal["lufs"] is None:
        return []
    return ["-af", "loudnorm=I=%.1f:TP=-1.0:LRA=11" % sal["lufs"]]


# --------------------------------------------------------------------------- #
# Camino 2: el render dentro de Resolve
# --------------------------------------------------------------------------- #

def ajustes_resolve(sal, carpeta, nombre):
    """Lo que hay que mandarle a `POST /render/settings` del puente.

    Los nombres de las claves son los de la API de scripting de Resolve, no
    inventos: `SetRenderSettings` acepta ese diccionario tal cual. El formato y
    el codec van aparte, por `SetCurrentRenderFormatAndCodec`, y por eso
    `formato_resolve` existe.

    OJO, y esto NO esta medido todavia dentro de Resolve: `VideoQuality` acepta
    un entero de kb/s cuando el codec deja fijar caudal, pero segun el codec
    espera una palabra ("Best", "High"...). Si un preset vuelve con error, es
    aqui donde hay que mirar primero. Hasta que se compruebe en pantalla, el
    camino de Resolve cae al suyo por defecto en vez de romper la exportacion.
    """
    ajustes = {
        "SelectAllFrames": True,
        "TargetDir": str(carpeta),
        "CustomName": str(nombre),
        "FormatWidth": int(sal["ancho"]),
        "FormatHeight": int(sal["alto"]),
        "AudioCodec": "aac",
        "ExportVideo": True,
        "ExportAudio": True,
    }
    if sal["kbps"]:
        ajustes["VideoQuality"] = int(sal["kbps"])
    if sal["fps"]:
        ajustes["FrameRate"] = float(sal["fps"])
    return ajustes


def formato_resolve(sal):
    """El par (formato, codec) para `POST /render/format`."""
    return {"mp4": "mp4"}.get(sal["formato"], "mp4"), "H264"
