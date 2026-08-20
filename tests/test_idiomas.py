"""Que no se le quede nada a medio traducir.

Vidorq habla dos idiomas en dos sitios distintos, y solo uno de los dos tiene
red debajo:

- En la ventana, `i18n.tsx` declara el ingles como `Record<keyof typeof es,
  string>`, asi que una clave que falte NO compila. Aqui se comprueba igual lo
  que TypeScript no mira: una frase que se copio del castellano y se quedo sin
  traducir se ve igual de mal, y compila perfectamente.

- En el motor no hay nadie mirando. `TEXT[lang].get(key, key)` devuelve la
  CLAVE cuando no encuentra la frase, asi que a un usuario en ingles le sale
  `no_speech` en la pantalla en vez de una frase. Sin error, sin traza y sin
  que nadie se entere hasta que lo ve.

Se lanza:  python tests/test_idiomas.py
"""
import io
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))
sys.path.insert(0, str(RAIZ / "engine"))

# Las tablas del motor que llevan un idioma en la primera llave.
TABLAS = ("TEXT", "CANNOT_WHY", "SETTING_WORDS", "ASK_WORDS",
          "TRANSITION_LABELS", "RATIO_LABELS", "CUT_LABELS", "DEED_WORDS")

# Frases que son la MISMA en los dos idiomas a proposito. Nombres propios,
# formatos y palabras que se escriben igual: traducirlas seria el error.
IGUALES_A_POSTA = {
    "MP4", "Resolve", "Vidorq", "Ollama", "DaVinci Resolve", "Pop", "Punch",
    "Minimal", "Mono", "Halo", "Neon", "Podcast", "9:16", "16:9", "1:1", "4:5",
}

PAR = re.compile(r'\n  "([^"]+)":\s*"((?:[^"\\]|\\.)*)"')


def bloques_de_la_ventana():
    """Los dos diccionarios de i18n.tsx, leidos como texto."""
    ruta = RAIZ / "app" / "src" / "i18n.tsx"
    if not ruta.exists():
        return {}, {}
    s = io.open(ruta, encoding="utf-8").read()

    def uno(nombre):
        m = re.search("^const " + nombre + "[^{]*{", s, re.M)
        if not m:
            return {}
        return dict(PAR.findall(s[m.start():s.index("\n};", m.start())]))

    return uno("es"), uno("en")


# Lo que se le enseña a una persona sale de una tabla con sus dos idiomas. Estas
# son las llamadas que se saltan la tabla y llevan la frase escrita dentro.
#
# Se lee la llamada ENTERA, con los parentesis contados, y no partiendola por
# comas: el segundo argumento suele ser algo como `min(32, 10 + int(...))`, que
# lleva comas dentro, y ahi es donde se escondia la ultima que quedaba.
CADENA = re.compile(r'"((?:[^"\\]|\\.)*)"')

# Plantillas puras (solo huecos y puntuacion) y palabras que se escriben igual
# en los dos idiomas: esas no son frases y no hay nada que traducir.
NO_ES_FRASE = re.compile(r"^[\s%sdfgx.,:;/|()\[\]0-9+-]*$")


def llamadas(texto, nombre="set_progress("):
    """Cada llamada a esa funcion, del parentesis que abre al que cierra."""
    i = 0
    while True:
        i = texto.find(nombre, i)
        if i < 0:
            return
        j = i + len(nombre) - 1
        hondo, fin = 0, None
        for k in range(j, min(len(texto), j + 4000)):
            if texto[k] == "(":
                hondo += 1
            elif texto[k] == ")":
                hondo -= 1
                if hondo == 0:
                    fin = k
                    break
        yield texto[i:(fin + 1) if fin else j + 200]
        i = j + 1


def sin_las_claves(llamada):
    """La llamada sin sus `tr(...)`, que solo llevan claves de la tabla.

    Se quitan enteras y no con un patron: dentro de un `tr()` puede haber otra
    llamada (`tr("no_look", str(e)[:120])`), y contar parentesis es lo unico
    que acierta con eso.
    """
    for nombre in ("tr(", "tr_in("):
        while True:
            i = llamada.find(nombre)
            # Solo si es la funcion y no el final de otra palabra ("_tr(").
            if i < 0 or (i and (llamada[i - 1].isalnum() or llamada[i - 1] == "_")):
                if i < 0:
                    break
                # Salta esta aparicion y sigue buscando mas adelante.
                resto = sin_las_claves(llamada[i + len(nombre):])
                return llamada[:i + len(nombre)] + resto
            hondo, fin = 0, None
            for k in range(i + len(nombre) - 1, len(llamada)):
                if llamada[k] == "(":
                    hondo += 1
                elif llamada[k] == ")":
                    hondo -= 1
                    if hondo == 0:
                        fin = k
                        break
            if fin is None:
                break
            llamada = llamada[:i] + llamada[fin + 1:]
    return llamada


def frases_a_mano():
    """Las frases que van a la pantalla sin pasar por TEXT."""
    ruta = RAIZ / "engine" / "server.py"
    if not ruta.exists():
        return []
    texto = io.open(ruta, encoding="utf-8").read()
    fuera = []
    for llamada in llamadas(texto):
        for m in CADENA.finditer(sin_las_claves(llamada)):
            frase = m.group(1)
            if len(frase) >= 10 and not NO_ES_FRASE.match(frase):
                fuera.append('"%s"' % frase)
    return sorted(set(fuera))


def casos():
    """Cada caso devuelve (nombre, lo que salio, lo que tenia que salir)."""
    argv, sys.argv = sys.argv, ["test"]
    import server  # noqa: E402
    sys.argv = argv

    mirados = 0
    for nombre in TABLAS:
        tabla = getattr(server, nombre, None)
        if not isinstance(tabla, dict) or "es" not in tabla:
            yield ("motor.%s existe y va por idioma" % nombre, False, True)
            continue
        es, en = set(tabla.get("es") or {}), set(tabla.get("en") or {})
        mirados += len(es)
        yield ("motor.%s: claves sin ingles" % nombre, sorted(es - en), [])
        yield ("motor.%s: claves solo en ingles" % nombre, sorted(en - es), [])

    es, en = bloques_de_la_ventana()
    yield ("ventana: claves sin ingles", sorted(set(es) - set(en)), [])
    yield ("ventana: claves solo en ingles", sorted(set(en) - set(es)), [])

    # Una frase larga identica en los dos idiomas es castellano sin traducir.
    # Las cortas no cuentan: "MP4" o "Pop" se escriben igual en todas partes.
    copiadas = sorted(k for k in es
                      if k in en and es[k] == en[k] and len(es[k]) > 12
                      and es[k] not in IGUALES_A_POSTA)
    yield ("ventana: frases sin traducir", copiadas, [])

    yield ("ninguna frase de pantalla escrita a mano", frases_a_mano(), [])

    # Y que de verdad haya mirado algo, para que un cambio de formato no deje
    # la prueba en verde sin comprobar nada.
    yield ("ha mirado las tablas del motor", mirados > 80, True)
    yield ("ha mirado los textos de la ventana", len(es) > 150, True)


def main():
    mal, n = [], 0
    for nombre, got, want in casos():
        n += 1
        if got != want:
            mal.append("%s -> %s" % (nombre, ", ".join(got)
                                     if isinstance(got, list) else got))
    if mal:
        print("%d de %d comprobaciones MAL:\n" % (len(mal), n))
        for linea in mal:
            print("  - %s" % linea)
        return 1
    print("%d comprobaciones, los dos idiomas completos." % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
