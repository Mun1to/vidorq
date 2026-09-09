"""La galeria de componentes: lo que Vidorq ha sacado de un video ajeno.

La idea del producto es pegar un video, sacarle las piezas de como esta hecho
y GUARDARLAS por separado para reutilizarlas: el estilo de los subtitulos, su
animacion de entrada, el ritmo de corte, el color. Cada pieza es un componente
con su id, y la pared de la ventana (Gallery.tsx) las enseña al lado de las de
la casa.

Lo que habia antes no era eso. Copiar un estilo guardaba el NOMBRE de la
plantilla mas parecida de un cajon de diez, asi que todo lo que se habia
medido del video (donde cae el texto, de que tamaño, de que color, con que
contorno) se tiraba en el mismo gesto de pulsar Guardar. La pantalla decia
"copiar un estilo" y lo que hacia era elegir uno de diez.

Aqui un componente se guarda ENTERO y por su cuenta, con la misma forma que
una entrada de captions.PRESETS, y a partir de ese momento no depende de
ninguna plantilla. Si mañana cambia `punch`, el estilo que alguien copio de su
video no se mueve.

  ¿Por que en disco y no en memoria del motor?
  Porque el id del estilo viaja por argv hasta OTROS interpretes: el render de
  MP4 corre como subproceso (`vidorq_render.py --preset X`) y el de Resolve
  corre dentro de Resolve (`resolve_captions.py`), que ni siquiera es el mismo
  Python. Un diccionario no cabe en una linea de comandos. Lo que si cruza esas
  tres fronteras es un id corto y un archivo que los tres leen.

  ¿Que se mide y que se hereda?
  Hoy se miden cuatro cosas (`y`, `size`, `fill`, `outline`) y el resto no se
  sabe mirando un MP4 todavia. Eso NO se esconde: cada componente guarda en
  `medido` la lista de lo que salio de mirar pixeles, y lo demas se copia una
  vez de la plantilla que se eligio y se queda congelado dentro. Un estilo que
  dice de que campos se fia vale mas que uno que aparenta saberlo todo.

  ¿Por que un solo archivo para todos los tipos?
  Porque los componentes que faltan (la animacion de entrada, el ritmo, las
  transiciones) son los puntos 4 y 5 de la META C y van a llegar. Un archivo
  por tipo obligaria a inventarse tres almacenes iguales; con el campo `tipo`
  ya caben, y `de_tipo()` los separa al leer.

El video del que se copia es AJENO (regla AL): de el salen numeros, nunca
texto ni ordenes, y no se guarda nada de su contenido.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# Los componentes propios llevan el prefijo delante del id. Sirve para dos
# cosas que se necesitan sin abrir ningun archivo: distinguirlos de los de la
# casa, y que un nombre inventado por el usuario no pueda pisar a `pop` ni a
# `neon` por mucho que lo llame asi.
PREFIJO = "propio-"
ARCHIVO = "galeria.json"

# Los tipos de componente. Hoy solo se sabe extraer el primero; los otros son
# los puntos 4 y 5 de la META C y estan aqui para que el almacen no haya que
# tocarlo cuando lleguen.
CAPTION = "caption"
TIPOS = (CAPTION,)

# Los campos que forman un estilo de subtitulo. Es el contrato con
# captions.PRESETS: si alli aparece uno nuevo, aqui tambien, o los estilos
# copiados se quedan sin el y el render tira del valor por defecto sin decirlo.
CAMPOS = ("words", "max_chars", "upper", "font", "style", "size", "fill",
          "outline", "shadow", "y", "anim", "glow", "panel", "word_fx",
          "accent", "tracking")

# Lo que hoy sale de mirar pixeles, en aprende.ficha()["subtitulo"]. El resto
# de CAMPOS se hereda de la plantilla. Cuando el analizador aprenda a medir uno
# mas, entra en esta lista y deja de heredarse.
DE_PIXELES = ("y", "size", "fill", "outline")

# Los campos donde el color son los TRES primeros numeros y detras va algo que
# no es color. `outline` es (r, g, b, grosor) y `shadow` es (r, g, b, alpha,
# dx, dy): de mirar el video sale el color y nada mas, asi que el color se
# mete delante y la cola se queda la de la plantilla.
#
# Esto no es una precaucion teorica. Guardar los tres numeros medidos tal cual
# en `outline` dejaba una tupla de tres, y to_ass lee `p["outline"][3]` para
# saber el grosor: reventaba con IndexError al renderizar, o sea DESPUES de
# guardar, con el estilo ya en la galeria y el usuario mirando una pantalla que
# decia que todo habia ido bien.
CON_COLA = {"outline": 4, "shadow": 6}


def _config_dir():
    return Path(os.environ.get("APPDATA", ".")) / "Vidorq"


def ws_dir():
    """La carpeta del workspace activo, la misma que usa el motor.

    Se calcula aqui en vez de importar el servidor a proposito: este modulo lo
    carga tambien el script que corre DENTRO de Resolve, donde `engine` no esta
    en el path y no tiene por que estarlo. Son ocho lineas repetidas a cambio
    de que los tres interpretes lean el mismo archivo.
    """
    base = _config_dir() / "workspaces"
    try:
        activo = json.loads(
            (_config_dir() / "config.json").read_text(encoding="utf-8")
        ).get("activeWorkspace") or ""
    except Exception:
        activo = ""
    # Un nombre que no existe cae al primero que haya, igual que en ws_list().
    # Si no cayera, un config.json que menciona un workspace ya borrado dejaria
    # la galeria entera invisible sin decir por que.
    if not activo or not (base / activo).is_dir():
        try:
            nombres = sorted(p.name for p in base.iterdir() if p.is_dir())
        except OSError:
            nombres = []
        activo = nombres[0] if nombres else "Principal"
    return base / activo


def _tuplas(v):
    """Las listas del JSON, de vuelta a tuplas.

    El resto del codigo desempaqueta estos valores (`r, g, b = p["fill"]`) y
    los compara con los del catalogo, que son tuplas. Una lista funciona para
    lo primero pero no es igual a una tupla para lo segundo, y esa diferencia
    solo aparece el dia que algo compara un componente copiado con uno de casa.
    """
    if isinstance(v, list):
        return tuple(_tuplas(x) for x in v)
    return v


def cargar():
    """Toda la galeria del workspace activo, por id.

    Nunca lanza: si el archivo no esta o esta roto, el programa tiene que
    seguir con los componentes de la casa. Perder lo copiado molesta; que no
    abra la pantalla de subtitulos por un JSON a medias es otra cosa.
    """
    try:
        datos = json.loads((ws_dir() / ARCHIVO).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(datos, dict):
        return {}
    return {str(eid): {k: _tuplas(v) for k, v in e.items()}
            for eid, e in datos.items() if isinstance(e, dict)}


def de_tipo(tipo):
    """Solo los componentes de un tipo. Las entradas viejas, sin `tipo`
    escrito, cuentan como estilos de subtitulo, que es lo unico que se sabia
    guardar cuando se escribieron."""
    return {eid: e for eid, e in cargar().items()
            if (e.get("tipo") or CAPTION) == tipo}


def _escribir(datos):
    destino = ws_dir()
    destino.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(datos, ensure_ascii=False, indent=1)
    # Atomico, por el mismo motivo que brand.json: `write_text` trunca antes de
    # escribir, asi que un corte a media escritura deja cero componentes donde
    # habia diez.
    tmp = destino / (ARCHIVO + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, destino / ARCHIVO)


def guardar(comp):
    """Mete o reemplaza un componente. Devuelve su id."""
    datos = cargar()
    datos[comp["id"]] = comp
    _escribir(datos)
    return comp["id"]


def borrar(eid):
    datos = cargar()
    if eid not in datos:
        return False
    del datos[eid]
    _escribir(datos)
    return True


def uno(eid):
    return cargar().get(eid)


def es_propio(eid):
    return isinstance(eid, str) and eid.startswith(PREFIJO)


def _pedazo(nombre):
    """El nombre que escribio el usuario, convertido en algo que puede ser un
    id y un nombre de archivo.

    Hace falta sanear porque el id acaba dentro del nombre de los PNG de la
    cache de previsualizaciones y en una linea de comandos. Lo escribe el
    usuario y no un video ajeno, pero un nombre con `..\\` dentro no deja de
    ser un nombre con `..\\` dentro.
    """
    limpio = re.sub(r"[^\w\- ]", "", (nombre or "").strip()).strip()
    return re.sub(r"[\s_]+", "-", limpio).strip("-").lower()[:32]


def id_para(nombre, existentes=None):
    """Un id libre a partir del nombre que puso el usuario.

    Si el nombre ya esta cogido se numera, en vez de pisar lo anterior en
    silencio: dos videos distintos llamados "mi estilo" son dos estilos.
    """
    if existentes is None:
        existentes = cargar()
    base = PREFIJO + (_pedazo(nombre) or "estilo")
    if base not in existentes:
        return base
    n = 2
    while "%s-%d" % (base, n) in existentes:
        n += 1
    return "%s-%d" % (base, n)


def caption_de(sub, base, nombre, video="", cuando=""):
    """Un estilo de subtitulo copiado, a partir de lo medido y de la plantilla.

    `sub` son los numeros ya validados que salieron de aprende.ficha(), y
    `base` el id de la plantilla que el usuario aprobo mirando las dos capturas
    juntas. Lo medido gana; lo que no se sabe medir se copia de la plantilla UNA
    VEZ y se queda dentro del componente, que es lo que le permite existir sin
    ella despues.
    """
    import captions as cap

    plantilla = cap.PRESETS.get(base) or cap.PRESETS[cap.DEFAULT_PRESET]
    comp = {k: plantilla[k] for k in CAMPOS if k in plantilla}
    medido = []
    for campo in DE_PIXELES:
        valor = (sub or {}).get(campo)
        if valor is None:
            continue
        if not isinstance(valor, (list, tuple)):
            comp[campo] = valor
            medido.append(campo)
            continue
        valor = tuple(valor)
        largo = CON_COLA.get(campo)
        if largo:
            # El color medido delante, y detras lo que la plantilla dijera. Si
            # la plantilla no llevaba ese campo (`punch` sin sombra), no hay
            # cola que heredar y guardar medio campo seria inventarse el resto:
            # se deja fuera y no entra en `medido`.
            cola = plantilla.get(campo)
            if not cola or len(cola) < largo:
                continue
            comp[campo] = valor[:3] + tuple(cola[3:largo])
        else:
            comp[campo] = valor
        medido.append(campo)
    # Lo que rodea a la letra, cuando se ha llegado a medir. Es lo que mas se
    # nota de todo: un subtitulo sin contorno reconstruido con el contorno
    # negro gordo de la plantilla se ve mal a un metro de la pantalla, por muy
    # clavado que este el color de cada palabra.
    borde = (sub or {}).get("borde")
    if isinstance(borde, dict) and borde.get("de"):
        caida = [c for c in (borde.get("caida") or []) if c is not None]
        duro = bool(caida) and min(caida[1:] or caida) < 0.12
        if not borde.get("contorno"):
            comp["outline"] = None              # no lleva, y se respeta
            medido.append("outline")
        elif not duro:
            # Hay algo oscuro alrededor pero baja despacio: es una sombra
            # difusa, no un contorno duro. Un contorno duro salta a 0,00 y se
            # queda ahi (`pop` da 0.33 y luego 0.00); una sombra baja poco a
            # poco (el video de referencia da 0.56, 0.41, 0.37, 0.32).
            comp["outline"] = None
            comp["shadow"] = (0.0, 0.0, 0.0, 0.55, 0.0, 0.0)
            medido.extend(["outline", "shadow"])
        if borde.get("halo"):
            # El halo se tiñe del color del relleno, que es de donde sale: un
            # halo es la propia letra desbordada, no una luz de otro color.
            r, g, b = comp.get("fill") or (1.0, 1.0, 1.0)
            comp["glow"] = (r, g, b, float(borde["halo"]), 1.4)
            medido.append("glow")
        elif comp.get("glow"):
            comp["glow"] = None                 # la plantilla lo traia, el video no
            medido.append("glow")
    etiqueta = (nombre or "").strip()[:40] or "Copiado"
    comp.update({
        "id": id_para(etiqueta),
        "tipo": CAPTION,
        "label": {"es": etiqueta, "en": etiqueta},
        # La nota se genera y no se pide: el usuario ya escribio un nombre, y
        # pedirle ademas una descripcion para una tarjeta que solo ve el es
        # trabajo que no le sirve a nadie. Y dice el numero de verdad, que es
        # lo que separa esta pantalla de la de antes.
        "note": {"es": "Copiado de un vídeo: %d de %d cosas medidas."
                       % (len(medido), len(CAMPOS)),
                 "en": "Copied from a video: %d of %d values measured."
                       % (len(medido), len(CAMPOS))},
        "propio": True,
        # De donde vino cada mitad. `medido` es la lista honesta: lo que no
        # esta ahi salio de la plantilla, no del video.
        "base": base,
        "medido": medido,
        # Lo que hay DETRAS de las letras se guarda como dato y no como campo
        # del estilo, porque esta medido que no se puede saber si ese color es
        # una plancha o un contorno grueso (ver aprende.color_de_fondo). Vale
        # para enseñarlo y para el dia que se sepa distinguir; no vale para
        # decidir un `panel` hoy.
        "fondo_medido": (sub or {}).get("fondo") or None,
        "de": {"video": Path(video).name if video else "", "cuando": cuando},
    })
    return comp


# --------------------------------------------------------------------------- #
# Llevarselo a otra maquina
# --------------------------------------------------------------------------- #
# El sobre lleva version para que dentro de un año se pueda leer un archivo de
# hoy sabiendo que es. Un JSON pelado no dice de que programa salio, y el dia
# que el formato cambie no habria forma de distinguir uno viejo de uno roto.
SELLO = "vidorq/estilo"
FORMATO = 1

# Lo que puede llevar una fuente. Nada de rutas ni signos: ese nombre acaba
# dentro de un `.setting` de Fusion y de una linea de ASS, que son dos formatos
# de texto donde un caracter suelto cambia lo que significa el resto.
_FUENTE_OK = re.compile(r"[^\w \-]", re.UNICODE)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def exportar(eid, destino):
    """Un estilo de la galeria a un archivo suelto. Devuelve la ruta o None."""
    comp = uno(eid)
    if not comp:
        return None
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps({"que": SELLO, "formato": FORMATO, "componente": comp},
                   ensure_ascii=False, indent=1),
        encoding="utf-8")
    return destino


def _num(v, lo, hi):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f < lo or f > hi:              # el primero caza los NaN
        return None
    return f


def _tira(v, largo, rangos):
    """Una tupla de `largo` numeros, cada uno en su rango. None si no cuadra.

    Se exige el largo EXACTO y no "al menos": una tupla corta no revienta al
    guardar, revienta al renderizar, o sea despues, con el usuario mirando una
    pantalla que decia que todo habia ido bien. Ya paso con `outline`.
    """
    if not isinstance(v, (list, tuple)) or len(v) != largo:
        return None
    fuera = [_num(x, *rangos[i]) for i, x in enumerate(v)]
    return tuple(fuera) if all(x is not None for x in fuera) else None


_RGB = [(0.0, 1.0)] * 3

# Cada campo con su forma. La `y` y el `size` repiten los topes del motor a
# proposito: un `size` de 40 quiere decir que la banda medida se comio el
# cuadro, y eso no se guarda aunque venga de un archivo que parezca nuestro.
_FORMA = {
    "outline": (4, _RGB + [(0.0, 1.0)]),
    "shadow": (6, _RGB + [(0.0, 1.0), (-0.5, 0.5), (-0.5, 0.5)]),
    "glow": (5, _RGB + [(0.0, 1.0), (0.0, 8.0)]),
    "panel": (5, _RGB + [(0.0, 1.0), (0.0, 1.0)]),
}


def _texto(v, tope):
    return _CONTROL.sub("", str(v or "")).strip()[:tope]


def saneado(crudo, nombre=None):
    """Un componente de fuera, reconstruido campo a campo. None si no vale.

    LISTA BLANCA, no lista negra: se parte de nada y solo entra lo que se
    reconoce. Un archivo de estilo lo puede haber escrito cualquiera y llegar
    por correo, asi que aqui se trata como lo que es, un dato sin credenciales.
    Lo que no se reconoce no se limpia: no entra.

    El `id` NO se lee del archivo, se genera aqui. Dos motivos: uno de fuera
    podria pisar un estilo que ya tienes, y ese id acaba en nombres de archivo
    de la cache y en una linea de comandos.
    """
    import captions as cap

    if not isinstance(crudo, dict):
        return None
    plantilla = cap.PRESETS.get(str(crudo.get("base") or ""),
                                cap.PRESETS[cap.DEFAULT_PRESET])
    comp = {}
    # Los campos cuyo valor del archivo SI paso la revision. Sirve para no
    # heredar la mentira: si llega un `fill` corrupto y se cae a la plantilla,
    # el estilo no puede seguir diciendo que ese color esta medido.
    vivos = set()
    for campo in CAMPOS:
        v = crudo.get(campo)
        if campo in _FORMA:
            largo, rangos = _FORMA[campo]
            comp[campo] = None if v is None else _tira(v, largo, rangos)
        elif campo in ("fill", "accent"):
            comp[campo] = _tira(v, 3, _RGB)
        elif campo == "size":
            comp[campo] = _num(v, 0.005, 0.5)
        elif campo == "y":
            comp[campo] = _num(v, 0.0, 1.0)
        elif campo == "tracking":
            comp[campo] = _num(v, -0.5, 1.0)
        elif campo in ("words", "max_chars"):
            n = _num(v, 0, 200)
            comp[campo] = None if n is None else int(n)
        elif campo == "upper":
            comp[campo] = bool(v)
        elif campo == "font":
            comp[campo] = _FUENTE_OK.sub("", _texto(v, 64))
        elif campo == "style":
            comp[campo] = _FUENTE_OK.sub("", _texto(v, 32))
        elif campo == "anim":
            comp[campo] = v if v in cap.ANIMS else plantilla["anim"]
        elif campo == "word_fx":
            comp[campo] = "karaoke" if v == "karaoke" else None
        # Un None puede ser una medida de verdad: "este video NO lleva
        # contorno" es un hallazgo, no un hueco, y por eso los cuatro campos
        # que admiten None cuentan como vivos cuando llegan vacios a proposito.
        if comp.get(campo) is not None or (v is None and campo in _FORMA):
            vivos.add(campo)
        # Lo que se cayo por el camino vuelve a la plantilla, que es lo mismo
        # que hace `caption_de` con lo que no se sabe medir.
        if comp.get(campo) is None and campo not in ("outline", "shadow",
                                                     "glow", "panel",
                                                     "word_fx"):
            comp[campo] = plantilla.get(campo)

    etiqueta = (_texto(nombre, 40)
                or _texto((crudo.get("label") or {}).get("es"), 40)
                or "Importado")
    medido = [m for m in (crudo.get("medido") or []) if m in vivos]
    comp.update({
        "id": id_para(etiqueta),
        "tipo": CAPTION,
        "label": {"es": etiqueta, "en": etiqueta},
        "note": {"es": "Importado: %d de %d cosas medidas."
                       % (len(medido), len(CAMPOS)),
                 "en": "Imported: %d of %d values measured."
                       % (len(medido), len(CAMPOS))},
        "propio": True,
        "base": str(crudo.get("base") or cap.DEFAULT_PRESET)[:32],
        "medido": medido,
        "fondo_medido": _tira(crudo.get("fondo_medido"), 3, _RGB),
        "de": {"video": _texto((crudo.get("de") or {}).get("video"), 80),
               "cuando": _texto((crudo.get("de") or {}).get("cuando"), 32)},
    })
    return comp


def importar(origen, nombre=None):
    """Mete en la galeria un estilo exportado. Devuelve el id nuevo o None.

    Acepta tanto el sobre de `exportar()` como el componente pelado, porque un
    usuario que abra el archivo y copie lo de dentro tiene toda la razon en
    esperar que funcione.
    """
    try:
        datos = json.loads(Path(origen).read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(datos, dict) and isinstance(datos.get("componente"), dict):
        if datos.get("que") != SELLO:
            return None
        datos = datos["componente"]
    comp = saneado(datos, nombre)
    if not comp or not comp.get("fill"):
        # Sin color de relleno no hay estilo que valga: seria la plantilla otra
        # vez, con otro nombre encima.
        return None
    return guardar(comp)
