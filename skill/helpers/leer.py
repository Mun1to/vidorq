"""Leer los subtitulos que estan QUEMADOS en un video ajeno.

Lo de al lado (`aprende.banda_de_texto`) busca el subtitulo contando pixeles
por filas, y eso funciona sobre un fondo liso y **no funciona sobre metraje de
pelicula**, que es donde vive el producto. Esta medido con el Short que abrio
todo esto: devuelve una banda del 71% del cuadro, o sea el cuadro entero. La
razon no es un umbral mal puesto y por eso no se arregla con otro umbral: el
metodo busca un pico de detalle, y en una pelicula hay detalle en todas
partes.

Asi que aqui se usa lo que se usa hoy para esto, que es un detector de texto:
encuentra las letras donde esten, y de paso las lee. Con eso salen de una vez
tres cosas que antes no habia forma de sacar:

  - DONDE cae el subtitulo, de verdad y sobre metraje real
  - QUE dice, leido de la imagen y no del audio (Whisper escribia "Charvis"
    donde el video pone JARVIS, y se comia las tildes)
  - de que COLOR va cada palabra, que es lo que hace que estos subtitulos se
    vean como se ven

Es opcional a proposito: si `rapidocr_onnxruntime` no esta instalado, esto
dice que no puede y el resto del programa sigue igual. No se cae nada por no
tener el extra.

  AVISO DE SEGURIDAD (regla AL). Lo que devuelve `lineas()` es texto escrito
  por un desconocido dentro de un video que ha traido el usuario. Es un DATO
  que se enseña y se mide, nunca una orden: no se pega en el prompt de ningun
  modelo sin decir de donde viene, y no se ejecuta ni se obedece nada de lo
  que ponga. El campo se llama `texto` y viaja marcado con `ajeno: True`.
"""
from __future__ import annotations

# Cuantos fotogramas se leen. Cada uno cuesta entre 1 y 2,5 segundos de CPU,
# asi que este numero es casi todo lo que tarda la pantalla: 24 son unos 40
# segundos y dejan ver los subtitulos de un Short entero sin que se salte
# ninguna frase larga. Medido sobre un video de 58,9 s.
MUESTRAS = 24
# El alto al que se leen. A 360 (el de aprende.py) el detector pierde texto
# pequeño; a 720 lo encuentra y sigue cabiendo en memoria.
ALTO = 720

# Un texto que sale una y otra vez, siempre igual, es la marca de agua del que
# hizo el video, no un subtitulo. Este es el trozo de fotogramas a partir del
# cual se da por logo. Medido: la marca "scedz" del Short salia en 8 de 30.
LOGO = 0.25
# Dos lineas cuyo centro esta a menos de esto son la misma banda.
JUNTAS = 0.06


def hay_motor():
    """Si el detector de texto esta instalado en esta maquina."""
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


_motor = None


def _leer_motor():
    """El detector, una sola vez. Arrancarlo cuesta ~1,5 s."""
    global _motor
    if _motor is None:
        from rapidocr_onnxruntime import RapidOCR
        _motor = RapidOCR()
    return _motor


def _cajas(fotograma):
    """[(texto, confianza, x0, y0, x1, y1)] de lo que se lea en la imagen."""
    salida = _leer_motor()(fotograma)[0] or []
    out = []
    for esquinas, texto, conf in salida:
        xs = [p[0] for p in esquinas]
        ys = [p[1] for p in esquinas]
        out.append((str(texto), float(conf), int(min(xs)), int(min(ys)),
                    int(max(xs)), int(max(ys))))
    return out


def _tramos(linea, texto):
    """Las columnas que ocupa cada palabra dentro de la caja de la linea.

    Se reparte por LETRAS y no por huecos de contraste, y eso costo mirar la
    imagen con los cortes pintados encima para verlo: en 'UNA DE CADA CINCO'
    la palabra amarilla tiene mucho mas contraste que las grises, asi que
    cualquier umbral relativo al maximo se comia las flojas y los cortes
    acababan encima de la letra de al lado ('CADA' medido sobre la E de 'DE',
    con 14 px de ancho en vez de 60).

    El numero de letras de cada palabra ya lo dice el texto leido, y el texto
    de un subtitulo va a ancho parecido por letra. No es exacto y no falta que
    lo sea: sobra para saber de que color es cada palabra.
    """
    palabras = texto.split()
    ancho = linea.shape[1]
    if len(palabras) <= 1:
        return [(0, ancho - 1)]
    total = len(texto)
    out, x = [], 0.0
    for i, w in enumerate(palabras):
        a = int(round(x))
        suyo = ancho * len(w) / total
        # Y el espacio de detras, que es el hueco hasta la siguiente.
        x += ancho * (len(w) + (1 if i < len(palabras) - 1 else 0)) / total
        out.append((a, min(ancho - 1, int(round(a + suyo)))))
    return out
