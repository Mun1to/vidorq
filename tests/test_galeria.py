"""Un estilo copiado de un video se guarda ENTERO y llega hasta el render.

Hasta agosto de 2026, copiar el estilo de un video ajeno guardaba el NOMBRE de
la plantilla mas parecida de un cajon de diez, asi que los numeros que se
acababan de medir (donde cae el texto, de que tamaño, de que color) se tiraban
en el mismo gesto de pulsar Guardar. Lo que quedaba guardado era una de las
diez plantillas de la casa con otro nombre encima.

Lo que se comprueba aqui, y por que cada cosa:

  - lo MEDIDO manda sobre la plantilla. Si no, todo lo demas da igual: el
    estilo copiado seria la plantilla otra vez.
  - lo que NO se sabe medir se hereda, y el componente DICE cuales son. Un
    estilo que aparenta saberlo todo es la mentira que este trabajo quita.
  - el contorno conserva sus cuatro numeros. Del video sale el COLOR (tres) y
    el grosor es el cuarto: guardar solo tres dejaba una tupla corta y to_ass
    reventaba con IndexError al renderizar, o sea DESPUES de guardar, con el
    usuario mirando una pantalla que decia que todo habia ido bien.
  - el estilo copiado deja de depender de la plantilla. Se comprueba moviendo
    la plantilla y viendo que el copiado no se mueve.
  - sobrevive al viaje por JSON, que no es un detalle: el id viaja por argv
    hasta otros dos interpretes (el render de MP4 y el que corre DENTRO de
    Resolve) y alli lo unico que hay es este archivo.
  - una galeria rota no deja sin subtitulos a quien solo usa los de la casa.

Se recorren LOS DIEZ presets como base, no dos elegidos a mano: probar un
subconjunto ya costo dos regresiones en un dia.

No necesita ffmpeg ni red. Escribe en un APPDATA temporal, nunca en el de
verdad: probar contra el de verdad ya destruyo una vez un perfil de marca.

Se lanza:  python tests/test_galeria.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))

# El APPDATA de mentira se pone ANTES de importar nada que lo lea. galeria lo
# consulta en cada llamada, asi que basta con esto y no hace falta parchear.
CASA = Path(tempfile.mkdtemp(prefix="vidorq_galeria_"))
os.environ["APPDATA"] = str(CASA)
(CASA / "Vidorq" / "workspaces" / "Principal").mkdir(parents=True)

import captions as cap        # noqa: E402
import galeria                # noqa: E402

# Lo que mediria aprende.py de un video con subtitulos amarillos a media
# altura. Los tres colores son los del Short que destapo todo esto, medidos
# mirando pixeles el 2026-08-23.
MEDIDO = {"y": 0.611, "size": 0.097, "fill": (0.92, 0.85, 0.11),
          "outline": (0.05, 0.04, 0.06), "fondo": (0.2, 0.2, 0.2)}

TRANSCRIPCION = {"segments": [{"start": 0.0, "end": 1.6, "words": [
    {"w": "UNA", "s": 0.0, "e": 0.5},
    {"w": "DE", "s": 0.5, "e": 0.9},
    {"w": "CADA", "s": 0.9, "e": 1.6}]}]}


def _pinta(eid, destino):
    """Renderiza el estilo por los dos caminos. Devuelve el ASS o el fallo.

    Los dos, y no solo el ASS, porque son dos renderizadores distintos: el de
    ffmpeg para el MP4 y el comp de Fusion para Resolve. Un estilo que pinta en
    uno y revienta en el otro esta roto en la mitad de los casos de uso.
    """
    try:
        trozos = cap.build_chunks(TRANSCRIPCION, eid, 1080, 1920)
        if not trozos:
            return "no troceo nada"
        cap.to_ass(destino / ("%s.ass" % eid), trozos, 0.0, 1.6, 1080, 1920, eid)
        cap.to_comp(destino / ("%s.comp" % eid), trozos[0], 1080, 1920, 1.6, eid)
        return (destino / ("%s.ass" % eid)).read_text(encoding="utf-8")
    except Exception as e:
        return "%s: %s" % (type(e).__name__, e)


def casos(casa):
    tmp = casa / "render"
    tmp.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- guardar
    comp = galeria.caption_de(MEDIDO, "punch", "Mi estilo",
                              video=r"C:\sitio\short.mp4", cuando="2026-08-23")
    eid = galeria.guardar(comp)
    yield ("el id sale del nombre del usuario", eid, "propio-mi-estilo")
    yield ("dice que midio cuatro cosas", comp["medido"],
           ["y", "size", "fill", "outline"])
    yield ("y no se inventa de donde salio", comp["base"], "punch")
    # El color de detras se guarda como DATO y no como `panel`: esta medido que
    # no se puede saber si ese color es una plancha o un contorno grueso.
    yield ("el fondo medido no se cuela como panel",
           comp["panel"], cap.PRESETS["punch"]["panel"])
    yield ("pero no se pierde", comp["fondo_medido"], (0.2, 0.2, 0.2))
    # El nombre del video se guarda; la RUTA no, que es de la maquina de otro.
    yield ("guarda de que video vino", comp["de"]["video"], "short.mp4")

    # ------------------------------------------------------ el viaje por JSON
    disco = json.loads((galeria.ws_dir() / galeria.ARCHIVO)
                       .read_text(encoding="utf-8"))
    yield ("esta en el archivo que leen los otros interpretes",
           eid in disco, True)
    yield ("y vuelve como tupla, no como lista",
           isinstance(galeria.cargar()[eid]["fill"], tuple), True)

    # ------------------------------------------------- captions lo reconoce
    p = cap.preset(eid)
    yield ("known() lo conoce", cap.known(eid), True)
    yield ("known() sigue diciendo que no a lo inventado",
           cap.known("no-existe-esto"), False)
    yield ("known() con vacio no revienta", cap.known(""), False)
    yield ("la posicion es la MEDIDA", p["y"], 0.611)
    yield ("el tamaño es el MEDIDO", p["size"], 0.097)
    yield ("el relleno es el MEDIDO", p["fill"], (0.92, 0.85, 0.11))
    yield ("y no son los de la plantilla",
           (p["y"], p["size"]) == (cap.PRESETS["punch"]["y"],
                                   cap.PRESETS["punch"]["size"]), False)
    yield ("la tipografia se hereda", p["font"], cap.PRESETS["punch"]["font"])
    yield ("y las palabras por linea tambien",
           p["words"], cap.PRESETS["punch"]["words"])
    yield ("sale en el selector, y el primero",
           cap.preset_list("es")[0]["id"], eid)
    yield ("marcado como propio", cap.preset_list("es")[0]["propio"], True)
    yield ("con los diez de la casa detras", len(cap.preset_list("es")), 11)
    yield ("anim_of lo incluye", cap.anim_of().get(eid),
           cap.PRESETS["punch"]["anim"])

    # ------------------------------------- ya no depende de la plantilla
    antes = cap.PRESETS["punch"]["y"]
    cap.PRESETS["punch"]["y"] = 0.99
    yield ("mover la plantilla no mueve el estilo copiado",
           cap.preset(eid)["y"], 0.611)
    cap.PRESETS["punch"]["y"] = antes

    # ------------------------------------------------ llega hasta el render
    ass = _pinta(eid, tmp)
    # 0.92, 0.85, 0.11 -> 235, 217, 28 -> en ASS, que va &HBBGGRR&, 1CD9EB.
    yield ("el color medido llega al ASS", "1CD9EB" in ass.upper(), True)
    # Alignment 8 pone el texto por su borde de arriba: 1920*(1-0.611) = 746,88.
    # Con la plantilla estaria en 1920*(1-0.22) = 1497, o sea 750 px mas abajo:
    # no hay empate posible ni margen que ajustar.
    import re
    m = re.search(r"\\pos\(\d+,(\d+)\)", ass)
    yield ("y cae donde dice lo medido, no la plantilla",
           bool(m) and 744 <= int(m.group(1)) <= 750, True)

    # ------------------------------------- LOS DIEZ como plantilla base
    for base in cap.PRESETS:
        c = galeria.caption_de(MEDIDO, base, "base " + base)
        galeria.guardar(c)
        q = cap.preset(c["id"])
        yield ("base %-8s: lo medido manda" % base,
               (q["y"], q["size"], q["fill"]),
               (0.611, 0.097, (0.92, 0.85, 0.11)))
        # O lleva los cuatro numeros con el color medido delante, o no lleva
        # contorno porque la plantilla no tenia. Nunca una tupla de tres.
        o = q["outline"]
        yield ("base %-8s: el contorno queda entero" % base,
               o is None or (len(o) == 4 and tuple(o[:3]) == (0.05, 0.04, 0.06)),
               True)
        yield ("base %-8s: y no cuela medio contorno como medido" % base,
               ("outline" in c["medido"]) == (o is not None), True)
        salida = _pinta(c["id"], tmp)
        # El BOM del principio esta puesto a proposito (libass lo quiere), asi
        # que se quita antes de mirar la cabecera en vez de dar por roto un
        # archivo correcto.
        yield ("base %-8s: y RENDERIZA por los dos caminos" % base,
               salida.lstrip("\ufeff").startswith("[Script Info]"), True)
        galeria.borrar(c["id"])

    # ------------------------------- lo que rodea a la letra, si se midio
    # Un video sin contorno reconstruido con el contorno negro gordo de la
    # plantilla se ve mal a un metro de la pantalla, por muy clavado que este
    # el color de cada palabra. Asi que cuando el lector ha mirado el borde,
    # manda el borde y no la plantilla.
    sin_borde = dict(MEDIDO)
    sin_borde["borde"] = {"contorno": 0, "halo": 0, "de": 9,
                          "caida": [0.41, 0.32, 0.31, 0.29, 0.24]}
    c = galeria.caption_de(sin_borde, "pop", "sin contorno")
    yield ("un video sin contorno no hereda el de la plantilla",
           c["outline"], None)
    yield ("y lo cuenta como medido", "outline" in c["medido"], True)
    yield ("la plantilla si lo llevaba",
           cap.PRESETS["pop"]["outline"] is not None, True)

    # Algo oscuro alrededor que baja DESPACIO es una sombra difusa, no un
    # contorno duro: un contorno duro salta a 0,00 y se queda ahi.
    suave = dict(MEDIDO)
    suave["borde"] = {"contorno": 5, "halo": 0, "de": 9,
                      "caida": [0.42, 0.33, 0.30, 0.27, 0.25]}
    c = galeria.caption_de(suave, "pop", "sombra suave")
    yield ("una caida suave no se pinta como contorno", c["outline"], None)
    yield ("se pinta como sombra centrada", c["shadow"][4:], (0.0, 0.0))
    duro = dict(MEDIDO)
    duro["borde"] = {"contorno": 12, "halo": 0, "de": 9,
                     "caida": [0.33, 0.0, 0.0, 0.0, 0.0]}
    c = galeria.caption_de(duro, "pop", "contorno duro")
    yield ("un contorno duro si se conserva", c["outline"] is not None, True)

    # Un halo se tiñe del color del relleno medido, no del de la plantilla:
    # un halo es la propia letra desbordada, no una luz de otro color.
    conhalo = dict(MEDIDO)
    conhalo["borde"] = {"contorno": 0, "halo": 7, "de": 9, "caida": [0.6] * 5}
    c = galeria.caption_de(conhalo, "pop", "con halo")
    yield ("el halo sale del color medido", c["glow"][:3], (0.92, 0.85, 0.11))
    yield ("y con el tamaño medido", c["glow"][3], 7.0)
    # Y al reves: si la plantilla trae halo y el video no, se quita.
    c = galeria.caption_de(sin_borde, "neon", "sin halo")
    yield ("la plantilla trae halo", cap.PRESETS["neon"]["glow"] is not None, True)
    yield ("pero el video no, asi que se quita", c["glow"], None)
    # Sin nada medido, no se toca: la plantilla manda, como hasta ahora.
    c = galeria.caption_de(MEDIDO, "pop", "sin medir el borde")
    yield ("sin medir el borde se respeta la plantilla",
           c["outline"][:3], (0.05, 0.04, 0.06))
    # Y todos los copiados con borde medido tienen que seguir PINTANDO.
    for base in cap.PRESETS:
        c = galeria.caption_de(sin_borde, base, "borde " + base)
        galeria.guardar(c)
        yield ("base %-8s: sin contorno y sigue pintando" % base,
               _pinta(c["id"], tmp).lstrip("\ufeff").startswith("[Script Info]"),
               True)
        galeria.borrar(c["id"])

    # ----------------------------------------------------- ids que chocan
    otro = galeria.caption_de(MEDIDO, "pop", "Mi estilo")
    galeria.guardar(otro)
    yield ("un nombre repetido se numera", otro["id"], "propio-mi-estilo-2")
    yield ("y no pisa al primero", cap.preset(eid)["y"], 0.611)
    # Un nombre que se queda en nada despues de limpiarlo tiene que dar un id
    # igual, no una cadena vacia con el prefijo suelto.
    raro = galeria.caption_de(MEDIDO, "pop", "!!! ???")
    yield ("un nombre de solo signos sigue dando un id",
           raro["id"], "propio-estilo")
    yield ("un nombre vacio tambien",
           galeria.caption_de(MEDIDO, "pop", "")["id"], "propio-copiado")

    # --------------------------------------------------------------- borrar
    yield ("borrar devuelve que si", galeria.borrar(otro["id"]), True)
    yield ("y deja de conocerse", cap.known(otro["id"]), False)
    yield ("borrar lo que no existe no revienta",
           galeria.borrar("propio-fantasma"), False)

    # ------------------------------------------- sin medida no hay estilo
    # Lo comprueba el motor antes de llegar aqui, pero el reparto tiene que ser
    # honesto igualmente: sin color medido, `medido` no puede decir que si.
    flojo = galeria.caption_de({"y": 0.5}, "pop", "solo altura")
    yield ("un estilo con una sola medida lo dice", flojo["medido"], ["y"])
    yield ("y el resto sigue siendo de la plantilla",
           flojo["fill"], cap.PRESETS["pop"]["fill"])

    # ------------------------------------------- una galeria rota no tumba nada
    (galeria.ws_dir() / galeria.ARCHIVO).write_text("{esto no es json",
                                                    encoding="utf-8")
    yield ("una galeria rota se lee como vacia", galeria.cargar(), {})
    yield ("y quedan los diez de la casa", len(cap.preset_list("es")), 10)
    yield ("y preset() cae al de la casa, no revienta",
           cap.preset(eid)["y"], cap.PRESETS[cap.DEFAULT_PRESET]["y"])
    yield ("y known() dice que no", cap.known(eid), False)

    # Una galeria que es una lista y no un diccionario: mismo trato.
    (galeria.ws_dir() / galeria.ARCHIVO).write_text("[1,2,3]", encoding="utf-8")
    yield ("una galeria que no es un diccionario tampoco tumba",
           galeria.cargar(), {})
    # Y una entrada suelta que no es un diccionario se descarta sin llevarse
    # por delante a las buenas que tenga al lado.
    (galeria.ws_dir() / galeria.ARCHIVO).write_text(
        '{"propio-a": "texto suelto", "propio-b": {"tipo": "caption", "y": 0.4}}',
        encoding="utf-8")
    yield ("una entrada rota se cae sola y la buena se queda",
           sorted(galeria.cargar()), ["propio-b"])
    # Una entrada sin `tipo` escrito es de cuando solo se sabian guardar
    # estilos de subtitulo, asi que cuenta como uno.
    (galeria.ws_dir() / galeria.ARCHIVO).write_text(
        '{"propio-viejo": {"y": 0.4}}', encoding="utf-8")
    yield ("una entrada vieja sin tipo cuenta como estilo",
           sorted(galeria.de_tipo(galeria.CAPTION)), ["propio-viejo"])


def main():
    try:
        bad, total = [], 0
        for nombre, got, want in casos(CASA):
            total += 1
            if got != want:
                bad.append("%s: esperaba %r y devolvio %r" % (nombre, want, got))
        if bad:
            print("%d de %d casos MAL:\n" % (len(bad), total))
            for line in bad:
                print("  - %s" % line)
            return 1
        print("%d casos, lo copiado se guarda entero y se pinta." % total)
        return 0
    finally:
        shutil.rmtree(CASA, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
