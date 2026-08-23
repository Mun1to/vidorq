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
    etiqueta = (nombre or "").strip()[:40] or "Copiado"
    comp.update({
        "id": id_para(etiqueta),
        "tipo": CAPTION,
        "label": {"es": etiqueta, "en": etiqueta},
        # La nota se genera y no se pide: el usuario ya escribio un nombre, y
        # pedirle ademas una descripcion para una tarjeta que solo ve el es
        # trabajo que no le sirve a nadie. Y dice el numero de verdad, que es
        # lo que separa esta pantalla de la de antes.
        "note": {"es": "Copiado de un video: %d de %d cosas medidas."
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
