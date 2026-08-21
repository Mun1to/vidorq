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

    # --- un retoque entero cambia de reloj de una sola vez ------------------
    # `actions_to_original` es donde se juntan los dos relojes en un retoque, y
    # tiene que hacerlo ANTES de tocar el montaje: en cuanto se aplica el primer
    # corte, el mapa ha cambiado debajo de las demas acciones. Este es el fallo
    # que ya se colo dos veces, y no da error: desplaza.
    def accion(at, **mas):
        return dict({"do": "title", "at": at, "text": "HOLA"}, **mas)

    tres = server.actions_to_original(
        [accion(0.0), accion(9.0), accion(15.0)], EDL)
    yield ("acciones: el 0 del montaje es el 5 del original",
           [a["at"] for a in tres], [5.0, 14.0, 25.0])
    yield ("acciones: llegan en el mismo orden que se pidieron", len(tres), 3)
    yield ("acciones: lo demas de la accion viaja entero",
           [(a["do"], a["text"]) for a in tres[:1]], [("title", "HOLA")])

    # El segundo de una union es el principio del plano SIGUIENTE, no el final
    # del anterior: lo que el usuario ve ahi es el plano nuevo, y el otro
    # fotograma es justo el que se corto.
    yield ("acciones: la union apunta al plano siguiente",
           [a["at"] for a in server.actions_to_original([accion(10.0)], EDL)],
           [20.0])

    # Un segundo que el corte se llevo no se coloca "cerca": se tira. Un cartel
    # dos segundos corrido es peor que un cartel que no sale, porque solo uno
    # de los dos se ve a la primera.
    yield ("acciones: la que cae fuera del montaje se tira",
           server.actions_to_original([accion(25.0)], EDL), [])
    yield ("acciones: sin montaje no se coloca ninguna",
           server.actions_to_original([accion(3.0, until=9.0)], []), [])

    # "Quita desde el minuto 3" sin decir hasta donde es normal y tiene una
    # respuesta obvia: hasta el final de lo que hay.
    largo = server.actions_to_original([accion(15.0, until=999.0)], EDL)
    yield ("acciones: sin final se llega hasta el final del video",
           [(a["at"], a.get("until")) for a in largo], [(25.0, 30.0)])

    # Y un tramo del reves no se endereza, se tira: enderezarlo seria decidir
    # por el usuario que quiso decir.
    yield ("acciones: un tramo del reves se tira",
           server.actions_to_original([accion(9.0, until=1.0)], EDL), [])

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


    # --- el corte cae en un momento quieto ----------------------------------
    # La otra promesa del README: "cuts land on a still moment rather than
    # mid-gesture". El track lleva cuanto se mueve la imagen en cada decima.
    def pista(picos):
        """Movimiento bajo en todas partes, y alto en los segundos que digas."""
        out = []
        t = 0.0
        while t < 30.0:
            alto = any(abs(t - p) < 0.05 for p in picos)
            out.append({"t": round(t, 2), "diff": 40.0 if alto else 1.0,
                        "sig": [10, 10, 10, 10]})
            t += 0.1
        return out

    # El corte cae justo encima de un movimiento: se aparta, y solo ese.
    uno = [{"start": 1.0, "end": 5.0, "zoom": 1.0, "note": ""},
           {"start": 10.0, "end": 14.0, "zoom": 1.0, "note": ""}]
    salida, movidos = server.snap_to_picture(uno, pista([5.0]))
    yield ("quieto: se aparta el corte que cae sobre un movimiento", movidos, 1)
    yield ("quieto: y no se va mas alla de la ventana",
           abs(float(salida[0]["end"]) - 5.0) <= 0.31, True)

    # Metraje tranquilo de principio a fin: no se toca nada. Aqui el instante
    # mas quieto es una moneda al aire, y correr cada corte un tercio de
    # segundo para nada es peor que dejarlos donde estaban.
    dos = [{"start": 1.0, "end": 5.0, "zoom": 1.0, "note": ""},
           {"start": 10.0, "end": 14.0, "zoom": 1.0, "note": ""}]
    _, n = server.snap_to_picture(dos, pista([]))
    yield ("quieto: en metraje tranquilo no mueve nada", n, 0)

    # Sin haber mirado el video no se inventa nada.
    tres2 = [{"start": 1.0, "end": 5.0, "zoom": 1.0, "note": ""}]
    _, n2 = server.snap_to_picture(tres2, None)
    yield ("quieto: sin mirar el video no mueve nada", n2, 0)

    # El caso que de verdad duele: el instante quieto mas cercano cae DENTRO
    # del tramo anterior. Apartar el corte hasta ahi solaparia los dos tramos,
    # asi que se prefiere un corte peor a una linea de tiempo rota.
    vecinos = [{"start": 1.0, "end": 5.0, "zoom": 1.0, "note": ""},
               {"start": 5.1, "end": 9.0, "zoom": 1.0, "note": ""}]
    server.snap_to_picture(vecinos, pista([5.1, 5.2, 5.3, 5.4]))
    yield ("quieto: no se mete en el tramo vecino",
           float(vecinos[0]["end"]) <= float(vecinos[1]["start"]) + 1e-9, True)
    yield ("quieto: no le da la vuelta a ningun tramo",
           [p for p in vecinos if float(p["end"]) <= float(p["start"])], [])

    # --- cortar sobre el movimiento -----------------------------------------
    # Parte un plano por dentro cuando la imagen hace algo (un salto, un
    # barrido). Partir es justo donde se pierde material si el reparto de los
    # trozos no cuadra, asi que eso es lo que mas se mira aqui.
    largo = [{"start": 0.0, "end": 20.0, "zoom": 1.0, "note": ""}]
    trozos, hechos = server.cut_on_beats([dict(p) for p in largo],
                                         pista([5.0, 10.0, 15.0]))
    yield ("latidos: tres movimientos parten el plano en cuatro", hechos, 3)
    yield ("latidos: salen cuatro trozos", len(trozos), 4)

    # Lo que de verdad importa: los trozos cubren el plano entero, sin huecos
    # y sin pisarse. Un fallo aqui borra segundos de video sin avisar.
    yield ("latidos: los trozos empiezan donde empezaba el plano",
           float(trozos[0]["start"]), 0.0)
    yield ("latidos: y acaban donde acababa", float(trozos[-1]["end"]), 20.0)
    yield ("latidos: no queda ni un hueco ni un solape entre trozos",
           [(trozos[i]["end"], trozos[i + 1]["start"])
            for i in range(len(trozos) - 1)
            if abs(float(trozos[i]["end"]) - float(trozos[i + 1]["start"])) > 1e-9],
           [])

    # El golpe alterna: sin alternar los cuatro trozos salen con el mismo
    # encuadre y el corte no se lee como corte, solo como un salto raro.
    enc = [round(float(p.get("zoom", 1.0)), 3) for p in trozos]
    yield ("latidos: el encuadre alterna trozo a trozo",
           [i for i in range(1, len(enc)) if enc[i] == enc[i - 1]], [])

    # Un movimiento pegado al borde del plano no parte nada: dejaria un
    # destello de dos decimas, que no es un plano.
    corto = [{"start": 0.0, "end": 3.0, "zoom": 1.0, "note": ""}]
    _, nada = server.cut_on_beats(corto, pista([0.5, 2.7]))
    yield ("latidos: un movimiento pegado al borde no parte nada", nada, 0)

    # Sin haber mirado el video, y sin movimiento ninguno, no se toca nada.
    quieto1 = [{"start": 0.0, "end": 20.0, "zoom": 1.0, "note": ""}]
    yield ("latidos: sin mirar el video no parte nada",
           server.cut_on_beats(quieto1, None)[1], 0)
    yield ("latidos: en metraje sin movimiento tampoco",
           server.cut_on_beats(quieto1, pista([]))[1], 0)

    # Y el temblor solo va en los trozos que EMPIEZAN sobre el movimiento:
    # el primero empieza donde empezaba el habla, y ahi no paso nada.
    temblor, _ = server.cut_on_beats([dict(p) for p in largo],
                                     pista([5.0, 10.0, 15.0]), shake=True)
    yield ("latidos: el primer trozo no tiembla", temblor[0].get("shake"), False)
    yield ("latidos: los que empiezan sobre el movimiento si",
           [bool(p.get("shake")) for p in temblor[1:]], [True, True, True])

    # --- esconder los saltos ------------------------------------------------
    # Lo que separa un video cortado de uno editado, y el README lo promete.
    # La huella de un track es una lista de numeros por segundo; iguales a los
    # dos lados = plano fijo = el corte salta.
    FIJO = [{"t": float(i), "sig": [10, 10, 10, 10]} for i in range(0, 60)]

    def tramos(*pares):
        return [{"start": a, "end": b, "zoom": 1.0, "note": ""} for a, b in pares]

    # Tres uniones seguidas sobre un plano fijo: las tres saltan.
    tres = tramos((0.0, 5.0), (8.0, 12.0), (15.0, 19.0), (22.0, 26.0))
    salida, tocadas = server.hide_jump_cuts(tres, FIJO)
    # Dos y no tres: el contador cuenta donde se PONE zoom, y como alterna, la
    # union del medio se arregla volviendo a 1.0, que tambien cambia el
    # encuadre. Lo que importa es la regla de abajo, no este numero.
    yield ("saltos: se pone zoom en dos de las tres uniones", tocadas, 2)
    # Y alternan: sin esto las tres acaban con el mismo encuadre y no sirve.
    zooms = [round(float(p.get("zoom", 1.0)), 3) for p in salida]
    yield ("saltos: el encuadre alterna en cada union",
           [i for i in range(1, len(zooms)) if zooms[i] == zooms[i - 1]], [])

    # Sin hueco entre dos tramos no se ha quitado nada, asi que no hay salto.
    pegados = tramos((0.0, 5.0), (5.0, 9.0))
    _, n = server.hide_jump_cuts(pegados, FIJO)
    yield ("saltos: sin hueco no hay salto que esconder", n, 0)

    # Un cambio de plano de verdad se deja en paz: ahi la imagen ya cambia.
    CAMBIA = ([{"t": float(i), "sig": [10, 10, 10, 10]} for i in range(0, 8)]
              + [{"t": float(i), "sig": [90, 90, 90, 90]} for i in range(8, 60)])
    otro = tramos((0.0, 5.0), (8.0, 12.0))
    _, n2 = server.hide_jump_cuts(otro, CAMBIA)
    yield ("saltos: un cambio de plano no se toca", n2, 0)

    # Y un zoom que ya estaba puesto por otra razon no se pisa.
    con_zoom = tramos((0.0, 5.0), (8.0, 12.0))
    con_zoom[1]["zoom"] = 1.06
    server.hide_jump_cuts(con_zoom, FIJO)
    yield ("saltos: no pisa un zoom que ya estaba", con_zoom[1]["zoom"], 1.06)

    # Sin track no se toca nada: sin mirar el video no se puede saber si salta.
    sin = tramos((0.0, 5.0), (8.0, 12.0))
    _, n3 = server.hide_jump_cuts(sin, None)
    yield ("saltos: sin mirar el video no se inventa nada", n3, 0)

    # --- las tomas repetidas ------------------------------------------------
    # Sale en el informe de cada edicion ("2 tomas repetidas") y no tenia
    # prueba. Decide cual de dos intentos se queda, asi que equivocarse aqui
    # borra algo que el usuario SI queria.
    def frase(texto, s0, e0):
        return {"text": texto, "start": s0, "end": e0,
                "words": [{"w": texto.split()[0], "s": s0, "e": e0}]}

    REPES = {"segments": [
        frase("hola a todos bienvenidos", 1.0, 3.0),
        frase("hola a todos bienvenidos", 4.0, 6.0),     # el mismo, otra vez
        frase("hoy vamos a ver una cosa", 7.0, 9.0),
        frase("y esto no se parece en nada", 20.0, 22.0),
        frase("hola a todos bienvenidos", 30.0, 32.0),   # vuelve, pero LEJOS
    ]}
    quedan, fuera = server.drop_repeated_takes(REPES)
    yield ("tomas: dos intentos seguidos se quedan en uno", fuera, 1)
    yield ("tomas: quedan cuatro frases", len(quedan), 4)
    # Y se queda el ULTIMO intento, no el primero: se mira por donde empieza.
    yield ("tomas: se queda el ultimo intento", quedan[0]["start"], 4.0)
    # La que vuelve mas tarde sobrevive: repetir algo al final es un recurso,
    # no un tropiezo, y solo se comparan vecinas.
    yield ("tomas: la que vuelve mas tarde sobrevive",
           [q["start"] for q in quedan if q["text"].startswith("hola")], [4.0, 30.0])
    # Y dos frases distintas no se tocan.
    DISTINTAS = {"segments": [frase("una cosa", 1.0, 2.0),
                              frase("otra completamente distinta", 3.0, 4.0)]}
    yield ("tomas: dos frases distintas se quedan las dos",
           len(server.drop_repeated_takes(DISTINTAS)[0]), 2)

    # --- el motor de corte por defecto -------------------------------------
    # Es lo que corre cuando no escribes nada (el preset Limpieza), o sea el
    # camino mas usado, y no tenia ni una prueba. Lo que cumple su salida no
    # depende del audio ni del modelo, asi que se puede fijar.
    def palabra(w, s0, e0):
        return {"w": w, "s": round(s0, 2), "e": round(e0, 2)}

    HABLADO = {"duration": 40.0, "language": "es", "segments": [
        # una frase normal
        {"text": "hola a todos", "start": 1.0, "end": 2.6, "words": [
            palabra("hola", 1.0, 1.4), palabra("a", 1.5, 1.6),
            palabra("todos", 1.7, 2.6)]},
        # un titubeo SOLO, con silencio a los dos lados
        {"text": "eh", "start": 6.0, "end": 6.3, "words": [palabra("eh", 6.0, 6.3)]},
        # otra frase, despues de un silencio largo
        {"text": "esto es lo que hay", "start": 12.0, "end": 14.2, "words": [
            palabra("esto", 12.0, 12.4), palabra("es", 12.5, 12.7),
            palabra("lo", 12.8, 12.9), palabra("que", 13.0, 13.2),
            palabra("hay", 13.3, 14.2)]},
        # y una palabra suelta al final, pegada al borde del video
        # Pegada al final a proposito: 39.95 + el margen de 0.15 se saldria
        # del video, asi que este es el dato que hace fallar la regla 3 si
        # alguien quita el tope. Sin el, esa regla no puede saltar nunca.
        {"text": "adios", "start": 39.3, "end": 39.95,
         "words": [palabra("adios", 39.3, 39.95)]},
    ]}
    corte, informe = server.edl_from_speech(HABLADO, "es")
    yield ("corte por defecto: salen tramos", len(corte) > 0, True)
    # 1) en orden y sin pisarse
    yield ("corte por defecto: en orden y sin pisarse",
           [(round(corte[i]["end"], 3), round(corte[i + 1]["start"], 3))
            for i in range(len(corte) - 1)
            if float(corte[i]["end"]) > float(corte[i + 1]["start"]) + 1e-9], [])
    # 2) ninguno demasiado corto para ser un plano
    yield ("corte por defecto: ninguno por debajo del minimo",
           [round(p["end"] - p["start"], 3) for p in corte
            if p["end"] - p["start"] < server.MIN_KEEP_S - 1e-9], [])
    # 3) nada fuera del video
    yield ("corte por defecto: nada se sale del video",
           [p for p in corte if p["start"] < -1e-9 or p["end"] > 40.0 + 1e-9], [])
    # 4) lo que se dice sigue dentro. El titubeo suelto NO cuenta: se va a
    #    proposito, que para eso esta.
    def dentro(t):
        return any(float(p["start"]) - 1e-9 <= t <= float(p["end"]) + 1e-9
                   for p in corte)
    perdidas = [w["w"] for seg in HABLADO["segments"] for w in seg["words"]
                if w["w"] != "eh" and not dentro(w["s"])]
    yield ("corte por defecto: no se pierde ninguna palabra", perdidas, [])
    # 5) y el titubeo aislado se fue
    yield ("corte por defecto: el titubeo suelto se va", dentro(6.1), False)

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

    # --- ni un nombre puede salirse de su carpeta -------------------------
    # El nombre del workspace lo escribe el usuario en un `window.prompt` que
    # no valida nada, y el del proyecto lo trae el puente de Resolve, que es
    # codigo de un tercero. Los dos acaban siendo una CARPETA, asi que la
    # unica defensa es `_safe_name`: una carpeta que se escapa de la suya
    # escribe donde nadie la va a buscar.
    RAIZ_FALSA = Path(tempfile.mkdtemp()) / "edit" / "video"
    PROHIBIDOS = "/" + BS + ':.*?"<>|'
    HOSTILES = ["..", "../..", "../../etc/passwd", ".." + BS + ".." + BS + "x",
                "C:" + BS + "Windows" + BS + "System32", "a/b", ".oculto",
                "nombre.txt", "", "   ", "***", "~", "$HOME", "con:stream"]
    for crudo in HOSTILES:
        limpio = server._safe_name(crudo)
        corto = crudo[:18] or "(vacio)"
        yield ("nombre: %r no deja separadores" % corto,
               [c for c in limpio if c in PROHIBIDOS], [])
        yield ("nombre: %r nunca sale vacio" % corto, bool(limpio), True)
        destino = (RAIZ_FALSA / "p" / limpio).resolve()
        yield ("nombre: %r se queda dentro de su carpeta" % corto,
               str(destino).startswith(str(RAIZ_FALSA.resolve())), True)

    # Limpiar dos veces tiene que dar lo mismo que limpiar una. El nombre
    # limpio es con el que se busca la carpeta que YA existe, asi que si
    # cambiara al pasarlo otra vez, la conversacion de ayer no se encontraria.
    for crudo in HOSTILES + ["Principal", "suelto", "Proyecto 12", "ñandú"]:
        una = server._safe_name(crudo)
        yield ("nombre: limpiar %r dos veces da lo mismo" % (crudo[:18] or "(vacio)"),
               server._safe_name(una), una)

    # Y no crece. El tope de 40 es lo que evita meter un nombre de mil
    # caracteres en una ruta de Windows, que se acaba a los 260.
    yield ("nombre: nunca pasa de 40 caracteres",
           len(server._safe_name("x" * 500)), 40)

    # --- un emoji en el nombre del archivo no puede tumbar el render -------
    # Los dos scripts que corren como SUBPROCESO heredan la codepage de la
    # consola (cp1252 en un Windows en espanol) para su propio stdout, pase lo
    # que pase en el lado que los lee. Un nombre arrastrado por el usuario tipo
    # "video (claqueta) prueba.mp4" reventaba el print de "MUX_OK: <ruta>" con
    # UnicodeEncodeError, y ahi el render ya iba por el 93%.
    import subprocess as _sp
    for guion in ("vidorq_render.py", "transcribe.py"):
        fuente = (RAIZ / "skill" / "helpers" / guion).read_text(encoding="utf-8")
        yield ("emoji: %s blinda su stdout" % guion,
               "reconfigure(encoding=" in fuente, True)
        # Y por DELANTE de los imports pesados, no detras: lo que se escriba
        # antes del blindaje sale con la codepage vieja, y eso incluye la traza
        # de un import que falle, que es justo la que hay que poder leer.
        # Medido el 21-ago-2026: con el blindaje detras, un ImportError que
        # dice "no se pudo cargar la libreria de video" se lee con rombos donde
        # van las tildes, o sea que el unico mensaje que ayuda llega roto.
        primero = fuente.index("reconfigure(encoding=")
        for pesado in ("NLimport av", "NLimport numpy"):
            pesado = pesado.replace("NL", chr(10))
            if pesado in fuente:
                yield ("emoji: %s blinda antes de %s" % (guion, pesado.strip()),
                       primero < fuente.index(pesado), True)

    # Y funciona de verdad: un hijo sin PYTHONIOENCODING imprimiendo un emoji.
    fuente = (RAIZ / "skill" / "helpers" / "vidorq_render.py").read_text(encoding="utf-8")
    i = fuente.index("if sys.stdout.encoding")
    j = fuente.index("sys.stderr.reconfigure", i)
    blindaje = fuente[i:fuente.index(chr(10), j)]
    carpeta = Path(tempfile.mkdtemp())
    CLAQUETA = chr(0x1F3AC)
    for nombre, cuerpo in (("sin blindaje", "import sys" + chr(10)),
                           ("con blindaje", "import sys" + chr(10) + blindaje + chr(10))):
        hijo = carpeta / ("h%d.py" % len(cuerpo))
        hijo.write_text(cuerpo + "print('MUX_OK: ' + sys.argv[1])" + chr(10),
                        encoding="utf-8")
        entorno = dict(os.environ)
        entorno.pop("PYTHONIOENCODING", None)
        fin = _sp.run([sys.executable, str(hijo), "video %s prueba.mp4" % CLAQUETA],
                      capture_output=True, env=entorno)
        yield ("emoji: un hijo %s" % nombre, fin.returncode == 0,
               nombre == "con blindaje")

    # --- el video vertical sin barras negras -------------------------------
    # Resolve METE un clip que no cuadra dentro del cuadro, asi que un 16:9 en
    # una linea de tiempo vertical llega con franjas negras arriba y abajo. El
    # zoom que las tapa es el unico numero que separa "exporta en vertical" de
    # "exporta en vertical con bandas". Pasarse recorta cara; quedarse corto
    # deja la banda.
    for ratio, quiere in (("vertical", (1080, 1920)), ("portrait", (1080, 1350)),
                          ("square", (1080, 1080)), ("wide", (1920, 1080))):
        yield ("encuadre: %r sale a su tamano" % ratio,
               server.out_frame(ratio, 1920, 1080), quiere)

    # Y "no lo cambies" tiene que respetar el tamano del ORIGINAL, sea cual sea.
    # Sin fuente distinta de 1920x1080 esto se cumple por casualidad: un 4K
    # exportado a 1080 sin que nadie lo pidiera es perdida de calidad callada.
    for w, h in ((3840, 2160), (1280, 720), (1080, 1920), (720, 480)):
        for ratio in ("source", "", None, "loquesea"):
            yield ("encuadre: %r deja un %dx%d como estaba" % (ratio, w, h),
                   server.out_frame(ratio, w, h), (w, h))

    # De 1920x1080 a 1080x1920 son 3.16, que es lo que dice el docstring.
    yield ("encuadre: de apaisado a vertical, 3.16",
           round(server.fill_zoom(1920, 1080, 1080, 1920), 2), 3.16)
    # Y al reves lo mismo: el zoom es simetrico, no depende de quien es mas ancho.
    yield ("encuadre: de vertical a apaisado, lo mismo",
           round(server.fill_zoom(1080, 1920, 1920, 1080), 2), 3.16)

    # Lo que de verdad tiene que cumplir: con ese zoom, el clip TAPA el cuadro.
    # Se comprueba con la cuenta de verdad, no repitiendo la formula: se mete el
    # clip como lo mete Resolve (min) y se mira si al multiplicar por el zoom
    # cubre los dos lados.
    for w, h, ow, oh in ((1920, 1080, 1080, 1920), (1920, 1080, 1080, 1080),
                         (1920, 1080, 1080, 1350), (3840, 2160, 1080, 1920),
                         (1080, 1920, 1080, 1080), (1440, 1080, 1920, 1080)):
        z = server.fill_zoom(w, h, ow, oh)
        mete = min(ow / w, oh / h)          # como lo mete Resolve
        ancho, alto = w * mete * z, h * mete * z
        yield ("encuadre: %dx%d en %dx%d no deja banda" % (w, h, ow, oh),
               (ancho >= ow - 0.5 and alto >= oh - 0.5), True)
        # Y no recorta mas de lo que el cambio de forma ya obliga: uno de los
        # dos lados tiene que quedar clavado.
        yield ("encuadre: %dx%d en %dx%d no recorta de mas" % (w, h, ow, oh),
               (abs(ancho - ow) < 0.5 or abs(alto - oh) < 0.5), True)

    # Misma forma, otro tamano: no hace falta zoom ninguno, meterlo ya lo llena.
    yield ("encuadre: de 720p a 1080p no hace falta zoom",
           server.fill_zoom(1280, 720, 1920, 1080), 1.0)
    yield ("encuadre: el mismo tamano no se toca",
           server.fill_zoom(1920, 1080, 1920, 1080), 1.0)
    # Y sin saber el tamano no se inventa un zoom, que seria recortar a ciegas.
    yield ("encuadre: sin medidas no se inventa un zoom",
           [server.fill_zoom(a, b, c, d) for a, b, c, d in
            ((0, 1080, 1080, 1920), (1920, 0, 1080, 1920),
             (1920, 1080, 0, 1920), (1920, 1080, 1080, 0))],
           [1.0, 1.0, 1.0, 1.0])

    # --- el deslizador de ritmo de "Tu marca" ------------------------------
    # Viajaba dentro del JSON de la marca hasta el prompt del modelo y ahi se
    # quedaba: moverlo de 1 a 10 no cambiaba una sola edicion. Ahora sale en
    # los dos numeros que cortan de verdad, y el 6 tiene que devolver EXACTO lo
    # de siempre, porque quien no toca el deslizador no debe notar que existe.
    yield ("ritmo: el 6 es lo de siempre", server.pace_gap(6), (0.6, 0.15))
    yield ("ritmo: sin poner nada, tambien", server.pace_gap(None), (0.6, 0.15))
    yield ("ritmo: el 1 aguanta mas silencio y deja mas aire",
           server.pace_gap(1), (1.1, 0.25))
    yield ("ritmo: el 10 corta lo que sobra", server.pace_gap(10), (0.2, 0.07))
    # Fuera de rango no se rompe: se pega al extremo. Ojo con el 0, que NO es
    # el extremo de abajo sino "sin poner": el deslizador va de 1 a 10, asi que
    # un 0 solo llega de un `brand.json` editado a mano o a medias, y ahi lo
    # sano es el valor de siempre y no el corte mas agresivo que existe.
    yield ("ritmo: el 0 es sin poner, no el minimo", server.pace_gap(0), (0.6, 0.15))
    yield ("ritmo: por debajo del 1 se queda en el 1",
           server.pace_gap(-5), (1.1, 0.25))
    yield ("ritmo: por encima del 10 se queda en el 10",
           server.pace_gap(99), (0.2, 0.07))
    # Y siempre va a menos: subir el deslizador nunca puede cortar menos.
    huecos = [server.pace_gap(p) for p in range(1, 11)]
    yield ("ritmo: subirlo siempre corta mas y respira menos",
           [i for i in range(1, 10)
            if huecos[i][0] >= huecos[i - 1][0] or huecos[i][1] >= huecos[i - 1][1]],
           [])
    yield ("ritmo: el aire nunca se va a cero",
           [g for g in huecos if g[1] <= 0 or g[0] <= 0], [])

    # --- el perfil de marca no se puede perder de un guardado --------------
    # Rellenar "Tu marca" es un rato de trabajo de alguien y no vive en ningun
    # otro sitio: si un guardado lo pisa, no hay de donde sacarlo. Por eso cada
    # guardado deja la version de antes al lado.
    #
    # `WORKSPACES` y `CONFIG` apuntan al %APPDATA% de VERDAD, asi que aqui se
    # desvian a una carpeta temporal y se devuelven a su sitio pase lo que
    # pase. Sin esto, la prueba haria el destrozo que viene a evitar.
    import json
    marca = []
    _ws, _cfg = server.WORKSPACES, server.CONFIG
    try:
        raiz = Path(tempfile.mkdtemp())
        server.WORKSPACES = raiz / "workspaces"
        server.CONFIG = raiz / "config.json"
        casa = server.ws_dir()
        bueno = {"brandName": "Vidorq", "pace": 7, "tone": "directo"}

        def copia():
            """La copia de seguridad, o None si no la hay. Sin reventar: una
            red que no esta tiene que salir como caso fallado con su nombre,
            no como una traza en mitad de la tanda."""
            try:
                return json.loads((casa / "brand.anterior.json").read_text(
                    encoding="utf-8"))
            except Exception:
                return None

        def perfil():
            try:
                return server.profile_load()
            except Exception as e:
                return "REVENTO: " + type(e).__name__

        server.profile_save(bueno)
        marca.append(("marca: lo guardado se lee igual", perfil(), bueno))
        marca.append(("marca: el primer guardado no inventa una copia",
                      (casa / "brand.anterior.json").exists(), False))

        # Y ahora lo que paso de verdad: llega un guardado que lo pisa.
        server.profile_save({"brandName": "Prueba"})
        marca.append(("marca: el perfil de antes queda al lado", copia(), bueno))

        # Guardar dos veces lo MISMO no puede comerse la copia buena, que es
        # como se pierde de verdad: pisas, te das cuenta, y al volver a darle
        # a guardar te has cargado la unica version que quedaba.
        server.profile_save({"brandName": "Prueba"})
        marca.append(("marca: guardar lo mismo no se come la copia", copia(), bueno))

        # Un perfil vacio no merece copia: guardarla taparia la buena con nada.
        server.profile_save({})
        marca.append(("marca: un perfil vacio se guarda", perfil(), {}))
        marca.append(("marca: y aun asi la copia buena sigue ahi",
                      (copia() or {}).get("brandName"), "Prueba"))

        # Un brand.json roto se lee como "no hay perfil" y no revienta el motor:
        # un JSON a medias no puede dejar la ventana sin abrir.
        (casa / "brand.json").write_text("{roto", encoding="utf-8")
        marca.append(("marca: un perfil roto no tumba nada", perfil(), {}))
    finally:
        server.WORKSPACES, server.CONFIG = _ws, _cfg
    for caso in marca:
        yield caso

    # --- el criterio Podcast: marcar donde se pregunta ----------------------
    # `mark_questions` es lo que hace que en un podcast el zoom entre justo
    # cuando alguien pregunta. Se equivoca de dos maneras: no marcar (y el
    # video queda plano) o marcar de mas (y el zoom entra a cada frase, que
    # marea).
    PREGUNTAS = {"duration": 60.0, "segments": [
        {"text": "Hola a todos, bienvenidos", "start": 1.0, "end": 3.0},
        {"text": "Que te llevo a montar esto", "start": 6.0, "end": 8.0},
        {"text": "Pues mira, fue por casualidad", "start": 9.0, "end": 12.0},
        {"text": "Y como lo hiciste?", "start": 20.0, "end": 22.0},
        {"text": "Con mucha paciencia", "start": 23.0, "end": 26.0},
        {"text": "Donde aprendiste", "start": 40.0, "end": 42.0},
    ]}
    tramos_q = [{"start": 0.0, "end": 5.0, "zoom": 1.0, "note": ""},
                {"start": 6.0, "end": 13.0, "zoom": 1.0, "note": ""},
                {"start": 20.0, "end": 27.0, "zoom": 1.0, "note": ""},
                {"start": 30.0, "end": 35.0, "zoom": 1.0, "note": ""},
                {"start": 40.0, "end": 45.0, "zoom": 1.0, "note": ""}]
    marcados = server.mark_questions(PREGUNTAS, [dict(t) for t in tramos_q])
    yield ("podcast: se marcan los tramos donde se pregunta",
           [round(float(t["zoom"]), 2) for t in marcados],
           [1.0, 1.05, 1.05, 1.0, 1.05])
    # El que no lleva pregunta se queda como estaba, sin nota inventada.
    yield ("podcast: el tramo sin pregunta no se toca",
           (marcados[0]["note"], marcados[3]["note"]), ("", ""))
    yield ("podcast: el marcado dice por que lo esta",
           bool(marcados[1]["note"]), True)
    # Se reconoce por el signo Y por como empieza la frase, con tilde y sin
    # ella: nadie dicta acentos, y "Como lo hiciste" es una pregunta igual.
    for frase, quiere in (("Que opinas", True), ("Qué opinas", True),
                          ("Como lo ves", True), ("Cómo lo ves", True),
                          ("Cual prefieres", True), ("Quien vino", True),
                          ("Por que no", True), ("Donde queda", True),
                          ("Cuando empieza", True), ("Cuanto cuesta", True),
                          ("Cuantos anos tienes", True),
                          ("Esto no es una pregunta", False),
                          ("Comodo, verdad?", True),
                          # Las que se colaban antes de poner la frontera de
                          # palabra: trece de diecinueve frases normales de
                          # podcast se leian como pregunta, o sea que el zoom
                          # entraba casi en cada frase.
                          ("Comodamente sentado", False),
                          ("Queremos hacer un video", False),
                          ("Queria contarte algo", False),
                          ("Quedamos en eso", False),
                          ("Quesos de la zona", False),
                          ("Cualidades que tiene", False),
                          ("Cualquiera lo hace", False),
                          ("Cuantioso el gasto", False),
                          ("Cuerpo entero en el plano", False),
                          ("Hola a todos", False)):
        uno = {"duration": 10.0,
               "segments": [{"text": frase, "start": 1.0, "end": 2.0}]}
        salida = server.mark_questions(
            uno, [{"start": 0.0, "end": 5.0, "zoom": 1.0, "note": ""}])
        yield ("podcast: %r se lee como pregunta" % frase,
               round(float(salida[0]["zoom"]), 2) == 1.05, quiere)

    # La union de dos tramos es del SIGUIENTE, no del anterior: una pregunta que
    # empieza justo donde acaba un tramo se ve en el que entra.
    borde = server.mark_questions(
        {"duration": 20.0, "segments": [{"text": "Que tal?", "start": 5.0, "end": 6.0}]},
        [{"start": 0.0, "end": 5.0, "zoom": 1.0, "note": ""},
         {"start": 5.0, "end": 10.0, "zoom": 1.0, "note": ""}])
    yield ("podcast: la pregunta del borde es del tramo que entra",
           [round(float(t["zoom"]), 2) for t in borde], [1.0, 1.05])

    # --- el criterio Montaje: quedarse con lo mejor -------------------------
    # Elige sobre lo que ya sobrevivio a la limpieza, asi que los titubeos y las
    # tomas repetidas ya no estan. Lo que no puede hacer nunca es inventarse
    # metraje que el video no tiene.
    def dice(texto, a, b):
        return {"text": texto, "start": a, "end": b,
                "words": [{"w": w, "s": round(a + i * 0.2, 2),
                           "e": round(a + i * 0.2 + 0.2, 2)}
                          for i, w in enumerate(texto.split())]}

    LARGO = {"duration": 60.0, "language": "es", "segments": [
        dice("primera frase del video", 1.0, 3.0),
        dice("segunda frase que dura", 6.0, 8.0),
        dice("tercera frase por aqui", 12.0, 14.0),
        dice("cuarta frase mas larga todavia", 18.0, 21.0),
        dice("quinta frase de las buenas", 26.0, 28.0),
        dice("sexta frase para acabar", 33.0, 35.0),
        dice("septima y ultima frase", 40.0, 42.0),
    ]}
    limpio, _r = server.edl_from_speech(LARGO, "es")
    pista_m = [{"t": round(i * 0.5, 2), "diff": 1.0 + (i % 7),
                "sig": [10, 10, 10, 10]} for i in range(0, 120)]
    corto, informe = server.edl_montage("no_existe.mp4", LARGO, keep_ratio=0.45,
                                        track=pista_m, lang="es")
    yield ("montaje: sale algo", len(corto) > 0, True)
    yield ("montaje: se queda con menos de lo que habia",
           len(corto) < len(limpio), True)
    # Lo que se queda tenia que estar en el video: cada tramo del montaje cae
    # dentro de uno de la limpieza. Inventarse un segundo aqui seria enseñar
    # metraje que el usuario nunca grabo.
    def cabe(p):
        return any(float(q["start"]) - 1e-6 <= float(p["start"])
                   and float(p["end"]) <= float(q["end"]) + 1e-6 for q in limpio)
    yield ("montaje: no se inventa ni un segundo",
           [p for p in corto if not cabe(p)], [])
    yield ("montaje: en orden y sin pisarse",
           [i for i in range(len(corto) - 1)
            if float(corto[i]["end"]) > float(corto[i + 1]["start"]) + 1e-9], [])
    # Y se acerca a lo que se le pidio guardar, por arriba: se para en cuanto
    # llega, asi que puede pasarse un tramo pero no quedarse corto.
    yield ("montaje: guarda al menos lo que se le pidio",
           float(informe["kept"]) >= float(informe["of"]) * 0.45 - 1e-6, True)
    yield ("montaje: el informe cuenta los tramos que salen",
           informe["cuts"], len(corto))

    # Con tres frases o menos no hay nada que elegir: se devuelve la limpieza
    # tal cual en vez de dejar un video de un solo plano.
    CORTO = {"duration": 20.0, "language": "es", "segments": [
        dice("una frase sola", 1.0, 3.0), dice("y otra mas", 8.0, 10.0)]}
    poco, _ = server.edl_montage("no_existe.mp4", CORTO, keep_ratio=0.45, lang="es")
    yield ("montaje: con dos frases no se elige nada",
           poco, server.edl_from_speech(CORTO, "es")[0])

    # --- quien puede hablarle al motor -------------------------------------
    # Escucha en 127.0.0.1, asi que desde fuera del ordenador no se llega. Lo
    # que SI llega es cualquier PAGINA abierta en el navegador: una web puede
    # pedirle cosas a localhost. Detras hay cosas del usuario (`/history` lleva
    # las rutas de sus videos, `/words` la transcripcion entera) y dos botones
    # que hacen dano sin leer nada (`/stop` y `/shutdown`).
    for origen in ("", None,                       # curl, el skill, Python
                   "http://localhost:1420",        # la ventana en desarrollo
                   "http://localhost",
                   "https://localhost:5173",
                   "http://127.0.0.1:9877",
                   "http://tauri.localhost",       # la aplicacion compilada
                   "tauri://localhost",
                   "asset://localhost",
                   "http://[::1]:1420"):
        yield ("puerta: %r es de casa" % (origen or "sin Origin"),
               server.de_casa(origen), True)

    for origen in ("https://evil.com",
                   "http://evil.com:1420",
                   # El clasico: un dominio que ACABA pareciendose a localhost.
                   "http://localhost.evil.com",
                   "http://127.0.0.1.evil.com",
                   "https://midominio.localhost.attacker.net",
                   # Un iframe en caja manda esto, y no es nadie conocido.
                   "null",
                   "http://192.168.1.50:1420",
                   "https://vidorq.com"):
        yield ("puerta: %r se queda fuera" % origen, server.de_casa(origen), False)

    # Y la puerta se cierra DE VERDAD, no solo en la funcion: se levanta el
    # motor en un puerto aparte, con un %APPDATA% de pega para no rozar nada
    # del usuario, y se le llama desde un origen de fuera.
    import json as _js, threading as _th, urllib.error as _ue
    import urllib.request as _ur
    from http.server import ThreadingHTTPServer as _THS
    _ws, _cfg = server.WORKSPACES, server.CONFIG
    puerta = []
    try:
        _raiz = Path(tempfile.mkdtemp())
        server.WORKSPACES, server.CONFIG = _raiz / "workspaces", _raiz / "config.json"
        srv = _THS(("127.0.0.1", 0), server.Handler)
        puerto = srv.server_address[1]
        hilo = _th.Thread(target=srv.serve_forever, daemon=True)
        hilo.start()

        def llamar(ruta, origen=None):
            pet = _ur.Request("http://127.0.0.1:%d%s" % (puerto, ruta))
            if origen:
                pet.add_header("Origin", origen)
            try:
                with _ur.urlopen(pet, timeout=6) as r:
                    return r.status, dict(r.headers).get("Access-Control-Allow-Origin")
            except _ue.HTTPError as e:
                return e.code, dict(e.headers).get("Access-Control-Allow-Origin")
            except Exception as e:
                return type(e).__name__, None

        for ruta in ("/health", "/history"):
            puerta.append(("puerta: la ventana entra en %s" % ruta,
                           llamar(ruta, "http://localhost:1420")[0], 200))
            puerta.append(("puerta: una web de fuera no entra en %s" % ruta,
                           llamar(ruta, "https://evil.com")[0], 403))
            # Y sin la cabecera de permiso, que es lo que impide LEER lo que
            # conteste. Las dos cosas, porque el 403 sin esto sigue siendo
            # legible desde la web que pregunto.
            puerta.append(("puerta: ni le deja leer la respuesta de %s" % ruta,
                           llamar(ruta, "https://evil.com")[1], None))
        # curl y el skill de un agente no mandan Origin, y tienen que seguir
        # entrando: por ahi es por donde se usa Vidorq sin la ventana.
        puerta.append(("puerta: sin Origin se entra como siempre",
                       llamar("/health")[0], 200))
        srv.shutdown()
    finally:
        server.WORKSPACES, server.CONFIG = _ws, _cfg
    for caso in puerta:
        yield caso

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

    # --- guardar el montaje no puede dejarlo a medias ----------------------
    # `edl.json` ES el montaje, y ademas es lo que decide de que reloj habla
    # una frase: leerlo roto se lee como "no hay montaje", asi que el turno
    # siguiente entiende "el segundo 12" en el reloj del original y apunta a
    # otro sitio, sin un solo error por pantalla. Por eso se escribe aparte y
    # se renombra, que es lo unico atomico de verdad en Windows.
    carpeta = Path(tempfile.mkdtemp())
    destino = carpeta / "edl.json"
    ANTES = '{"segments": [{"start": 0.0, "end": 5.0}]}'
    destino.write_text(ANTES, encoding="utf-8")

    try:
        server._atomic_write(destino, "roto " + chr(0xD800))   # no se codifica
        fallo = False
    except Exception:
        fallo = True
    yield ("guardar: una escritura rota falla y se nota", fallo, True)
    yield ("guardar: el montaje de antes sigue entero",
           destino.read_text(encoding="utf-8"), ANTES)
    # Y estos archivos viven en la carpeta del usuario, al lado de su video:
    # un `edl.json.part9184` suelto ahi es basura que el ve y no entiende.
    yield ("guardar: no deja un .part suelto cuando falla",
           sorted(p.name for p in carpeta.iterdir()), ["edl.json"])

    server._atomic_write(destino, '{"segments": []}')
    yield ("guardar: el montaje nuevo pisa al viejo entero",
           destino.read_text(encoding="utf-8"), '{"segments": []}')
    yield ("guardar: ni cuando sale bien",
           sorted(p.name for p in carpeta.iterdir()), ["edl.json"])

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
