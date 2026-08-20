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

    # --- un cartel se escribe en el reloj del MONTAJE -----------------------
    # `titles_into` recibe el segundo del ORIGINAL (ya traducido por el motor) y
    # devuelve el del montaje, porque lo que arma es la lista de subtitulos.
    chunks = server.titles_into([], [{"do": "title", "at": 6.0, "secs": 2.0,
                                      "text": "HOLA"}], EDL)
    yield "el cartel del segundo 6 cae en el 1 del montaje", chunks[0]["start"], 1.0
    yield "y dura los 2 segundos pedidos", chunks[0]["end"], 3.0

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
