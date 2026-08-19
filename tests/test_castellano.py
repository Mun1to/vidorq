# -*- coding: utf-8 -*-
"""El castellano que ve el usuario, con sus tildes y sus enes.

Por que existe: el 19-ago-2026 se arreglaron a mano cuarenta y una cadenas sin
tilde, y a la semana siguiente (bueno, media hora despues) aparecieron siete
mas escondidas en las notas del catalogo. La tercera vez que haces algo a mano
se automatiza, asi que esto es la tercera.

El problema real no es la falta de tilde en si, es que el producto habla dos
castellanos a la vez: la ventana pregunta "¿Que transicion?" con tilde y el
motor contesta "transicion: Fundido a negro" sin ella, en el mismo renglon.

Como funciona: una lista de palabras que en castellano SIEMPRE llevan tilde o
ene y que no tienen un homografo valido sin ella. Nada de "esta", "solo", "aun"
ni "el", que son palabras distintas segun la tilde y aqui no se puede saber
cual toca. Si alguna de estas aparece pelada en un texto que va a pantalla, el
caso sale rojo con su archivo y su clave.

No mira el codigo ni los comentarios: solo lo que se le ensena a una persona.

Se lanza:  python tests/test_castellano.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))
sys.path.insert(0, str(RAIZ / "engine"))

# Palabras sin homografo: si aparecen asi, estan mal. Escritas en minusculas;
# la comprobacion no distingue mayusculas.
PELADAS = """
    mayusculas minusculas numero numeros tambien ademas aqui asi segun quiza
    ultimo ultima ultimos ultimas unico unica unicos unicas
    rapido rapida rapidos rapidas facil dificil faciles dificiles
    automatico automatica automaticos automaticas clasico clasica basico
    logico grafico graficos practico estatico tipico
    video videos titulo titulos parrafo parrafos codigo codigos
    boton linea lineas pagina paginas camara camaras maquina maquinas
    sesion version opcion accion animacion duracion transicion resolucion
    traduccion correccion posicion precision decision edicion cancion razon
    region saturacion iluminacion configuracion informacion deteccion
    seleccion direccion suscripcion retencion atencion intencion
    explicacion expresion impresion tension pasion vision mision ocasion
    presion revision television
    energia energias musica dia dias sabado
    frances ingles aleman japones portugues arabe hungaro
    pequeno pequena pequenos pequenas tamano tamanos senal senales espanol
    enfasis exito exitos numero telefono parametro parametros
    estan sera seran hara haran podra podran vera veran quedara quedaran
    """.split()

# Y las que hay que dejar en paz, porque la version sin tilde tambien existe:
#   esta/está  solo/sólo  aun/aún  el/él  tu/tú  mi/mí  si/sí  se/sé  de/dé
#   mas/más    este/éste  ano/año (el segundo no sale en esta interfaz)
# Y tampoco van los plurales de la familia -cion / -sion / -on, que PIERDEN la
# tilde al pasar al plural porque cambia la silaba fuerte: transiciones,
# ediciones, opciones, botones, razones. Estaban al principio y sacaron cinco
# falsos positivos a la primera pasada.
# No estan en la lista de arriba a proposito, y no se anaden.

RX = re.compile(r"\b(%s)\b" % "|".join(PELADAS), re.IGNORECASE)


def textos_del_motor():
    """Todo lo que el motor le dice a una persona, en castellano."""
    argv, sys.argv = sys.argv, ["test"]
    import server  # noqa: E402
    sys.argv = argv
    for nombre in ("TEXT", "CANNOT_WHY", "SETTING_WORDS", "ASK_WORDS",
                   "TRANSITION_LABELS", "RATIO_LABELS", "CUT_LABELS", "DEED_WORDS"):
        tabla = getattr(server, nombre, None)
        if not isinstance(tabla, dict):
            continue
        for clave, valor in (tabla.get("es") or {}).items():
            if isinstance(valor, str):
                yield ("motor.%s" % nombre, clave, valor)
            elif isinstance(valor, (list, tuple)):
                for v in valor:
                    if isinstance(v, str):
                        yield ("motor.%s" % nombre, clave, v)
    for clave, valor in (getattr(server, "OUTPUT_WORDS", None) or {}).items():
        yield ("motor.OUTPUT_WORDS", clave, valor)


def textos_de_catalogos():
    """Los nombres y las notas que se pintan en la galeria y en los ajustes."""
    import captions
    import looks
    import overlays
    import providers
    import speech

    def suelta(origen, items):
        for x in items:
            yield (origen, x.get("id", "?"), x.get("label", ""))
            yield (origen, x.get("id", "?"), x.get("note", ""))

    yield from suelta("captions", captions.preset_list("es"))
    yield from suelta("anims", captions.anim_list("es"))
    yield from suelta("looks", looks.catalogue("es"))
    yield from suelta("overlays", overlays.kind_list("es"))
    for pid, p in providers.PROVIDERS.items():
        nota = p.get("note")
        yield ("providers", pid, p.get("label") or "")
        yield ("providers", pid,
               nota.get("es", "") if isinstance(nota, dict) else (nota or ""))
    for eid, e in speech.ENGINES.items():
        nota = e.get("note")
        yield ("speech", eid, str(e.get("label") or ""))
        yield ("speech", eid,
               str(nota.get("es", "") if isinstance(nota, dict) else (nota or "")))


def textos_de_la_ventana():
    """El bloque español de i18n.tsx, leido como texto.

    Sin parsear TypeScript: son lineas `"clave": "valor",` y con eso basta. Si
    algun dia dejan de serlo, este caso se queda sin nada que mirar y lo dice
    el contador, que es mejor que fingir que todo esta bien.
    """
    ruta = RAIZ / "app" / "src" / "i18n.tsx"
    if not ruta.exists():
        return
    dentro = False
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.startswith("const es = {"):
            dentro = True
            continue
        if linea.startswith("const en"):
            break
        if not dentro:
            continue
        m = re.match(r'\s*"([^"]+)":\s*"(.*)",\s*$', linea)
        if m:
            yield ("ventana", m.group(1), m.group(2))


def casos():
    """Cada caso devuelve (nombre, lo que salio, lo que tenia que salir)."""
    n = 0
    for origen, clave, texto in list(textos_del_motor()) + \
            list(textos_de_catalogos()) + list(textos_de_la_ventana()):
        if not texto:
            continue
        n += 1
        malas = sorted(set(m.group(0).lower() for m in RX.finditer(texto)))
        yield ("%s[%s]" % (origen, clave), malas, [])
    # Y que de verdad haya mirado algo: si un cambio de formato deja las tres
    # fuentes vacias, este caso lo canta en vez de pasar en verde con cero
    # comprobaciones, que es la forma mas silenciosa de romper una prueba.
    yield ("ha mirado bastantes textos", n > 200, True)


def main():
    mal, n = [], 0
    for nombre, got, want in casos():
        n += 1
        if got != want:
            mal.append("%s: sin tilde -> %s" % (nombre, ", ".join(got)
                                                if isinstance(got, list) else got))
    if mal:
        print("%d de %d textos MAL:\n" % (len(mal), n))
        for line in mal:
            print("  - %s" % line)
        return 1
    print("%d textos, todos con sus tildes." % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
