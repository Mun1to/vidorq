"""Turn a sentence from the user into the decisions an edit needs.

"editame este video en vertical estilo short de youtube, con subtitulos animados"
is not an EDL. It is a set of choices: the shape of the frame, whether captions
go on, which look, which entrance, what to do at the joins. Those choices used to
live in the interface only, so a prompt could ask for them and be ignored.

Split in two on purpose, because the two halves have very different difficulty:

  look()      what the video should look like. A short, constrained answer that a
              small local model gets right, and it is validated against the real
              catalogues afterwards so a hallucinated name can never reach the
              renderer.
  segments()  which parts to keep. Long, exact, and the part a local model is
              most likely to fumble, so a failure here falls back to the
              deterministic cut engine rather than ruining the edit.

Anthropic is used when a key is present. Without one it runs on local Ollama, so
the prompt mode works out of the box instead of being locked behind a key.
"""
from __future__ import annotations

import json
import re
import urllib.request

import captions as cap
from vision import OLLAMA, available_models

# Ordered by what actually works here, which is neither "biggest" nor "newest".
# Two things were measured on the same prompt:
#   a 27B at Q4 is 17 GB, and an 8 GB card answers HTTP 500 rather than loading it
#   a reasoning model spends its budget reasoning: qwen3.5:9b took 130 s to decide
#   one small thing, while llama3.1:8b answered the same question correctly in 13
#   and granite4.1:3b in 7
# So the plain instruction-followers go first and the reasoners are the fallback.
DIRECTORS = ("llama3.1:8b", "granite4.1:3b", "phi4-mini:3.8b", "qwen3.5:4b",
             "qwen3.5:9b", "llama3.2:3b", "qwen2.5:3b",
             "phi4:14b", "mistral-small:24b", "gpt-oss:20b", "qwen3.5:27b")

RATIOS = ("source", "vertical", "portrait", "square", "wide")
TRANSITIONS = ("none", "dissolve", "dip", "white", "slide", "wipe", "zoom")
CUTS = ("clean", "podcast", "montage")


def candidates(prefer=None):
    """Every model worth trying, best-that-fits first.

    A list rather than one choice, because a model that is present is not
    necessarily a model that loads: too big for the card and Ollama answers 500.
    """
    have = set(available_models())
    out = [prefer] if prefer and prefer in have else []
    out += [n for n in DIRECTORS if n in have and n != prefer]
    return out


def pick_model(prefer=None):
    got = candidates(prefer)
    return got[0] if got else None


def _try_local(system, user, predict, log=None, prefer=None):
    """Ask each candidate in turn until one answers. Returns (text, model)."""
    tried = candidates(prefer)
    if not tried:
        raise RuntimeError("no hay ningun modelo local para esto")
    last = None
    for name in tried:
        try:
            return _ollama(name, system, user, predict=predict), name
        except Exception as e:
            last = e
            if log:
                log("%s no pudo (%s), pruebo el siguiente" % (name, str(e)[:50]))
    raise RuntimeError(str(last))


def _ollama(model, system, user, timeout=300, predict=900):
    req = urllib.request.Request(
        OLLAMA + "/api/generate",
        data=json.dumps({"model": model, "system": system, "prompt": user,
                         "stream": False,
                         "options": {"temperature": 0.1, "num_predict": predict}}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return (d.get("response") or d.get("thinking") or "").strip()


def _anthropic(key, system, user, timeout=180, tokens=4000):
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": "claude-sonnet-5", "max_tokens": tokens,
                         "system": system,
                         "messages": [{"role": "user", "content": user}]}).encode(),
        headers={"Content-Type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return "".join(b.get("text", "") for b in d.get("content", []))


def _json_in(text):
    """The first JSON object in whatever came back, or None.

    Models wrap answers in prose and fences however they feel like, and a
    director that dies on a stray "Sure!" is not a director.
    """
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M)
    depth = start = 0
    for i, ch in enumerate(text):
        if ch == "{":
            if not depth:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if not depth:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    depth = 0
    return None


# --------------------------------------------------------------------------- #
# Half one: what it should look like
# --------------------------------------------------------------------------- #
def _look_system(lang="es"):
    styles = ", ".join("%s (%s)" % (pid, p["note"].get(lang, p["note"]["en"])[:70])
                       for pid, p in cap.PRESETS.items())
    anims = ", ".join("%s (%s)" % (aid, a["note"].get(lang, a["note"]["en"])[:50])
                      for aid, a in cap.ANIMS.items())
    return (
        "Eres el director de arte de un editor de video. El usuario describe en una "
        "frase el video que quiere y tu eliges los ajustes. Responde SOLO un objeto "
        "JSON, sin texto alrededor, con estas claves exactas:\n"
        '{"ratio": uno de [%s], "captions": true o false, '
        '"captionPreset": uno de los estilos, "captionAnim": una de las animaciones, '
        '"transition": uno de [%s], "cuts": uno de [%s], "why": "una frase corta"}\n\n'
        "ESTILOS DE SUBTITULO: %s\n\n"
        "ANIMACIONES: %s\n\n"
        "Reglas: 'vertical' es para shorts, reels y TikTok. 'wide' u 'source' para "
        "YouTube normal. Si pide subtitulos animados, captionAnim NO puede ser 'none'. "
        "Si no dice nada de transiciones usa 'none', porque sobre voz una disolvencia "
        "emborrona las palabras. 'montage' solo si pide un resumen o los mejores "
        "momentos; si solo pide limpiar y cortar bien, usa 'clean'."
        % (", ".join(RATIOS), ", ".join(TRANSITIONS), ", ".join(CUTS), styles, anims))


