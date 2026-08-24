"""Comprueba dentro de Resolve que un subtitulo sale con un color POR PALABRA.

Por que existe. Esto se dio por imposible durante dos dias, y lo que lo desatono
fue mirar un fotograma de verdad: el estilo por caracteres no es un campo del
`Text+`, es el operador `StyledTextCLS` colgado de su entrada `StyledText`
(`docs/FUSION.md` lo cuenta entero). Ese baile de "monta el comp, importalo,
vete a Color, saca el fotograma y mira" se hizo TRES veces a mano en una noche,
asi que se automatiza: a la tercera se automatiza (regla W).

Lo que hace, sin tocar nada tuyo: crea su propio timeline `PruebaVidorqCLS`, le
mete un titulo, le importa un comp con tres palabras de tres colores, saca el
fotograma por la pagina de Color y lo deja en un PNG. La unica parte que no
puede hacer un programa es la ultima, mirar el PNG, y por eso dice donde esta.

    ANTES DE LANZARLO
    1. Abre DaVinci Resolve y entra en un proyecto (vale uno nuevo vacio).
    2. Dentro de Resolve: Workspace > Scripts > Vidorq.
    3. Aqui:  python resolve/comprobar_cls.py

    Y para dejarlo como estaba:  python resolve/comprobar_cls.py --limpiar
    (borra el timeline que creo; se le pueden dar mas nombres detras).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ / "engine"))
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))

TIMELINE = "PruebaVidorqCLS"
ALBUM = "PruebaVidorqCLS"
# Tres palabras y tres colores que no se parecen entre si ni al blanco, para que
# un vistazo baste. El amarillo y el verde son los del preset `marker`.
TROZO = {
    "start": 0.0, "end": 2.0, "text": "ESTO SI PINTA",
    "words": [
        {"w": "ESTO", "s": 0.0, "e": 0.6},
        {"w": "SI", "s": 0.6, "e": 1.1, "color": (1.0, 0.85, 0.10)},
        {"w": "PINTA", "s": 1.1, "e": 2.0, "color": (0.10, 0.95, 0.55)},
    ],
}


def falta(que, arreglo):
    print("\n  FALTA: %s" % que)
    print("  %s\n" % arreglo)
    return 1


def limpiar(server, nombres):
    """Borra los timelines de prueba. Un timeline vive en el media pool como un
    clip mas, asi que se borra por su nombre igual que cualquier otro."""
    r = server.bridge_post("/mediapool/clips/delete", {"clipNames": nombres}) or {}
    if r.get("error"):
        print("  no se pudieron borrar: %s" % r["error"])
        return 1
    print("  borrados: %d   sin encontrar: %s"
          % (r.get("deleted", 0), ", ".join(r.get("notFound") or []) or "ninguno"))
    return 0


def main(argv):
    import captions as cap
    # `server` mira `sys.argv` al importarse, y aqui detras vienen nuestros
    # propios argumentos: sin esto, `--limpiar` acaba en su parser.
    guardado, sys.argv = sys.argv, [sys.argv[0]]
    import server
    sys.argv = guardado

    if "--limpiar" in argv:
        otros = [a for a in argv[1:] if not a.startswith("--")]
        return limpiar(server, otros or [TIMELINE])

    print("Comprobando el color por palabra dentro de Resolve.\n")
    estado = server.bridge_status() or {}
    if not estado.get("bridge"):
        if not estado.get("app"):
            return falta("DaVinci Resolve no esta abierto.",
                         "Abrelo y entra en un proyecto, aunque este vacio.")
        return falta("Resolve esta abierto pero el puente no.",
                     "Dentro de Resolve: Workspace > Scripts > Vidorq.")
    if not estado.get("project"):
        return falta("El puente responde pero no hay ningun proyecto abierto.",
                     "Entra en un proyecto de Resolve, aunque sea uno nuevo.")
    print("  puente: si    proyecto: %s" % estado.get("project"))

    casa = Path(tempfile.mkdtemp(prefix="vidorq_cls_"))
    comp = casa / "cls.comp"
    cap.to_comp(comp, TROZO, 1920, 1080, 48, "pop")
    if "StyledTextCLS" not in comp.read_text(encoding="utf-8"):
        return falta("el comp salio SIN el modificador",
                     "mira `_tramos` en skill/helpers/captions.py: el texto "
                     "tiene que reconstruirse juntando las palabras")
    print("  comp escrito, con su modificador dentro")

    # Su propio timeline, para no descolocar el tuyo: un titulo insertado cae
    # siempre en V1 y hace ripple, asi que aqui no puede caer en tu edicion.
    r = server.bridge_post("/timeline/create", {"name": TIMELINE}) or {}
    if r.get("error"):
        return falta("no pude crear el timeline de prueba: %s" % r["error"],
                     "si ya existe uno con ese nombre, lanza --limpiar antes")
    r = server.bridge_post("/title/insert",
                           {"titleName": "Text+", "fusionTitle": True}) or {}
    if not r.get("success"):
        return falta("no pude insertar el titulo: %s" % r.get("error", "?"),
                     "comprueba que Resolve tiene el titulo 'Text+'")
    r = server.bridge_post("/clip/fusion/import",
                           {"clipIndex": 0, "path": str(comp)}) or {}
    if not r.get("success"):
        return falta("no pude importar el comp: %s" % r.get("error", "?"),
                     "el clipIndex empieza en 0, no en 1")
    print("  titulo insertado y comp importado")

    # Un album propio, o el fotograma se pierde entre los que ya tuvieras.
    server.bridge_post("/gallery/album/create", {"name": ALBUM})
    server.bridge_post("/page", {"page": "color"})
    grab = server.bridge_post("/gallery/grab", {}) or {}
    salida = {}
    if grab.get("success"):
        albums = (server.bridge_get("/gallery/albums") or {}).get("stillAlbums") or []
        mio = [a["index"] for a in albums if a.get("name") == ALBUM]
        salida = server.bridge_post("/gallery/stills/export", {
            "albumIndex": mio[-1] if mio else 0, "folderPath": str(casa),
            "filePrefix": "cls", "format": "png"}) or {}
    server.bridge_post("/page", {"page": "edit"})

    pngs = sorted(casa.glob("cls*.png"))
    if not grab.get("success") or salida.get("error") or not pngs:
        print("\n  El comp esta puesto, pero no pude sacarte el fotograma solo.")
        print("  Miralo en Resolve: timeline '%s', doble clic en el clip." % TIMELINE)
        return 1

    print("\n  FOTOGRAMA: %s" % pngs[-1])
    print("""
  ABRELO Y MIRA. Tienen que verse las tres palabras de tres colores:

    1. ESTO   en BLANCO
    2. SI     en AMARILLO
    3. PINTA  en VERDE

  Si salen las tres blancas, el modificador no esta pintando y hay que volver a
  `docs/FUSION.md`. Si sale una sola palabra de color y las otras dos mal
  cortadas, el fallo esta en los indices de `_tramos`, que cuenta caracteres.

  Para dejarlo como estaba:  python resolve/comprobar_cls.py --limpiar
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
