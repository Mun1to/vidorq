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
