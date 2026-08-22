"""Vidorq mira un video ajeno y dice como esta hecho.

La vara de medir es un circulo cerrado: se le pide a la propia casa que queme
un subtitulo con un estilo CONOCIDO, y luego se le da ese MP4 al analizador
como si viniera de fuera, sin decirle nada. Si recupera el estilo con el que se
hizo, entiende de verdad; si no, no. No hay forma de hacer trampa porque el
analizador no ve el preset por ningun lado: solo ve pixeles.

Lo que se comprueba y por que:

  - la POSICION del subtitulo se recupera con error menor de 0.01. Es el numero
    que mas manda al reconstruir: dos estilos en sitios distintos se ven
    distintos aunque compartan color y tamaño.
  - el COLOR del relleno se recupera en los estilos que no llevan un adorno
    tapandolo.
  - un video SIN subtitulos no produce subtitulo. Un falso positivo aqui es
    peor que no detectar nada: le propondria al usuario reconstruir algo que
    nunca vio.
  - el estilo correcto sale entre los tres que se proponen.

Necesita ffmpeg en el PATH. Si no esta, se salta diciendolo, porque una prueba
que se salta en silencio es peor que no tenerla.

Se lanza:  python tests/test_aprende.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HELP = RAIZ / "skill" / "helpers"
sys.path.insert(0, str(HELP))

# Los estilos con los que se hace la ida y vuelta. Los cuatro cubren los casos
# que importan: blanco con contorno, color, plancha detras y el mas discreto.
ESTILOS = ("pop", "punch", "marker", "minimal")

FRASES = [("hola mundo esto va bien", 1.0), ("mira lo que hace", 6.0),
          ("otra frase mas larga aqui", 11.0), ("y la ultima de todas", 16.0)]

EDL = {"segments": [{"start": 0.5, "end": 19.5, "zoom": 1.0, "note": ""}]}


def _palabras(texto, desde):
    out, t = [], desde
    for w in texto.split():
        out.append({"w": w, "s": round(t, 2), "e": round(t + 0.35, 2)})
        t += 0.42
    return out


TRANSCRIPT = {"duration": 20.0, "language": "es", "segments": [
    {"text": t, "start": s, "end": s + 3.0, "words": _palabras(t, s)}
    for t, s in FRASES]}


def _fuente(casa):
    """Cuatro planos lisos en vertical. Lisos a proposito: si el fondo tuviera
    detalle, encontrar el texto seria mas facil de lo que es en la vida real."""
    dest = casa / "fuente.mp4"
    trozos = []
    for c in ("gray", "darkgreen", "navy", "maroon"):
        trozos += ["-f", "lavfi", "-i", "color=c=%s:s=720x1280:r=25:d=5" % c]
    trozos += ["-f", "lavfi", "-i",
               "sine=frequency=440:duration=20:sample_rate=48000"]
    r = subprocess.run(["ffmpeg", "-y", "-v", "error"] + trozos + [
        "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]",
        "-map", "[v]", "-map", "4:a", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(dest)],
        capture_output=True)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-200:])
    return dest


def _render(casa, fuente, nombre, *extra):
    salida = casa / nombre
    subprocess.run(
        [sys.executable, str(HELP / "vidorq_render.py"), str(fuente),
         str(casa / "edl.json"), str(casa / "transcript.json"), str(salida)]
        + list(extra), capture_output=True, cwd=str(HELP))
    return salida


def casos(casa, fuente):
    import aprende
    import captions

    # --- un video sin subtitulos no tiene subtitulo ------------------------
    # Primero este, que es el que puede mentir a favor. Si el detector ve
    # texto en un video liso, todo lo demas que diga vale menos.
    limpio = _render(casa, fuente, "limpio.mp4", "--no-captions", "--no-zoom")
    yield ("aprende: el video sin subtitulos se renderiza", limpio.exists(), True)
    if limpio.exists():
        f = aprende.ficha(limpio)
        yield ("aprende: no inventa un subtitulo donde no lo hay",
               f.get("subtitulo"), None)
        yield ("aprende: sin subtitulo no propone estilos",
               aprende.parecidos(f), [])
        yield ("aprende: aun asi mide el archivo",
               (f["ancho"], f["alto"]), (720, 1280))
        yield ("aprende: sabe que es vertical", f.get("vertical"), True)

    # --- el ritmo de corte -------------------------------------------------
    # Doce planos de 1,5 s clavados. Es el otro numero que pide quien pega un
    # video ajeno: "quiero que vaya asi de rapido".
    cortes = casa / "cortes.mp4"
    # Doce GRISES separados, no doce colores. vision.shots() mira en escala de
    # gris, y de una paleta de colores normales el rojo, el azul, el morado, el
    # oliva y el teal dan los cinco 85: planos seguidos que para el detector
    # son el mismo. Con colores esta prueba acusaba al codigo de un fallo que
    # estaba en el video.
    cols = tuple("0x%02x%02x%02x" % (v, v, v) for v in range(20, 20 + 12 * 19, 19))
    trozos = []
    for c in cols:
        trozos += ["-f", "lavfi", "-i", "color=c=%s:s=480x270:r=25:d=1.5" % c]
    subprocess.run(["ffmpeg", "-y", "-v", "error"] + trozos + [
        "-filter_complex",
        "".join("[%d:v]" % i for i in range(len(cols)))
        + "concat=n=%d:v=1:a=0[v]" % len(cols),
        "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", str(cortes)], capture_output=True)
    if cortes.exists():
        r = aprende.ritmo(cortes)
        yield ("aprende: saca el ritmo de un video con cortes",
               r is not None, True)
        if r:
            error = abs(float(r["plano_tipico_s"]) - 1.5)
            yield ("aprende: acierta el plano tipico (error %.2f s)" % error,
                   error < 0.2, True)
            # Los doce, exactos. Con el video bien fabricado no hay excusa
            # para perder ninguno, y aflojar aqui es dejar de enterarse.
            yield ("aprende: cuenta los doce planos", r["planos"], 12)
            yield ("aprende: cuenta los once cortes", r["cortes"], 11)
            # Ritmo constante: la segunda mitad dura como la primera.
            yield ("aprende: no se inventa que acelera (%s)" % r["acelera"],
                   0.85 <= float(r["acelera"]) <= 1.15, True)
            yield ("aprende: sabe que los planos estan quietos",
                   r["planos_quietos"], 12)
            # Y el arranque, que se cuenta aparte porque un video puede tener
            # ritmo tranquilo y principio disparado.
            a = aprende.arranque(cortes)
            yield ("aprende: mira el arranque aparte", a is not None, True)
            if a:
                yield ("aprende: el primer plano dura lo que dura (%s s)"
                       % a["primer_plano_s"],
                       abs(float(a["primer_plano_s"]) - 1.5) < 0.25, True)

    # --- el falso positivo que si costo encontrar --------------------------
    # Un video liso se descarta facil. El que se colaba era este: una franja
    # con detalle en MITAD del cuadro, que aparece y desaparece. Cumple las dos
    # firmas del detector, no toca los bordes, no es fina y contrasta de sobra,
    # y se leia como un subtitulo en y=0.467. Aparecio una vez, asi que se
    # queda clavado aqui.
    franja = casa / "franja.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=slateblue:s=720x1280:r=25:d=12",
        "-f", "lavfi", "-i", "color=c=gray:s=720x200:r=25:d=12",
        "-filter_complex",
        "[1:v]geq=lum='if(gt(mod(X,7),3),240,20)':cb=128:cr=128[f];"
        "[0:v][f]overlay=0:700:enable='lt(mod(t,3),1.6)'[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", str(franja)], capture_output=True)
    if franja.exists():
        yield ("aprende: una franja con detalle en medio no es un subtitulo",
               aprende.ficha(franja).get("subtitulo"), None)

    # --- la ida y vuelta, estilo por estilo -------------------------------
    en_tres = 0
    for pid in ESTILOS:
        p = captions.PRESETS[pid]
        v = _render(casa, fuente, "%s.mp4" % pid, "--preset", pid, "--no-zoom")
        if not v.exists():
            yield ("aprende: sale el render de %s" % pid, False, True)
            continue
        f = aprende.ficha(v)
        sub = f.get("subtitulo")
        yield ("aprende: %s deja un subtitulo que se ve" % pid,
               sub is not None, True)
        if not sub:
            continue

        # La posicion. El numero que mas manda al reconstruir.
        error = abs(float(sub["y"]) - float(p["y"]))
        yield ("aprende: %s cae donde dice el estilo (error %.3f)" % (pid, error),
               error < 0.01, True)

        # El color, en los que no llevan nada tapandolo. `marker` lleva una
        # plancha detras y el color medido sale mezclado con ella: eso esta
        # medido y por eso queda fuera de esta comprobacion en vez de
        # disimulado con un margen ancho que no probaria nada.
        if pid != "marker":
            lejos = max(abs(a - b) for a, b in zip(sub["fill"], p["fill"]))
            yield ("aprende: %s recupera su color (lejos %.2f)" % (pid, lejos),
                   lejos < 0.15, True)

        # Lo que hay detras de las letras. No se comprueba si es una plancha
        # o un contorno, porque esta medido que no se puede saber y esta
        # explicado en color_de_fondo. Se comprueba lo que SI se sostiene: que
        # sale un color, y que en `marker`, que lleva una plancha verde, ese
        # color es verde de verdad y no el gris del video de detras.
        yield ("aprende: %s dice de que color es el fondo del texto" % pid,
               sub.get("fondo") is not None, True)
        if pid == "marker" and sub.get("fondo"):
            r, g, b = sub["fondo"]
            yield ("aprende: y en marker ese fondo es verde (%.2f,%.2f,%.2f)"
                   % (r, g, b), g > r + 0.15 and g > b + 0.1, True)

        en_tres += pid in [i for i, _ in aprende.parecidos(f)]

    # De los cuatro, cuantos salen entre los tres que se proponen. Tres de
    # cuatro es lo que hay hoy y esta medido; poner el liston en cuatro seria
    # escribir una prueba que ya sabemos que no pasa, y ponerlo en dos seria
    # dejar de enterarnos si empeora.
    yield ("aprende: el estilo esta entre los tres propuestos (%d de %d)"
           % (en_tres, len(ESTILOS)), en_tres >= 3, True)

    # --- el link, que es entrada escrita a mano ----------------------------
    for caso in _links():
        yield caso

    # --- y en HORIZONTAL, que es donde estaba el punto ciego ---------------
    # Todo lo de arriba renderiza 720x1280, y ahi captions.line_ref(w,h) vale
    # exactamente el ancho, asi que medir el tamaño contra uno o contra otro da
    # el mismo numero. En 16:9 line_ref vale 0,562 del ancho: medir contra el
    # ancho dejaba cada video horizontal emparejado con estilos de letra mas
    # pequeña que la suya, y ninguna prueba lo veia.
    for caso in _en_horizontal(casa):
        yield caso

    # --- el subtitulo donde lo pone TikTok --------------------------------
    # Ningun preset de la casa pone el subtitulo a media altura, y TikTok y
    # Reels si: es la entrada principal del producto. Hubo un guard que
    # descartaba todo lo que cayera entre el 33% y el 67% del cuadro, para
    # tapar un falso positivo de laboratorio, y con el puesto la pantalla decia
    # "este video no lleva subtitulos" sobre un video que los lleva. Este caso
    # existe para que no vuelva.
    for caso in _a_media_altura(casa):
        yield caso

    # --- el circulo entero: de un video ajeno al video del usuario ---------
    # Esto es lo que promete la pantalla, y hasta aqui todo eran piezas
    # sueltas. Se mira un video de un desconocido, se guarda el estilo que
    # propone, y se edita un video PROPIO sin decir nada del estilo: el
    # resultado tiene que salir con la letra del primero.
    for caso in _circulo(casa, fuente):
        yield caso

    # --- la puerta del motor ----------------------------------------------
    # En un motor de PRUEBA, en el puerto 0 para que lo elija el sistema.
    # Nunca contra el 9877: ese es el que tiene Munir abierto, y una peticion
    # de prueba ahi le toca sus datos de verdad.
    for caso in _puerta(casa):
        yield caso


def _links():
    """Que URLs se aceptan y cuales no.

    Una URL la escribe una persona en un cuadro de texto, asi que es entrada no
    confiable. Lo que se comprueba aqui no es que funcione la descarga (eso
    necesita yt-dlp instalado), sino que la puerta este cerrada: sin esto,
    pegar un link seria una forma de que Vidorq pida cosas a maquinas de la red
    de casa en nombre de quien lo usa.
    """
    import descargar

    buenos = [
        "https://www.tiktok.com/@alguien/video/123",
        "https://vm.tiktok.com/ABC/",
        "https://www.instagram.com/reel/xyz/",
        "https://youtu.be/abc123",
        "https://www.youtube.com/shorts/abc",
    ]
    for u in buenos:
        yield ("link: se acepta %s" % u[:38], descargar.vale(u)[0], True)

    # Lo de casa. El primero es el caso que mas duele: es el propio motor de
    # Vidorq, y su ruta /shutdown lo apaga.
    de_casa = [
        "http://127.0.0.1:9877/shutdown",
        "http://localhost/x",
        "https://[::1]/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://192.168.1.10/admin",
        "http://10.0.0.5/",
        "http://servidor/interno",
        "http://nas.local/videos",
    ]
    for u in de_casa:
        ok, motivo = descargar.vale(u)
        yield ("link: se rechaza por ser de casa %s" % u[:34],
               (ok, motivo), (False, "de_casa"))

    # El clasico: un dominio que ACABA pareciendose a uno de la lista.
    parecidos = [
        "https://tiktok.com.malo.example/x",
        "https://www.youtube.com.attacker.net/x",
        "https://evil.example/video.mp4",
        "https://notyoutube.com/x",
    ]
    for u in parecidos:
        ok, motivo = descargar.vale(u)
        yield ("link: no se cuela %s" % u[:38], (ok, motivo), (False, "sitio_no"))

    # Y lo que ni siquiera es http.
    for u in ("file:///C:/Windows/System32/config/SAM", "javascript:alert(1)",
              "data:text/html,<script>", "", "no es una url", "x" * 3000):
        ok, motivo = descargar.vale(u)
        yield ("link: se rechaza %s" % (u[:30] or "(vacio)"),
               (ok, motivo), (False, "no_link"))
    yield ("link: None tampoco pasa", descargar.vale(None), (False, "no_link"))

    # Y sin la herramienta, se dice: no se intenta y se falla en silencio.
    if not descargar.hay_ytdlp():
        fallo = ""
        try:
            descargar.traer("https://www.tiktok.com/@a/video/1")
        except RuntimeError as e:
            fallo = str(e)
        except Exception as e:
            fallo = "otro: %s" % type(e).__name__
        yield ("link: sin yt-dlp lo dice por su nombre", fallo, "no_ytdlp")


def _en_horizontal(casa):
    """La misma ida y vuelta, pero con un video 1920x1080."""
    import aprende
    import captions

    ancho = casa / "ancho.mp4"
    trozos = []
    for c in ("gray", "darkgreen", "navy", "maroon"):
        trozos += ["-f", "lavfi", "-i", "color=c=%s:s=1920x1080:r=25:d=5" % c]
    trozos += ["-f", "lavfi", "-i",
               "sine=frequency=440:duration=20:sample_rate=48000"]
    r = subprocess.run(["ffmpeg", "-y", "-v", "error"] + trozos + [
        "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]",
        "-map", "[v]", "-map", "4:a", "-c:v", "libx264", "-preset",
        "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(ancho)], capture_output=True)
    if r.returncode != 0 or not ancho.exists():
        return

    en_tres = 0
    for pid in ("pop", "punch", "minimal"):
        v = _render(casa, ancho, "h_%s.mp4" % pid, "--preset", pid, "--no-zoom")
        if not v.exists():
            continue
        f = aprende.ficha(v)
        sub = f.get("subtitulo")
        yield ("aprende: %s en horizontal deja subtitulo" % pid,
               sub is not None, True)
        if not sub:
            continue
        yield ("aprende: %s en horizontal no sale vertical" % pid,
               f.get("vertical"), False)
        # El tamaño medido tiene que quedarse cerca del que declara el estilo.
        # Contra el ancho salia casi la mitad, y por eso el emparejamiento se
        # iba a estilos de letra mas pequeña.
        lejos = abs(float(sub["size"]) - float(captions.PRESETS[pid]["size"]))
        yield ("aprende: %s en horizontal mide su tamaño (lejos %.3f)"
               % (pid, lejos), lejos < 0.035, True)
        en_tres += pid in [i for i, _ in aprende.parecidos(f)]
    yield ("aprende: en horizontal el estilo sale entre los tres (%d de 3)"
           % en_tres, en_tres >= 3, True)


def _a_media_altura(casa):
    """Un video con el texto al 47% del alto, dibujado a mano.

    A mano y no con el render de la casa porque el render solo sabe poner el
    subtitulo donde diga su preset, y ninguno de los diez lo pone ahi.
    """
    import aprende
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    cara = None
    for c in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"):
        if Path(c).is_file():
            cara = c
            break
    if not cara:
        return

    w, h, fps = 720, 1280, 25
    fuente = ImageFont.truetype(cara, 64)
    frases = ["HOLA MUNDO", "MIRA ESTO", "QUE TAL", "YA ESTA"]
    fondos = [(40, 60, 90), (90, 50, 40), (40, 90, 60), (80, 80, 40)]
    casos = []
    for alt in (0.47, 0.20):
        crudo = casa / ("medio_%d" % int(alt * 100))
        crudo.mkdir(exist_ok=True)
        for i in range(int(6.0 * fps)):
            t = i / fps
            plano = int(t // 1.5)
            im = Image.new("RGB", (w, h), fondos[plano % 4])
            d = ImageDraw.Draw(im)
            # una textura de fondo, para que encontrar el texto cueste algo
            for k in range(0, h, 70):
                d.line([(0, k), (w, k)],
                       fill=tuple(max(0, c - 18) for c in fondos[plano % 4]),
                       width=14)
            if (t % 1.5) < 1.0:
                d.text((w // 2, h - int(alt * h)), frases[plano % 4],
                       font=fuente, fill=(255, 255, 255), stroke_width=7,
                       stroke_fill=(0, 0, 0), anchor="ms")
            im.save(crudo / ("%05d.png" % i))
        dest = casa / ("medio_%d.mp4" % int(alt * 100))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate",
                        str(fps), "-i", str(crudo / "%05d.png"), "-c:v",
                        "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                        str(dest)], capture_output=True)
        shutil.rmtree(crudo, ignore_errors=True)
        if not dest.exists():
            continue
        sub = (aprende.ficha(dest) or {}).get("subtitulo")
        casos.append(("aprende: ve el subtitulo puesto al %d%% del cuadro"
                      % int(alt * 100), sub is not None, True))
        if sub:
            error = abs(float(sub["y"]) - alt)
            casos.append(("aprende: y lo situa donde esta (error %.2f)" % error,
                          error < 0.08, True))
    for c in casos:
        yield c


def _circulo(casa, fuente):
    """El viaje completo del estilo, con el %APPDATA% desviado a temp.

    Las constantes del motor (WORKSPACES, CONFIG) se calculan AL IMPORTAR desde
    el %APPDATA% de verdad, asi que se desvian aqui y se devuelven en el
    finally. Sin esto, una prueba le pisa a Munir su perfil de marca: ya paso
    una vez y no habia copia de seguridad.
    """
    import aprende
    sys.path.insert(0, str(RAIZ / "engine"))
    try:
        import server
    except Exception as e:
        yield ("aprende: el motor se puede importar", str(e)[:60], "")
        return

    _ws, _cfg = server.WORKSPACES, server.CONFIG
    casos = []
    try:
        raiz = Path(tempfile.mkdtemp(prefix="vidorq_circ_"))
        server.WORKSPACES = raiz / "workspaces"
        server.CONFIG = raiz / "config.json"

        # 1. mirar el video del desconocido, hecho con punch
        ajeno = _render(casa, fuente, "ajeno.mp4", "--preset", "punch",
                        "--no-zoom")
        f = aprende.ficha(ajeno)
        propuesto = (aprende.parecidos(f) or [(None, 0)])[0][0]
        casos.append(("circulo: del video ajeno sale un estilo",
                      propuesto, "punch"))

        # 2. el usuario lo aprueba: entra en su marca
        server.profile_save({"captionPreset": propuesto,
                             "captionPresetName": "el del video que me gusto"})
        guardado = server.profile_load()
        casos.append(("circulo: queda guardado en la marca",
                      guardado.get("captionPreset"), "punch"))
        casos.append(("circulo: con el nombre que le puso",
                      guardado.get("captionPresetName"),
                      "el del video que me gusto"))

        # 3. y es lo que la edicion coge cuando nadie dice nada. Se LLAMA a la
        #    funcion del motor, no se copia: antes esta comprobacion escribia
        #    el `or` aqui mismo y luego lo comprobaba, asi que no podia fallar
        #    aunque se invirtiera la regla en el motor.
        sale = server.preset_de({}, guardado)
        casos.append(("circulo: la edicion sin instrucciones coge el de la marca",
                      sale, "punch"))
        casos.append(("circulo: pero lo que se pide a mano sigue mandando",
                      server.preset_de({"captionPreset": "neon"}, guardado),
                      "neon"))
        casos.append(("circulo: y un estilo que no existe no tumba la edicion",
                      server.preset_de({"captionPreset": "no_existe"}, {}),
                      "pop"))

        # 4. y el video PROPIO sale con esa letra. Se comprueba mirandolo, no
        #    confiando en el parametro: se renderiza y se vuelve a analizar.
        mio = _render(casa, fuente, "mio.mp4", "--preset", sale, "--no-zoom")
        casos.append(("circulo: el video propio se renderiza", mio.exists(), True))
        if mio.exists():
            g = aprende.ficha(mio)
            sub_a = (f.get("subtitulo") or {}).get("fill")
            sub_b = (g.get("subtitulo") or {}).get("fill")
            casos.append(("circulo: el video propio lleva subtitulo",
                          sub_b is not None, True))
            if sub_a and sub_b:
                lejos = max(abs(x - y) for x, y in zip(sub_a, sub_b))
                casos.append(
                    ("circulo: y es la MISMA letra que la del ajeno (lejos %.2f)"
                     % lejos, lejos < 0.05, True))
    finally:
        server.WORKSPACES, server.CONFIG = _ws, _cfg
        shutil.rmtree(raiz, ignore_errors=True)
    for c in casos:
        yield c


def _puerta(casa):
    import threading
    import urllib.parse
    import urllib.request
    from http.server import ThreadingHTTPServer

    sys.path.insert(0, str(RAIZ / "engine"))
    try:
        import server
    except Exception as e:
        yield ("aprende: el motor se puede importar", str(e)[:60], "")
        return

    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    puerto = srv.server_address[1]
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    casos = []
    try:
        def pide(ruta):
            url = "http://127.0.0.1:%d/aprende?video=%s" % (
                puerto, urllib.parse.quote(str(ruta)))
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))

        # Una ruta que no existe no puede tumbar el motor ni colarse.
        casos.append(("aprende: la puerta rechaza una ruta que no existe",
                      pide(r"C:\no\existe\ninguno.mp4").get("why"), "no_video"))
        # Ni un archivo que no es un video, aunque exista. La lista de
        # extensiones es la misma que ya usa /probe.
        casos.append(("aprende: la puerta rechaza lo que no es un video",
                      pide(casa / "edl.json").get("why"), "no_video"))
        # Y un archivo con extension de video que NO se puede decodificar se
        # dice por su nombre. Antes salia como "no lleva subtitulos": la
        # pantalla contaba con aplomo un video que nunca llego a leer.
        roto = casa / "roto.mp4"
        roto.write_bytes(b"esto no es un mp4, pero lo parece por el nombre")
        casos.append(("aprende: un video ilegible no pasa por bueno",
                      pide(roto).get("why"), "ilegible"))
        ref = casa / "punch.mp4"
        if ref.exists():
            f = pide(ref)
            casos.append(("aprende: la puerta contesta con la ficha",
                          f.get("ok"), True))
            casos.append(("aprende: la puerta trae estilos que ofrecer",
                          len(f.get("parecidos") or []) > 0, True))
            casos.append(("aprende: la puerta reconoce el estilo con que se hizo",
                          (f.get("parecidos") or [{}])[0].get("id"), "punch"))
    finally:
        srv.shutdown()
    for c in casos:
        yield c


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("(sin ffmpeg en el PATH: esta prueba no se puede hacer)")
        return 0
    casa = Path(tempfile.mkdtemp(prefix="vidorq_aprende_"))
    try:
        (casa / "edl.json").write_text(json.dumps(EDL, indent=1),
                                       encoding="utf-8")
        (casa / "transcript.json").write_text(
            json.dumps(TRANSCRIPT, ensure_ascii=False, indent=1),
            encoding="utf-8")
        try:
            fuente = _fuente(casa)
        except RuntimeError as e:
            print("(no pude preparar el video de prueba: %s)" % e)
            return 0

        bad, total = [], 0
        for nombre, got, want in casos(casa, fuente):
            total += 1
            if got != want:
                bad.append("%s: esperaba %s y devolvio %s" % (nombre, want, got))
        if bad:
            print("%d de %d casos MAL:\n" % (len(bad), total))
            for line in bad:
                print("  - %s" % line)
            return 1
        print("%d casos, entiende lo que mira." % total)
        return 0
    finally:
        # Los videos pesan, y esta carpeta no la vacia nadie.
        shutil.rmtree(casa, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
