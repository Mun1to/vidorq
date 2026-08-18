"""Voice over, from the machine's own voice or from a paid one.

Same shape as providers.py and for the same reason: the thing that ships must
work with no key and no account, and paying only buys a better version of
something that is already there. Here that is Windows' own speech synthesiser,
installed on every Windows machine, free, working with the network unplugged,
and sounding like 2009. ElevenLabs and OpenAI sound like a person.

Untrusted input is the whole risk in this file. The line to be spoken comes out
of a transcript, or out of a model reading a transcript, which is to say it
comes from a video somebody else made, and it ends up as an argument to a
program. So the text is never interpolated into a command line: it is written
to a UTF-8 file and the synthesiser is told to read that file. There is no
quoting to get wrong because there is no quoting.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TIMEOUT = 120
# Long enough for a hook or a card, short enough that a runaway model cannot
# bill somebody for a novel.
MAX_CHARS = 600

ENGINES = {
    "windows": {
        "label": "Voz de Windows",
        "needs_key": False, "key_id": "", "key_url": "",
        "base": "", "default_voice": "", "default_model": "", "ext": ".wav",
        "note": {"es": "La que ya trae tu equipo. Gratis, sin clave y sin internet. "
                       "Suena a robot, pero para un aviso o una nota cumple.",
                 "en": "The one your machine already has. Free, no key, no internet. "
                       "It sounds like a robot, but for a note it does the job."},
    },
    "elevenlabs": {
        "label": "ElevenLabs",
        "needs_key": True, "key_id": "elevenlabs",
        "key_url": "https://elevenlabs.io/app/settings/api-keys",
        "base": "https://api.elevenlabs.io/v1",
        "default_voice": "21m00Tcm4TlvDq8ikWAM",
        "default_model": "eleven_multilingual_v2", "ext": ".mp3",
        "note": {"es": "La mejor voz del mercado ahora mismo, y la que clona la tuya. "
                       "Se paga por caracteres y tiene un plan gratis pequeno.",
                 "en": "The best voice on the market right now, and the one that clones "
                       "yours. Billed per character, with a small free tier."},
    },
    "openai": {
        "label": "OpenAI",
        "needs_key": True, "key_id": "openai",
        "key_url": "https://platform.openai.com/api-keys",
        "base": "https://api.openai.com/v1",
        "default_voice": "alloy", "default_model": "gpt-4o-mini-tts", "ext": ".mp3",
        "note": {"es": "La misma clave que ya usas para los prompts, si la tienes "
                       "puesta. Barata y suficiente para casi todo.",
                 "en": "The same key you already use for prompts, if you have one in. "
                       "Cheap and good enough for nearly everything."},
    },
    "custom": {
        "label": "Compatible con OpenAI",
        "needs_key": True, "key_id": "custom", "key_url": "",
        "base": "", "default_voice": "alloy", "default_model": "tts-1", "ext": ".mp3",
        "note": {"es": "Cualquier endpoint con un /audio/speech al estilo de OpenAI. "
                       "Pon la URL base y su clave.",
                 "en": "Any endpoint with an OpenAI-style /audio/speech. Give it the "
                       "base URL and its key."},
    },
}

DEFAULT_ENGINE = "windows"

# OpenAI does not publish a voice list over the API, so it is written down here.
# Asking and getting a 404 back tells the user their key is broken when it is not.
OPENAI_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable",
                 "nova", "onyx", "sage", "shimmer", "verse"]


def catalogue(lang="es"):
    """What the settings screen needs to draw the picker."""
    return [{"id": eid, "label": e["label"], "needsKey": e["needs_key"],
             "keyId": e["key_id"], "keyUrl": e["key_url"],
             "note": e["note"].get(lang, e["note"]["es"])}
            for eid, e in ENGINES.items()]


def _root(engine, base_url=""):
    e = ENGINES.get(engine) or ENGINES[DEFAULT_ENGINE]
    return e, (base_url or e["base"] or "").rstrip("/")


def _post_bytes(url, body, headers, timeout=TIMEOUT):
    """Like providers._post, except the answer is audio and not JSON."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers=dict(headers, **{"Content-Type": "application/json"}), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:300]
        except Exception:
            pass
        host = url.split("//", 1)[-1].split("/", 1)[0]
        raise RuntimeError("%s respondio %s. %s" % (host, e.code, detail)) from None


# --------------------------------------------------------------------------- #
# Windows' own voice
# --------------------------------------------------------------------------- #
_VOICES_PS = (
    "Add-Type -AssemblyName System.Speech; "
    "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
    ".GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
)