# What the prompt says outright, in the words people actually use. This runs
# before any model and wins over it, for a blunt reason: asking a model whether
# the word "vertical" appears is slow, costs a GPU, and has been measured getting
# it wrong while its own reasoning said "vertical is appropriate" out loud. Rules
# for what is stated, the model for what has to be judged.
WORD_RULES = (
    ("ratio", "vertical", r"\bvertical|\bshort|\bshorts\b|tiktok|tik tok|reel|"
                          r"9\s*[:x/]\s*16|movil|m[oó]vil"),
    ("ratio", "square", r"\bcuadrad|\bsquare\b|1\s*[:x/]\s*1"),
    ("ratio", "portrait", r"4\s*[:x/]\s*5|\bretrato\b"),
    ("ratio", "wide", r"\bhorizontal|\bapaisad|16\s*[:x/]\s*9|\bwide\b"),
    ("captions", False, r"sin subt[ií]tul|no subt[ií]tul|sin caption|no caption"),
    ("captions", True, r"subt[ií]tul|caption|\brotul"),
    ("cuts", "montage", r"resumen|mejores momentos|highlight|montaje|best bits|"
                        r"lo mejor\b"),
    ("cuts", "podcast", r"podcast|entrevista|preguntas y respuestas|\bq&a\b"),
    ("transition", "dissolve", r"disolvenc|\bfundido\b(?!.*negro)|cross ?dissolve"),
    ("transition", "dip", r"fundido a negro|dip to black|a negro"),
)

# A style named outright wins too. The keys are what someone would actually type.
STYLE_WORDS = {
    "pop": r"\bpop\b|hormozi|\bgordo|muy grande",
    "punch": r"\bpunch\b|palabra a palabra|una palabra",
    "marker": r"marcador|rotulador|highlighter|subrayad",
    "bar": r"\bbarra\b|\bbar\b",
    "glass": r"cristal|glass|panel|translucid",
    "minimal": r"minimal|discret|sobrio|sencill|\bfino\b",
    "neon": r"\bneon\b|\bne[oó]n\b|\bcian\b",
    "ember": r"brasa|ember|naranja",
    "halo": r"\bhalo\b|resplandor|\bbrillo\b",
    "mono": r"\bmono\b|monoespaci|c[oó]digo|terminal",
}

ANIM_WORDS = {
    "bounce": r"rebot|bounce|muelle|capcut",
    "zoom": r"\bzoom\b",
    "throb": r"latido|throb|pulso",
    "focus": r"enfoq|focus|desenfoq",
    "ignite": r"encendid|ignite|se enciende",
    "fade": r"fundido suave|solo aparec",
    "none": r"sin animaci|quieto|est[aá]tic",
}


def from_words(prompt):
    """The settings the prompt states literally. Cheap, exact, no model."""
    got = {}
    low = " " + (prompt or "").lower() + " "
    for key, value, pattern in WORD_RULES:
        if key in got:
            continue                      # first rule that matches a key wins
        if re.search(pattern, low, re.I):
            got[key] = value
    for pid, pattern in STYLE_WORDS.items():
        if re.search(pattern, low, re.I):
            got["captionPreset"] = pid
            break
    for aid, pattern in ANIM_WORDS.items():
        if re.search(pattern, low, re.I):
            got["captionAnim"] = aid
            break
    if "captionAnim" not in got and re.search(r"anima|movimiento|animated|motion", low, re.I):
        got["captionAnim"] = "__any__"    # animated, but which one is a judgement
    return got


