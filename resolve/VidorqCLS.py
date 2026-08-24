r"""Le pregunta a Fusion, desde DENTRO, como se aplica Character Level Styling.

YA CONTESTO, y esto es lo que dijo (2026-08-24). El operador se llama
`StyledTextCLS`, `comp.AddTool("StyledTextCLS")` lo crea, y se cuelga de la
entrada `StyledText` del `Text+`; el texto pasa a vivir en el `Text` del
modificador. El `.setting` que guardo Resolve lo dejo escrito con todas sus
letras. Con eso, un color por palabra pinta: `captions.to_comp` lo escribe y
`docs/FUSION.md` tiene la tabla de codigos.

Se queda porque el METODO es lo que vale: cuando algo de Resolve parezca una
pared, esto es como se le pregunta a Fusion en vez de adivinar desde fuera.
`resolve/instalar.ps1` NO lo copia a proposito, porque es una herramienta de
diagnostico y no tiene por que estar en el menu de Munir todos los dias. Para
usarlo se copia a mano a la carpeta `Scripts\Utility` de Resolve y se lanza con
`Workspace > Scripts > Utility > VidorqCLS`; deja el log en el escritorio.

Por que existe. Escribir `CharacterLevelStyling` o `CharacterLevelStylingBase`
en un comp no pinta nada: Resolve los conserva enteros al ir y volver y los
IGNORA al renderizar (medido el 2026-08-23, dos intentos, fotograma blanco las
dos veces; detalle en `docs/FUSION.md`). Asi que el campo no es el mecanismo, o
no es el mecanismo entero.

La forma honesta de averiguarlo no es probar mas sintaxis: es preguntarle a
Fusion. Y a Fusion solo se le puede preguntar desde dentro de Resolve, porque la
version Free no admite scripting externo. Este archivo se ejecuta desde
`Workspace > Scripts > Utility > VidorqCLS` y escribe lo que encuentre en un
log que se lee desde fuera.

NO TOCA EL PROYECTO ABIERTO. Trabaja sobre una composicion NUEVA que crea el, y
lo unico que deja en el disco es el log y, si lo consigue, un `.setting`.

Lo que intenta, en orden, y todo queda escrito pase lo que pase:

  1. Que hay en las globales (`fusion`, `fu`, `bmd`, `resolve`).
  2. La lista de operadores REGISTRADOS, buscando cualquiera que suene a estilo
     por caracteres. Aqui esta la respuesta si el estilo es un modificador: su
     identificador saldria en esa lista y nunca lo hemos sabido.
  3. Crear un Text+ y mirar que atributos tiene su entrada de texto.
  4. Probar a colgarle un modificador por cada identificador candidato.
  5. Guardar los ajustes del Text+ a `.setting`, que es un fichero escrito por
     RESOLVE y no por nosotros, que es justo lo que pedia el encargo.
"""

import json
import os
import traceback

SALIDA = os.path.join(os.path.expanduser("~"), "Desktop", "vidorq_cls")
LOG = SALIDA + ".txt"

# Identificadores que podria tener el modificador. No se inventan a lo loco: son
# las formas en que Fusion nombra sus operadores (sin espacios, en CamelCase) a
# partir del nombre que ensena el menu, "Character Level Styling", mas la
# abreviatura CLS que usa Blackmagic en su propia documentacion.
CANDIDATOS = [
    "StyledTextCLS", "CharacterLevelStyling", "TextCharacterStyle",
    "StyledTextModifier", "CharacterStyling", "TextStyle", "StyledText",
    "CharacterLevelStylingModifier", "TextPlusCLS",
]

lineas = []


def di(*trozos):
    texto = " ".join(str(t) for t in trozos)
    lineas.append(texto)
    print(texto)


def intenta(que, fn):
    """Corre `fn` y deja escrito el resultado o el fallo. Nunca lanza."""
    try:
        r = fn()
        di("OK   %-42s -> %r" % (que, r))
        return r
    except Exception as e:
        di("FALLA %-41s -> %s: %s" % (que, type(e).__name__, e))
        return None


