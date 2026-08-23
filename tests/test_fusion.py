"""Un estilo de Vidorq sale de Fusion como un titulo que se puede arrastrar.

Recrear un estilo NO es pegar la frase del video dentro de un comp: eso copia el
TEXTO. Es dejar el ESTILO suelto en `Effects Library > Titles`, para escribirle
encima cualquier frase. La diferencia la marco Munir el 2026-08-23 y es la razon
de que exista `skill/helpers/fusion.py`.

Lo que se comprueba aqui, y por que cada cosa:

  - el fichero esta EQUILIBRADO. Un `.setting` es una tabla de Lua: una llave de
    mas y Resolve no lo abre, y no avisa, simplemente no aparece en la lista.
  - ningun `SourceOp` cuelga. Esta es la que de verdad pilla los fallos. El
    sangrado equivocado (tres tabuladores en vez de cuatro) dejaba el fichero
    con las llaves cuadradas y los nodos FUERA del grupo, asi que mirarlo no lo
    delataba: lo delato comprobar que cada nodo citado estuviera definido.
  - el grupo y el Text+ de dentro NO se llaman igual. Con el mismo nombre, los
    mandos publicos apuntan a dos sitios a la vez.
  - el TEXTO es un mando publico, que es el punto entero: una plantilla con la
    frase clavada dentro no sirve para el video siguiente.
  - la entrada viaja como `BezierSpline`. Es la unica forma de que un keyframe
    sobreviva, porque la API de Resolve no los pone.
  - `desinstalar()` se niega a borrar un `.setting` que no escribimos nosotros.
    Esa carpeta es del usuario y puede tener trabajo suyo.
  - `faltantes()` DICE lo que no sabe hacer. Un estilo a medias que no avisa es
    la mentira que este proyecto lleva una semana quitando.

Se recorren LOS DIEZ presets, no dos elegidos a mano: probar un subconjunto ya
costo dos regresiones en un dia.

No necesita Resolve, ni ffmpeg, ni red. Escribe en un APPDATA temporal, nunca en
el de verdad: probar contra el de verdad ya destruyo una vez un perfil de marca.

Lo que estas pruebas NO pueden decir: si Resolve lo abre. Eso se ve con Resolve
delante, y esta escrito en `docs/FUSION.md`.

Se lanza:  python tests/test_fusion.py
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))

# El APPDATA de mentira se pone ANTES de importar nada que lo lea. fusion lo
# consulta en cada llamada, asi que basta con esto.
CASA = Path(tempfile.mkdtemp(prefix="vidorq_fusion_"))
os.environ["APPDATA"] = str(CASA)
(CASA / "Vidorq" / "workspaces" / "Principal").mkdir(parents=True)

import captions as cap        # noqa: E402
import fusion                 # noqa: E402

# Un nodo del grupo se define a CUATRO tabuladores:
#   { > Tools > grupo > Tools > nodo
# Comprobado contra las plantillas de fabrica de Blackmagic, que ponen ahi
# mismo sus BezierSpline (`Background Reveal Lower Third.setting`, 2026-08-23).
NODO = re.compile(r"^\t{4}(\w+) = \w+ \{", re.M)
CITA = re.compile(r'SourceOp = "(\w+)"')
GRUPO = re.compile(r"^\t\t(\w+) = GroupOperator \{", re.M)
SALIDA = re.compile(r'MainOutput1 = InstanceOutput \{\s*SourceOp = "(\w+)"')
MANDO = re.compile(r'Input\d+ = InstanceInput \{\s*SourceOp = "(\w+)",\s*'
                   r'Source = "(\w+)"')


def _llaves(texto):
    """Cuantas llaves quedan abiertas. 0 esta bien, -1 es que cerro de mas."""
    n = 0
    for ch in texto:
        if ch == "{":
            n += 1
        elif ch == "}":
            n -= 1
            if n < 0:
                return -1
    return n


def revisar(texto, nombre):
    """Los fallos de este `.setting`, uno por linea. Lista vacia = esta bien."""
    fallos = []
    if _llaves(texto) != 0:
        fallos.append("las llaves no cuadran (%d)" % _llaves(texto))

    nodos = set(NODO.findall(texto))
    colgando = sorted(set(CITA.findall(texto)) - nodos)
    if colgando:
        fallos.append("cita nodos que no existen: %s" % ", ".join(colgando))

    grupos = GRUPO.findall(texto)
    if len(grupos) != 1:
        fallos.append("esperaba UN GroupOperator y hay %d" % len(grupos))
    elif grupos[0] in nodos:
        fallos.append("el grupo y un nodo de dentro se llaman igual (%s)"
                      % grupos[0])

    salida = SALIDA.search(texto)
    if not salida:
        fallos.append("no tiene MainOutput1")
    elif salida.group(1) not in nodos:
        fallos.append("la salida apunta a '%s', que no esta definido"
                      % salida.group(1))

    if "TextPlus" not in texto:
        fallos.append("no lleva ningun Text+")

    fuentes = {src for _, src in MANDO.findall(texto)}
    if "StyledText" not in fuentes:
        fallos.append("el texto no es un mando publico")
    for hace_falta in ("Size", "Center", "Red1"):
        if hace_falta not in fuentes:
            fallos.append("falta el mando publico %s" % hace_falta)

    if fusion.MARCA not in texto:
        fallos.append("no lleva la marca de Vidorq")
    return ["%s: %s" % (nombre, f) for f in fallos]


def main():
    fallos, total = [], 0
    try:
        # 1) Los DIEZ presets, enteros.
        for pid in cap.PRESETS:
            total += 1
            fallos += revisar(fusion.plantilla("Prueba " + pid, pid), pid)

        # 2) La entrada viaja como spline. Se comprueba en los presets cuya
        #    animacion mueve el tamaño, que son los que tienen algo que animar.
        for pid in cap.PRESETS:
            total += 1
            texto = fusion.plantilla("Prueba " + pid, pid)
            if "AnimSize" in texto and "BezierSpline" not in texto:
                fallos.append("%s: anima el tamaño sin escribir el spline" % pid)
            if "BezierSpline" in texto and "KeyFrames" not in texto:
                fallos.append("%s: un spline sin un solo keyframe" % pid)

        # 3) Nombres. Un nombre con acentos y espacios vale de FICHERO pero no
        #    de identificador de Lua, y las dos cosas se piden por separado.
        total += 1
        if fusion.nodo_de("Mi Estilo Ñandú 3") != "Mi_Estilo_and_3":
            # El acento se cae porque no es ASCII; lo que importa es que salga
            # un identificador valido, no cual exactamente.
            ident = fusion.nodo_de("Mi Estilo Ñandú 3")
            if not re.fullmatch(r"[A-Za-z_]\w*", ident):
                fallos.append("nodo_de devolvio algo que no es identificador: %r"
                              % ident)
        total += 1
        if not re.fullmatch(r"[A-Za-z_]\w*", fusion.nodo_de("3 pasos")):
            fallos.append("un nombre que empieza por numero no da identificador")
        total += 1
        if not re.fullmatch(r"[A-Za-z_]\w*", fusion.nodo_de("")):
            fallos.append("un nombre vacio no da identificador")

        # 4) Instalar, listar y quitar.
        total += 1
        ruta = fusion.instalar("Copiado del Short", "pop")
        if not ruta.is_file():
            fallos.append("instalar() no dejo el fichero")
        total += 1
        if "Copiado del Short" not in fusion.instaladas():
            fallos.append("instaladas() no ve la que se acaba de poner")
        total += 1
        if not fusion.desinstalar("Copiado del Short"):
            fallos.append("desinstalar() no pudo con la suya propia")
        total += 1
        if ruta.exists():
            fallos.append("desinstalar() dijo que si y el fichero sigue ahi")

        # 5) Lo AJENO no se toca. Esta es la que protege trabajo del usuario.
        total += 1
        suyo = fusion.carpeta() / "Titulo del usuario.setting"
        suyo.write_text("{ Tools = ordered() { } }", encoding="utf-8")
        if fusion.desinstalar("Titulo del usuario"):
            fallos.append("desinstalar() borro un .setting que no era nuestro")
        total += 1
        if not suyo.exists():
            fallos.append("un .setting ajeno desaparecio")
        total += 1
        if "Titulo del usuario" in fusion.instaladas():
            fallos.append("instaladas() se apunta ficheros ajenos")

        # 6) Lo que no sabe hacer, lo dice. `marker` es el preset con karaoke.
        total += 1
        karaoke = [p for p, v in cap.PRESETS.items()
                   if v.get("word_fx") == "karaoke"]
        for pid in karaoke:
            if not fusion.faltantes(pid):
                fallos.append("%s pinta por palabra y faltantes() calla" % pid)
        total += 1
        for pid in cap.PRESETS:
            for hueco in fusion.faltantes(pid):
                if not (hueco.get("que") and hueco.get("porque")):
                    fallos.append("%s: un hueco sin explicar" % pid)

        # 7) El texto de muestra se puede cambiar, y comillas dentro no rompen
        #    el fichero: un `.setting` es Lua y una comilla suelta lo parte.
        total += 1
        con_comillas = fusion.plantilla("Comillas", "pop", texto='DI "HOLA"')
        fallos += revisar(con_comillas, "texto con comillas")
        total += 1
        if '\\"HOLA\\"' not in con_comillas:
            fallos.append("las comillas del texto no se escaparon")

        if fallos:
            print("%d de %d casos MAL:\n" % (len(fallos), total))
            for line in fallos:
                print("  - %s" % line)
            return 1
        print("%d casos, un estilo sale de Fusion como titulo arrastrable."
              % total)
        return 0
    finally:
        shutil.rmtree(CASA, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
