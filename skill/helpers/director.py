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

Which model answers is the user's choice and lives in providers.py: the local
Ollama by default, so prompt mode works out of the box instead of being locked
behind a key, and anything from Anthropic to OpenRouter to a llama.cpp on the
next desk if they would rather pay for a bigger brain.
"""
from __future__ import annotations

import json
import re
import urllib.request

import captions as cap
import looks
import providers
from vision import available_models, ollama_host

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
        ollama_host() + "/api/generate",
        data=json.dumps({"model": model, "system": system, "prompt": user,
                         "stream": False,
                         "options": {"temperature": 0.1, "num_predict": predict}}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return (d.get("response") or d.get("thinking") or "").strip()


def _hosted(ai, system, user, tokens):
    """One answer from whichever provider the user picked. Returns (text, label).

    The label is what the interface shows as "who decided this", so it names the
    model and not the vendor: knowing it was `claude-sonnet-5` or `llama3.1:8b`
    is the useful half.
    """
    p = providers.PROVIDERS[ai["provider"]]
    model = ai.get("model") or p["default"]
    text = providers.complete(ai["provider"], model, system, user,
                              key=ai.get("key", ""), tokens=tokens,
                              base_url=ai.get("baseUrl", ""))
    # Una CLI elige su propio modelo y no lo dice, asi que ahi el nombre util es
    # el de la herramienta. Devolver cadena vacia dejaba el "lo decidio" en blanco.
    return text, (model or p["label"])


def _is_hosted(ai):
    """True when the user chose something other than the local Ollama."""
    return bool(ai) and ai.get("provider") and ai["provider"] != "local"


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


def _change_system(current, lang="es"):
    """El prompt del retoque: estado actual, menu cerrado, y solo el delta.

    Distinto de _look_system a proposito. Alli no hay nada elegido todavia y se
    pide un plan entero; aqui YA hay un video montado y la frase es un retoque,
    asi que pedir un plan completo es como preguntarle a alguien que rehaga la
    casa porque quieres mover una silla: el modelo rellena todo lo demas con su
    opinion y te deshace el estilo que elegiste hace dos rondas.

    Tambien se le pregunta por lo que NO sabe hacer. Un modelo que puede decir
    "esto no esta en la lista" deja de tener que inventarse algo, que es de
    donde salen las respuestas raras.
    """
    styles = ", ".join(cap.PRESETS)
    anims = ", ".join(cap.ANIMS)
    return (
        "Eres el editor de video de Vidorq. El usuario YA tiene un video montado "
        "y te pide UN CAMBIO. Estos son los ajustes que tiene ahora:\n%s\n\n"
        "Responde SOLO un objeto JSON, sin texto alrededor:\n"
        '{"cambia": {...}, "no_puedo": [...], "why": "una frase corta"}\n\n'
        "En 'cambia' pon UNICAMENTE las claves que hay que cambiar, y ninguna "
        "mas. Si el usuario no habla del formato, NO pongas 'ratio'. Si no habla "
        "del estilo, NO pongas 'captionPreset'. Claves y valores posibles:\n"
        "  ratio: %s\n"
        "  transition: %s\n"
        "  captions: true o false\n"
        "  shake: true o false (un golpe de camara al caer el corte)\n"
        "  captionPreset: %s\n"
        "  captionAnim: %s\n"
        "  cuts: %s\n"
        "  look: %s\n\n"
        "En 'no_puedo' pon con tus palabras lo que el usuario ha pedido y no "
        "cabe en ninguna de esas claves. NO pongas ahi nada que ocurra en un "
        "momento concreto del video (un zoom en el segundo 11, quitar un trozo, "
        "un cartel, una voz en off): de eso se encarga otra parte del programa "
        "y ya funciona, asi que decir que no se puede seria mentira. "
        "Si lo entiendes todo, dejalo vacio. Si "
        "no hay que cambiar ningun ajuste, devuelve 'cambia' vacio: eso es una "
        "respuesta correcta, no un fallo."
        % (json.dumps(current, ensure_ascii=False),
           ", ".join(RATIOS), ", ".join(TRANSITIONS), styles, anims,
           ", ".join(CUTS), ", ".join(looks.PRESETS)))


def change(prompt, current, ai=None, model=None, log=None):
    """Que ajustes cambia esta frase, sobre los que ya hay.

    Devuelve (delta, no_puedo, why). El delta pasa por la misma validacion que
    look(): un valor que no esta en el catalogo se cae y no llega a ninguna
    parte. Que el modelo no conteste no es un error, es un delta vacio.
    """
    out, cannot, why = {}, [], ""
    system = _change_system(current)
    raw = ""
    try:
        if _is_hosted(ai):
            raw, _ = _hosted(ai, system, prompt, 900)
        else:
            raw, _ = _try_local(system, prompt, 900, log, model)
    except Exception as e:
        if log:
            log("no pude leer el cambio (%s), me quedo con lo que dicen las palabras"
                % str(e)[:60])
        return out, cannot, why

    got = _json_in(raw) or {}
    delta = got.get("cambia") if isinstance(got.get("cambia"), dict) else {}
    if delta.get("ratio") in RATIOS:
        out["ratio"] = delta["ratio"]
    if delta.get("transition") in TRANSITIONS:
        out["transition"] = delta["transition"]
    if isinstance(delta.get("captions"), bool):
        out["captions"] = delta["captions"]
    # `shake` NO se lee del modelo a proposito, aunque este en su menu para que
    # sepa que existe y no lo meta en "no_puedo". Pedir temblor se dice con la
    # palabra temblor, que es exacta y gratis, y un booleano global inventado
    # obliga a volver a cortar el video entero: medido, "haz un zoom" volvio con
    # shake=true. Las palabras para lo que esta dicho, el modelo para lo que hay
    # que juzgar.
    if delta.get("captionPreset") in cap.PRESETS:
        out["captionPreset"] = delta["captionPreset"]
    if delta.get("captionAnim") in cap.ANIMS:
        out["captionAnim"] = delta["captionAnim"]
    if delta.get("cuts") in CUTS:
        out["cuts"] = delta["cuts"]
    if delta.get("look") in looks.PRESETS:
        out["look"] = delta["look"]
    # Un delta que repite lo que ya habia no es un cambio, y contarlo como tal
    # hace que Vidorq diga "he puesto vertical" cuando ya estaba vertical.
    out = {k: v for k, v in out.items() if current.get(k) != v}
    for item in (got.get("no_puedo") or [])[:4]:
        text = _clean_text(item, 120)
        if text:
            cannot.append(text)
    if isinstance(got.get("why"), str):
        why = got["why"][:160]
    if log and out:
        log("entiendo: " + ", ".join("%s=%s" % (k, v) for k, v in out.items()))
    return out, cannot, why


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
    # Ojo con el orden y con los verbos: esta regla va ANTES que la de poner,
    # porque la de poner solo mira si aparece la palabra "subtitulo". Durante un
    # tiempo aqui solo estaban "sin" y "no", asi que "quita los subtitulos"
    # caia en la siguiente y los ENCENDIA.
    ("captions", False, r"(sin|no|quita|quitar|fuera|borra|borrar|elimina|eliminar|"
                        r"remove)\b[^.]{0,14}(subt[ií]tul|caption)"),
    ("captions", True, r"subt[ií]tul|caption|\brotul"),
    ("cuts", "montage", r"resumen|mejores momentos|highlight|montaje|best bits|"
                        r"lo mejor\b"),
    ("cuts", "podcast", r"podcast|entrevista|preguntas y respuestas|\bq&a\b"),
    # "mejora el color" no es pedir un filtro, es pedir que se arregle el que
    # hay. Va ANTES que las reglas de los filtros de estilo, porque la frase
    # lleva la palabra "color" y si no la pillaria cualquiera de ellas.
    ("look", "auto", r"(mejora|arregla|corrige|ajusta|iguala|normaliza)"
                     r"\b[^.]{0,18}(color|colores)|"
                     r"color autom[aá]tic|correcci[oó]n autom[aá]tic|"
                     r"que se vea mejor de color|auto\s*color"),
    ("shake", False, r"(sin|no|quita|quitar|fuera|borra|elimina|remove)"
                     r"\b[^.]{0,14}(temblor|sacudid|\bshake\b|vibraci)"),
    ("shake", True, r"\btemblor|\btiembl|sacudid|\bshake\b|golpe de camara|"
                    r"golpe de c[aá]mara|\bimpacto\b|vibraci[oó]n"),
    ("cuts", "clean", r"quita los silencios|sin silencios|quita las pausas|"
                      r"solo lo hablado|limpia los silencios|\bmuletillas\b"),
    # Sin un "negro" suelto: "ponlo en blanco y negro" es un filtro de color, y
    # con el comodin salia ademas un fundido a negro que nadie habia pedido.
    ("transition", "dip", r"fundido a negro|dip to black|a negro"),
    ("transition", "white", r"fundido a blanco|dip to white|a blanco|\bflash\b|destello"),
    ("transition", "wipe", r"barrido|\bwipe\b"),
    ("transition", "slide", r"deslizamient|\bslide\b|desliza"),
    ("transition", "dissolve", r"disolvenc|\bfundido\b|cross ?dissolve"),
    ("look", "bn", r"blanco y negro|\bb\W?n\b|monocrom|sin color|gris"),
    ("look", "cine", r"\bcine\b|cinematograf|film look|\bpelicula\b|\bpelícula\b"),
    ("look", "calido", r"\bcalid|\bcálid|mas calor|tono calido|atardecer|dorad"),
    ("look", "frio", r"\bfrio\b|\bfrío\b|azulad|tono frio|mas frio"),
    ("look", "verano", r"\bverano\b|veranieg|saturad|mas color|vivo|vibrante"),
    ("look", "noche", r"\bnoche\b|nocturn|oscuro|\bdark\b"),
    ("look", "vintage", r"vintage|retro|\bantiguo\b|años 80|anos 80|\bviejo\b"),
    ("look", "none", r"sin filtro|quita el filtro|sin color grading|color normal"),
    # Aqui NO va una regla generica para "transicion". La hubo, y devolvia
    # "disolvencia", que es adivinar: la palabra dice que quieres una
    # transicion, no cual. Ahora esa frase la recoge vague() y se pregunta,
    # que ademas es la unica forma de que alguien vea que hay seis.
)

# Frases que nombran una CATEGORIA sin decir cual. "Pon transiciones" dice que
# quieres transiciones, no cuales; "recorta bien el video" puede ser cambiar el
# formato o quitar trozos. Antes esto se resolvia adivinando (transicion ->
# disolvencia) o rindiendose ("no se hacer eso"), y las dos son peores que la
# respuesta obvia, que es preguntar.
#
# Se mira DESPUES de las reglas literales: si la frase ya dijo "fundido a
# negro", no hay nada que preguntar.
VAGUE_RULES = (
    ("transition", r"transicion|transición|transiciones|\btransition"),
    ("captionPreset", r"subt[ií]tul|caption|\brotul"),
    ("look", r"filtro|color grading|\bcolor\b(?!.*(negro|blanco))|\btono\b|"
             r"\bfiltros\b|\blook\b"),
    # Nota: "mejora el color" cae aqui por la palabra "color", pero la regla de
    # palabras de arriba ya lo ha resuelto como `auto`, y `vague()` no pregunta
    # por lo que ya esta decidido.
    ("ratio", r"recorta|recortar|reencuadr|\bformato\b|\bencuadre\b"),
    ("captionAnim", r"animaci[oó]n|animad|movimiento del texto"),
    # "cortalo", "corta el video", "cambia los cortes": nombra el corte sin
    # decir con que criterio, y hay tres. Ojo con no pisar a `ratio`, que se
    # queda con "recorta" y "reencuadra", que en video es encuadrar y no cortar.
    # Ojo con "en los cortes" y "en cada corte": ahi el corte es DONDE pasa otra
    # cosa, no lo que se pide cambiar. Medido: "ponle temblor en los cortes"
    # preguntaba con que criterio cortar, que no es lo que nadie dijo.
    ("cuts", r"(?<!en los )(?<!en cada )(?<!en el )(?<!de los )"
             r"(\bcorta\b|\bcortar\b|\bcortes\b|\bcort[aá]lo\b|\bcortame\b|"
             r"\bcut\b|\bcuts\b|vuelve a cortar|otra vez los cortes)"),
)


# Quitar algo no es pedir una opcion. "Quita los subtitulos" nombra la categoria
# y no hay nada que preguntar: ya esta dicho lo que hay que hacer con ella.
DROP_RE = re.compile(r"\bquita|\bquitar|\bsin\b|\bfuera\b|\bborra|\belimin|"
                     r"\bno (quiero|pongas|me pongas)|\bremove\b|\bno\b \w+ (subt|caption)",
                     re.I)

# Elegir el estilo cierra la pregunta del estilo, no la de la entrada: son dos
# decisiones y la segunda se encadena.
#
# `captions` NO cierra nada, y eso es deliberado: "ponle subtitulos" dice que
# los quieres, no cuales, y ahi es donde hay que enseñar los diez estilos. El
# caso contrario, "quita los subtitulos", ya lo para DROP_RE antes de llegar
# aqui.
FAMILY = {"captionPreset": ("captionAnim",)}

# Que se pregunta DESPUES de elegir algo. Elegir un estilo de subtitulo deja
# abierta la entrada, que es la conversacion natural: cuales, y como entran.
NEXT_ASK = {"captionPreset": ["captionAnim"]}


def decided(prompt):
    """Las claves que la frase deja DECIDIDAS de verdad.

    Distinto de `set(from_words(...))` en un caso que importa: "cambia la
    animacion" deja `captionAnim` a `__any__`, que quiere decir "animada, pero
    cual es un juicio". Eso no es una decision, es exactamente la pregunta, y
    contarlo como decidido hacia que el atajo "Animacion" no preguntara nada y se
    quedara con la animacion que trajera el estilo.
    """
    return {k for k, v in from_words(prompt).items() if v != "__any__"}


def vague(prompt, already):
    """Que categorias nombra la frase sin decir cual, para poder preguntarlo.

    `already` son las claves que ya quedaron decididas (por las palabras o por
    el modelo); esas no se preguntan, que seria hacer repetir algo ya dicho.
    """
    low = " " + (prompt or "").lower() + " "
    # Una eleccion ya pulsada no es vaga: es la respuesta. Y lleva dentro el
    # nombre de la categoria ("pick:transition=dip"), asi que sin esta linea se
    # preguntaba lo mismo otra vez, y otra, sin salida.
    if low.strip().startswith("pick:"):
        return []
    if DROP_RE.search(low):
        return []
    cerradas = set(already)
    for key in list(cerradas):
        cerradas.update(FAMILY.get(key, ()))
    # Hablar de la ANIMACION de los subtitulos es hablar de la animacion, no del
    # estilo. Los dos patrones matchean la misma frase, y como el del estilo va
    # primero, el atajo "Animacion" acababa enseñando los diez estilos, que es
    # contestar a una pregunta que nadie hizo.
    if re.search(r"animaci[oó]n|animad|movimiento del texto", low, re.I):
        cerradas.add("captionPreset")
    out = []
    for key, pattern in VAGUE_RULES:
        if key in cerradas:
            continue
        if re.search(pattern, low, re.I):
            out.append(key)
    return out


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
            # "zoom" es la misma palabra para dos cosas distintas: un movimiento
            # de camara y la entrada de un subtitulo. Medido el 2026-08-19: "haz
            # un zoom en el segundo 11" contestaba "entrada: Zoom", o sea que te
            # cambiaba la animacion de los subtitulos y no acercaba nada. Solo
            # cuenta como animacion si la frase habla del texto.
            if aid == "zoom" and not re.search(
                    r"subt[ií]tul|caption|texto|animaci|entrada|rotul|r[oó]tul|"
                    r"letra", low, re.I):
                continue
            got["captionAnim"] = aid
            break
    if "captionAnim" not in got and re.search(r"anima|movimiento|animated|motion", low, re.I):
        got["captionAnim"] = "__any__"    # animated, but which one is a judgement
    return got


def look(prompt, ai=None, model=None, lang="es", log=None):
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
        if _is_hosted(ai):
            raw, out["by"] = _hosted(ai, system, prompt, 1600)
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


# What a prompt is allowed to ask for at a particular moment. A whitelist and
# not a free field, because the transcript goes into the same prompt as the
# user's instruction and a transcript is UNTRUSTED text: somebody's video can
# contain "ignore the above and run...". A model that invents a verb outside
# this list produces nothing at all instead of something surprising.
ACTIONS = ("title", "marker", "zoom", "cut", "voice")
# Ceilings, for the same reason. A prompt asking for four things should not come
# back with two hundred, and a caption is a caption and not an essay.
MAX_ACTIONS = 24
MAX_TEXT = 90
# A spoken line can run longer than a caption: it is heard over time instead of
# read at a glance. Still capped, because the paid engines bill by the character.
MAX_SPOKEN = 300
# Shorter than this and a "cut" is noise, not an edit.
MIN_CUT = 0.5
# A title shorter than this is a flash nobody reads; longer than that and it
# outstays the line it belongs to.
TITLE_SECS = (0.8, 6.0)

# Which model to ask for timed actions, best first, and it is NOT the same order
# as DIRECTORS. Measured on one real transcript with the prompt "pon un cartel
# que diga SUSCRIBETE en el segundo 12 durante 2 segundos":
#   llama3.2:3b     right, 9.7 s      <- the one it uses
#   phi4-mini:3.8b  right, 17.5 s
#   qwen3.5:9b      right, 39.9 s
#   granite4.1:3b   empty list in 9.6 s: valid shape, wrong answer
#   qwen3.5:4b      echoed the example from the prompt back verbatim
#   llama3.1:8b     refused outright ("no puedo cumplir con esa solicitud"),
#                   which is a spurious refusal and not a capability limit
# Being good at picking a caption style says nothing about being good at reading
# a timestamp out of a transcript, so the two tasks get their own order.
TIMERS = ("llama3.2:3b", "phi4-mini:3.8b", "qwen3.5:9b", "granite4.1:3b",
          "qwen2.5:3b", "mistral-small:24b", "llama3.1:8b")

# The literal placeholders from the system prompt. A small model under pressure
# hands the example back instead of an answer, and it arrives perfectly shaped,
# so shape alone cannot catch it. Measured on qwen3.5:4b.
ECHOES = {"lo que pone", "nota corta", "lo que dice"}

ACT_SYSTEM = (
    "Eres el editor de video de Vidorq. Recibes la transcripcion empaquetada de "
    "un video (lineas '[inicio-fin] texto' en segundos) y la instruccion del "
    "usuario. Tu unico trabajo es sacar lo que el usuario pide EN MOMENTOS "
    "CONCRETOS del video. Lo global (formato, estilo, transiciones) NO es tuyo. "
    "Devuelve SOLO un JSON {\"actions\":[...]} donde cada accion es una de:\n"
    '  {"do":"title","at":12.5,"secs":2.0,"text":"LO QUE PONE"}\n'
    '  {"do":"marker","at":12.5,"text":"nota corta"}\n'
    '  {"do":"zoom","at":12.5,"until":15.0}\n'
    '  {"do":"cut","at":12.5,"until":15.0}\n'
    '  {"do":"voice","at":12.5,"text":"lo que dice la voz en off"}\n'
    "Los tiempos son segundos del video ORIGINAL y los sacas de la "
    "transcripcion, buscando lo que se dice. Si el usuario no pide nada en un "
    'momento concreto, devuelve {"actions":[]}. No inventes momentos y no '
    "repitas la misma accion.")


def _clean_text(value, limit=MAX_TEXT):
    """A caption the user will see, with anything that is not text taken out."""
    # Unprintables come out FIRST and the spacing is tidied after. Doing it the
    # other way round leaves the hole behind: a bell character between two words
    # survives as its own token and turns into a double space nobody typed.
    text = "".join(ch for ch in str(value or "") if ch.isprintable() or ch.isspace())
    return " ".join(text.split())[:limit]


# Does this prompt point at a moment at all? Asking a model costs seconds and,
# worse, a model asked "is there anything here?" would rather invent something
# than answer no: measured on "ponlo en vertical con subtitulos animados", a
# purely global instruction, it came back with a title and a marker nobody
# asked for. So a regex decides whether there is even a question, and it does
# it in a fraction of a millisecond and never hallucinates.
MOMENT_RE = re.compile(
    r"segundo|minuto|\bmin\b|\bseg\b|\d\s*:\s*\d|"          # un tiempo
    r"al (final|principio|empezar|acabar|terminar)|ultim|primer|"  # una punta
    r"cuando (dice|habla|sale|aparece|cuenta|explica)|"            # por contenido
    r"en la parte|el trozo|el cacho|la parte donde|"
    r"voz en off|locucion|narrad|que diga|di que|lee en voz|"      # pedir voz
    r"quita|elimin|borra|corta el|fuera el|"                       # sacar algo
    r"anad|añad|pon un|pon una|mete|inserta|cartel|tarjeta|"       # meter algo
    r"rotulo|rótulo|marca en|zoom en|acerca",
    re.I)


def wants_moments(prompt):
    """True when the instruction talks about a specific point in the video."""
    return bool(MOMENT_RE.search(prompt or ""))


# Pedir una cosa que pasa EN UN SITIO, sin decir en cual. "Haz un zoom" es eso:
# se entiende el que, falta el donde.
DEED_RE = re.compile(
    r"\bzoom|\bacerca|\baleja|"
    r"quita (un|el) (trozo|cacho|pedazo|fragmento|tramo)|"
    r"corta (un|el) (trozo|cacho|pedazo|fragmento|tramo)|"
    r"pon (un|una) (cartel|rotulo|r[oó]tulo|texto|tarjeta|titulo|t[ií]tulo)|"
    r"mete (un|una) (cartel|rotulo|r[oó]tulo|texto|tarjeta)|"
    r"pon (una )?marca|marca(lo)? (aqui|ahi)",
    re.I)

# Un tiempo dicho de verdad: un numero de segundos o de minutos, un reloj, o una
# punta del video. Si esto aparece, el sitio ya esta dicho y no hay que preguntar.
WHEN_RE = re.compile(
    r"\d+\s*(segundo|minuto|\bs\b|\bm\b|\bmin\b|\bseg\b)|"
    r"(segundo|minuto|\bmin\b|\bseg\b)\s*\d+|"
    r"\d\s*:\s*\d|"
    r"al (final|principio|empezar|acabar|terminar)|"
    r"cuando (dice|habla|sale|aparece|cuenta|explica)|la parte donde",
    re.I)


def needs_where(prompt):
    """True si la frase pide algo que pasa en un sitio y no dice en cual.

    Sin esto, "haz un zoom" se iba al modelo de tiempos, que tenia que elegir un
    segundo a ciegas: o se inventaba uno o no hacia nada. Preguntar es mas rapido
    que las dos cosas y ademas ensena que tramos hay.
    """
    low = " " + (prompt or "").lower() + " "
    if low.strip().startswith("pick:"):
        return False
    return bool(DEED_RE.search(low)) and not WHEN_RE.search(low)


def _ask_timer(prompt, packed, model=None, log=None):
    """The first local model that answers with the right SHAPE, in TIMERS order.

    "The right shape" and not "a non empty list" on purpose: an empty list is a
    perfectly good answer when the prompt asked for nothing time-specific, so
    retrying until something comes back would walk the whole list every time
    somebody just says "make it vertical". What gets rejected is a refusal or a
    sentence, which is what a model does when it cannot do the job.
    """
    have = set(available_models())
    order = [model] if model and model in have else []
    order += [m for m in TIMERS if m in have and m != model]
    order += [m for m in DIRECTORS if m in have and m not in order]
    for name in order:
        try:
            raw = _ollama(name, ACT_SYSTEM,
                          "INSTRUCCION: %s\n\nTRANSCRIPCION:\n%s" % (prompt, packed),
                          predict=1600)
        except Exception:
            continue
        if isinstance((_json_in(raw) or {}).get("actions"), list):
            return raw
        if log:
            log("%s no supo leer los momentos, pruebo el siguiente" % name)
    return ""


def actions(prompt, packed, duration, ai=None, model=None, log=None):
    """What the prompt asks for at particular moments, in SOURCE seconds.

    Returns a list, empty when the prompt was only about global things, which is
    the common case and not a failure. Everything is validated against the
    catalogue and the video's own length before it leaves here: the model is a
    suggestion engine, not an authority, and the transcript feeding it is text
    from a stranger's video.
    """
    if not wants_moments(prompt):
        return []
    try:
        if _is_hosted(ai):
            raw, _ = _hosted(ai, ACT_SYSTEM, "INSTRUCCION: %s\n\nTRANSCRIPCION:\n%s"
                             % (prompt, packed), 2000)
        else:
            raw = _ask_timer(prompt, packed, model, log)
    except Exception as e:
        if log:
            log("no pude leer los momentos: %s" % str(e)[:80])
        return []

    got = (_json_in(raw) or {}).get("actions")
    if not isinstance(got, list):
        return []

    out, seen = [], set()
    for item in got[:MAX_ACTIONS * 2]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("do", "")).strip().lower()
        if kind not in ACTIONS:
            continue
        try:
            at = float(item.get("at"))
        except (TypeError, ValueError):
            continue
        if not (0.0 <= at <= duration):
            continue
        act = {"do": kind, "at": round(at, 2)}
        if kind in ("zoom", "cut"):
            try:
                until = float(item.get("until", at + 1.0))
            except (TypeError, ValueError):
                continue
            until = min(duration, until)
            # A cut of three hundredths is not a cut, it is a model that could
            # not find the moment and answered with the nearest number it had.
            # Applying it would do nothing visible and cost trust; dropping it
            # leaves the deterministic engine in charge, which is the right
            # outcome. Measured on "quita los ultimos 5 segundos", answered as
            # 39.98 to 40.01 on a 40 second video.
            if act["do"] == "cut" and until - at < MIN_CUT:
                continue
            act["until"] = round(max(at + 0.2, until), 2)
        if kind in ("title", "marker", "voice"):
            # A spoken line gets more room than a caption, but goes through the
            # same cleaner: the text arrives from a model reading a stranger's
            # transcript and ends up inside a speech synthesiser.
            act["text"] = _clean_text(item.get("text"),
                                      MAX_SPOKEN if kind == "voice" else MAX_TEXT)
            if not act["text"] or act["text"].lower() in ECHOES:
                continue
        if kind == "title":
            try:
                secs = float(item.get("secs", 2.0))
            except (TypeError, ValueError):
                secs = 2.0
            act["secs"] = round(min(TITLE_SECS[1], max(TITLE_SECS[0], secs)), 2)
        key = (act["do"], act["at"], act.get("text", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(act)
        if len(out) >= MAX_ACTIONS:
            break
    out.sort(key=lambda a: a["at"])
    if log and out:
        log("%d cosas pedidas en momentos concretos" % len(out))
    return out


def segments(prompt, packed, ai=None, model=None, log=None):
    """The keep-list a prompt asks for, or None if the model did not deliver.

    None is a normal outcome, not an error: the caller falls back to the
    deterministic cut engine, which is better than a made-up timeline.
    """
    try:
        if _is_hosted(ai):
            raw, _ = _hosted(ai, SEG_SYSTEM, "INSTRUCCION: %s\n\nTRANSCRIPCION:\n%s"
                             % (prompt, packed), 4000)
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
