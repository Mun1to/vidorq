# Vidorq

### The open-source AI video editor that lives inside DaVinci Resolve Free.

> "Cut this podcast down and add an animated topic card every time the subject changes."
>
> That's the whole workflow. You describe the edit. Vidorq does it.

[![Status](https://img.shields.io/badge/status-foundation-orange.svg)](docs/METAS.md)
[![DaVinci Resolve](https://img.shields.io/badge/DaVinci%20Resolve-Free%20%2B%20Studio-00b359.svg)](https://www.blackmagicdesign.com/products/davinciresolve)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## Why

Video editing is overwhelming. Shortcuts, keyframes, effects, render settings - a single short can take over an hour, a gaming montage can take a full day. And if you want a free tool that produces professional results, you can spend a week just choosing the editor.

Meanwhile, we live in a time where you can build software with a prompt - but there is still no great open-source tool where you describe an edit in plain language and get a professional result inside a real NLE.

Vidorq is that tool. Built on top of DaVinci Resolve (the most powerful free editor in existence), driven by the AI assistant you already use.

## What makes it different

Most "AI video" tools are generic: one prompt, one template, one more piece of content slop. Vidorq is built around **taste training**:

- **You train it on YOUR style.** Feed it links to videos you admire (YouTube, TikTok, Reels). Vidorq analyzes their cut rhythm, text animations, pacing and hooks, and builds a style profile for your brand.
- **It edits like an editor, not like a filter.** Transcript-first reasoning: the AI reads your footage word by word (with timestamps), finds the good moments, cuts on speech boundaries, and self-reviews the result before showing it to you.
- **Cinematic animations from prompts.** Animations are code (React/CSS via Remotion, Fusion templates) rendered as transparent overlays - clean, brand-consistent, reusable.
- **Bring your own keys.** Connect Claude, Gemini or OpenAI with your own API keys. Or run fully local with Whisper, Demucs and Ollama models. No subscription, no lock-in.

## How it works

```
You: "Cut the dead air and subtitle this in my style"
        |
        v
  AI assistant (Claude Code, Cursor, any MCP client)
        |
        |  MCP tools
        v
  Vidorq orchestration layer
        |                \
        |                 \-> Animation engine (Remotion / Fusion templates)
        |                 \-> Local AI (Whisper, Demucs, rembg)
        |                 \-> Style profile (your taste training)
        v
  DaVinci Resolve bridge (works on the FREE version)
        |
        v
  Your timeline, edited.
```

The Resolve connection builds on [davinci-resolve-mcp](https://github.com/hiteshK03/davinci-resolve-mcp), the only MCP bridge that works on Resolve Free (162 tools: timeline, clips, color, Fusion, rendering, local AI replacements for Studio features).

## Status

Foundation stage. Architecture and roadmap are being defined in the open:

- [Vision](docs/VISION.md) (Spanish)
- [Architecture](docs/ARQUITECTURA.md) (Spanish)
- [Taste training system](docs/ENTRENAMIENTO.md) (Spanish)
- [Goals roadmap](docs/METAS.md) (Spanish)
- [Resources](docs/RECURSOS.md) (Spanish)

## License

MIT - use it however you want.
