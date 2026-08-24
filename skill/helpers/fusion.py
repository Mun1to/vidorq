"""Estilos de Vidorq convertidos en Title Templates de Fusion.

La diferencia con `captions.to_comp()` no es un matiz y conviene tenerla escrita.
Un comp lleva UNA frase dentro y sirve para ese subtitulo: es copiar el TEXTO.
Un Title Template es el ESTILO suelto, que Resolve ensena en
`Effects Library > Titles` y se arrastra al timeline con cualquier frase encima.
Eso es "recrear el estilo", y es lo que pidio Munir.

EL FORMATO NO ESTA INVENTADO. Sale de los 417 `.setting` que Blackmagic reparte
dentro de `Fusion/Templates/Templates.drfx` de la propia instalacion, leidos el
2026-08-23. Un titulo de fabrica es exactamente esto:

    {
        Tools = ordered() {
            <Nombre> = GroupOperator {
                Inputs = ordered() {
                    Input1 = InstanceInput { SourceOp = "Text_1",
                                             Source = "StyledText", },
                    ...
                },
                Outputs = { MainOutput1 = InstanceOutput { ... } },
                ViewInfo = GroupInfo { ... },
                Tools = ordered() { Text_1 = TextPlus { ... }, ... },
            }
        }
    }

Los `InstanceInput` son los mandos PUBLICOS: lo que el usuario ve en el
Inspector al soltar el titulo. Por eso el texto entra ahi y no como un valor
fijo, que es el punto 3 del encargo.

Los nodos de dentro se piden prestados a `captions`, que ya los escribe y estan
medidos contra Resolve 21.0.4.5 Free renderizando y mirando el fotograma. Aqui
solo cambia el envoltorio, asi que un arreglo en el estilo de los subtitulos
llega solo a las plantillas.

COMPROBADO CONTRA RESOLVE, no supuesto. El 2026-08-23, con Resolve abierto y el
puente puesto: la plantilla aparece en Effects Library > Titles y se inserta por
su nombre, el comp que devuelve Resolve trae el tipo de letra, el encuadre, el
contorno, la sombra y el spline de la entrada, y escribirle CUALQUIER frase la
pinta con ese estilo. Los pasos y la salida real estan en `docs/FUSION.md`.

UN COLOR POR PALABRA SI SALE, desde el 2026-08-24. Lo que faltaba no era la
sintaxis, era el OPERADOR: el estilo por caracteres no es un campo del Text+,
es un modificador aparte, `StyledTextCLS`, colgado de su entrada `StyledText`.
Escrito en el propio Text+ Resolve lo guarda y lo ignora al pintar, que es lo
que se midio dos veces y se dio por pared; colgado del modificador, pinta. Lo
escribe `captions.to_comp` cuando una palabra trae `color`.

EL LIMITE QUE QUEDA, y se avisa en vez de disimularlo: ese color no se MUEVE.
El barrido de karaoke (pintar la palabra que SUENA, y que vaya cambiando) sigue
siendo cosa del MP4, donde libass tiene `\\kf`. **Esto es razonado, NO PROBADO
con un fotograma**, y la diferencia importa: lo medido es que la entrada se
llama `CharacterLevelStyling` y es de tipo `StyledText`, o sea un valor con su
array, mientras que en esta casa todas las splines cuelgan de entradas `Number`
con `Source = "Value"`. Falta intentarlo de verdad antes de darlo por cerrado.
`faltantes()` lo dice con ese mismo cuidado.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import captions as cap

# Donde Resolve busca los titulos del usuario. La carpeta `Templates` existe en
# una instalacion limpia pero llega VACIA (comprobado en la maquina de Munir el
# 2026-08-23): `Edit/Titles` hay que crearla, y por eso `carpeta()` la crea.
SUB = ("Blackmagic Design", "DaVinci Resolve", "Support", "Fusion",
       "Templates", "Edit", "Titles")

EXT = ".setting"

# Marca nuestra dentro del fichero, para poder distinguir una plantilla escrita
# por Vidorq de una que haya puesto ahi el usuario a mano. Sin esto,
# `desinstalar()` podria borrarle trabajo suyo.
MARCA = "VIDORQ_ESTILO"

# El Text+ de dentro se llama SIEMPRE igual, y no puede llamarse como el grupo:
# los `SourceOp` de los mandos publicos apuntan al nodo interior, y con los dos
# nombres iguales Resolve no sabe a cual. Blackmagic usa `Text_1` en sus
# plantillas y aqui se copia, que ademas hace los ficheros comparables.
TEXTO = "Text_1"


def _appdata():
    """El APPDATA de itinerancia, leido en CADA llamada.

    No se cachea a proposito: las pruebas desvian APPDATA a una carpeta
    temporal antes de importar nada, y un valor congelado en el import las
    mandaria a escribir en el Resolve de verdad.
    """
    return Path(os.environ.get("APPDATA")
                or (Path.home() / "AppData" / "Roaming"))


def carpeta(crear=True):
    """`.../Support/Fusion/Templates/Edit/Titles`, creada si hace falta."""
    d = _appdata().joinpath(*SUB)
    if crear:
        d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# Nombres
# --------------------------------------------------------------------------- #
_MALO = re.compile(r"[^A-Za-z0-9]+")


def nodo_de(nombre):
    """El nombre del GroupOperator, que es un identificador de Lua.

    Fusion no acepta ahi espacios, acentos ni signos, pero el fichero SI puede
    llamarse como quiera el usuario: lo que ve en Effects Library es el nombre
    del fichero, no el del nodo.
    """
    limpio = _MALO.sub("_", str(nombre or "")).strip("_")
    if not limpio or limpio[0].isdigit():
        limpio = "Vidorq_" + limpio
    return limpio[:48] or "Vidorq"


def fichero_de(nombre):
    """El `.setting` de este estilo, dentro de Edit/Titles.

    Se limpian los caracteres que Windows no deja en un nombre de fichero, pero
    se conservan espacios y acentos, que si valen y se leen mejor.
    """
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(nombre or "")).strip()
    return carpeta() / ((base or "Vidorq") + EXT)


# --------------------------------------------------------------------------- #
# El fichero
# --------------------------------------------------------------------------- #
def _hundir(bloque, n=2):
    """Mete `n` tabuladores mas en cada linea con contenido.

    `captions` escribe sus nodos para un `Composition`, donde cuelgan a DOS
    tabuladores (`Composition > Tools > nodo`). En un `.setting` el mismo nodo
    cuelga de `{ > Tools > grupo > Tools > nodo`, o sea a CUATRO. Reindentar
    aqui evita duplicar los generadores solo por el sangrado.

    El sangrado no es cosmetico: con los nodos a tres tabuladores el fichero
    seguia teniendo las llaves equilibradas, asi que un vistazo no lo delata.
    Lo que lo delato fue comprobar que ningun `SourceOp` colgase.
    """
    if not bloque:
        return ""
    pad = "\t" * n
    return "\n".join(pad + ln if ln.strip() else ln
                     for ln in bloque.split("\n"))


def _mandos(p):
    """Los InstanceInput: lo que el usuario toca en el Inspector.

    El orden importa, porque es el orden en que Resolve los pinta. El texto
    primero, que es lo que todo el mundo cambia; el color al final, agrupado en
    un solo mando de color con `ControlGroup`, que es como lo hace Blackmagic
    en sus propias plantillas (`Gradient.setting`).
    """
    filas = []

    def mando(src, extra=""):
        filas.append(
            "\t\t\t\tInput%d = InstanceInput {\n"
            '\t\t\t\t\tSourceOp = "%s",\n'
            '\t\t\t\t\tSource = "%s",\n'
            "%s"
            "\t\t\t\t},\n" % (len(filas) + 1, TEXTO, src, extra))

    mando("StyledText", '\t\t\t\t\tName = "Texto",\n')
    mando("Font", "\t\t\t\t\tControlGroup = 2,\n")
    mando("Style", "\t\t\t\t\tControlGroup = 2,\n")
    mando("Size")
    mando("Center", '\t\t\t\t\tName = "Posicion",\n')
    r, g, b = p["fill"]
    mando("Red1", '\t\t\t\t\tName = "Color",\n\t\t\t\t\tControlGroup = 6,\n'
                  "\t\t\t\t\tDefault = %.4f,\n" % r)
    mando("Green1", "\t\t\t\t\tControlGroup = 6,\n\t\t\t\t\tDefault = %.4f,\n" % g)
    mando("Blue1", "\t\t\t\t\tControlGroup = 6,\n\t\t\t\t\tDefault = %.4f,\n" % b)
    return "".join(filas)


def plantilla(nombre, estilo=None, w=1920, h=1080, dur=120, texto="TEXTO",
              anim_name=None):
    """El texto entero del `.setting` para este estilo. No escribe nada.

    `dur` son los fotogramas que dura la entrada. Un titulo de fabrica trae 500
    y aqui el defecto son 120, que a 30 fps son cuatro segundos: lo que dura un
    subtitulo largo. La entrada se escribe como `BezierSpline` dentro del
    fichero, que es la unica forma de que un keyframe sobreviva a la API.
    """
    p = cap.preset(estilo)
    a = cap.anim(anim_name) or cap.anim(p["anim"]) or cap.ANIMS[cap.DEFAULT_ANIM]
    nodo = nodo_de(nombre)

    # El mismo tamano que en un comp, pero SIN el techo por linea mas larga.
    # Ese techo existe para que una frase concreta quepa, y aqui la frase no se
    # conoce: la escribe el usuario despues. Meterlo obligaria a encoger la
    # plantilla al ancho de la palabra de muestra, que no significa nada.
    size = float(p["size"]) * 2.259 * (cap.line_ref(w, h) / max(1.0, float(w)))
    els = cap._elements(p)
    anim_tools, wires, extra = cap._anim_splines(a, dur, size, els)

    # Text+ -> Blur -> Glow -> Merge, la misma cadena que un comp y por el mismo
    # motivo: un estilo que no quiere ninguno de los tres se queda con un solo
    # nodo en vez de arrastrar tres apagados.
    chain, out, x = "", TEXTO, 220
    if extra.get("blur"):
        x += 165
        chain += cap._blur_tool(out, extra["blur"], x)
        out = "Soft"
    if p["glow"]:
        x += 165
        if extra.get("glow"):
            anim_tools = cap._rescale_spline(anim_tools, extra["glow"],
                                             p["glow"][3])
        chain += cap._glow_tool(out, p["glow"], extra.get("glow"), x,
                                keep_edge=not p["outline"])
        out = "Shine"
    if extra.get("fade"):
        x += 165
        chain += cap._fade_tool(out, extra["fade"], w, h, x)
        out = "Mezcla"

    cuerpo = cap._text_inputs(p, {"text": texto}, w, h, dur, wires, size,
                              float(p["y"]), els)

    return (
        "{\n"
        "\tTools = ordered() {\n"
        "\t\t%s = GroupOperator {\n"
        "\t\t\tCtrlWZoom = false,\n"
        "\t\t\tNameSet = true,\n"
        "\t\t\tCustomData = {\n"
        '\t\t\t\t%s = "%s",\n'
        '\t\t\t\tVIDORQ_ANIM = "%s"\n'
        "\t\t\t},\n"
        "\t\t\tInputs = ordered() {\n"
        "%s"
        "\t\t\t},\n"
        "\t\t\tOutputs = {\n"
        "\t\t\t\tMainOutput1 = InstanceOutput {\n"
        '\t\t\t\t\tSourceOp = "%s",\n'
        '\t\t\t\t\tSource = "Output",\n'
        "\t\t\t\t}\n"
        "\t\t\t},\n"
        "\t\t\tViewInfo = GroupInfo {\n"
        "\t\t\t\tPos = { 112.15, 49.5 },\n"
        "\t\t\t\tFlags = {\n"
        "\t\t\t\t\tAllowPan = false,\n"
        "\t\t\t\t\tConnectedSnap = true,\n"
        "\t\t\t\t\tAutoSnap = true,\n"
        "\t\t\t\t\tRemoveRouters = true\n"
        "\t\t\t\t},\n"
        "\t\t\t\tSize = { 301.258, 107.477, 150.629, 24.2424 },\n"
        '\t\t\t\tDirection = "Horizontal",\n'
        '\t\t\t\tPipeStyle = "Direct",\n'
        "\t\t\t\tScale = 1,\n"
        "\t\t\t\tOffset = { 0, 0 }\n"
        "\t\t\t},\n"
        "\t\t\tTools = ordered() {\n"
        "%s"
        "\t\t\t\t%s = TextPlus {\n"
        "\t\t\t\t\tNameSet = true,\n"
        "\t\t\t\t\tInputs = {\n"
        "\t\t\t\t\t\t%s\n"
        "\t\t\t\t\t},\n"
        "\t\t\t\t\tViewInfo = OperatorInfo { Pos = { 220, 49.5 } },\n"
        "\t\t\t\t},\n"
        "%s"
        "\t\t\t},\n"
        "\t\t}\n"
        "\t}\n"
        "}\n"
        % (nodo, MARCA, cap._fu_str(str(estilo or cap.DEFAULT_PRESET)),
           cap._fu_str(str(anim_name or p["anim"])),
           _mandos(p), out,
           _hundir(anim_tools), TEXTO,
           cuerpo.replace("\n\t\t\t\t", "\n\t\t\t\t\t\t"),
           _hundir(chain)))


# --------------------------------------------------------------------------- #
# Instalar y quitar
# --------------------------------------------------------------------------- #
def instalar(nombre, estilo=None, **kw):
    """Deja el `.setting` en Edit/Titles y devuelve su ruta."""
    destino = fichero_de(nombre)
    destino.write_text(plantilla(nombre, estilo, **kw), encoding="utf-8")
    return destino


def instaladas():
    """Las plantillas que ha puesto Vidorq, por nombre de fichero.

    Solo las suyas: se mira la marca de dentro, no el nombre. Una plantilla que
    el usuario haya metido a mano no es asunto nuestro.
    """
    d = carpeta(crear=False)
    if not d.is_dir():
        return []
    fuera = []
    for f in sorted(d.glob("*" + EXT)):
        try:
            if MARCA in f.read_text(encoding="utf-8", errors="replace"):
                fuera.append(f.stem)
        except OSError:
            continue
    return fuera


def desinstalar(nombre):
    """Borra la plantilla, y SOLO si la escribio Vidorq.

    Devuelve True si se fue, False si no estaba o si no lleva nuestra marca.
    Lo segundo no es un fallo: es la proteccion. Un `.setting` que no marcamos
    nosotros puede ser trabajo del usuario, y eso no se toca.
    """
    f = fichero_de(nombre)
    if not f.is_file():
        return False
    try:
        if MARCA not in f.read_text(encoding="utf-8", errors="replace"):
            return False
        f.unlink()
    except OSError:
        return False
    return True


# --------------------------------------------------------------------------- #
# Lo que no da Fusion de casa
# --------------------------------------------------------------------------- #
def faltantes(estilo=None):
    """Que parte de este estilo NO se recrea con nodos nativos.

    Devuelve una lista de dicts `{que, porque, pieza}`. Vacia quiere decir que
    la plantilla sale entera, no que "casi".

    Existe por una razon concreta: un estilo a medias que no avisa es una
    mentira, y este proyecto lleva una semana quitandolas. Si algun dia hace
    falta un plugin de terceros, `pieza` dice cual.
    """
    p = cap.preset(estilo)
    fuera = []
    if p.get("word_fx") == "karaoke":
        fuera.append({
            "que": "el barrido de karaoke, o sea que se pinte la palabra que "
                   "SUENA y vaya cambiando con el audio",
            "porque": "un color FIJO por palabra si sale desde el 2026-08-24, "
                      "con el modificador `StyledTextCLS` colgado del Text+ "
                      "(medido sacando el fotograma: salio cada palabra de su "
                      "color). Lo que no sale es que ese color se MUEVA con el "
                      "audio: hoy Vidorq escribe un solo reparto de colores por "
                      "cartel, el mismo del primer fotograma al ultimo. Que "
                      "ademas sea IMPOSIBLE moverlo esta razonado y NO PROBADO: "
                      "la entrada es de tipo `StyledText`, un valor con su "
                      "array, y las splines de esta casa cuelgan de entradas "
                      "`Number`. El MP4 si lo hace, porque libass tiene `\\kf`",
            "pieza": None,
        })
    # Un Text+ NO ajusta el texto: una frase larga se sale por los dos bordes en
    # vez de partirse en dos lineas. En un comp eso se tapa encogiendo la letra
    # contra la linea mas larga, pero una plantilla no sabe que frase le van a
    # escribir, asi que aqui se avisa y ya. El mando de tamaño es publico.
    fuera.append({
        "que": "partir una frase larga en dos lineas",
        "porque": "un Text+ no ajusta el texto: lo que no cabe se sale por los "
                  "bordes. Una plantilla no sabe de antemano que frase le van a "
                  "escribir, asi que no puede encoger la letra por ti. El mando "
                  "de tamaño esta a la vista en el Inspector",
        "pieza": None,
    })
    return fuera
