# Vidorq

### The open-source AI video editor that lives inside DaVinci Resolve Free.

> "Edit this in vertical, YouTube-short style, cut it well, and give the subtitles animations."
>
> That is the whole workflow. You describe the edit. Vidorq does it.

[![DaVinci Resolve](https://img.shields.io/badge/DaVinci%20Resolve-Free-00b359.svg)](https://www.blackmagicdesign.com/products/davinciresolve)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1511%20checks-00b359.svg)](tests/)

**[vidorq site](https://mun1to.github.io/vidorq/)** (Spanish)

| | |
| --- | --- |
| **[Quick start](#quick-start)** | five steps, about ten minutes |
| **[What it actually does](#what-it-actually-does)** | cuts, subtitles, vertical, prompts, colour, voice |
| **[Which AI thinks about your prompt](#which-ai-thinks-about-your-prompt)** | Ollama, your existing CLI agent, or a key |
| **[From the AI agent you already use](#from-the-ai-agent-you-already-use)** | Vidorq as a skill |
| **[Where your stuff goes](#where-your-stuff-goes)** | what leaves the machine, and what does not |
| **[Honest limits](#honest-limits)** | what Resolve Free will not do, measured |
| **[How it is checked](#how-it-is-checked)** | the test suite, and what it proves |
| **[Something broke](#something-broke)** | the three usual ones |
| **[Don't trust it, check it](#dont-trust-it-check-it)** | audit this repo with your own AI |

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

**Got an NVIDIA card?** One more line, and it is the difference between waiting
and not waiting:

```
.venv\Scripts\pip install -r requirements-gpu.txt
```

Measured on one 10 minute 43 second video: **16 minutes** transcribing on the
CPU, **42 seconds** on the card, and on the card it uses the big model instead
of the small one, so it is more accurate as well. Skip it and everything still
works, just slower.

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

**Cuts.** Word-level transcription with local Whisper (`large-v3-turbo` on a
graphics card, `small` on a CPU), then dead air, isolated
filler sounds and repeated takes come out. Cuts land on a still moment rather
than mid-gesture, and jump cuts get hidden with a small alternating zoom.

**Subtitles.** Ten styles and eight entrance animations (plus none), mixed
freely, in both outputs. Three styles carry a real halo from Fusion's Glow node. In Resolve they
arrive as **editable** Text+ titles on their own track, not burned into the
picture.

**Vertical.** 9:16, 4:5, 1:1 or 16:9. The crop is aimed at the **face** by a
227 KB detector that runs on the CPU, so a vertical short does not cut the
speaker out of frame. There is a manual slider when you would rather choose.

**It keeps editing, and it answers.** The screen at the end is not a dead end,
it is a conversation: type the next change and it is applied on top of the edit
that exists, and every turn comes back saying what it did, what it could not do
here and why, and what it did not understand. When something only works in the
other output it offers to switch, instead of quietly doing nothing. No re-transcribing, no re-deciding the cuts, and the settings carry
over. Re-measured on 20-aug-2026, 30 s clip, captions on, MP4 out, on a laptop
with an RTX 5060: the first pass took 26 s and three changes on top of it took
11.2 s, 13.7 s and 12.7 s. The first pass is the one that transcribes; a change
re-renders but does not re-listen. Times are read on the clock of the EDIT, not
the original file, because
that is what you are looking at by then. In Resolve the previous version is
replaced rather than piled up next to it.

**Edit by reading.** The transcription already carries the second of every word,
so the panel paints all of them and you find a moment by reading instead of
dragging the playhead at it. Mark two words and it writes the same sentence you
could have typed ("cut the bit from second 12 to 19"), so there is one cutting
mechanism and not two. What the automatic cut already took out is shown struck
through, and clicking a word moves Resolve's playhead there, which is the part a
web page cannot do. The other half is **order**: the same panel lists the edit as
segments with what is said in each one, and you drag them somewhere else. That
is a permutation of the montage, so no model is asked anything.

**Undo.** The session keeps the montage *and* the settings from before each
turn, and one button goes back to both. Undoing the cut and leaving you with the
setting that same turn applied would not be undoing anything. One step, not a
stack: pressing it twice puts you back where you were.

**History.** Every edit leaves a row: when, which video, which project, what it
did and how long it took. The ones you stopped and the ones that failed go in
too, because a list that only kept the successes would tell a false story of the
day. Clicking a row reopens that video with its whole conversation behind it.

**Prompts.** "vertical, short style, animated subtitles" sets the frame shape,
the subtitle style, the animation, the transition and the kind of cut. It also
takes instructions aimed at **one moment**: "put a card saying SUBSCRIBE at
second 12", "zoom in where he talks about the price", "cut that bit out",
"put a voice at second 5 saying watch this". It
works with **no API key** on a local model, and it never trusts the model
blindly: verbs come from a closed list, times are checked against the real
length, and anything invented produces nothing at all.

**Previews and the gallery.** Every look, entrance and crop is shown as a
picture before you commit to it, made by the same renderer that makes the final
video, on your own footage, with the crop aimed where it will really be aimed.
The gallery puts all ten looks on one wall and the nine entrances animating over
the one you picked, so choosing is looking rather than reading names.

**Colour.** Eight filters, each defined once as ASC CDL numbers, and both
outputs read that one definition. They are not pixel for pixel identical, and
saying they were would be easy and wrong: measured on the same frame with the
warm filter, the MP4 moves it R+11.77 G+3.42 B-10.27 and the file Resolve
renders moves it R+14.87 G+5.54 B-6.92. Same direction, same intent, about
three levels out of 255 apart, because Resolve applies it inside its own
colour-managed pipeline and ffmpeg applies it to the encoded values. In Resolve
they land as an ordinary primary correction you can keep adjusting by hand, not
a baked-in look.

**Transitions.** Dissolve, wipe, slide and the rest in the MP4. In Resolve, the
three that only cover the cut - dip to black, dip to white and a short flash -
are built as animated layers on their own track, because Resolve's API has no
transitions of its own. Measured on three seams: the frame at each one comes
out pure black, against 102.60 average brightness two seconds earlier, and it
fades rather than jumping (138.60, 92.81, 22.78, 56.03, 139.57 across one
seam). Each one lasts the same in both outputs, off the same table, so a dip is
not half a second in the timeline and a third of one in the file. The ones that
need both shots blended stay MP4-only, and the picker says where each one lands
and switches the output for you rather than refusing after you press it.

**Voice.** A prompt can ask for a voice-over at a given second. Windows' own
synthesiser ships as the default, so it works with no key and no internet;
**ElevenLabs**, **OpenAI** and any OpenAI-compatible `/audio/speech` endpoint
are there when it needs to sound like a person. The original audio ducks
underneath the line. MP4 output only.

## Which AI thinks about your prompt

Out of the box it is the **Ollama on your own machine**: free, no key, and
nothing leaves the computer. In `Settings > Model and AI` you can point it at:

| provider | notes |
| --- | --- |
| **Ollama local** | the default, no key |
| **Claude Code** | the one you already have installed and signed in. Spends your **subscription**, asks for no key |
| **Codex** | same, on your ChatGPT subscription |
| **Gemini CLI** | same, on your Google account |
| Anthropic | an API key from the console, billed per token. A Claude.ai subscription is **not** API access - but the Claude Code row above is |
| OpenAI | |
| **OpenRouter** | one key, hundreds of models |
| Google Gemini | |
| **OpenAI-compatible** | give it a base URL: Groq, DeepSeek, xAI, LM Studio, llama.cpp |

The three command-line entries need nothing set up: if the tool is on your
PATH it lights up, and if it is not it shows greyed out. The prompt goes to them
on stdin with their tools switched off, in an empty scratch folder, because they
are agents and the transcript in that prompt came out of somebody else's video.

`Settings > Voice` is the same idea for speech: Windows' own voice by default,
then ElevenLabs, OpenAI or any OpenAI-compatible endpoint.

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

## Where your stuff goes

The engine is a small HTTP server on `127.0.0.1:9877`, so nothing of yours
leaves the machine unless you have set an API key and asked for a prompt. Four
details worth knowing, because "local" is not the same as "private":

- It answers the Vidorq window and refuses everything else. A local port is
  reachable from any page you happen to have open in a browser, and until it
  was fixed this one replied to all of them with `Access-Control-Allow-Origin:
  *`, so a website could have read `/history` (the paths of your videos and
  what you asked for), `/words` (a whole transcript) or simply stopped the
  engine mid-edit. Requests carrying an `Origin` that is not this machine now
  get a 403 before anything happens. Tools with no browser behind them - curl,
  your own agent, Python - are unaffected.
- Keys live in `%APPDATA%/Vidorq/config.json`, outside this repository, one per
  provider, and the engine never hands one back out. Checked rather than assumed:
  five fake keys were planted in a throwaway config and every GET endpoint was
  swept for them - sixteen endpoints, no leaks. The hole was somewhere else. A
  provider's own error body is relayed to the screen and written to the history,
  and OpenAI's 401 answers `Incorrect API key provided: sk-ant-C****...9f3a` -
  the first seven characters and the last four, coming straight back. Anthropic
  does not do it; a self-chosen OpenAI-compatible endpoint could do worse. The
  key we sent is now struck out of any error before it is shown or stored.
- Text that came from somewhere else cannot give orders. A transcript is
  somebody else's material and so is whatever a model writes back, and both get
  drawn into files that have their own syntax. All five places were checked by
  attacking them: the Fusion comp escapes quotes and braces and its structure
  does not move; the Windows voice passes the line, the voice and the
  destination as files rather than as PowerShell arguments, so a line carrying
  `"; Set-Content ...` is read aloud instead of run; and two that were not safe
  are now. A caption saying `{n8}` used to jump to the top of the frame, and
  one carrying a blank line used to split the .srt and forge an extra subtitle
  at second zero.
- The same transcript also goes into the prompt, next to your instruction, and
  there it is fenced and labelled as data. A video that says "ignore the above"
  out loud was tried: through Claude only the title that had actually been asked
  for came back. That is one model on one day, so it is not the defence. The
  defence is that nothing the model returns is trusted: five verbs are allowed
  and anything else is dropped, times must fall inside the video, and the text
  is capped and stripped. The fence just removes the easy path, and it cannot be
  closed from the inside - a video reading the closing marker aloud gets it
  taken out of the text.

## Honest limits

Resolve Free's scripting API is missing things, and pretending otherwise wastes
your afternoon. Measured on 21.0.4.5:

- **No transitions by API.** Worked around for the ones that only cover the
  cut, which are built as animated layers instead. Dissolve, wipe and slide
  have to blend both shots and stay MP4-only.
- **No audio by API**, so a voice-over also comes out in the MP4 only. Vidorq
  says so when it finishes rather than handing back a silent timeline that
  looks done.
- **No typewriter reveal.** Text+ accepts the parameters and ignores them.
- **No gradient fill** inside a title comp. It crashed Resolve, so it is not
  attempted.
- Keyframes are not settable by API. Vidorq works around this by writing the
  animation into a `.comp` file, which Resolve imports splines and all.

Everything above was checked by rendering it and looking at the frame. The
details are in [docs/SUBTITULOS.md](docs/SUBTITULOS.md) and
[docs/INTELIGENCIA.md](docs/INTELIGENCIA.md) (Spanish).

## How it is checked

A video editor fails quietly. A cut half a second off, a caption ten seconds
late, a montage that lost a sentence - none of them throw an error, they just
make the video worse, and you find out watching it. So the tests are not there
to make a badge green:

```
python tests/todas.py
```

```
test_relojes.py          409 cases          the two clocks, the cut engine, the safety nets
test_understanding.py    533 cases          what a sentence means, and what a button does
test_castellano.py       485 strings        every accent in the Spanish the app shows
test_idiomas.py           22 checks         Spanish and English say the same things
test_promesas.py          20 promises       this README matches the code
test_render.py            18 cases          a real video in, a real MP4 out
test_aprende.py           24 cases          reads a video back and names its style
```

Eleven seconds, no model, no network, no API key.

Three of those deserve a word. **`test_promesas.py`** reads this file and compares
its counts against the catalogues in the code, so a README that drifts out of
date fails the build rather than misleading you. And **`test_render.py`** is the
only one that can say the product works: it builds a video of four flat colour
blocks - red, green, blue, yellow, five seconds each - edits it with the real
engine, then **opens the resulting MP4 and reads the frames**. A cut that lands
half a second off shows a different colour, and the test sees it.

**`test_aprende.py`** closes a circle: it asks Vidorq to burn in captions with
a known style, then hands that MP4 back to the analyser as if it came from a
stranger. The analyser never sees the style name, only pixels. It recovers the
caption position to within 0.01 of the frame height on every preset tried,
and the cut rhythm of a twelve-shot video to the exact second.

Every rule in there was checked by deliberately breaking the code to watch the
test fail. A check that cannot fail is worse than no check, and one of them was
thrown out for exactly that: it asserted the vertical export leaves no black
bars, which turned out to be impossible in the MP4 path by construction.

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
