r"""Lee un `.setting` escrito por Resolve y dice que operadores lleva dentro.

LA PREGUNTA PARA LA QUE NACIO YA ESTA CONTESTADA (2026-08-24). Se escribio para
averiguar por que un color por palabra no pintaba, y la respuesta fue que el
estilo por caracteres NO es un campo del `Text+`: es el operador aparte
`StyledTextCLS`, colgado de su entrada `StyledText`. Escrito dentro del nodo,
Resolve lo guarda y lo ignora al pintar. Todo el detalle, en `docs/FUSION.md`.

Se queda porque el trabajo que hace sigue valiendo, y es el que contesto: un
fichero escrito por Resolve dice la verdad sobre como monta las cosas, y este
script separa los NODOS de los envoltorios de valor (que se escriben igual, con
`X = Tipo {`) y ensena quien alimenta a quien. Cuando algo de Fusion no salga,
guarda uno hecho a mano y pasaselo por aqui antes de dar nada por imposible.

Se lanza:  python resolve/leer_cls.py [ruta.setting]

Sin argumento busca `%USERPROFILE%\Desktop\cls.setting`. No toca nada, solo lee.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Donde se le pide que lo guarde. Se aceptan otros sitios por argumento.
POR_DEFECTO = Path.home() / "Desktop" / "cls.setting"

# Lo que Vidorq escribio en su intento y NO renderizo. Sirve de referencia:
# lo interesante es lo que aparezca en el fichero de Munir y no este aqui.
LO_QUE_YA_PROBAMOS = {
    "CharacterLevelStyling", "CharacterLevelStylingBase",
    # `StyledText` sale por dos sitios y ninguno es noticia: es el nombre del
    # cuadro de texto del Text+ y tambien el del envoltorio del valor. Sin
    # ponerlo aqui, el script grita "NUEVO" en todos los ficheros del mundo.
    "StyledText",
}

# Un modificador de Fusion se ve asi dentro de un fichero: un operador propio,
# con nombre, cableado a una entrada del nodo. Si el estilo por caracteres es un
# MODIFICADOR y no un valor, esto es lo que lo delata, y explicaria por que
# escribir el campo a pelo no hace nada.
RE_OPERADOR = re.compile(r"^\s*(\w+)\s*=\s*(\w+)\s*\{", re.M)

# Un valor de Fusion se escribe igual que un operador (`X = Tipo {`), asi que
# distinguirlos por la forma no vale: hay que descartar los tipos que son
# envoltorios de valor. Sin esto, un fichero normal parece tener veinte nodos.
NO_SON_NODOS = {
    "Input", "InstanceInput", "InstanceOutput", "StyledText", "Number", "Point",
    "OperatorInfo", "GroupInfo", "Matrix", "FuID", "ScriptVal", "Text", "Gradient",
    "LUTBezier", "ViewInfo", "Flags", "KeyFrames", "SplineColor", "CustomData",
}
RE_FUENTE = re.compile(r'SourceOp\s*=\s*"(\w+)"')
RE_CLS = re.compile(r"\w*(?:CharacterLevel|StyledText|CLS)\w*")


def bloque(texto, clave, largo=1500):
    """El trozo del fichero que empieza en `clave`, para poder leerlo."""
    i = texto.find(clave)
    return texto[i:i + largo] if i >= 0 else ""


def main(argv):
    ruta = Path(argv[1]) if len(argv) > 1 else POR_DEFECTO
    if not ruta.is_file():
        print("No encuentro %s" % ruta)
        print()
        print("Los pasos para generarlo estan arriba del todo de este archivo,")
        print("y tambien en docs/FUSION.md. Duran un minuto.")
        return 1

    t = ruta.read_text(encoding="utf-8", errors="replace")
    print("Leyendo %s (%d bytes)" % (ruta, len(t)))
    print()

    # 1) Todos los operadores del fichero. Si hay uno que no sea el Text+, ahi
    #    esta la respuesta: la interfaz crea algo que nosotros no creamos.
    ops = [(n, k) for n, k in RE_OPERADOR.findall(t) if k not in NO_SON_NODOS]
    print("--- NODOS ---")
    for nombre, tipo in ops:
        marca = "  <-- NO es el Text+" if tipo not in ("TextPlus", "MultiText") else ""
        print("  %-28s %s%s" % (nombre, tipo, marca))
    otros = [(n, k) for n, k in ops if k not in ("TextPlus", "MultiText")]
    print()
    if otros:
        print("HAY %d NODO(S) APARTE DEL TEXT+." % len(otros))
        print("Si alguno es el estilo por caracteres, entonces es un MODIFICADOR")
        print("y no un valor, y eso explica por que escribir el campo no pinta.")
    else:
        print("Solo hay Text+. Entonces el estilo por caracteres NO es un")
        print("operador aparte, y la diferencia esta en los valores de abajo.")
    print()

    # 2) Todo lo que suene a estilo por caracteres.
    print("--- NOMBRES RELACIONADOS QUE APARECEN ---")
    vistos = sorted(set(RE_CLS.findall(t)))
    for v in vistos:
        nuevo = "  <-- NUEVO, no lo escribiamos" if v not in LO_QUE_YA_PROBAMOS else ""
        print("  %s%s" % (v, nuevo))
    nuevos = [v for v in vistos if v not in LO_QUE_YA_PROBAMOS]
    print()
    if nuevos:
        print("ESTO ES LO IMPORTANTE: %s" % ", ".join(nuevos))
    print()

    # 3) Cableados: quien alimenta a quien.
    print("--- CABLEADOS (SourceOp) ---")
    for f in sorted(set(RE_FUENTE.findall(t))):
        print("  ->", f)
    print()

    # 4) Y el bloque entero, para leerlo con los ojos, que es lo que de verdad
    #    contesta. Un resumen automatico se pierde justo el detalle raro.
    for clave in ("CharacterLevelStyling", "StyledTextCLS", "StyledText"):
        b = bloque(t, clave)
        if b:
            print("--- EL BLOQUE DE '%s', TAL CUAL ---" % clave)
            print(b)
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
