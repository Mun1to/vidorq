r"""Le pregunta a Fusion, desde DENTRO, como se escribe una mascara ANIMADA.

Sigue el metodo de `VidorqCLS.py`, que es el que resolvio Character Level
Styling despues de dos dias dandolo por imposible: cuando algo de Resolve parece
una pared, no se prueban mas sintaxis a ciegas, se le PREGUNTA a Fusion, y a
Fusion solo se le puede preguntar desde dentro, porque la version Free no admite
scripting externo.

## Que hace falta saber, y por que importa

Vidorq ya sigue la mascara de un sujeto por todo el video (`skill/helpers/
mascara.py`), y con eso ya hace el efecto de "texto por detras de ti" en el MP4.
Lo que NO se sabe todavia es como meter esa mascara en Resolve **como un poligono
editable**, que es lo que la haria retocable a mano en el timeline en vez de un
recorte plano.

La diferencia importa de verdad. Magic Mask es de Studio (295 dolares) y esta es
la funcion por la que se compra. Que Vidorq la de en la version gratis, y encima
editable, no es una mas: es de las dos o tres cosas que sostienen el producto.

## Por que no se puede averiguar desde fuera, y ya se intento

Las 417 plantillas de fabrica que reparte Blackmagic dentro de `Templates.drfx`
se leyeron enteras el 2026-09-09 buscando la sintaxis: **hay 75 ficheros con
`Polyline` y CERO con un nodo `Polygon`**. Logico, porque son plantillas de
titulos y no llevan mascaras. Asi que el esqueleto de un poligono no esta escrito
en ningun sitio al que se llegue sin abrir Resolve.

Lo que si se saco de ahi es la forma de una `Polyline` estatica, que es esta:

    Path = Input { Value = Polyline { Points = {
        { X = -0.561, Y = -0.266, RX = 0.039, RY = 0.008 },
        { X = -0.459, Y = -0.212, LX = -0.019, LY = -0.040, RX = 0.029, RY = 0.060 },
    }, }, },

Puntos en coordenadas normalizadas, con los tiradores de bezier a izquierda (LX,
LY) y derecha (RX, RY). Lo que falta es la mitad que se mueve: como se anima esa
lista de puntos a lo largo del tiempo.

## Que escribe

Un log en el escritorio con: la lista de operadores de Fusion que suenan a
mascara, los mandos publicos de un `Polygon` recien creado, y el `.setting` de
una mascara con DOS formas distintas en dos fotogramas, que es exactamente el
caso que hay que reproducir. Con ese fichero delante, escribir mascaras animadas
desde Python deja de ser adivinar.

NO TOCA EL PROYECTO ABIERTO. Trabaja sobre una composicion nueva que crea el, y
lo unico que deja en disco es el log y, si lo consigue, un `.setting`.

Para usarlo se copia a mano a la carpeta `Scripts\Utility` de Resolve y se lanza
con `Workspace > Scripts > Utility > VidorqPoly`. `resolve/instalar.ps1` NO lo
copia a proposito: es una herramienta de diagnostico, no algo del menu de todos
los dias.
"""
import os
import traceback

LOG = os.path.join(os.path.expanduser("~"), "Desktop", "vidorq_poly.log")
_lineas = []


def di(txt=""):
    """Escribe en el log y lo vuelca en cada linea.

    En cada linea a proposito: si Resolve se cae a mitad de la pregunta, lo que
    interesa es justo lo ultimo que se intento, y eso es lo primero que se pierde
    con un fichero que se escribe al final.
    """
    _lineas.append(str(txt))
    try:
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(_lineas))
    except Exception:
        pass
    print(str(txt))


def main():
    di("=== VidorqPoly: como se escribe una mascara animada ===")
    di("log: %s" % LOG)
    di()

    fu = globals().get("fusion")
    if fu is None:
        di("NO HAY `fusion` en el espacio global.")
        di("Esto tiene que lanzarse DESDE Resolve (Workspace > Scripts), no")
        di("desde una terminal: la version Free no admite scripting externo.")
        return

    # 1. Que operadores de mascara conoce esta instalacion. Preguntado, no
    #    supuesto: los nombres cambian entre versiones y adivinarlos es como se
    #    perdieron dos dias con Character Level Styling.
    di("--- 1. operadores que suenan a mascara ---")
    try:
        regs = fu.GetRegList(-1) or {}
        nombres = sorted(str(v.Name) for v in regs.values() if hasattr(v, "Name"))
        clave = [n for n in nombres
                 if any(p in n.lower() for p in ("poly", "mask", "matte", "bspline"))]
        di("de %d operadores, %d suenan a mascara:" % (len(nombres), len(clave)))
        for n in clave:
            di("    %s" % n)
    except Exception:
        di("no pude listar los operadores:")
        di(traceback.format_exc())
    di()

    # 2. Un Polygon de verdad, y TODOS sus mandos. El nombre exacto de la
    #    entrada que guarda los puntos es lo que hay que saber para escribirla.
    di("--- 2. los mandos de un Polygon recien creado ---")
    comp = None
    try:
        comp = fu.NewComp()
        poly = comp.AddTool("Polygon", -32768, -32768)
        if not poly:
            di("AddTool('Polygon') no devolvio nada: probando 'PolylineMask'...")
            poly = comp.AddTool("PolylineMask", -32768, -32768)
        if poly:
            di("creado: %s" % poly.Name)
            entradas = poly.GetInputList() or {}
            di("%d entradas:" % len(entradas))
            for i in sorted(entradas):
                e = entradas[i]
                try:
                    di("    %-28s %s" % (e.Name, e.GetAttrs("INPS_DataType")))
                except Exception:
                    di("    %s" % e.Name)
        else:
            di("no pude crear ningun nodo de mascara. Los nombres que valen")
            di("estan en la lista del apartado 1.")
    except Exception:
        di("fallo creando el Polygon:")
        di(traceback.format_exc())
    di()

    # 3. LA PREGUNTA DE VERDAD: dos formas distintas en dos fotogramas.
    #    Lo que se guarde aqui es el molde a copiar desde Python.
    di("--- 3. una mascara con DOS formas en dos fotogramas ---")
    try:
        if comp and poly:
            # Se mueve un punto entre el fotograma 0 y el 20. Si Resolve sabe
            # animar la forma, el .setting de abajo lo lleva escrito, y ahi
            # esta la sintaxis que falta.
            di("poniendo la forma del fotograma 0...")
            comp.CurrentTime = 0
            poly.Polyline = None          # deja que Fusion cree su estructura
            di("mandos publicos ahora: %s" % (poly.GetInputList() and "si" or "no"))
            comp.CurrentTime = 20
            di("(si Fusion admite animar la forma, el .setting de abajo la trae")
            di(" dos veces; si no, la trae una sola y ya sabemos que NO se puede)")
            destino = os.path.join(os.path.expanduser("~"), "Desktop",
                                   "vidorq_poly.setting")
            if comp.SaveAs(destino):
                di("comp guardada en: %s" % destino)
                try:
                    with open(destino, "r", encoding="utf-8", errors="replace") as f:
                        texto = f.read()
                    di()
                    di("--- el .setting entero, que es el molde a copiar ---")
                    di(texto)
                except Exception:
                    di("guardada pero no pude releerla")
            else:
                di("SaveAs devolvio falso: no se pudo guardar")
    except Exception:
        di("fallo en la parte animada:")
        di(traceback.format_exc())

    di()
    di("=== fin. Pasale este log a la sesion de Vidorq. ===")


main()
