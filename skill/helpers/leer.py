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


# Hasta que anillo alrededor de la letra se mira. Un halo de verdad llega
# lejos: `neon` sigue encendido en el anillo 12.
ANILLOS = 14


def _borde(caja, fill):
    """Que lleva la letra ALREDEDOR: contorno, halo, o nada.

    Es lo que de verdad separa un subtitulo reconstruido de su original, y no
    se estaba mirando: el color de cada palabra puede estar clavado y aun asi
    verse mal, porque la plantilla heredada trae un contorno negro gordo y el
    video no lleva ninguno. Se ve a un metro de la pantalla.

    Como: se toma la mancha de la letra, se dilata de uno en uno, y se mira el
    ANILLO que se añade en cada paso. El perfil cuenta la historia:

      contorno   anillos mucho mas oscuros que el fondo lejano, y de golpe
      halo       anillos que se parecen al color de la letra y se apagan poco
                 a poco durante muchos pixeles
      nada       el perfil baja suave hacia el fondo, sin salto ni halo

    Devuelve (contorno_px, halo_px, caida, alto, grosor) o None. `caida` es el
    perfil de luz, que distingue un contorno duro (salta a 0,00 y se queda) de
    una sombra difusa (baja despacio), y esa diferencia no cabe en un numero.
    `alto` es el de la LETRA y no el de la caja del detector, que viene con
    aire y con el halo dentro: medir el tamaño contra la caja lo sobreestimaba
    y el subtitulo reconstruido salia mas grande que el original.

    Medido contra LOS DIEZ estilos de la casa, con su contorno y su halo
    conocidos: pop 13 y punch 13 (contorno gordo), mono 6 (fino), marker, bar
    y minimal 0 (ninguno), neon 12 y halo 5 (halo). Dos no cuadran y se dicen:
    `glass` cuenta su plancha oscura como contorno, que opticamente lo es, y
    `ember` no llega a enseñar su halo porque su fondo queda demasiado claro.
    """
    import cv2
    import numpy as np

    obj = np.array(fill, dtype="float32") * 255.0
    d = np.abs(caja.astype("float32") - obj).sum(axis=2)
    # Cerca del color de la letra: 110 sobre los tres canales sumados son unos
    # 37 por canal, que aguanta la compresion sin tragarse medio fondo.
    m = (d < 110).astype("uint8")
    if m.sum() < 25:
        return None
    # Sin agujeros: en una letra hueca el interior es fondo, y sin taparlo se
    # mide el anillo de dentro como si fuera el de fuera.
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), "uint8"))
    lum = caja.mean(axis=2).astype("float32") / 255.0
    col = caja.astype("float32") / 255.0
    fillv = np.array(fill, dtype="float32")

    prof, previo = [], m
    for _ in range(ANILLOS):
        crecido = cv2.dilate(previo, np.ones((3, 3), "uint8"))
        anillo = (crecido - previo).astype(bool)
        prof.append(None if anillo.sum() < 8 else
                    (float(lum[anillo].mean()),
                     float(np.abs(col[anillo] - fillv).sum(axis=1).mean())))
        previo = crecido
    fuera = ~previo.astype(bool)
    if fuera.sum() < 20:
        return None
    lejos = float(lum[fuera].mean())
    # Se empieza a contar en el anillo 2: el 1 todavia es el borde suavizado
    # de la propia letra, mezcla de la letra y de lo que tenga detras. Contarlo
    # hacia que ningun contorno se detectara nunca.
    contorno = sum(1 for a in prof[1:] if a and a[0] < lejos - 0.10)
    halo = sum(1 for a in prof[1:] if a and a[0] > lejos + 0.06 and a[1] < 1.35)
    caida = [round(a[0], 3) if a else None for a in prof[:8]]
    # El alto de la LETRA, de la mancha misma.
    filas = np.where(m.any(axis=1))[0]
    alto = int(filas[-1] - filas[0] + 1) if len(filas) else 0
    # Y su grosor de trazo, por la transformada de distancia: dentro de la
    # mancha, cada pixel vale lo que dista del borde, asi que el pico dentro de
    # un trazo es su radio. Se toma la mediana de los picos y no el maximo,
    # que lo dispara el cruce de dos trazos.
    dt = cv2.distanceTransform(m, cv2.DIST_L2, 3)
    picos = dt[dt > dt.max() * 0.45] if dt.max() > 0 else []
    grosor = float(np.median(picos)) * 2.0 if len(picos) >= 5 else 0.0
    return contorno, halo, caida, alto, grosor


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
    contornos, halos, caidas, letras, pesos = [], [], [], [], []
    for d in sorted(dentro, key=lambda d: d["i"]):
        caja = frames[d["i"]][max(0, d["y0"]):d["y1"] + 1,
                              max(0, d["x0"]):d["x1"] + 1]
        if caja.size < 90:
            continue
        # Con aire alrededor para lo del borde: el halo y el contorno viven
        # FUERA de la caja del detector, que viene ceñida a las letras. Sin
        # aire no hay anillos que medir y todo sale "sin contorno".
        aire = max(6, (d["y1"] - d["y0"]) // 2)
        ancha = frames[d["i"]][max(0, d["y0"] - aire):d["y1"] + 1 + aire,
                               max(0, d["x0"] - aire):d["x1"] + 1 + aire]
        palabras = []
        for w, (a, b) in zip(d["texto"].split(), _tramos(caja, d["texto"])):
            c, px = _color(caja, a, b)
            if not c:
                continue
            palabras.append({"w": w, "color": c, "px": px})
            k = tuple(int(v * 8) for v in c)
            paleta[k] = paleta.get(k, 0) + px
            anillos = _borde(ancha, c)
            if anillos:
                contornos.append(anillos[0])
                halos.append(anillos[1])
                caidas.append(anillos[2])
                if anillos[3] >= 6:
                    letras.append(anillos[3])
                    if anillos[4] > 0:
                        pesos.append(anillos[4] / anillos[3])
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
    # El tamaño sale del alto de la LETRA cuando se ha podido medir, y solo
    # cae al de la caja del detector si no. La caja trae aire y el halo dentro,
    # asi que sobreestima: con ella el subtitulo reconstruido salia mas grande
    # que el original, y eso se ve al ponerlos uno al lado del otro.
    alto_letra = float(np.median(letras)) if letras else 0.0

    # Como ENTRA el texto. Se pregunta por varias lineas y gana la respuesta
    # que mas se repita: una sola puede caer justo donde el plano cambia y
    # entonces lo que se mide es el corte, no la entrada del subtitulo.
    #
    # Es una pasada aparte sobre trozos de un segundo, porque una entrada dura
    # tres o cuatro fotogramas y el muestreo normal se la salta entera. Si no
    # se puede ver, se dice que no en vez de suponer "de golpe".
    entrada = None
    # El color que mas se repite en el texto, para poder buscar la mancha POR
    # COLOR y no por brillo: sobre metraje el cuadro entero pasa cualquier
    # umbral de brillo y el texto no "aparece" nunca.
    dominante = None
    if paleta:
        k = max(paleta, key=lambda k: paleta[k])
        dominante = tuple(v / 8 + 1 / 16 for v in k)
    try:
        import efectos
        banda = (max(0.0, (arriba - alto_px) / H),
                 min(1.0, (arriba + alto_px * 2) / H))
        votos = []
        for d in sorted(dentro, key=lambda d: d["i"])[:4]:
            t = dur * (d["i"] + 0.5) / len(frames)
            e = efectos.entrada(video, t, banda=banda, antes=1.4, despues=0.3,
                                color=dominante)
            if e:
                votos.append(e)
        if votos:
            cuenta = {}
            for v in votos:
                cuenta[v["como"]] = cuenta.get(v["como"], 0) + 1
            gana = max(cuenta, key=lambda k: cuenta[k])
            entrada = {"como": gana, "de": len(votos),
                       "acuerdo": round(cuenta[gana] / len(votos), 2)}
    except Exception:
        entrada = None

    return {
        "y": round(1.0 - arriba / H + borde, 3),
        "size": round((alto_letra or alto_px) / ref, 3),
        "size_de": "letra" if alto_letra else "caja",
        # Grosor del trazo entre alto de la letra. Separa una letra fina de una
        # gorda: medido sobre los diez estilos de la casa, Regular da 0,080 y
        # todo lo Bold o Black cae entre 0,133 y 0,163. Lo que NO hace es
        # separar Bold de Black, que se solapan, asi que aqui solo se decide
        # "fina" o "gorda" y no se finge mas precision de la que hay.
        "peso": round(float(np.median(pesos)), 4) if pesos else None,
        "lineas": lineas,
        "paleta": [tuple(round(v / 8 + 1 / 16, 3) for v in k) for k, _ in orden[:6]],
        "logo": sorted(logo),
        # Como entra el texto: "creciendo", "apareciendo", "de golpe", o None
        # si no se ha podido ver. `acuerdo` dice cuantas de las lineas miradas
        # opinaban lo mismo, para poder desconfiar de un 0,5.
        "entrada": entrada,
        # Lo que rodea a la letra. La MEDIANA y no la media: una palabra sobre
        # un plano oscuro da un contorno que no existe, y con la media una sola
        # basta para inventarse uno en todo el video.
        "borde": {
            "contorno": int(np.median(contornos)) if contornos else 0,
            "halo": int(np.median(halos)) if halos else 0,
            # El perfil de luz, para poder distinguir un contorno duro (salta
            # a 0,00 y se queda) de una sombra difusa (baja despacio). Esa
            # diferencia no cabe en un solo numero y es justo la que se veia
            # mal en pantalla.
            "caida": ([round(float(np.median([c[i] for c in caidas
                                              if c[i] is not None])), 3)
                       if any(c[i] is not None for c in caidas) else None
                       for i in range(8)] if caidas else []),
            "de": len(contornos),
        },
    }
