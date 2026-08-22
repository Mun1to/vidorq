"""Lo que Vidorq entiende mirando un video que edito otro.

El usuario pega un video que le gusto y quiere ESO. Este modulo lo mira y
devuelve como esta hecho, en la misma forma que ya tiene el catalogo de la
casa: la ficha que sale de aqui se parece a una entrada de captions.PRESETS,
no a un informe en prosa. Esa es la decision de diseño que sostiene el resto,
porque asi extraer y reconstruir son la MISMA estructura y no hay que traducir
nada por el camino.

Todo lo de aqui es aritmetica sobre fotogramas, sin modelo y sin red. La vista
cara (vision.describe con un modelo local) es otra pasada y no entra aqui.

  ¿Y por que no se lee el texto de los subtitulos?
  Porque para RECONSTRUIR un subtitulo hace falta su forma (donde cae, de que
  tamaño, de que color, con que contorno), no sus palabras: las palabras las
  pone el usuario con su propio video. Leer el texto ademas mete en el sistema
  la frase de un desconocido, que es entrada no confiable y hay que tratarla
  como tal (regla AL). Aqui simplemente no hace falta.

El video que se analiza es AJENO: se mira para sacar el patron y no se copia
nada de su contenido.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Cuantos fotogramas se miran. 40 reparte bien sin que la espera se note: por
# debajo de ~25 un subtitulo corto puede caer entre dos muestras y no salir.
MUESTRAS = 40
# El alto al que se reducen. 360 conserva el contorno de las letras (que es lo
# que las distingue de un fondo) y hace las cuentas veinte veces mas baratas
# que a tamaño completo.
ALTO = 360

# Una fila cuenta como parte del texto si su señal pasa este trozo del maximo.
# Medido contra videos renderizados por la propia casa: con 0.5 el contorno
# negro se queda fuera y el tamaño sale corto; con 0.25 entra medio fondo.
UMBRAL = 0.35

# Lo que el umbral se come por arriba. Las primeras filas de una linea de texto
# son las puntas de cuatro o cinco letras y casi no dan señal, asi que la banda
# empieza un poco mas abajo de donde empieza el texto. Medido renderizando los
# diez presets del catalogo y comparando con su `y` declarado: la diferencia
# salio entre 0.008 y 0.020, con media 0.014 y sin depender del tamaño.
BORDE_ALTO = 0.014


def _ffprobe(video, campos):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", campos, "-of", "csv=p=0:s=x", str(video)],
        capture_output=True, text=True, creationflags=NO_WINDOW)
    return r.stdout.strip()


def medidas(video):
    """(ancho, alto, duracion) del archivo, preguntadas, no supuestas."""
    forma = _ffprobe(video, "stream=width,height")
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(video)],
        capture_output=True, text=True, creationflags=NO_WINDOW)
    try:
        w, h = [int(v) for v in forma.split("x")[:2]]
        return w, h, float(r.stdout.strip())
    except (ValueError, IndexError):
        return 0, 0, 0.0


def fotogramas(video, n=MUESTRAS, alto=ALTO):
    """n fotogramas repartidos por el video, como arrays (alto, ancho, 3).

    Se piden a ffmpeg en una sola pasada. Pedirlos de uno en uno con -ss cuesta
    una apertura del archivo por fotograma y se nota en un video largo.
    """
    import numpy as np

    w0, h0, dur = medidas(video)
    if not (w0 and h0 and dur > 0):
        return [], 0.0
    ancho = int(round(w0 * alto / h0))
    ancho -= ancho % 2
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", "fps=%.6f,scale=%d:%d" % (n / dur, ancho, alto),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, creationflags=NO_WINDOW)
    paso = ancho * alto * 3
    return ([np.frombuffer(r.stdout[i * paso:(i + 1) * paso],
                           dtype="uint8").reshape(alto, ancho, 3)
             for i in range(len(r.stdout) // paso)], dur)


def banda_de_texto(frames):
    """La franja donde hay texto quemado, como (fila_arriba, fila_abajo).

    Un subtitulo tiene DOS firmas a la vez y hacen falta las dos:

      detalle    los bordes de las letras son muchos cambios seguidos en
                 horizontal, mas de los que tiene cualquier fondo
      presencia  aparece y desaparece

    Un logo fijo cumple la primera y falla la segunda. Un fondo que cambia de
    plano cumple la segunda y falla la primera. Multiplicarlas deja solo lo que
    es texto puesto encima. Devuelve None si el video no lleva texto.
    """
    import numpy as np

    if len(frames) < 4:
        return None
    perfiles = np.array([np.abs(np.diff(a.mean(axis=2), axis=1)).mean(axis=1)
                         for a in frames])
    score = perfiles.std(axis=0) * perfiles.mean(axis=0)
    if not np.isfinite(score).all() or score.max() <= 0:
        return None
    score = score / score.max()
    filas = np.where(score > UMBRAL)[0]
    if len(filas) == 0:
        return None
    grupos, actual = [], [int(filas[0])]
    for f in filas[1:]:
        if f - actual[-1] <= 3:                 # un hueco de 3 filas es la
            actual.append(int(f))               # separacion entre dos lineas
        else:                                   # del mismo subtitulo
            grupos.append(actual)
            actual = [int(f)]
    grupos.append(actual)
    mejor = max(grupos, key=lambda g: float(score[g].sum()))
    a0, a1 = mejor[0], mejor[-1]
    alto = len(score)
    # Dos descartes de forma. El score se normaliza contra su propio maximo, y
    # eso quiere decir que un video liso SIEMPRE tiene una fila ganadora: la
    # del ruido mas alto. Sin esto, un video sin subtitulos devolvia una banda
    # de cuatro filas pegada al borde de arriba y el usuario habria visto una
    # propuesta para reconstruir algo que nunca estuvo ahi.
    if a0 <= alto * 0.02 or a1 >= alto * 0.99:
        return None                              # pegada a un borde
    if (a1 - a0) < alto * 0.008:
        return None                              # mas fina que una letra
    # Y el tercero, que es de sitio y no de forma: un subtitulo vive abajo, y
    # un rotulo arriba. Ninguno de los dos cruza el centro del cuadro.
    #
    # Medido con un video sin texto y una banda de rayas en mitad de la
    # imagen: cumplia las dos firmas de arriba, no tocaba bordes, no era fina,
    # contrastaba de sobra, y se colaba como subtitulo en y=0.467. Lo unico
    # que la delataba era estar donde no vive ningun subtitulo. Los diez
    # presets del catalogo caen por debajo de 0.22, asi que el tercio central
    # sobra por los dos lados.
    #
    # Se probo antes a exigir que el texto dejara margen a los lados, y NO
    # sirve: `pop` es tan gordo que llega de borde a borde igual que la franja.
    centro = 1.0 - ((a0 + a1) / 2.0) / alto      # fraccion desde abajo
    if 0.33 < centro < 0.67:
        return None                              # en mitad del cuadro no hay
    return a0, a1                                # subtitulos que valgan


def colores_del_texto(frames, banda):
    """(relleno, contorno) dentro de la banda, cada uno en 0-1, o None.

    El relleno es el color que MAS SE REPITE entre los pixeles que destacan del
    fondo, y el contorno el de los que lo rodean. Se mira solo en los
    fotogramas que de verdad tienen texto: promediar los que no lo tienen
    arrastra el color del fondo hacia el resultado y sale un gris de nadie.
    """
    import numpy as np

    if not banda:
        return None, None
    a0, a1 = banda
    trozos = [a[a0:a1 + 1] for a in frames]
    # con texto = el fotograma con mas contraste dentro de la banda
    fuerza = [float(t.mean(axis=2).std()) for t in trozos]
    if not fuerza:
        return None, None
    corte = max(fuerza) * 0.6
    vivos = [t for t, f in zip(trozos, fuerza) if f >= corte]
    if not vivos:
        return None, None
    px = np.concatenate([t.reshape(-1, 3) for t in vivos])
    lum = px.mean(axis=1)
    # El relleno esta en el 10% mas luminoso o en el 10% menos, segun de que
    # lado se salga mas del fondo: hay subtitulos blancos y los hay negros.
    medio = float(np.median(lum))
    alto_, bajo = np.percentile(lum, 92), np.percentile(lum, 8)
    claro = (alto_ - medio) >= (medio - bajo)
    relleno = px[lum >= alto_] if claro else px[lum <= bajo]
    contorno = px[lum <= bajo] if claro else px[lum >= alto_]
    if len(relleno) == 0:
        return None, None
    r = tuple(round(float(v) / 255.0, 3) for v in relleno.mean(axis=0))
    c = (tuple(round(float(v) / 255.0, 3) for v in contorno.mean(axis=0))
         if len(contorno) else None)
    return r, c


def hay_panel(frames, banda):
    """Si detras del texto hay una plancha de color solido, y de que color.

    Distingue dos estilos que por color y posicion son el mismo: uno lleva el
    texto blanco con contorno negro sobre el video, y el otro el mismo texto
    blanco sobre una tarjeta. Mirando solo el relleno son identicos; mirando lo
    que hay DETRAS no se parecen en nada.

    La prueba: dentro de la banda, los pixeles que no son texto forman un color
    uniforme y distinto del que hay justo encima de la banda. Un contorno no lo
    consigue, porque solo pinta el reborde de cada letra y deja ver el video
    entre palabra y palabra.

    NO PROBADO que acierte, y la causa esta medida: hoy devuelve False para
    `marker`, que si lleva plancha. La plancha cubre solo el ancho de las
    palabras y la banda que se analiza es tan ancha como el cuadro, asi que al
    promediar la banda entera gana el video de fondo y la plancha desaparece en
    la media. El arreglo pasa por acotar la zona antes de promediar, no por
    mover los umbrales de aqui, y hasta que eso este hecho un False de esta
    funcion significa "no lo se", no "no hay plancha". Por eso quien la usa
    solo se fia del True.
    """
    import numpy as np

    if not banda:
        return False, None
    a0, a1 = banda
    alto_px = frames[0].shape[0]
    fuera_a = max(0, a0 - (a1 - a0) - 4)
    if fuera_a >= a0 - 1:
        return False, None
    dentro = [a[a0:a1 + 1] for a in frames]
    fuerza = [float(t.mean(axis=2).std()) for t in dentro]
    if not fuerza or max(fuerza) <= 0:
        return False, None
    corte = max(fuerza) * 0.6
    vivos = [i for i, f in enumerate(fuerza) if f >= corte]
    if not vivos:
        return False, None
    px = np.concatenate([dentro[i].reshape(-1, 3) for i in vivos])
    lum = px.mean(axis=1)
    fondo_sub = px[lum <= np.percentile(lum, 55)]
    if len(fondo_sub) < 10:
        return False, None
    color = fondo_sub.mean(axis=0)
    # Uniforme? Una plancha lo es; el video que se ve entre letras, no.
    uniforme = float(fondo_sub.std(axis=0).mean()) < 26.0
    fuera = np.concatenate([a[fuera_a:a0 - 1].reshape(-1, 3) for a in
                            [frames[i] for i in vivos]])
    distinto = float(np.abs(color - fuera.mean(axis=0)).mean()) > 28.0
    if uniforme and distinto:
        return True, tuple(round(float(v) / 255.0, 3) for v in color)
    return False, None


def ritmo(video):
    """Cada cuanto corta, y si acelera. Devuelve None si no se pudo mirar.

    El corte es lo primero que se nota de un montaje ajeno y lo primero que
    pide quien pega un video: "quiero que vaya asi de rapido". Se apoya en
    vision.shots(), que ya sabe encontrar los limites de plano y esta probado,
    en vez de escribir otro detector al lado.

    La MEDIANA manda sobre la media a proposito: un plano largo al final (una
    despedida, un cartel) arrastra la media y no cambia como se siente el
    video. La mediana dice el plano tipico, que es lo que se quiere copiar.

    Medido con doce planos de 1,50 s clavados: `plano_tipico_s` devolvio 1,50 y
    `planos` devolvio diez, porque dos pares de planos seguidos se le fundieron
    en uno. Esa es justo la razon de la mediana, que aguanto el fallo sin
    moverse mientras la media se iba a 1,80.

    `acelera` hereda ese fallo y NO es de fiar: en ese mismo video, que va a
    ritmo constante de principio a fin, dijo 0,69 como si acelerara, solo
    porque los planos que se perdieron no cayeron repartidos. Se devuelve
    porque orienta, pero no se le enseña al usuario como un dato ni se decide
    nada con el hasta que la cuenta de planos sea exacta.
    """
    try:
        import vision
    except ImportError:
        return None
    try:
        planos, track = vision.shots(video)
    except Exception:
        return None
    if len(planos) < 2:
        return None
    largos = sorted(float(p["end"]) - float(p["start"]) for p in planos)
    n = len(largos)
    mediana = largos[n // 2] if n % 2 else (largos[n // 2 - 1] + largos[n // 2]) / 2.0
    # Acelera? Se compara la primera mitad del video con la segunda, en el
    # orden en que ocurren y no ordenados por duracion.
    en_orden = [float(p["end"]) - float(p["start"]) for p in planos]
    mitad = len(en_orden) // 2
    antes = sum(en_orden[:mitad]) / max(1, mitad)
    despues = sum(en_orden[mitad:]) / max(1, len(en_orden) - mitad)
    return {
        "planos": n,
        "plano_tipico_s": round(mediana, 2),
        "plano_medio_s": round(sum(largos) / n, 2),
        "mas_corto_s": round(largos[0], 2),
        "mas_largo_s": round(largos[-1], 2),
        # Menos de 1 = los planos se acortan hacia el final.
        "acelera": round(despues / antes, 2) if antes > 0 else None,
        "golpes": len(vision.beats(track)) if track else 0,
    }


def ficha(video):
    """Como esta editado este video. Numeros, nunca adjetivos."""
    frames, dur = fotogramas(video)
    w, h, _ = medidas(video)
    out = {"ancho": w, "alto": h, "duracion": round(dur, 2),
           "vertical": bool(h and w and h > w), "subtitulo": None,
           "ritmo": ritmo(video)}
    if not frames:
        return out
    banda = banda_de_texto(frames)
    if not banda:
        return out
    alto_px = frames[0].shape[0]
    a0, a1 = banda
    relleno, contorno = colores_del_texto(frames, banda)
    # Y el descarte que de verdad cierra la puerta: un subtitulo se LEE, y algo
    # se lee cuando contrasta con lo que tiene detras. Si el color de las
    # letras y el de su alrededor salen iguales, ahi no hay texto, hay una zona
    # lisa cuyo ruido gano la votacion. Medido en un video sin subtitulos:
    # relleno y contorno salian los dos (0.0, 0.384, 0.0), el verde del fondo.
    if not relleno or not contorno or _rgb_cerca(relleno, contorno) < 0.15:
        return out
    # `y` en la escala de la casa: fraccion desde abajo hasta el TOPE del
    # texto, no hasta su base. Lo dice el propio render: to_ass escribe
    # Alignment 8 (arriba-centro) y coloca con y = h * (1 - p["y"]), asi que el
    # numero del preset es el borde de ARRIBA. Medirlo por la base daba un
    # desfase de 0.016 constante, que resulto ser la sombra cayendo por debajo.
    # `size` en fraccion del ANCHO, que es como lo miden captions y overlays.
    ancho_px = frames[0].shape[1]
    panel, color_panel = hay_panel(frames, banda)
    out["subtitulo"] = {
        "y": round(1.0 - (a0 / float(alto_px)) + BORDE_ALTO, 3),
        "size": round((a1 - a0) / float(ancho_px), 3),
        "fill": relleno,
        "outline": None if panel else contorno,
        "panel": color_panel,
        "banda_px": [a0, a1, alto_px],
    }
    return out


def momento_con_texto(video, f=None):
    """El segundo del video donde el subtitulo se ve mejor, o None.

    Para poder ENSEÑAR lo que se ha visto en vez de contarlo. Un numero en una
    tabla no le dice nada a quien nunca edito un video; el fotograma con su
    subtitulo dentro se entiende sin leer.
    """
    import numpy as np

    frames, dur = fotogramas(video)
    if not frames or dur <= 0:
        return None
    banda = banda_de_texto(frames)
    if not banda:
        return None
    a0, a1 = banda
    # El fotograma con mas contraste dentro de la banda es el que tiene el
    # texto mas entero: los de la entrada y la salida lo tienen a medias.
    fuerza = [float(a[a0:a1 + 1].mean(axis=2).std()) for a in frames]
    mejor = int(np.argmax(fuerza))
    return round(dur * (mejor + 0.5) / len(frames), 2)


def captura(video, destino, solo_banda=False, ancho=520):
    """Un fotograma del video de referencia, en `destino`. Devuelve la ruta.

    Con `solo_banda` recorta a la franja del subtitulo con un poco de aire:
    es el primer plano que hace falta para comparar el subtitulo ajeno con el
    que Vidorq sabe hacer, uno al lado del otro.
    """
    at = momento_con_texto(video)
    w, h, dur = medidas(video)
    if at is None:
        at = round((dur or 2.0) / 3.0, 2)
    corte = "scale=%d:-2" % ancho
    if solo_banda and w and h:
        frames, _ = fotogramas(video)
        banda = banda_de_texto(frames) if frames else None
        if banda:
            alto_px = frames[0].shape[0]
            aire = max(6, (banda[1] - banda[0]) // 2)
            y0 = max(0, int((banda[0] - aire) * h / alto_px))
            alto = min(h - y0, int((banda[1] - banda[0] + 2 * aire) * h / alto_px))
            alto -= alto % 2
            if alto > 8:
                corte = "crop=%d:%d:0:%d,scale=%d:-2" % (w, alto, y0, ancho)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-i", str(video),
         "-frames:v", "1", "-vf", corte, str(destino)],
        capture_output=True, creationflags=NO_WINDOW)
    return destino if destino.exists() else None


def _rgb_cerca(uno, otro):
    """Distancia entre dos colores 0-1, 0 = iguales."""
    if not uno or not otro:
        return 9.9
    return sum(abs(a - b) for a, b in zip(uno[:3], otro[:3])) / 3.0


def parecidos(f, catalogo=None, cuantos=3):
    """Los estilos de la casa que mas se parecen a lo que se vio, en orden.

    Devuelve [(id, distancia), ...]. Varios y no uno, y es a proposito.

    Medido renderizando cada preset y volviendolo a mirar: de los diez del
    catalogo, cuatro son texto BLANCO en la misma franja de abajo, y lo unico
    que los separa es un adorno (contorno, plancha, halo) que en un MP4
    comprimido se difumina. Ninguna distancia sobre tres numeros los desempata
    de forma fiable, y forzarla solo produce una respuesta segura y equivocada.

    Un ojo humano los distingue de un vistazo, asi que la propuesta se enseña
    con los tres candidatos y elige el usuario. Acertar el primero es un lujo;
    tener el bueno entre los tres es el compromiso que si se sostiene.

    No adivina el nombre de la tipografia, que no se puede saber mirando un
    MP4: propone los estilos que Vidorq sabe reconstruir de verdad.
    """
    if catalogo is None:
        import captions
        catalogo = captions.PRESETS
    sub = (f or {}).get("subtitulo")
    if not sub:
        return []
    puntos = []
    for pid, p in catalogo.items():
        d = (_rgb_cerca(sub.get("fill"), p.get("fill")) * 2.0
             + abs(float(sub.get("y", 0)) - float(p.get("y", 0))) * 1.5
             + abs(float(sub.get("size", 0)) - float(p.get("size", 0))) * 1.0)
        # Llevar plancha separa dos estilos que por color y sitio son gemelos,
        # asi que pesa mas que afinar el tamaño: el tamaño que se mide es el
        # alto de la mayuscula y el del preset es el cuerpo nominal de la
        # fuente, que no son el mismo numero.
        #
        # Solo se penaliza en un sentido, y es a proposito: hay_panel acierta
        # cuando dice que SI y todavia se equivoca cuando dice que no (esta
        # explicado alli). Castigar por un "no" que no es de fiar apartaria los
        # estilos con plancha en todos los videos, que es peor que no mirarlo.
        if sub.get("panel") and not p.get("panel"):
            d += 0.35
        puntos.append((d, pid))
    puntos.sort()
    return [(pid, round(d, 3)) for d, pid in puntos[:cuantos]]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python aprende.py <video>")
        raise SystemExit(2)
    f = ficha(sys.argv[1])
    f["parecido_a"] = [{"preset": pid, "distancia": d}
                       for pid, d in parecidos(f)]
    print(json.dumps(f, indent=1, ensure_ascii=False))