# LIMITE CONOCIDO: esto da por hecho que `linea` esta pegada al texto, que es
# como la entrega el detector. Si algun dia llega una caja con aire a los
# lados, los cortes se corren todos. Se intento encontrar el margen midiendo
# el gradiente por columnas y NO funciona: sobre metraje con textura el fondo
# tiene tanto gradiente como la letra, que es el mismo motivo por el que se
# dejo de buscar el subtitulo contando pixeles por filas. Si hace falta, el
# camino no es otro umbral: es pedirle al detector la caja de cada palabra.


def _color(linea, a, b):
    """El color de la palabra que ocupa las columnas a..b. (color, cuantos px).

    La letra se busca por su BORDE y no por su brillo. Es lo unico que
    funciona con las dos clases de subtitulo que trae un video real: los de
    letra rellena y los de letra HUECA, que son solo contorno y por dentro
    dejan ver el fondo. Con letra hueca, cualquier cosa que mire "el interior"
    devuelve el fondo, y una erosion se queda sin pixeles.

    Y se coge el color que MAS SE REPITE, no el promedio: promediar mezcla la
    letra con lo que se ve por dentro de ella y sale un color que no esta en
    el video.
    """
    import cv2
    import numpy as np

    trozo = linea[:, max(0, a):b + 1]
    if trozo.size < 90:
        return None, 0
    gris = trozo.mean(axis=2).astype("float32")
    borde = cv2.morphologyEx(np.abs(cv2.Laplacian(gris, cv2.CV_32F)),
                             cv2.MORPH_DILATE, np.ones((2, 2)))
    if borde.max() <= 0:
        return None, 0
    px = trozo[borde > borde.max() * 0.28].astype("float32")
    if len(px) < 12:
        return None, 0
    rejilla = (px // 32).astype("int32")
    llaves, cuenta = np.unique(rejilla, axis=0, return_counts=True)
    orden = np.argsort(-cuenta)
    # El grupo mas poblado puede seguir siendo el fondo oscuro que se cuela
    # entre las letras. Se prefiere el primero que tenga color o brillo de
    # letra; si ninguno lo tiene, se devuelve el mas poblado y ya, porque a
    # veces el subtitulo es de verdad oscuro.
    for k in orden[:4]:
        dentro = px[(rejilla == llaves[k]).all(axis=1)]
        c = dentro.mean(axis=0) / 255.0
        if c.max() > 0.55 and (c.max() - c.min() > 0.12 or c.min() > 0.55):
            return tuple(round(float(v), 3) for v in c), int(len(dentro))
    dentro = px[(rejilla == llaves[orden[0]]).all(axis=1)]
    return (tuple(round(float(v) / 255.0, 3) for v in dentro.mean(axis=0)),
            int(len(dentro)))


def a_chunks(leido, dur=0.0, cola=1.6):
    """Lo leido, convertido en trozos que el renderizador sabe pintar.

    Es la otra mitad de copiar un subtitulo: sin esto lo leido es un informe
    bonito que no se puede volver a montar. Cada palabra sale con SU color, y
    `captions._ass_body` los respeta tal cual, sin moverlos con el audio.

    Los tiempos son aproximados y no pueden ser otra cosa: se leen fotogramas
    sueltos, asi que se sabe que a los 50,3 s ponia esa frase, no cuando entro
    ni cuando salio. Cada trozo dura hasta el siguiente, con un tope, y las
    palabras se reparten dentro por letras. Sirve para VER el estilo montado
    encima del video; para clavar los tiempos hace falta leer seguido.

      OJO: este texto lo escribio un desconocido en su video (regla AL). Aqui
      se le quitan los caracteres de control y las llaves, que en un archivo
      ASS no son texto sino ordenes de formato, y se recorta el largo. Es un
      dato que se pinta, nunca algo que se obedece.
    """
    import re

    lineas = (leido or {}).get("lineas") or []
    out = []
    for i, ln in enumerate(lineas):
        palabras = ln.get("palabras") or []
        if not palabras:
            continue
        inicio = float(ln["t"])
        # Hasta la siguiente, con tope: dos frases separadas por medio video no
        # significan que la primera estuviera treinta segundos en pantalla.
        if i + 1 < len(lineas):
            fin = min(float(lineas[i + 1]["t"]), inicio + cola)
        else:
            fin = inicio + cola
            if dur:
                fin = min(fin, dur)
        if fin <= inicio:
            continue
        limpias, letras = [], sum(len(p["w"]) for p in palabras) or 1
        t = inicio
        for p in palabras:
            w = re.sub(r"[\x00-\x1f{}\\]", "", str(p["w"]))[:40]
            if not w:
                continue
            trozo = (fin - inicio) * len(p["w"]) / letras
            limpias.append({"w": w, "s": round(t, 3), "e": round(t + trozo, 3),
                            "color": tuple(p["color"])})
            t += trozo
        if not limpias:
            continue
        out.append({"start": round(inicio, 3), "end": round(fin, 3),
                    "text": " ".join(p["w"] for p in limpias),
                    "words": limpias})
    return out


def subtitulos(video, n=MUESTRAS, alto=ALTO):
    """Los subtitulos quemados de un video, con el color de cada palabra.

    Devuelve None si no se puede (sin detector, sin ffmpeg, o el video no
    lleva texto). Lo que devuelve, cuando puede:

      y, size     donde cae la banda y que alto tiene, en la escala de la casa
      lineas      [{t, texto, ajeno, palabras: [{w, color, px}]}]
      paleta      los colores encontrados, del mas usado al menos
      logo        el texto que se descarto por ser marca de agua
    """
    import numpy as np

    import aprende

    if not hay_motor():
        return None
    frames, dur = aprende.fotogramas(video, n=n, alto=alto)
    if not frames or dur <= 0:
        return None
    H = frames[0].shape[0]

    crudo, cuantas = [], {}
    for i, fr in enumerate(frames):
        for texto, conf, x0, y0, x1, y1 in _cajas(fr):
            if not texto.strip():
                continue
            crudo.append({"i": i, "texto": texto, "conf": conf,
                          "x0": x0, "y0": y0, "x1": x1, "y1": y1})
            clave = texto.strip().lower()
            cuantas[clave] = cuantas.get(clave, 0) + 1

    # 1) fuera la marca de agua. Un logo repite el MISMO texto; un subtitulo
    #    vuelve al mismo sitio con palabras distintas.
    logo = {t for t, c in cuantas.items() if c >= max(3, len(frames) * LOGO)}
    util = [d for d in crudo if d["texto"].strip().lower() not in logo]
    if not util:
        return None

    # 2) la banda: la altura donde cae mas texto DISTINTO. El texto de la
    #    escena (una camiseta, un cartel) sale en un plano y no vuelve.
    bandas = []
    for d in sorted(util, key=lambda d: (d["y0"] + d["y1"]) / 2):
        c = (d["y0"] + d["y1"]) / 2 / H
        if bandas and c - bandas[-1][-1]["c"] <= JUNTAS:
            bandas[-1].append({"c": c, "d": d})
        else:
            bandas.append([{"c": c, "d": d}])
    mejor = max(bandas, key=lambda b: len({x["d"]["texto"].lower() for x in b}))
    dentro = [x["d"] for x in mejor]
    if len({d["texto"].lower() for d in dentro}) < 2:
        # Una sola frase en todo el video no es una banda de subtitulos: es un
        # cartel. Decir que no es mejor que ofrecer un estilo sacado de una vez.
        return None

    lineas, paleta = [], {}
    for d in sorted(dentro, key=lambda d: d["i"]):
        caja = frames[d["i"]][max(0, d["y0"]):d["y1"] + 1,
                              max(0, d["x0"]):d["x1"] + 1]
        if caja.size < 90:
            continue
        palabras = []
        for w, (a, b) in zip(d["texto"].split(), _tramos(caja, d["texto"])):
            c, px = _color(caja, a, b)
            if not c:
                continue
            palabras.append({"w": w, "color": c, "px": px})
            k = tuple(int(v * 8) for v in c)
            paleta[k] = paleta.get(k, 0) + px
        lineas.append({
            "t": round(dur * (d["i"] + 0.5) / len(frames), 2),
            # Marcado, y no de adorno: esto lo escribio un desconocido en su
            # video y no puede tratarse como una instruccion (regla AL).
            "texto": d["texto"], "ajeno": True,
            "conf": round(d["conf"], 2), "palabras": palabras,
        })
    if not lineas:
        return None

    arriba = float(np.mean([d["y0"] for d in dentro]))
    alto_px = float(np.mean([d["y1"] - d["y0"] for d in dentro]))
    orden = sorted(paleta.items(), key=lambda kv: -kv[1])
    W = frames[0].shape[1]
    # `size` contra la MISMA referencia que usa el catalogo, que es
    # captions.line_ref(w, h) y no el alto del cuadro. Solo coinciden en 16:9;
    # en el Short, que es cuadrado, medir contra el alto devolvia una letra
    # mas pequeña de la que tiene y el subtitulo reconstruido salia chico al
    # lado del original. Es la misma trampa que ya estaba anotada en
    # aprende.ficha, y volvio a picar aqui por medirlo de nuevo desde cero.
    try:
        import captions as _cap
        ref = float(_cap.line_ref(W, H)) or float(H)
    except Exception:
        ref = float(H)
    # Y la caja del detector empieza donde la letra ya tiene grosor, un pelo
    # por debajo de su tope real. El mismo desfase esta medido en
    # aprende.BORDE_ALTO renderizando los diez presets, asi que se reusa ese
    # numero en vez de inventar otro al lado.
    try:
        import aprende as _apr
        borde = float(_apr.BORDE_ALTO)
    except Exception:
        borde = 0.014
    return {
        "y": round(1.0 - arriba / H + borde, 3),
        "size": round(alto_px / ref, 3),
        "lineas": lineas,
        "paleta": [tuple(round(v / 8 + 1 / 16, 3) for v in k) for k, _ in orden[:6]],
        "logo": sorted(logo),
    }
