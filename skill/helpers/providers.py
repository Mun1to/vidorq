"""Where the thinking happens: one call, several providers.

Vidorq needs one thing from a language model, and it is not an agent: a prompt
goes in, a JSON edit plan comes out. That is a low bar, which is why this can be
pointed at almost anything, from a 3B model on the user's own graphics card to
the biggest hosted model they are willing to pay for.

Five protocols cover the whole field, so there are five implementations here
and not one per vendor:

  ollama      the local instance. No key, no network, the default.
  anthropic   /v1/messages, x-api-key, system as its own field.
  gemini      /v1beta/models/<model>:generateContent.
  openai      /v1/chat/completions. This one is the lingua franca: OpenAI,
              OpenRouter, Groq, DeepSeek, xAI, Together, LM Studio and
              llama.cpp all speak it, so "custom" plus a base URL reaches
              anything not listed by name.
  cli         a coding-agent command line that is already installed and already
              logged in. No API key: it runs on the SUBSCRIPTION the user is
              paying for anyway.

That last one used to say, right here, that coding agents "are programs that
drive an editor, not endpoints that answer a prompt, and there is nothing for
Vidorq to call". That was wrong, and it was measured wrong: `claude -p`,
`codex exec` and `gemini -p` each take a prompt on stdin and print an answer,
which is the entire contract this file needs. Paying for an API key while a
subscription sits unused was a worse answer than checking.

Two things make that safe, and both are load-bearing. These are AGENTS, with
file tools, and the prompt they get carries a transcript from a stranger's
video. So the prompt goes in on STDIN, never as an argument, and the tools are
switched off with the flags each one offers, and the whole thing runs in an
empty scratch folder. Measured: fed a transcript whose middle line orders it to
create a file, Claude Code returned the JSON and created nothing.

Keys never appear in a log line or an error message here. They live in
%APPDATA%/Vidorq/config.json, which is outside the repo, and the only thing that
ever leaves this file with one attached is the request itself.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

# label     what the interface shows
# protocol  which of the four request shapes to build
# base      default endpoint root; "custom" asks the user for it
# key_url   where a human goes to get a key, because "get an API key" without a
#           link is a small cruelty
# default   a sane model to start on, so a fresh install is one field away from
#           working instead of two
PROVIDERS = {
    "local": {
        "label": "Ollama local",
        "protocol": "ollama", "base": "", "needs_key": False,
        "key_url": "", "default": "",
        "note": {"es": "Gratis, sin clave y sin salir de tu maquina. Lo que trae de fabrica.",
                 "en": "Free, no key, never leaves your machine. What ships by default."},
    },
    "anthropic": {
        "label": "Anthropic",
        "protocol": "anthropic", "base": "https://api.anthropic.com/v1",
        "needs_key": True, "key_url": "https://console.anthropic.com/settings/keys",
        "default": "claude-sonnet-5",
        "note": {"es": "Clave de la API, que se paga por tokens y NO va incluida en la "
                       "suscripcion de Claude.ai.",
                 "en": "An API key, billed per token. A Claude.ai subscription does NOT "
                       "include it."},
    },
    "openai": {
        "label": "OpenAI",
        "protocol": "openai", "base": "https://api.openai.com/v1",
        "needs_key": True, "key_url": "https://platform.openai.com/api-keys",
        "default": "gpt-4.1-mini",
        "note": {"es": "Clave de la API de OpenAI.", "en": "An OpenAI API key."},
    },
    "openrouter": {
        "label": "OpenRouter",
        "protocol": "openai", "base": "https://openrouter.ai/api/v1",
        "needs_key": True, "key_url": "https://openrouter.ai/keys",
        "default": "anthropic/claude-sonnet-4.5",
        "note": {"es": "Una sola clave para cientos de modelos de casi todos los "
                       "proveedores. El que mas cunde si vas a probar varios.",
                 "en": "One key for hundreds of models across nearly every vendor. The "
                       "best value if you plan to try several."},
    },
    "gemini": {
        "label": "Google Gemini",
        "protocol": "gemini", "base": "https://generativelanguage.googleapis.com/v1beta",
        "needs_key": True, "key_url": "https://aistudio.google.com/apikey",
        "default": "gemini-2.5-flash",
        "note": {"es": "Clave de Google AI Studio.", "en": "A Google AI Studio key."},
    },
    # --- Las que van con la suscripcion que ya pagas, sin clave de API ------
    #
    # `cmd` es la invocacion sin el prompt: el prompt entra SIEMPRE por stdin.
    # `model_flag` es como se le dice que modelo, o "" si no se le dice.
    # Los flags de apagar herramientas no son opcionales, ver la cabecera.
    "claude-cli": {
        "label": "Claude Code (tu suscripcion)",
        "protocol": "cli", "base": "", "needs_key": False, "key_url": "",
        "default": "",
        "cmd": ["claude", "-p", "--tools", "", "--permission-mode", "plan"],
        "model_flag": "--model",
        "note": {"es": "Usa el Claude Code que ya tienes instalado y con sesion "
                       "iniciada, asi que gasta de tu suscripcion y NO de una clave "
                       "de API. Sin clave, sin configurar nada.",
                 "en": "Uses the Claude Code you already have installed and signed "
                       "in, so it spends your subscription and NOT an API key. No "
                       "key, nothing to set up."},
    },
    "codex-cli": {
        "label": "Codex (tu ChatGPT)",
        "protocol": "cli", "base": "", "needs_key": False, "key_url": "",
        "default": "",
        "cmd": ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only"],
        "model_flag": "--model",
        "note": {"es": "El Codex de OpenAI que ya tienes instalado. Gasta de tu "
                       "suscripcion de ChatGPT, no de una clave.",
                 "en": "The OpenAI Codex you already have installed. Spends your "
                       "ChatGPT subscription, not a key."},
    },
    "gemini-cli": {
        "label": "Gemini CLI (tu cuenta)",
        "protocol": "cli", "base": "", "needs_key": False, "key_url": "",
        "default": "",
        # Sin `-p`: ese flag QUIERE el prompt pegado detras, y aqui el prompt
        # entra por stdin. Con `-p` vacio la CLI muere con "Not enough arguments".
        "cmd": ["gemini", "--skip-trust", "--approval-mode", "plan"],
        "model_flag": "-m",
        "note": {"es": "El Gemini CLI que ya tienes instalado, con tu cuenta de "
                       "Google y su capa gratuita.",
                 "en": "The Gemini CLI you already have installed, on your Google "
                       "account and its free tier."},
    },
    "custom": {
        "label": "Compatible con OpenAI",
        "protocol": "openai", "base": "", "needs_key": True, "key_url": "",
        "default": "",
        "note": {"es": "Cualquier endpoint que hable el protocolo de OpenAI: Groq, "
                       "DeepSeek, xAI, Together, LM Studio, llama.cpp. Pon la URL base.",
                 "en": "Any endpoint speaking OpenAI's protocol: Groq, DeepSeek, xAI, "
                       "Together, LM Studio, llama.cpp. Give it the base URL."},
    },
}

DEFAULT_PROVIDER = "local"
TIMEOUT = 180


def catalogue(lang="es"):
    """What the interface needs to draw the provider picker."""
    out = []
    for pid, p in PROVIDERS.items():
        out.append({"id": pid, "label": p["label"], "needsKey": p["needs_key"],
                    "keyUrl": p["key_url"], "default": p["default"],
                    "custom": pid == "custom",
                    "cli": p["protocol"] == "cli",
                    "note": p["note"].get(lang, p["note"]["es"]),
                    # Una CLI que no esta instalada se ensena apagada en vez de
                    # esconderse: saber que existe es la mitad del valor.
                    "installed": cli_ready(pid)})
    return out


def cli_ready(provider):
    """True si esta es una CLI y de verdad esta en el PATH."""
    p = PROVIDERS.get(provider) or {}
    if p.get("protocol") != "cli":
        return True
    return bool(shutil.which(p["cmd"][0]))


def _post(url, body, headers, timeout=TIMEOUT):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers=dict(headers, **{"Content-Type": "application/json"}),
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # The body of a rejected request says WHY, and "HTTP Error 401" on its own
        # sends people hunting through their firewall instead of their key.
        detail = ""
        try:
            detail = e.read().decode()[:300]
        except Exception:
            pass
        raise RuntimeError("%s respondio %s. %s" % (_host(url), e.code, detail)) from None


def _get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _host(url):
    part = url.split("//", 1)[-1]
    return part.split("/", 1)[0]


def _root(provider, base_url=""):
    p = PROVIDERS.get(provider) or PROVIDERS[DEFAULT_PROVIDER]
    root = (base_url or p["base"] or "").rstrip("/")
    if root and not root.startswith("http"):
        root = "http://" + root
    return p, root


# --------------------------------------------------------------------------- #
# The four request shapes
# --------------------------------------------------------------------------- #
def _ollama(root, model, system, user, tokens, timeout):
    from vision import ollama_host
    d = _post((root or ollama_host()) + "/api/generate",
              {"model": model, "system": system, "prompt": user, "stream": False,
               # A reasoning model spends its first few hundred tokens reasoning
               # and hands back an empty answer if the budget is tight. Measured
               # three times on three different models; see docs/INTELIGENCIA.md.
               "options": {"temperature": 0.1, "num_predict": tokens}},
              {}, timeout)
    return (d.get("response") or d.get("thinking") or "").strip()


def _anthropic(root, key, model, system, user, tokens, timeout):
    d = _post(root + "/messages",
              {"model": model, "max_tokens": tokens, "system": system,
               "messages": [{"role": "user", "content": user}]},
              {"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout)
    return "".join(b.get("text", "") for b in d.get("content", [])).strip()


def _openai(root, key, model, system, user, tokens, timeout):
    d = _post(root + "/chat/completions",
              {"model": model, "max_tokens": tokens, "temperature": 0.1,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]},
              {"Authorization": "Bearer " + key,
               # OpenRouter asks callers to identify themselves, and being a good
               # citizen costs one header.
               "HTTP-Referer": "https://github.com/Mun1to/vidorq",
               "X-Title": "Vidorq"}, timeout)
    choices = d.get("choices") or []
    if not choices:
        raise RuntimeError("la respuesta no traia ninguna opcion")
    msg = choices[0].get("message") or {}
    return (msg.get("content") or "").strip()


def _gemini(root, key, model, system, user, tokens, timeout):
    # The key rides in a header, not the query string, so it cannot end up in a
    # proxy log or a browser history.
    d = _post("%s/models/%s:generateContent" % (root, model),
              {"systemInstruction": {"parts": [{"text": system}]},
               "contents": [{"role": "user", "parts": [{"text": user}]}],
               "generationConfig": {"temperature": 0.1, "maxOutputTokens": tokens}},
              {"x-goog-api-key": key}, timeout)
    for cand in d.get("candidates", []):
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if text:
            return text
    return ""


def _cli(p, model, system, user, timeout):
    """Ask a coding-agent command line that is already signed in.

    The prompt goes in on stdin. Not for elegance: it carries a transcript
    lifted from somebody else's video, it can be tens of kilobytes, and Windows
    has a hard limit on a command line that a long video would walk straight
    into. Stdin has neither problem and no quoting to get wrong.

    The working directory is an empty temp folder, so the agent has no project
    around it to read, no CLAUDE.md to obey and nothing of the user's to touch
    if a line in the transcript talks it into trying.
    """
    exe = shutil.which(p["cmd"][0])
    if not exe:
        raise RuntimeError("%s no esta instalado en este equipo" % p["cmd"][0])
    cmd = [exe] + p["cmd"][1:]
    if model and p.get("model_flag"):
        cmd += [p["model_flag"], model]
    work = tempfile.mkdtemp(prefix="vidorq_cli_")
    try:
        r = subprocess.run(
            cmd, input=("%s\n\n%s" % (system, user)).encode("utf-8"),
            cwd=work, capture_output=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise RuntimeError("%s tardo mas de %ds en contestar"
                           % (p["cmd"][0], timeout)) from None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    out = r.stdout.decode("utf-8", "replace").strip()
    if r.returncode != 0 and not out:
        err = r.stderr.decode("utf-8", "replace").strip()[:300]
        raise RuntimeError("%s fallo: %s" % (p["cmd"][0], err or "sin decir por que"))
    return out


def complete(provider, model, system, user, key="", tokens=4000, base_url="",
             timeout=TIMEOUT):
    """One answer from whichever provider was chosen. Raises on refusal."""
    p, root = _root(provider, base_url)
    # Una CLI ya sabe con que modelo habla, asi que no exigirle uno: pedirselo
    # al usuario seria pedirle un dato que su propia herramienta ya tiene.
    if p["protocol"] == "cli":
        return _cli(p, model, system, user, timeout)
    model = model or p["default"]
    if not model:
        raise RuntimeError("falta decir que modelo usar en %s" % p["label"])
    if p["needs_key"] and not key:
        raise RuntimeError("%s necesita una clave de API" % p["label"])
    if p["protocol"] != "ollama" and not root:
        raise RuntimeError("falta la URL base del proveedor")
    if p["protocol"] == "ollama":
        return _ollama(root, model, system, user, tokens, timeout)
    if p["protocol"] == "anthropic":
        return _anthropic(root, key, model, system, user, tokens, timeout)
    if p["protocol"] == "gemini":
        return _gemini(root, key, model, system, user, tokens, timeout)
    return _openai(root, key, model, system, user, tokens, timeout)


# --------------------------------------------------------------------------- #
# What can I choose?
# --------------------------------------------------------------------------- #
def models(provider, key="", base_url=""):
    """Model ids the provider says it has, newest-looking first.

    Asked live rather than shipped as a list, because a hardcoded model list is
    wrong within weeks and then the app is telling the user lies about what they
    can pick. An unreachable provider returns nothing rather than raising: a
    picker with no options is a smaller problem than a settings screen that
    cannot open.
    """
    p, root = _root(provider, base_url)
    try:
        if p["protocol"] == "cli":
            return []          # el modelo lo elige la propia herramienta
        if p["protocol"] == "ollama":
            from vision import available_models
            return list(available_models())
        if p["protocol"] == "anthropic":
            d = _get(root + "/models?limit=100",
                     {"x-api-key": key, "anthropic-version": "2023-06-01"})
            return [m["id"] for m in d.get("data", []) if m.get("id")]
        if p["protocol"] == "gemini":
            d = _get(root + "/models", {"x-goog-api-key": key})
            return [m["name"].split("/")[-1] for m in d.get("models", [])
                    if "generateContent" in (m.get("supportedGenerationMethods") or [])]
        head = {"Authorization": "Bearer " + key} if key else {}
        d = _get(root + "/models", head)
        return [m["id"] for m in d.get("data", []) if m.get("id")]
    except Exception:
        return []