# Every value this script works with is read from a file whose folder arrives in
# an environment variable. Nothing the user or a model wrote is ever part of the
# command line, which is what makes a spoken line safe to take from a video.
_SAY_PS = (
    "$ErrorActionPreference='Stop';"
    "Add-Type -AssemblyName System.Speech;"
    "$d=$env:VIDORQ_SAY;"
    "$t=[IO.File]::ReadAllText((Join-Path $d 'linea.txt'),[Text.Encoding]::UTF8);"
    "$o=[IO.File]::ReadAllText((Join-Path $d 'salida.txt'),[Text.Encoding]::UTF8);"
    "$v=[IO.File]::ReadAllText((Join-Path $d 'voz.txt'),[Text.Encoding]::UTF8);"
    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "if($v){ try { $s.SelectVoice($v) } catch {} }"
    "$s.SetOutputToWaveFile($o);"
    "$s.Speak($t);"
    "$s.Dispose()"
)


def _powershell(script, env=None, timeout=TIMEOUT):
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, timeout=timeout, env=env, creationflags=NO_WINDOW)


def _windows_voices():
    if os.name != "nt":
        return []
    try:
        p = _powershell(_VOICES_PS, timeout=30)
        names = [n.strip() for n in p.stdout.decode("utf-8", "replace").splitlines()]
        return [{"id": n, "label": n} for n in names if n]
    except Exception:
        return []


def _windows_say(text, dest, voice=""):
    """Speak into a .wav with System.Speech.

    The text, the voice and the destination all travel as FILES. A line lifted
    from somebody else's video can contain quotes, semicolons, backticks and
    subshells, and PowerShell would happily run the lot.
    """
    if os.name != "nt":
        raise RuntimeError("la voz de Windows solo existe en Windows")
    tmp = Path(tempfile.mkdtemp(prefix="vidorq_say_"))
    try:
        (tmp / "linea.txt").write_text(text, encoding="utf-8")
        (tmp / "salida.txt").write_text(str(dest), encoding="utf-8")
        (tmp / "voz.txt").write_text(voice or "", encoding="utf-8")
        p = _powershell(_SAY_PS, env=dict(os.environ, VIDORQ_SAY=str(tmp)))
        if p.returncode != 0 or not Path(dest).is_file():
            raise RuntimeError(p.stderr.decode("utf-8", "replace")[:300]
                               or "la voz de Windows no escribio nada")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return Path(dest)


# --------------------------------------------------------------------------- #
# The paid ones
# --------------------------------------------------------------------------- #
def _eleven_voices(root, key):
    req = urllib.request.Request(root + "/voices", headers={"xi-api-key": key})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    return [{"id": v.get("voice_id", ""), "label": v.get("name", "")}
            for v in data.get("voices", []) if v.get("voice_id")]


def _eleven_say(root, key, text, dest, voice, model):
    audio = _post_bytes("%s/text-to-speech/%s" % (root, voice),
                        {"text": text, "model_id": model},
                        {"xi-api-key": key, "Accept": "audio/mpeg"})
    Path(dest).write_bytes(audio)
    return Path(dest)


def _openai_say(root, key, text, dest, voice, model):
    audio = _post_bytes(root + "/audio/speech",
                        {"model": model, "input": text, "voice": voice,
                         "response_format": "mp3"},
                        {"Authorization": "Bearer " + key})
    Path(dest).write_bytes(audio)
    return Path(dest)


# --------------------------------------------------------------------------- #
# What the rest of the program calls
# --------------------------------------------------------------------------- #
def voices(engine=DEFAULT_ENGINE, key="", base_url=""):
    """The voices this engine offers, asked live wherever that is possible."""
    e, root = _root(engine, base_url)
    if engine == "windows":
        return _windows_voices()
    if engine == "elevenlabs":
        return _eleven_voices(root, key) if key else []
    return [{"id": v, "label": v.capitalize()} for v in OPENAI_VOICES]


def say(text, dest, engine=DEFAULT_ENGINE, voice="", key="", base_url="", model=""):
    """One line of speech, written to `dest`. Returns the path.

    Raises rather than returning nothing: a voice-over that silently did not
    happen is worse than one that says why, because the video comes out looking
    finished and is not.
    """
    text = (text or "").strip()[:MAX_CHARS]
    if not text:
        raise RuntimeError("no hay nada que decir")
    e, root = _root(engine, base_url)
    voice = voice or e["default_voice"]
    model = model or e["default_model"]
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    if engine == "windows":
        return _windows_say(text, dest, voice)
    if e["needs_key"] and not key:
        raise RuntimeError("%s necesita una clave de API" % e["label"])
    if engine == "elevenlabs":
        return _eleven_say(root, key, text, dest, voice, model)
    if not root:
        raise RuntimeError("falta la URL base del endpoint de voz")
    return _openai_say(root, key, text, dest, voice, model)


def ext(engine):
    """The file extension this engine writes, so callers can name the file."""
    return (ENGINES.get(engine) or ENGINES[DEFAULT_ENGINE])["ext"]