def look(prompt, key="", model=None, lang="es", log=None):
    """The settings a prompt asks for, validated against the real catalogues.

    Three layers, each overriding the one before: sane defaults, then whatever a
    model judged, then whatever the prompt said outright. Anything the model
    invents or leaves out simply does not survive the validation, so the worst
    case is an ordinary edit rather than a crash.
    """
    out = {"ratio": "source", "captions": True,
           "captionPreset": cap.DEFAULT_PRESET, "captionAnim": "",
           "transition": "none", "cuts": "clean", "why": "", "by": ""}
    said = from_words(prompt)
    system = _look_system(lang)
    raw = ""
    try:
        if key:
            raw = _anthropic(key, system, prompt, tokens=1600)
            out["by"] = "claude-sonnet-5"
        else:
            # 1600 and not 700: a reasoning model spends its first several
            # hundred tokens thinking and then has to have room left to answer.
            # Measured on qwen3.5:9b, which reasoned its way to the right answer
            # and ran out of budget before writing a single character of JSON.
            raw, out["by"] = _try_local(system, prompt, 1600, log, model)
    except Exception as e:
        if log:
            log("el director no contesto (%s), me guio por el texto" % str(e)[:60])
        out["by"] = ""

    got = _json_in(raw) or {}
    if got.get("ratio") in RATIOS:
        out["ratio"] = got["ratio"]
    if isinstance(got.get("captions"), bool):
        out["captions"] = got["captions"]
    if got.get("captionPreset") in cap.PRESETS:
        out["captionPreset"] = got["captionPreset"]
    if got.get("captionAnim") in cap.ANIMS:
        out["captionAnim"] = got["captionAnim"]
    if got.get("transition") in TRANSITIONS:
        out["transition"] = got["transition"]
    if got.get("cuts") in CUTS:
        out["cuts"] = got["cuts"]
    if isinstance(got.get("why"), str):
        out["why"] = got["why"][:160]

    # Last word to the prompt itself. A model that ignored "vertical" does not
    # get to overrule the person who typed it.
    for key, value in said.items():
        if key == "captionAnim" and value == "__any__":
            continue
        out[key] = value
    # "Animated" without naming one means any of them, so the look's own applies -
    # never "none", which would contradict what was asked.
    if said.get("captionAnim") == "__any__" and out["captionAnim"] in ("", "none"):
        out["captionAnim"] = cap.PRESETS[out["captionPreset"]]["anim"]
    if not out["captions"]:
        out["captionAnim"] = ""
    # A short lives on a phone screen held at arm's length, so a quiet caption is
    # the wrong call there whatever a model prefers. Only overridden when the
    # style was not asked for by name.
    if (out["ratio"] in ("vertical", "portrait")
            and "captionPreset" not in said
            and cap.PRESETS[out["captionPreset"]]["size"] < 0.09):
        out["captionPreset"] = "pop"
    out["said"] = sorted(k for k in said if k != "captionAnim" or
                         said["captionAnim"] != "__any__")
    return out


# --------------------------------------------------------------------------- #
# Half two: which parts to keep
# --------------------------------------------------------------------------- #
SEG_SYSTEM = (
    "Eres el editor de video de Vidorq. Recibes la transcripcion empaquetada de un "
    "video (lineas '[inicio-fin] texto' en segundos), a veces lo que se VE plano a "
    "plano, y la instruccion del usuario. Devuelve SOLO un JSON: "
    '{"segments":[{"start":s,"end":s,"zoom":1.0,"note":"..."}]} con los tramos A '
    "CONSERVAR, en orden, cortando en limites de frase. Los tiempos en segundos con "
    "decimales, dentro de la duracion del video, sin solaparse. Zoom entre 1.0 y 1.08, "
    "solo en momentos de enfasis.")


def segments(prompt, packed, key="", model=None, log=None):
    """The keep-list a prompt asks for, or None if the model did not deliver.

    None is a normal outcome, not an error: the caller falls back to the
    deterministic cut engine, which is better than a made-up timeline.
    """
    try:
        if key:
            raw = _anthropic(key, SEG_SYSTEM, "INSTRUCCION: %s\n\nTRANSCRIPCION:\n%s"
                             % (prompt, packed))
        else:
            chosen = pick_model(model)
            if not chosen:
                return None
            raw = _ollama(chosen, SEG_SYSTEM, "INSTRUCCION: %s\n\nTRANSCRIPCION:\n%s"
                          % (prompt, packed), predict=2500)
    except Exception as e:
        if log:
            log("el editor no contesto: %s" % str(e)[:80])
        return None

    got = _json_in(raw)
    segs = (got or {}).get("segments")
    if not isinstance(segs, list) or not segs:
        if log:
            log("el modelo no devolvio tramos usables")
        return None

    clean = []
    for s in segs:
        try:
            a, b = float(s["start"]), float(s["end"])
        except Exception:
            continue
        if b - a < 0.25:
            continue
        if clean and a < clean[-1]["end"]:      # no overlaps, no going backwards
            a = clean[-1]["end"]
            if b - a < 0.25:
                continue
        z = float(s.get("zoom", 1.0) or 1.0)
        clean.append({"start": round(a, 3), "end": round(b, 3),
                      "zoom": min(1.08, max(1.0, z)),
                      "note": str(s.get("note", ""))[:60]})
    if not clean:
        if log:
            log("los tramos del modelo no pasaron la revision")
        return None
    return clean
