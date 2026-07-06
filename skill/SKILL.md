# Vidorq skill — edición por IA (v1)

> Pipeline de edición que corre desde Claude Code. v1 usa el **backend de render directo**
> (PyAV + NVENC), independiente de DaVinci Resolve. El backend Resolve (timeline editable)
> se añade cuando el puente esté disponible. Documentación interna en español (regla D).

## Flujo

```
video crudo ──► transcribe.py ──► transcript.json + takes_packed.md
                                          │
                            (el LLM lee y razona el corte)
                                          ▼
                                     edl.json  ──► vidorq_render.py ──► final.mp4
                                    (keep-segments + zoom)   (cortes + punch zoom + captions)
```

## Uso

```bash
PY="C:/proyectos/davinci-resolve-mcp/venv/Scripts/python.exe"   # venv con faster-whisper, PyAV, Pillow

# 1) Transcribir (word-level, local)
"$PY" skill/helpers/transcribe.py "<video>" "<out_dir>" es

# 2) Autorar edl.json a partir de takes_packed.md  (paso de razonamiento del LLM)
#    formato: {"strategy": "...", "segments": [{"start","end","zoom","note"}, ...]}

# 3) Renderizar
"$PY" skill/helpers/vidorq_render.py "<video>" "<out_dir>/edl.json" "<out_dir>/transcript.json" "<out_dir>/final.mp4"
#    flags: --no-captions  --no-zoom
```

## helpers/

- **transcribe.py** — faster-whisper `small` int8 CPU. Escribe `transcript.json` (segmentos con
  timestamps por palabra) y `takes_packed.md` (vista compacta para que el LLM razone el corte).
- **vidorq_render.py** — motor de render:
  - **Cortes**: solo los keep-segments del EDL, en orden, con fades de audio de 30 ms en cada
    frontera (sin pops).
  - **Punch zoom**: `zoom` por segmento (p. ej. 1.06) = crop central estático + reescalado.
    Sin keyframes (respeta la filosofía del MVP).
  - **Captions**: chunks Hormozi de 2 palabras UPPERCASE renderizados con PIL (Arial Black,
    contorno + sombra) y compositados como overlay. Este build de PyAV no trae drawtext/libass.
  - Salida vídeo con **h264_nvenc** (GPU). Vídeo y audio se renderizan por separado y se muxean.

## Requisitos

- Python con: `faster-whisper`, `av` (PyAV, con libx264 + h264_nvenc), `Pillow`, `numpy`.
  (El venv de `davinci-resolve-mcp` ya los tiene salvo que se indique lo contrario.)
- GPU NVIDIA para NVENC (si no, cambiar `h264_nvenc` por `libx264` en vidorq_render.py).

## Pendiente (siguientes versiones)

- Backend Resolve: mismo `edl.json` → timeline editable vía el puente MCP.
- Captions animados (aparición palabra por palabra) vía macro Fusion o overlay animado.
- Detección automática de énfasis para colocar los zooms sin autoría manual del EDL.
- Perfil de estilo por marca (colores, fuente, posición de captions configurables).