def main():
    di("=" * 70)
    di("VidorqCLS: preguntandole a Fusion como se aplica el estilo por caracteres")
    di("=" * 70)

    g = globals()
    di("\n--- 1) GLOBALES ---")
    di("presentes:", ", ".join(n for n in ("bmd", "fusion", "fu", "resolve",
                                           "app", "davinci") if n in g))

    fu = g.get("fusion") or g.get("fu")
    if fu is None:
        di("No hay objeto fusion. Sin eso no hay nada que preguntar.")
        return

    # ---------------------------------------------------------------- 2
    di("\n--- 2) OPERADORES REGISTRADOS ---")
    # `GetRegList` pide una constante de clase, y su nombre cambia entre
    # versiones. Se prueban las que existen, y basta con que UNA conteste.
    listas = {}
    for nombre in ("CT_Tool", "CT_Modifier", "CT_ViewLut", "CT_Any"):
        cte = getattr(g.get("bmd", object()), nombre, None)
        if cte is None:
            cte = getattr(fu, nombre, None)
        if cte is None:
            continue
        r = intenta("GetRegList(%s)" % nombre, lambda c=cte: fu.GetRegList(c))
        if r:
            listas[nombre] = r

    # Sin constantes, se prueba a pelo con los enteros que usa Fusion.
    if not listas:
        for n in range(0, 8):
            r = intenta("GetRegList(%d)" % n, lambda k=n: fu.GetRegList(k))
            if r:
                listas[str(n)] = r

    interesantes = []
    for de, lista in listas.items():
        try:
            claves = list(lista.keys()) if hasattr(lista, "keys") else list(lista)
        except Exception:
            continue
        di("  %s: %d entradas" % (de, len(claves)))
        for k in claves:
            s = str(k)
            if any(t in s.lower() for t in ("cls", "character", "styled", "style")):
                interesantes.append(s)
    di("\n  LO QUE SUENA A ESTILO POR CARACTERES: %s"
       % (", ".join(sorted(set(interesantes))) or "NADA"))

    # ---------------------------------------------------------------- 3
    di("\n--- 3) UN TEXT+ NUEVO, EN UNA COMPOSICION APARTE ---")
    comp = intenta("fusion.NewComp()", lambda: fu.NewComp())
    if comp is None:
        comp = intenta("fusion.CurrentComp", lambda: fu.CurrentComp)
    if comp is None:
        di("Sin composicion no se puede seguir.")
        return escribir()

    intenta("comp.Lock()", lambda: comp.Lock())
    txt = intenta('comp.AddTool("TextPlus")', lambda: comp.AddTool("TextPlus"))
    if txt is None:
        intenta("comp.Unlock()", lambda: comp.Unlock())
        return escribir()

    intenta("poner el texto", lambda: setattr(txt, "StyledText", "HOLA MUNDO"))
    intenta("txt.StyledText:GetAttrs()",
            lambda: json.dumps({str(k): str(v) for k, v in
                                (txt.StyledText.GetAttrs() or {}).items()})[:900])

    # Las entradas del Text+, por si el estilo por caracteres es una de ellas y
    # se llama de otra forma.
    def entradas():
        d = txt.GetInputList() or {}
        nombres = []
        for k in d:
            try:
                a = d[k].GetAttrs() or {}
                nombres.append(str(a.get("INPS_ID", k)))
            except Exception:
                nombres.append(str(k))
        return [n for n in nombres
                if any(t in n.lower() for t in ("cls", "character", "styl"))]
    intenta("entradas que suenan a estilo", entradas)

    # ---------------------------------------------------------------- 4
    di("\n--- 4) COLGARLE UN MODIFICADOR ---")
    puesto = None
    for cid in CANDIDATOS + sorted(set(interesantes)):
        r = intenta('AddTool("%s")' % cid, lambda c=cid: comp.AddTool(c))
        if r:
            puesto = cid
            di("  >>> ESTE EXISTE: %s" % cid)
            intenta("colgarlo del texto",
                    lambda t=r: setattr(txt, "StyledText", t))
            break

    # ---------------------------------------------------------------- 4b
    di("\n--- 4b) LAS ENTRADAS DEL MODIFICADOR ---")
    # El modificador existe y esta cableado. Lo que falta es DONDE guarda el
    # color de cada caracter, y eso se le pregunta a el en vez de adivinarlo.
    mod = intenta("el modificador colgado del texto",
                  lambda: txt.StyledText.GetConnectedOutput().GetTool())
    if mod is None:
        mod = intenta("por nombre en la comp",
                      lambda: comp.FindTool("CharacterLevelStyling1"))
    if mod is not None:
        def ids():
            d = mod.GetInputList() or {}
            fuera = []
            for k in d:
                try:
                    a = d[k].GetAttrs() or {}
                    fuera.append("%s   [%s]" % (a.get("INPS_ID", k),
                                                a.get("INPS_DataType", "?")))
                except Exception:
                    fuera.append(str(k))
            return sorted(fuera)
        for linea in (intenta("entradas del modificador", ids) or []):
            di("      " + linea)

    # ---------------------------------------------------------------- 5
    di("\n--- 5) GUARDAR LO QUE ESCRIBA RESOLVE ---")
    dest = SALIDA + ".setting"
    intenta("txt.SaveSettings(...)", lambda: txt.SaveSettings(dest))
    di("  fichero:", dest, "existe:", os.path.isfile(dest))
    di("\n  modificador que se pudo crear:", puesto or "NINGUNO")

    intenta("comp.Unlock()", lambda: comp.Unlock())
    return escribir()


def escribir():
    try:
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas))
        print("\nLog en: %s" % LOG)
    except Exception:
        traceback.print_exc()


try:
    main()
except Exception:
    di("REVENTO:\n" + traceback.format_exc())
    escribir()
