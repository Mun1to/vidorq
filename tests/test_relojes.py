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

import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))
sys.path.insert(0, str(RAIZ / "engine"))

import captions as cap  # noqa: E402

# La contrabarra, escrita asi para que se lea sin contar barras.
BS = chr(92)

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

    # Y el barrido: cada cuarto de segundo del montaje, sobre cinco trozos
    # desordenados. Del montaje al original y de vuelta tiene que caer en el
    # mismo sitio SIEMPRE, no solo en los seis valores que se le ocurrieron a
    # alguien. Es el suelo de todo lo demas: cortes, subtitulos, rotulos y
    # marcadores se colocan traduciendo entre estos dos relojes.
    CINCO = [{"start": 40.0, "end": 47.5}, {"start": 5.0, "end": 15.0},
             {"start": 60.0, "end": 60.25}, {"start": 20.0, "end": 30.0},
             {"start": 33.0, "end": 39.0}]
    dura = sum(p["end"] - p["start"] for p in CINCO)
    malos = []
    m = 0.0
    while m < dura - 0.001:
        o = server.to_original(m, CINCO)
        vuelta = server.to_edited(o, CINCO) if o is not None else None
        if o is None or vuelta is None or abs(vuelta - m) > 0.001:
            malos.append(round(m, 2))
        m += 0.25
    yield ("relojes: ida y vuelta en todo el montaje", malos[:6], [])

    # Y el ultimo segundo del montaje existe: un montaje que acaba antes de su
    # propia duracion se come el final de la ultima frase.
    yield ("relojes: el ultimo instante del montaje tiene original",
           server.to_original(round(dura - 0.01, 2), CINCO) is not None, True)

    # --- un cartel se escribe en el reloj del MONTAJE -----------------------
    # `titles_into` recibe el segundo del ORIGINAL (ya traducido por el motor) y
    # devuelve el del montaje, porque lo que arma es la lista de subtitulos.
    chunks = server.titles_into([], [{"do": "title", "at": 6.0, "secs": 2.0,
                                      "text": "HOLA"}], EDL)
    yield "el cartel del segundo 6 cae en el 1 del montaje", chunks[0]["start"], 1.0
    yield "y dura los 2 segundos pedidos", chunks[0]["end"], 3.0

    # Y lo que promete su docstring: meter un rotulo en una lista densa de
    # subtitulos no deja dos lineas en pantalla a la vez. Un subtitulo cada
    # medio segundo es como sale de verdad con subtitulos de dos palabras.
    densos = [{"start": round(i * 0.5, 2), "end": round(i * 0.5 + 0.5, 2),
               "text": "s%d" % i,
               "words": [{"w": "s%d" % i, "s": round(i * 0.5, 2),
                          "e": round(i * 0.5 + 0.5, 2)}]}
              for i in range(0, 40)]
    for donde, dura in ((6.0, 2.0), (5.0, 3.0), (14.5, 2.0), (25.0, 1.5)):
        salida = server.titles_into([dict(c) for c in densos],
                                    [{"do": "title", "at": donde, "secs": dura,
                                      "text": "ROTULO"}], EDL)
        solapes = [(round(salida[i]["end"], 2), round(salida[i + 1]["start"], 2))
                   for i in range(len(salida) - 1)
                   if float(salida[i]["end"]) > float(salida[i + 1]["start"]) + 0.001]
        yield ("rotulo en %g: no deja dos lineas a la vez" % donde, solapes[:3], [])
        # Y sale ordenado, que es como lo lee el renderizador.
        empiezos = [round(float(c["start"]), 3) for c in salida]
        yield ("rotulo en %g: la lista sale en orden" % donde,
               empiezos, sorted(empiezos))

    # Un rotulo pedido en un segundo que el corte se llevo no aparece: no hay
    # sitio donde ponerlo, y ponerlo "cerca" seria inventarse el momento.
    cortado = server.titles_into([], [{"do": "title", "at": 17.0, "secs": 2.0,
                                       "text": "NO"}], EDL)
    yield ("rotulo en material cortado no se pone", cortado, [])

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


    # --- el montaje reordenado ---------------------------------------------
    # Mover un tramo de sitio es una permutacion del montaje, y todo lo demas
    # (los subtitulos, editar leyendo, un cartel) sigue hablando en segundos.
    # Si los dos relojes no aguantan el orden nuevo, no falla: desplaza.
    VUELTA = [EDL[1], EDL[0]]                   # el segundo tramo, primero

    yield "reordenado: to_original(0) = 20", server.to_original(0.0, VUELTA), 20.0
    yield "reordenado: to_original(10) = 5", server.to_original(10.0, VUELTA), 5.0
    # Y a la inversa. Esta es la que se rompia: `to_edited` descartaba por "ya
    # hemos pasado ese segundo", que en un montaje reordenado no quiere decir
    # nada, y el segundo 5 del original devolvia None estando en el montaje.
    yield "reordenado: to_edited(20) = 0", server.to_edited(20.0, VUELTA), 0.0
    yield "reordenado: to_edited(5) = 10", server.to_edited(5.0, VUELTA), 10.0
    yield "reordenado: to_edited(25) = 5", server.to_edited(25.0, VUELTA), 5.0
    yield "reordenado: lo cortado sigue cortado", server.to_edited(17.0, VUELTA), None
    for t in (5.0, 14.9, 20.0, 29.9):
        ida = server.to_edited(t, VUELTA)
        yield ("reordenado: ida y vuelta del %.2f" % t,
               round(server.to_original(ida, VUELTA), 3), t)

    # `reordered` solo acepta una permutacion exacta. Cualquier otra cosa
    # devuelve el montaje intacto: una lista mal formada aqui no da error, da
    # una edicion equivocada en silencio.
    yield "reordenar: la permutacion se aplica", server.reordered(EDL, [1, 0]), VUELTA
    yield "reordenar: sin orden no toca nada", server.reordered(EDL, None), EDL
    yield "reordenar: un indice repetido no vale", server.reordered(EDL, [0, 0]), EDL
    yield "reordenar: un indice inventado no vale", server.reordered(EDL, [0, 5]), EDL
    yield "reordenar: de otro largo no vale", server.reordered(EDL, [0]), EDL
    yield "reordenar: texto no vale", server.reordered(EDL, ["a", "b"]), EDL
    yield "reordenar: los tramos viajan enteros", server.reordered(EDL, [1, 0])[0], EDL[1]

    # Las palabras siguen al montaje, no al original. Dos frases, una en cada
    # tramo: al dar la vuelta a los tramos, la que se dice primero es la otra.
    T = {"segments": [
        {"words": [{"w": "uno", "s": 6.0, "e": 6.5}, {"w": "dos", "s": 7.0, "e": 7.5}]},
        {"words": [{"w": "tres", "s": 21.0, "e": 21.5}, {"w": "cuatro", "s": 22.0, "e": 22.5}]},
    ]}
    normal = server.retime_transcript(T, EDL)["segments"]
    yield "sin reordenar, primero 'uno dos'", normal[0]["text"], "uno dos"
    yield "sin reordenar, despues 'tres cuatro'", normal[1]["text"], "tres cuatro"
    revuelto = server.retime_transcript(T, VUELTA)["segments"]
    yield "reordenado, primero 'tres cuatro'", revuelto[0]["text"], "tres cuatro"
    yield "reordenado, despues 'uno dos'", revuelto[1]["text"], "uno dos"
    yield "reordenado, y empieza en el segundo 1", round(revuelto[0]["start"], 3), 1.0
    # Las frases salen en el orden en que se OYEN, que es lo unico que puede
    # leer quien pone los subtitulos.
    yield ("reordenado, las frases van en orden",
           [round(x["start"], 3) for x in revuelto], sorted(round(x["start"], 3) for x in revuelto))

    # Y una frase partida por un corte ya no sale como una sola. Esto estaba mal
    # desde antes de poder reordenar: el principio caia a un lado del corte y el
    # final al otro, y el subtitulo cruzaba el corte.
    PARTIDA = {"segments": [{"words": [{"w": "antes", "s": 14.0, "e": 14.5},
                                       {"w": "despues", "s": 21.0, "e": 21.5}]}]}
    partido = server.retime_transcript(PARTIDA, EDL)["segments"]
    yield "una frase partida por un corte son dos", len(partido), 2
    yield "  y la primera acaba antes del corte", round(partido[0]["end"], 3), 9.5


    # Y la regla, sobre cinco trozos desordenados y palabras repartidas por
    # todo el video: cada una cae donde dice `to_edited`, o no cae. Si estas
    # dos cuentas se separan, los subtitulos se van desincronizando solos y
    # parece culpa del modelo.
    CINCO2 = [{"start": 40.0, "end": 47.5}, {"start": 5.0, "end": 15.0},
              {"start": 60.0, "end": 60.25}, {"start": 20.0, "end": 30.0},
              {"start": 33.0, "end": 39.0}]
    sueltas = [{"w": "p%d" % i, "s": round(i * 2.0, 2), "e": round(i * 2.0 + 0.4, 2)}
               for i in range(1, 31)]
    T2 = {"segments": [{"words": [w]} for w in sueltas]}
    salidas = server.retime_transcript(T2, CINCO2)["segments"]
    # Cada palabra que sale, en el sitio que dice el otro reloj.
    descolocadas = []
    for seg in salidas:
        for w in seg.get("words", []):
            orig = next(x for x in sueltas if x["w"] == w["w"])
            debe = server.to_edited(orig["s"], CINCO2)
            if debe is None or abs(w["s"] - debe) > 0.001:
                descolocadas.append(w["w"])
    yield ("subtitulos: cada palabra cae donde dice el reloj", descolocadas, [])

    # Y las que estaban dentro de un corte no salen: no estan en el montaje.
    salieron = {w["w"] for seg in salidas for w in seg.get("words", [])}
    coladas = [x["w"] for x in sueltas
               if server.to_edited(x["s"], CINCO2) is None and x["w"] in salieron]
    yield ("subtitulos: lo cortado no se cuela", coladas, [])
    yield ("subtitulos: y algo sobrevive", len(salieron) > 5, True)

    # --- un corte quita lo pedido y nada mas -------------------------------
    # De aqui salio el fallo de esta manana: pedir tres segundos y perder 4,15.
    # Se arreglo en el flujo del motor; esto fija la aritmetica de debajo, que
    # tiene que aguantar aunque el flujo vuelva a cambiar.
    def segundos_dentro(lista):
        """Los decimos de segundo del ORIGINAL que sobreviven en ese montaje."""
        fuera = set()
        for p in lista:
            x = float(p["start"])
            while x < float(p["end"]) - 1e-9:
                fuera.add(round(x, 1))
                x += 0.1
        return fuera

    CUATRO = [{"start": 0.0, "end": 10.0}, {"start": 20.0, "end": 26.0},
              {"start": 30.0, "end": 33.0}, {"start": 40.0, "end": 50.0}]
    for desde, hasta in ((4.0, 7.0), (0.0, 2.0), (9.0, 21.0), (25.0, 31.0),
                         (32.5, 41.0), (49.0, 60.0), (12.0, 18.0)):
        antes_lista = [dict(x) for x in CUATRO]
        antes = segundos_dentro(antes_lista)
        despues_lista = [dict(x) for x in CUATRO]
        server.apply_actions(despues_lista, [{"do": "cut", "at": desde, "until": hasta}])
        despues = segundos_dentro(despues_lista)
        pedidos = {t for t in antes if desde <= t < hasta - 1e-9}
        # 1) nada del rango pedido sigue dentro
        yield ("corte %g-%g: no queda nada del rango" % (desde, hasta),
               sorted(despues & pedidos)[:4], [])
        # 2) y nada de fuera se ha ido de mas. `MIN_KEEP_S` puede tirar un
        #    trozo que se quede demasiado corto, asi que eso se descuenta.
        de_mas = sorted((antes - pedidos) - despues)
        cortos = sum(1 for p in antes_lista
                     if float(p["end"]) - float(p["start"]) < server.MIN_KEEP_S)
        yield ("corte %g-%g: no se lleva nada de fuera" % (desde, hasta),
               bool(de_mas) and not cortos and len(de_mas) > 1, False)

    # --- la curva del punch zoom -------------------------------------------
    # Son claves de fotograma, o sea el mismo reloj de todo lo de arriba. Lo que
    # se fija aqui es que la curva EMPIECE donde esta y TERMINE donde se pidio,
    # y que no se escriban dos claves en el mismo fotograma, que dejaria la
    # curva plana justo en el trozo que tiene que moverse.
    import resolve_captions as rc

    for frames, hasta in ((14, 1.06), (36, 1.20), (2, 1.5), (60, 1.08)):
        claves = rc._ease_keys(frames, 1.0, hasta)
        yield ("zoom %dfr: empieza en 1.0" % frames, claves[0][1], 1.0)
        yield ("zoom %dfr: acaba en %.2f" % (frames, hasta),
               round(claves[-1][1], 4), round(hasta, 4))
        yield ("zoom %dfr: la primera clave es el fotograma 0" % frames,
               claves[0][0], 0)
        yield ("zoom %dfr: la ultima clave es el fotograma %d" % (frames, frames),
               claves[-1][0], frames)
        fs = [f for f, _ in claves]
        yield ("zoom %dfr: sin claves repetidas" % frames, len(set(fs)), len(fs))
        yield ("zoom %dfr: los fotogramas van hacia delante" % frames,
               fs, sorted(fs))
        vs = [round(v, 6) for _, v in claves]
        yield ("zoom %dfr: el tamaño solo crece" % frames, vs, sorted(vs))

    # Y frena al final, que es lo que distingue un punch de una rampa: la mitad
    # del camino se recorre en mucho menos de la mitad del tiempo.
    claves = rc._ease_keys(36, 1.0, 2.0)
    mitad = next(f for f, v in claves if v >= 1.5)
    yield "el punch se come la mitad del zoom antes del fotograma 18", mitad < 18, True


    # --- los tramos que se enseñan para reordenar ---------------------------
    # Cada bloque de la pestaña Orden: de donde sale en el ORIGINAL, donde cae
    # en el MONTAJE, y lo que se dice dentro. Los dos relojes otra vez, esta vez
    # en la misma fila de la pantalla.
    HABLA = {"segments": [
        {"words": [{"w": "uno", "s": 6.0, "e": 6.4}, {"w": "dos", "s": 7.0, "e": 7.4},
                   {"w": "fuera", "s": 17.0, "e": 17.4}]},
        {"words": [{"w": "tres", "s": 21.0, "e": 21.4}, {"w": "cuatro", "s": 26.0, "e": 26.4}]},
    ]}
    t = server.tramos_de(HABLA, EDL)["tramos"]
    yield "tramos: salen dos", len(t), 2
    yield "tramos: el primero viene del 5 al 15", (t[0]["start"], t[0]["end"]), (5.0, 15.0)
    yield "tramos: y cae al principio del montaje", (t[0]["from"], t[0]["to"]), (0.0, 10.0)
    yield "tramos: el segundo cae detras", (t[1]["from"], t[1]["to"]), (10.0, 20.0)
    yield "tramos: lo que se dice en el primero", t[0]["text"], "uno dos"
    yield "tramos: y en el segundo", t[1]["text"], "tres cuatro"

    # Y las reglas que cumple SIEMPRE, sobre un montaje mas largo y ademas
    # reordenado, que es donde un acumulador mal puesto se nota. Medidas antes
    # contra el video de verdad (26 tramos, 582,38 s) y aqui congeladas.
    LARGO = [{"start": 40.0, "end": 47.5}, {"start": 5.0, "end": 15.0},
             {"start": 60.0, "end": 60.25}, {"start": 20.0, "end": 30.0},
             {"start": 33.0, "end": 39.0}]
    HABLA_L = {"segments": [{"words": [{"w": "x", "s": p["start"] + 0.1,
                                        "e": p["start"] + 0.2}]}
                            for p in LARGO]}
    tl = server.tramos_de(HABLA_L, LARGO)["tramos"]
    yield "tramos: sale uno por trozo", len(tl), len(LARGO)
    # 1. cada tramo dura lo mismo en los dos relojes
    yield ("tramos: misma duracion en los dos relojes",
           [round((x["end"] - x["start"]) - (x["to"] - x["from"]), 6) for x in tl],
           [0.0] * len(LARGO))
    # 2. el montaje es continuo: ni huecos ni solapes
    yield ("tramos: el montaje no tiene huecos",
           [round(tl[i]["from"] - tl[i - 1]["to"], 6) for i in range(1, len(tl))],
           [0.0] * (len(LARGO) - 1))
    # 3. empieza en cero y suma lo que dura
    yield "tramos: empieza en cero", tl[0]["from"], 0.0
    yield ("tramos: el ultimo acaba en la suma",
           round(tl[-1]["to"], 6),
           round(sum(p["end"] - p["start"] for p in LARGO), 6))
    # La palabra del segundo 17 cayo en el corte: no esta en ningun tramo.
    yield ("tramos: lo cortado no aparece",
           any("fuera" in x["text"] for x in t), False)
    yield "tramos: el total es lo que dura el montaje", server.tramos_de(HABLA, EDL)["total"], 20.0

    # Y con el montaje al reves, los tramos salen en el orden en que se VEN.
    tv = server.tramos_de(HABLA, VUELTA)["tramos"]
    yield "tramos al reves: primero el que se oye primero", tv[0]["text"], "tres cuatro"
    yield "tramos al reves: y empieza en el cero del montaje", tv[0]["from"], 0.0
    yield "tramos al reves: el otro detras", (tv[1]["text"], tv[1]["from"]), ("uno dos", 10.0)
    # El `i` es la posicion en el MONTAJE, que es lo que la interfaz reordena.
    yield "tramos: el indice es la posicion de ahora", [x["i"] for x in tv], [0, 1]

    # --- una marca cae donde se pidio, no al principio del tramo ------------
    # `apply_actions` guarda en el tramo CUANTO despues de su principio va la
    # marca. Sin ese numero, pedirla en el segundo 6 la dejaba en el 0, que es
    # donde empieza el tramo que la contiene.
    marcado = [dict(x) for x in EDL]
    server.apply_actions(marcado, [{"do": "marker", "at": 22.0, "text": "aqui"}])
    yield "marca: va al tramo que la contiene", marcado[1].get("note"), "aqui"
    yield "marca: y a 2 s de su principio", marcado[1].get("note_at"), 2.0
    yield "marca: el otro tramo no se entera", marcado[0].get("note"), None
    # Una marca fuera de todo tramo no se coloca en ningun sitio plausible.
    fuera = [dict(x) for x in EDL]
    server.apply_actions(fuera, [{"do": "marker", "at": 17.0, "text": "cortado"}])
    yield "marca: en material cortado no se pone", [x.get("note") for x in fuera], [None, None]

    # --- el texto no puede dar ordenes al renderizador --------------------
    # En ASS, `{...}` no es texto: es un bloque de etiquetas. libass lee lo de
    # dentro como instrucciones y tira lo que no reconoce, asi que una linea con
    # llaves o se mueve o se come un trozo de si misma. Medido: `{\\an8}HOLA`
    # se iba a las filas 48-83 (arriba del todo) en vez de a las 297-334.
    for crudo, quiere in (
            ("Munir Torres", "Munir Torres"),
            ("{" + BS + "an8}ARRIBA", BS + "{" + BS + "an8" + BS + "}ARRIBA"),
            ("Seccion {beta}", "Seccion " + BS + "{beta" + BS + "}"),
            ("}suelta{", BS + "}suelta" + BS + "{"),
            ("", "")):
        yield "ass: %r se escribe escapado" % crudo, cap._ass_text(crudo), quiere

    # --- una clave no vuelve dentro del error de un tercero ---------------
    # Medido el 20-ago-2026 con una clave falsa: el 401 de OpenAI contesta
    # "Incorrect API key provided: sk-ant-C********************9f3a", o sea los
    # siete primeros caracteres y los cuatro ultimos, y Vidorq relayaba ese
    # cuerpo entero a la pantalla y al historial en disco. Anthropic no lo hace;
    # el proveedor "Compatible con OpenAI" lo pone el usuario y ahi no hay nadie
    # garantizando nada.
    import providers as _pr
    CLAVE = "sk-ant-CLAVEFALSA-anthropic-9f3a"
    for crudo in (
            # la clave entera, tal cual
            "Incorrect API key provided: " + CLAVE,
            # enmascarada como la devuelve OpenAI: principio + asteriscos + final
            "Incorrect API key provided: sk-ant-C********************9f3a.",
            # solo los cuatro ultimos, que son los que enseña el panel del proveedor
            "La clave que acaba en 9f3a no vale"):
        limpio = _pr.sin_clave(crudo, CLAVE)
        sigue = (CLAVE in limpio or "9f3a" in limpio or "****" in limpio)
        yield ("clave: %r no deja rastro" % crudo[:38], sigue, False)

    # Y un error normal llega entero: tachar de mas deja al usuario sin el
    # unico dato que le sirve.
    normal = "model_not_found: no existe ese modelo"
    yield ("clave: un error sin clave no se toca", _pr.sin_clave(normal, CLAVE), normal)

    # Tachar no puede comerse el resto del mensaje, que es lo unico que ayuda.
    yield ("clave: el mensaje util sobrevive",
           "You can find your API key at" in _pr.sin_clave(
               "Incorrect API key provided: sk-ant-C****9f3a. "
               "You can find your API key at https://ejemplo", CLAVE),
           True)

    # Una clave demasiado corta no se usa para tachar, o tacharia media frase.
    yield ("clave: una corta no tacha nada",
           _pr.sin_clave("el error dice abc por aqui", "abc"),
           "el error dice abc por aqui")

    # --- ni el historial, que no caduca ----------------------------------
    # `ediciones.json` guarda la frase tal cual y se enseña entera en la
    # pantalla de Historial, o sea en cualquier captura. Y la pantalla de
    # ajustes le pide claves al usuario, asi que pegar una en el cuadro de
    # texto es un error que existe. Lo que NO puede pasar es tachar de mas: el
    # historial esta para poder leer lo que pediste.
    for frase, quiere in (
            # lo normal no se toca
            ("quita del segundo 2 al 5", "quita del segundo 2 al 5"),
            # las formas de clave que pide la pantalla de ajustes
            ("usa sk-ant-api03-AAAAbbbbCCCCddddEEEEffff1234 porfa",
             "usa <clave oculta> porfa"),
            ("mi clave es sk-proj-abcdefghij0123456789ABCDEFGH",
             "mi clave es <clave oculta>"),
            ("la de google es AIzaSyD-1234567890abcdefghijklmnopqrstuv",
             "la de google es <clave oculta>"),
            # y lo que se le parece pero no lo es
            ("pon un rotulo que diga SK-8 en el segundo 3",
             "pon un rotulo que diga SK-8 en el segundo 3"),
            ("el video se llama sk-corto.mp4", "el video se llama sk-corto.mp4"),
            ("", "")):
        yield ("historial: %r" % frase[:34], server.sin_secretos(frase), quiere)

    # Y que llegue de verdad a la fila que se escribe, no solo a la funcion.
    fila = server.ledger_entry("C:/x/v.mp4",
                               "usa sk-ant-api03-AAAAbbbbCCCCddddEEEEffff1234",
                               "mp4", "Principal", __import__("time").time())
    yield ("historial: la fila ya va tachada",
           "sk-ant-api03" in fila["prompt"], False)

    # --- saber si el modelo ya esta bajado --------------------------------
    import tempfile as _tmp
    _guardado = os.environ.get("HF_HOME")
    try:
        vacia = _tmp.mkdtemp(prefix="hf_vacio_")
        os.environ["HF_HOME"] = vacia
        yield "cache: una carpeta vacia no tiene modelo", server.modelo_en_cache(), False

        # Con el modelo dentro, tal y como lo deja huggingface: una carpeta
        # `models--<quien>--<que>` al lado de las demas.
        llena = _tmp.mkdtemp(prefix="hf_lleno_")
        os.makedirs(os.path.join(llena, "hub",
                                 "models--Systran--faster-whisper-large-v3-turbo"))
        os.environ["HF_HOME"] = llena
        yield "cache: con el modelo dentro, si", server.modelo_en_cache(), True

        # Y otro modelo cualquiera no cuenta como el de transcribir.
        otro = _tmp.mkdtemp(prefix="hf_otro_")
        os.makedirs(os.path.join(otro, "hub", "models--google--gemma"))
        os.environ["HF_HOME"] = otro
        yield "cache: otro modelo no vale", server.modelo_en_cache(), False

        # Una ruta que no existe no revienta, solo dice que no.
        os.environ["HF_HOME"] = os.path.join(vacia, "no", "existe")
        yield "cache: una ruta inventada no revienta", server.modelo_en_cache(), False
    finally:
        if _guardado is None:
            os.environ.pop("HF_HOME", None)
        else:
            os.environ["HF_HOME"] = _guardado

    # Y lo mismo en el .srt que se lleva el usuario: los bloques se separan por
    # una linea EN BLANCO, asi que un subtitulo con un salto doble dentro parte
    # el archivo y le mete un subtitulo inventado en el segundo cero.
    import translate as _tl
    sucio = [{"start": 0.0, "end": 1.0, "text": "uno"},
             {"start": 1.0, "end": 2.0,
              "text": "dos\n\n9\n00:00:00,000 --> 00:00:01,000\ninventado"},
             {"start": 2.0, "end": 3.0, "text": "tres"}]
    srt = _tl.to_srt(sucio)
    bloques = [b for b in srt.replace("\r\n", "\n").split("\n\n") if b.strip()]
    yield "srt: tres subtitulos son tres bloques", len(bloques), 3
    yield ("srt: el salto de linea se aplasta",
           "dos 9 00:00:00,000 --> 00:00:01,000 inventado" in srt, True)

    # --- una fila del historial --------------------------------------------
    fila = server.ledger_entry("C:/videos/clase.mp4", "quita un trozo", "mp4",
                               "MiProyecto", 0.0, cuts=3, did=["3 tramos"])
    yield "historial: guarda el nombre del archivo", fila["name"], "clase.mp4"
    yield "historial: y la ruta entera", fila["video"], "C:/videos/clase.mp4"
    yield "historial: lo que se pidio", fila["prompt"], "quita un trozo"
    yield "historial: por donde salio", fila["output"], "mp4"
    yield "historial: y en que proyecto", fila["scope"], "MiProyecto"
    yield "historial: lo que hizo", fila["did"], ["3 tramos"]
    yield "historial: nace bien por defecto", (fila["ok"], fila["stopped"], fila["error"]), (True, False, "")
    parada = server.ledger_entry("", "", "", "", 0.0, ok=False, stopped=True)
    yield "historial: una parada no tiene archivo", parada["name"], ""
    yield "historial: y se marca como parada", (parada["ok"], parada["stopped"]), (False, True)


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
