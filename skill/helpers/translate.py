"""Subtitles in another language, without sending the video anywhere.

Whisper can already translate, but only ever into English, so it is no use for
the thing people actually ask for: the same video captioned in three languages.
This does it with a local model first, on the caption chunks Vidorq already
built, which keeps the timings exactly as they were.

Chunks go over in batches, numbered, and come back numbered. A model that
answers with prose, an apology or a renumbered list gets caught and the batch is
retried one line at a time, because a translation that silently shifts by one
line would put every caption on the wrong word.

Local-only until 20-ago-2026: `translate_lines` talked to Ollama and nothing
else, no matter which AI provider the rest of the app had picked in Ajustes.
On a machine with zero Ollama models installed (measured: this one) that made
"traducir subtitulos" unusable regardless of having Claude, OpenAI or Gemini
configured and working for every other prompt. Local still goes first when a
model is there, because it is free and keeps the video on the machine; the
chosen provider is now the fallback instead of a dead end.
"""
from __future__ import annotations

import json
import re
import urllib.request

import providers
from vision import available_models, ollama_host

# Multilingual first. aya-expanse was trained for exactly this, the qwen3.5
# family is strong across languages, and the rest are decent fallbacks.
TRANSLATORS = ("aya-expanse:8b", "qwen3.5:9b", "qwen3.5:4b", "gemma4:26b",
               "mistral-small:24b", "llama3.1:8b", "qwen3.5:2b", "llama3.2:3b")

LANGS = {
    "es": "espanol", "en": "English", "pt": "portugues", "fr": "francais",
    "de": "Deutsch", "it": "italiano", "ca": "catala", "gl": "galego",
    "eu": "euskara", "ja": "Japanese", "zh": "Chinese", "ar": "Arabic",
}

# Small enough that a model keeps the numbering straight, big enough that a long
# video does not turn into hundreds of round trips.
BATCH = 12


def pick_model(prefer=None):
    have = set(available_models())
    if prefer and prefer in have:
        return prefer
    for name in TRANSLATORS:
        if name in have:
            return name
    return None


