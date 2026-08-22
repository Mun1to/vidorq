"""Traer a disco el video de un link, para poder copiarle el estilo.

Lo que entra aqui es una URL que ha escrito una persona en un cuadro de texto,
asi que es entrada NO CONFIABLE y se trata como tal (regla AL): se valida
antes de tocarla, se pasa a yt-dlp como argumento de una lista y NUNCA por una
shell, con su tiempo maximo, y a una carpeta temporal que se borra sola.

  ¿Por que hay una lista de dominios y no vale cualquier URL?
  Porque una URL escrita a mano puede apuntar al propio ordenador
  (127.0.0.1, [::1], 169.254.169.254, un nombre de la red local) y entonces
  esto seria una herramienta para que el programa pida cosas a maquinas de
  dentro de casa en nombre del usuario. Con lista blanca eso no existe.

yt-dlp NO es una dependencia de Vidorq y no esta en requirements.txt. Se usa si
la persona lo tiene instalado, y si no, se le dice. La razon es de licencias y
esta medida (2026-08-22, ver docs/RECURSOS.md): el paquete de PyPI es Unlicense
y se puede usar en un producto de pago, pero los ejecutables que ellos
empaquetan llevan GPLv3+, asi que meterlo en el instalador es otra decision y
no la toma este archivo.
"""
from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Cuanto se espera a una descarga. Un video de redes son segundos; cinco
# minutos es de sobra y pone techo a un link que se quede colgado.
TIMEOUT = 300

# De donde se acepta traer un video. Es una lista blanca a proposito: la lista
# negra siempre se queda corta.
SITIOS = (
    "tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    "instagram.com", "www.instagram.com",
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
    "youtube-nocookie.com",
    "twitter.com", "x.com", "www.x.com",
    "vimeo.com", "www.vimeo.com", "player.vimeo.com",
    "facebook.com", "www.facebook.com", "fb.watch",
    "twitch.tv", "www.twitch.tv", "clips.twitch.tv",
)

# Un nombre de maquina de la red de casa, sin punto, tipo "servidor" o
# "nas". No llevan dominio publico y no pueden ser un sitio de videos.
_SIN_PUNTO = re.compile(r"^[^.]+$")


def _es_de_casa(host):
    """Si ese nombre apunta a esta maquina o a la red local."""
    h = (host or "").strip("[]").lower()
    if not h or h in ("localhost",) or h.endswith(".localhost"):
        return True
    if h.endswith(".local") or h.endswith(".internal") or h.endswith(".home"):
        return True
    if _SIN_PUNTO.match(h):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def vale(url):
    """(True, '') si de ese link se puede traer un video, o (False, motivo).

    Los motivos son claves, no frases: la ventana las traduce al idioma que
    tenga puesto.
    """
    if not url or not isinstance(url, str) or len(url) > 2048:
        return False, "no_link"
    u = url.strip()
    try:
        p = urlparse(u)
    except ValueError:
        return False, "no_link"
    if p.scheme.lower() not in ("http", "https"):
        # file://, data://, javascript:// y compania se quedan fuera aqui.
        return False, "no_link"
    host = (p.hostname or "").lower()
    if not host or _es_de_casa(host):
        return False, "de_casa"
    if host not in SITIOS and not any(
            host.endswith("." + s) for s in SITIOS):
        return False, "sitio_no"
    return True, ""


def hay_ytdlp():
    """Si la herramienta de descarga esta en esta maquina."""
    return bool(shutil.which("yt-dlp") or shutil.which("yt-dlp.exe"))


def traer(url, destino=None, log=None):
    """Descarga el video de `url` y devuelve su ruta, o lanza.

    El archivo cae en una carpeta temporal. Quien lo llama es responsable de
    borrarla al terminar: el video es de otra persona y no se guarda.
    """
    ok, motivo = vale(url)
    if not ok:
        raise ValueError(motivo)
    if not hay_ytdlp():
        raise RuntimeError("no_ytdlp")
    casa = Path(destino or tempfile.mkdtemp(prefix="vidorq_ref_"))
    casa.mkdir(parents=True, exist_ok=True)
    if log:
        log("bajando el video")
    r = subprocess.run(
        # Sin shell, con la url como UN argumento, y con -- delante para que
        # una url que empiece por guion no se lea como una opcion.
        ["yt-dlp", "--no-playlist", "--no-continue", "--no-part",
         "--max-filesize", "500M", "--socket-timeout", "30",
         "-f", "mp4/best", "-o", str(casa / "ref.%(ext)s"), "--", url.strip()],
        capture_output=True, timeout=TIMEOUT, creationflags=NO_WINDOW)
    salidas = sorted(casa.glob("ref.*"))
    if r.returncode != 0 or not salidas:
        raise RuntimeError(
            "no_baja: %s" % r.stderr.decode("utf-8", "replace")[-200:])
    return salidas[0]
