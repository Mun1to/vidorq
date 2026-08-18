# Vidorq

### The open-source AI video editor that lives inside DaVinci Resolve Free.

> "Edit this in vertical, YouTube-short style, cut it well, and give the subtitles animations."
>
> That is the whole workflow. You describe the edit. Vidorq does it.

[![DaVinci Resolve](https://img.shields.io/badge/DaVinci%20Resolve-Free-00b359.svg)](https://www.blackmagicdesign.com/products/davinciresolve)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## Quick start

Five steps. About ten minutes, most of it downloading.

### 1. What you need first

| | |
| --- | --- |
| **Windows** | that is what this is tested on |
| **DaVinci Resolve** | the **free** version is enough, no Studio licence |
| **Python 3.10+** | `python --version` has to answer |
| **ffmpeg** | `ffmpeg -version` has to answer. [Download](https://www.gyan.dev/ffmpeg/builds/) |
| **Ollama** *(optional)* | only if you want prompts to work with no API key. [ollama.com](https://ollama.com) |

### 2. Get the two repositories, side by side

Vidorq talks to Resolve through a bridge that lives in its own project, so clone
both into the **same folder**:

```
git clone https://github.com/Mun1to/vidorq
git clone https://github.com/hiteshK03/davinci-resolve-mcp
```

```
your-folder/
  vidorq/
  davinci-resolve-mcp/
```

The installer finds its neighbour on its own. If you keep the bridge somewhere
else, set `VIDORQ_BRIDGE` to the full path of its `src/CursorBridge.py`.

### 3. Install the Python side

```
cd vidorq
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 4. Put Vidorq in Resolve's menu

```
powershell -ExecutionPolicy Bypass -File resolve\instalar.ps1
```

Once, not once per project. It prints where it found the bridge and which Python
it will use, and it adds a single entry to Resolve.

### 5. Use it

Open DaVinci Resolve, open a project, then click:

**`Workspace > Scripts > Vidorq`**

That one click starts the engine, opens the Vidorq window and leaves the bridge
listening. Then:

1. Drag your video onto the window.
2. Choose **MP4** or **Timeline in Resolve** as the output.
3. Write what you want, or pick a preset.
4. Hit **Edit video**.

If the timeline is the output, you will watch it build itself inside Resolve.

---

## What it actually does

**Cuts.** Word-level transcription with local Whisper, then dead air, isolated
filler sounds and repeated takes come out. Cuts land on a still moment rather
than mid-gesture, and jump cuts get hidden with a small alternating zoom.

**Subtitles.** Ten styles and nine entrance animations, mixed freely, in both
outputs. Three styles carry a real halo from Fusion's Glow node. In Resolve they
arrive as **editable** Text+ titles on their own track, not burned into the
picture.

**Vertical.** 9:16, 4:5, 1:1 or 16:9. The crop is aimed at the **face** by a
227 KB detector that runs on the CPU, so a vertical short does not cut the
speaker out of frame. There is a manual slider when you would rather choose.

**Prompts.** "vertical, short style, animated subtitles" sets the frame shape,
the subtitle style, the animation, the transition and the kind of cut. It also
takes instructions aimed at **one moment**: "put a card saying SUBSCRIBE at
second 12", "zoom in where he talks about the price", "cut that bit out". It
works with **no API key** on a local model, and it never trusts the model
blindly: verbs come from a closed list, times are checked against the real
length, and anything invented produces nothing at all.

**Previews.** Every look, entrance and crop is shown as a picture before you
commit to it, made by the same renderer that makes the final video, on your own
footage, with the crop aimed where it will really be aimed.

## Which AI thinks about your prompt

Out of the box it is the **Ollama on your own machine**: free, no key, and
nothing leaves the computer. In `Settings > Model and AI` you can point it at:

| provider | notes |
| --- | --- |
| **Ollama local** | the default, no key |
| Anthropic | an API key from the console, billed per token. A Claude.ai subscription is **not** API access |
| OpenAI | |
| **OpenRouter** | one key, hundreds of models |
| Google Gemini | |
| **OpenAI-compatible** | give it a base URL: Groq, DeepSeek, xAI, LM Studio, llama.cpp |

The model list is asked of the provider live, so it is whatever they have today.
Keys are stored per provider in `%APPDATA%/Vidorq/config.json`, outside this
repository, and the engine never hands one back out.

## From the AI agent you already use

Vidorq is also a **skill**. Your agent reads `skill/SKILL.md` and drives the same
engine and the same Resolve:

```
mklink /J "%USERPROFILE%\.claude\skills\vidorq" "<path>\vidorq\skill"
```

Same idea for Codex or OpenCode with their own skills folder. In Cursor or
Antigravity, open the repo and ask the agent to read `skill/SKILL.md`.

## Honest limits

Resolve Free's scripting API is missing things, and pretending otherwise wastes
your afternoon. Measured on 21.0.4.5:

- **No transitions by API.** They exist in the MP4 output only.
- **No typewriter reveal.** Text+ accepts the parameters and ignores them.
- **No gradient fill** inside a title comp. It crashed Resolve, so it is not
  attempted.
- Keyframes are not settable by API. Vidorq works around this by writing the
  animation into a `.comp` file, which Resolve imports splines and all.

Everything above was checked by rendering it and looking at the frame. The
details are in [docs/SUBTITULOS.md](docs/SUBTITULOS.md) and
[docs/INTELIGENCIA.md](docs/INTELIGENCIA.md) (Spanish).

## Something broke

| what you see | what it means |
| --- | --- |
| "The engine is missing av, faster_whisper..." | it started with the wrong Python. Close it and use `engine\start_engine.bat` |
| "I could not talk to Resolve" | Resolve is not open, or nobody clicked `Workspace > Scripts > Vidorq` this session |
| The prompt is ignored | no local model and no key. Install Ollama or add a key in Settings |

## Don't trust it, check it

Open source only helps if somebody actually reads the code, and almost nobody
does. So instead of asking you to trust this project, here is the prompt to check
it: point your own AI agent at this repository and get a security report, in your
language, in a few minutes, even if you do not know how to program.

**[Open AI-AUDIT.md](AI-AUDIT.md)** and paste it into Claude Code, Codex, Cursor,
Copilot or whatever you use. It is the same prompt in every public repository
here, so you can compare.

> **ES:** No hace falta que te fíes. Abre [AI-AUDIT.md](AI-AUDIT.md), pega ese texto en tu IA
> y te dirá en tu idioma qué hace este programa de verdad: qué envía por internet, qué toca
> en tu ordenador y qué ejecuta al instalarse.

## More

- [What Vidorq understands about a video](docs/INTELIGENCIA.md) (Spanish)
- [Subtitles, and the walls in Resolve Free](docs/SUBTITULOS.md) (Spanish)
- [Architecture](docs/ARQUITECTURA.md) (Spanish)
- [Roadmap](docs/METAS.md) (Spanish)

## License

MIT - use it however you want.