def _ask(model, system, user, ai=None, timeout=240):
    """One answer, from Ollama if `model` names one, from the chosen provider
    otherwise. `ai` is the same choice dict `director.py` uses for everything
    else (provider, model, key, baseUrl): translation was the one caller that
    never got to use it.
    """
    if not model and ai and ai.get("provider") and ai["provider"] != "local":
        return providers.complete(ai["provider"], ai.get("model") or "", system, user,
                                  key=ai.get("key", ""), tokens=1400,
                                  base_url=ai.get("baseUrl", ""))
    req = urllib.request.Request(
        ollama_host() + "/api/generate",
        data=json.dumps({"model": model, "system": system, "prompt": user,
                         "stream": False,
                         "options": {"temperature": 0.2, "num_predict": 1400}}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return (d.get("response") or d.get("thinking") or "").strip()


SYSTEM = ("Eres un traductor de subtitulos. Traduces al %s. Reglas: devuelves "
          "EXACTAMENTE una linea por cada linea numerada que recibes, con el "
          "mismo numero y el mismo orden; no juntas ni partes lineas; no "
          "explicas nada; mantienes el tono hablado y la longitud parecida, "
          "porque el texto va en pantalla poco tiempo.")

LINE_RE = re.compile(r"^\s*(\d+)\s*[.):\]]\s*(.+?)\s*$")


def _parse(reply, n):
    """Pull `n` numbered lines out of whatever the model said."""
    got = {}
    for raw in reply.splitlines():
        m = LINE_RE.match(raw)
        if m:
            got[int(m.group(1))] = m.group(2)
    return [got.get(i + 1) for i in range(n)]


def translate_lines(lines, target, model=None, ai=None, log=None):
    """Translate a list of strings, keeping the list length exactly.

    Returns a list the same length; anything the model failed to give back stays
    as the original rather than becoming an empty caption. Local Ollama goes
    first when there is a model for it; `ai` (the provider the user picked in
    Ajustes) is what runs when there is not, instead of failing outright.
    """
    picked = model or pick_model()
    if not picked and not (ai and ai.get("provider") and ai["provider"] != "local"):
        raise RuntimeError(
            "No hay modelo de traduccion en Ollama ni un proveedor con clave "
            "puesto en Ajustes. Instala uno (por ejemplo 'ollama pull "
            "aya-expanse:8b') o elige un proveedor.")
    lang = LANGS.get(target, target)
    system = SYSTEM % lang
    out = list(lines)

    for start in range(0, len(lines), BATCH):
        batch = lines[start:start + BATCH]
        body = "\n".join("%d. %s" % (i + 1, t) for i, t in enumerate(batch))
        try:
            got = _parse(_ask(picked, system, body, ai=ai), len(batch))
        except Exception as e:
            if log:
                log("lote %d sin traducir: %s" % (start // BATCH + 1, str(e)[:70]))
            continue
        # A batch that came back short or shifted is not trusted as a batch: the
        # lines are asked for one at a time, where nothing can slide.
        if sum(1 for g in got if g) < len(batch):
            if log:
                log("lote %d desalineado, lo repito linea a linea" % (start // BATCH + 1))
            got = []
            for one in batch:
                try:
                    r = _parse(_ask(picked, system, "1. " + one, ai=ai), 1)[0]
                except Exception:
                    r = None
                got.append(r)
        for i, g in enumerate(got):
            if g:
                out[start + i] = g
        if log:
            log("traducidas %d/%d" % (min(start + BATCH, len(lines)), len(lines)))
    return out


# Chino y japones no separan las palabras con espacios, asi que ".split()"
# devuelve la frase ENTERA como una sola "palabra". Medido el 20-ago-2026:
# una frase de 34 caracteres se quedaba en pantalla 8,1 segundos de un tiron,
# porque para el renderizador solo habia una palabra que ocupar ese hueco - el
# estilo "punch" (una palabra por golpe) dejaba de tener sentido en chino. Por
# caracter no es la segmentacion lingueisticamente correcta, pero reparte el
# tiempo de verdad y es lo que hacen la mayoria de generadores de subtitulos
# cuando no llevan un segmentador de idioma aparte.
NO_SPACES = {"zh", "ja"}


def _split_words(text, target):
    if target in NO_SPACES:
        return [c for c in text if not c.isspace()]
    return [w for w in text.split() if w]


def translate_transcript(transcript, target, model=None, ai=None, log=None):
    """Translate whole sentences, then hand the words their times back.

    Translating the caption chunks directly is the obvious thing and it is
    wrong: a two-word chunk has no context, so "muchisimas preguntas" split
    across two captions came back as "so many of" / "them arrived". Sentences
    carry their meaning, so sentences are what gets translated.

    The new words then need timings, and there is no honest way to know them -
    a different language puts the words in a different order. They are shared
    out across the sentence in proportion to how long each word is, which is
    close enough for a caption and never drifts outside its own sentence.
    """
    segs = [s for s in transcript.get("segments", []) if (s.get("text") or "").strip()]
    if not segs:
        return {"duration": transcript.get("duration", 0), "segments": []}
    done = translate_lines([s["text"].strip() for s in segs], target, model, ai, log)

    out = []
    for seg, text in zip(segs, done):
        words = _split_words(text or "", target)
        if not words:
            continue
        start, end = float(seg["start"]), float(seg["end"])
        span = max(0.2, end - start)
        total = sum(len(w) for w in words) or 1
        at, timed = start, []
        for w in words:
            dur = span * len(w) / total
            timed.append({"w": w, "s": round(at, 3), "e": round(min(at + dur, end), 3)})
            at += dur
        out.append({"start": start, "end": end, "text": " ".join(words), "words": timed})
    return {"duration": transcript.get("duration", 0), "segments": out}


def translate_chunks(chunks, target, model=None, ai=None, log=None):
    """Caption chunks in another language, timings kept.

    Only for text that is already a full line. For anything chunked into two or
    three words use translate_transcript() and re-chunk, or the translation
    loses the sentence it belonged to.
    """
    texts = [c["text"] for c in chunks]
    done = translate_lines(texts, target, model, ai, log)
    out = []
    for c, text in zip(chunks, done):
        out.append({"start": c["start"], "end": c["end"], "text": text,
                    "words": [{"w": text, "s": c["start"], "e": c["end"]}]})
    return out


def to_srt(chunks):
    """A plain .srt, which is what every platform accepts for a second language.

    Un bloque de SRT se separa del siguiente por una linea EN BLANCO, asi que un
    subtitulo con un salto de linea doble dentro parte el archivo en dos. Medido
    el 20-ago-2026: con cuatro subtitulos, uno de ellos con un salto y un numero
    dentro, un lector de SRT contaba CINCO, y el de sobra era un subtitulo
    inventado en el segundo cero.

    De donde puede venir un salto ahi: el texto traducido lo escribe un modelo, y
    lo que devuelve un modelo es un dato ajeno como cualquier otro. Los
    subtitulos de Vidorq no llevan saltos a proposito en ningun caso, asi que
    aplastar los espacios no quita nada y cierra el agujero entero.
    """
    def stamp(t):
        ms = max(0, int(round(t * 1000)))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return "%02d:%02d:%02d,%03d" % (h, m, s, ms)

    def plano(t):
        return re.sub(r"\s+", " ", str(t or "")).strip()

    return "".join("%d\n%s --> %s\n%s\n\n"
                   % (i, stamp(c["start"]), stamp(c["end"]), plano(c["text"]))
                   for i, c in enumerate(chunks, 1))
