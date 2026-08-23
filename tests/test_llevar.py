"""Un estilo copiado se puede llevar a otra maquina sin que llegue mintiendo.

Exportar es facil y no es la parte interesante. La parte interesante es
IMPORTAR, porque un archivo de estilo lo puede haber escrito cualquiera y
llegar por correo o por un chat: es contenido de fuera, sin credenciales, y se
trata como tal. La regla de la casa es lista blanca, no lista negra: se parte
de nada y solo entra lo que se reconoce.

Lo que se comprueba aqui, y por que cada cosa:

  - la ida y vuelta conserva lo MEDIDO. Si no, exportar seria una forma cara de
    perder justo lo que costo sacar del video.
  - lo que vuelve RENDERIZA por los dos caminos, el ASS del MP4 y el comp de
    Fusion. Un estilo que entra en la galeria y revienta al pintar esta roto en
    el unico momento en que se nota.
  - el `id` NUNCA sale del archivo. Uno de fuera podria pisar un estilo que ya
    tienes, y ese id acaba en nombres de archivo de la cache y en una linea de
    comandos.
  - los presets de la casa siguen intactos despues de importar. Un archivo que
    dice llamarse `pop` no puede cambiar el `pop` de nadie.
  - un numero imposible cae a la plantilla Y SE CAE DE LA LISTA DE MEDIDO. Esto
    ultimo es la mitad que importa: heredar el numero de la plantilla y seguir
    diciendo que esta medido es la mentira que este proyecto lleva una semana
    quitando.
  - un `None` a proposito SI cuenta como medido. "Este video no lleva contorno"
    es un hallazgo, no un hueco, y es lo que mas se nota al reconstruir.
  - las tuplas cortas se rechazan. `outline` son CUATRO numeros: guardar tres
    no revienta al guardar, revienta al renderizar, o sea despues, con el
    usuario mirando una pantalla que decia que todo habia ido bien.
  - un archivo roto, ajeno o inexistente se rechaza sin lanzar.

Se recorren LOS DIEZ presets como base: probar un subconjunto ya costo dos
regresiones en un dia.

No necesita ffmpeg ni red. Escribe en un APPDATA temporal, nunca en el de
verdad.

Se lanza:  python tests/test_llevar.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "skill" / "helpers"))

CASA = Path(tempfile.mkdtemp(prefix="vidorq_llevar_"))
os.environ["APPDATA"] = str(CASA)
(CASA / "Vidorq" / "workspaces" / "Principal").mkdir(parents=True)

import captions as cap        # noqa: E402
import galeria                # noqa: E402

FUERA = CASA / "sueltos"
FUERA.mkdir()

TRANSCRIPCION = {"segments": [{"start": 0.0, "end": 1.6, "words": [
    {"w": "UNA", "s": 0.0, "e": 0.5},
    {"w": "DE", "s": 0.5, "e": 0.9},
    {"w": "CADA", "s": 0.9, "e": 1.6}]}]}


def _pinta(eid):
    """Renderiza el estilo por los dos caminos. Devuelve el fallo o None.

    Los dos, y no solo el ASS, porque son dos renderizadores distintos. Un
    estilo que pinta en uno y revienta en el otro esta roto a medias.
    """
    try:
        trozos = cap.build_chunks(TRANSCRIPCION, eid, 1080, 1920)
        ass = FUERA / (eid + ".ass")
        cap.to_ass(ass, trozos, 0.0, 2.0, 1080, 1920, eid)
        comp = FUERA / (eid + ".comp")
        cap.to_comp(comp, trozos[0], 1080, 1920, 48, eid)
        if not ass.exists() or not comp.exists():
            return "no escribio uno de los dos"
    except Exception as e:
        return "%s: %s" % (type(e).__name__, e)
    return None


def _sobre(comp, nombre):
    """Deja un archivo de estilo en el disco y lo importa. Devuelve el id."""
    f = FUERA / "sobre.json"
    f.write_text(json.dumps({"que": galeria.SELLO, "formato": galeria.FORMATO,
                             "componente": comp},
                            default=str, ensure_ascii=False),
                 encoding="utf-8")
    return galeria.importar(f, nombre)


def main():
    fallos, total = [], 0
    try:
        # 1) Ida y vuelta sobre LOS DIEZ presets, con medidas encima.
        sub = {"y": 0.611, "size": 0.097, "fill": (0.92, 0.85, 0.11),
               "outline": (0.05, 0.04, 0.06)}
        for pid in cap.PRESETS:
            total += 1
            comp = galeria.caption_de(sub, pid, "Base " + pid)
            eid = galeria.guardar(comp)
            suelto = FUERA / (pid + ".json")
            if galeria.exportar(eid, suelto) is None or not suelto.exists():
                fallos.append("%s: exportar no dejo archivo" % pid)
                continue
            vuelto = galeria.importar(suelto, "Vuelto " + pid)
            if not vuelto:
                fallos.append("%s: no se pudo importar lo que acabo de salir" % pid)
                continue
            v = galeria.uno(vuelto)
            if tuple(v["fill"]) != tuple(comp["fill"]):
                fallos.append("%s: el color no sobrevivio al viaje" % pid)
            if v["size"] != comp["size"] or v["y"] != comp["y"]:
                fallos.append("%s: tamaño o altura cambiaron al viajar" % pid)
            if sorted(v["medido"]) != sorted(comp["medido"]):
                fallos.append("%s: la lista de medido cambio al viajar" % pid)

            total += 1
            mal = _pinta(vuelto)
            if mal:
                fallos.append("%s: lo importado no pinta (%s)" % (pid, mal))

        # 2) El id NUNCA sale del archivo, y los presets de casa no se tocan.
        base = dict(cap.PRESETS["pop"], base="pop")
        for intento in ("pop", "../../../fuera", "propio-del-short", ""):
            total += 1
            eid = _sobre(dict(base, id=intento), "Intruso")
            if eid == intento:
                fallos.append("el id del archivo se uso tal cual: %r" % intento)
            if eid and not galeria.es_propio(eid):
                fallos.append("un id importado sin el prefijo: %r" % eid)
        total += 1
        if cap.PRESETS["pop"]["size"] != 0.115:
            fallos.append("importar cambio el preset 'pop' de la casa")

        # 3) Un numero imposible cae a la plantilla y SE CAE DE MEDIDO.
        imposibles = [
            ("size", 40), ("size", -1), ("y", 99), ("fill", ("rojo", 0.2, 0.3)),
            ("tracking", 1e9), ("size", float("nan")),
        ]
        for campo, valor in imposibles:
            total += 1
            crudo = dict(base, medido=[campo], **{campo: valor})
            v = galeria.uno(_sobre(crudo, "Imposible %s" % campo))
            if not v:
                fallos.append("%s=%r tumbo la importacion entera" % (campo, valor))
                continue
            if campo in v["medido"]:
                fallos.append("%s=%r se guardo y ademas dice estar medido"
                              % (campo, valor))
            if v[campo] != cap.PRESETS["pop"][campo]:
                fallos.append("%s=%r no cayo a la plantilla (quedo %r)"
                              % (campo, valor, v[campo]))

        # 4) Un None a proposito SI es una medida.
        total += 1
        v = galeria.uno(_sobre(dict(base, outline=None, medido=["outline"]),
                               "Sin contorno"))
        if not v or v["outline"] is not None:
            fallos.append("un contorno medido como ausente no se respeto")
        elif "outline" not in v["medido"]:
            fallos.append("'no lleva contorno' dejo de contar como medido")

        # 5) Tuplas cortas: se rechazan, no se rellenan.
        for campo, corta in (("outline", (0.1, 0.2, 0.3)),
                             ("shadow", (0.1, 0.2, 0.3)),
                             ("glow", (0.1, 0.2)),
                             ("panel", (0.1, 0.2, 0.3, 0.4))):
            total += 1
            v = galeria.uno(_sobre(dict(base, medido=[campo], **{campo: corta}),
                                   "Corto %s" % campo))
            if v and v[campo] is not None and len(v[campo]) == len(corta):
                fallos.append("%s se guardo con %d numeros" % (campo, len(corta)))
            total += 1
            if v and campo in v["medido"]:
                fallos.append("%s corto sigue diciendo que esta medido" % campo)

        # 6) Texto de fuera: sin caracteres de control, y con tope.
        total += 1
        v = galeria.uno(_sobre(base, "Ma\x00lo\x1b[31m" + "x" * 90))
        if not v:
            fallos.append("un nombre raro tumbo la importacion")
        else:
            et = v["label"]["es"]
            if any(ord(c) < 32 or ord(c) == 127 for c in et):
                fallos.append("quedaron caracteres de control en la etiqueta")
            if len(et) > 40:
                fallos.append("la etiqueta no respeta el tope de 40")
        total += 1
        v = galeria.uno(_sobre(dict(base, font='Ari"al\\evil', style="B\x00d"),
                               "Fuente rara"))
        if v and ('"' in v["font"] or "\\" in v["font"]):
            fallos.append("la fuente conservo comillas o barras: %r" % v["font"])

        # 7) Archivos que no valen. Ninguno puede lanzar.
        malos = []
        f = FUERA / "roto.json"
        f.write_text("no soy json {{{", encoding="utf-8")
        malos.append(("json roto", f))
        f2 = FUERA / "sinsello.json"
        f2.write_text(json.dumps({"componente": base}), encoding="utf-8")
        malos.append(("sobre sin sello", f2))
        f3 = FUERA / "sello_ajeno.json"
        f3.write_text(json.dumps({"que": "otro/programa", "componente": base}),
                      encoding="utf-8")
        malos.append(("sello de otro", f3))
        f4 = FUERA / "lista.json"
        f4.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        malos.append(("una lista", f4))
        malos.append(("no existe", FUERA / "no_esta.json"))
        for nombre, ruta in malos:
            total += 1
            try:
                if galeria.importar(ruta) is not None:
                    fallos.append("%s se acepto" % nombre)
            except Exception as e:
                fallos.append("%s lanzo %s" % (nombre, type(e).__name__))

        # 8) Exportar algo que no esta no lanza, devuelve None.
        total += 1
        try:
            if galeria.exportar("propio-no-existe", FUERA / "nada.json") is not None:
                fallos.append("exportar un id inexistente devolvio algo")
        except Exception as e:
            fallos.append("exportar un id inexistente lanzo %s" % type(e).__name__)

        if fallos:
            print("%d de %d casos MAL:\n" % (len(fallos), total))
            for line in fallos:
                print("  - %s" % line)
            return 1
        print("%d casos, un estilo viaja sin perder lo medido ni ganar mentiras."
              % total)
        return 0
    finally:
        shutil.rmtree(CASA, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
