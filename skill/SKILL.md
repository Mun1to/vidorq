# Vidorq skill — edición por IA (v1)

> Pipeline de edición que corre desde Claude Code. Hay **dos salidas y las dos funcionan**:
> el render directo (PyAV + NVENC), que no necesita Resolve para nada, y el timeline
> editable dentro de Resolve a través del puente. Auditadas las dos con el mismo encargo
> el 19-ago-2026. Documentación interna en español (regla D).

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
# El intérprete con faster-whisper, PyAV, Pillow y onnxruntime dentro. En una
# instalación normal es el entorno de Vidorq; si usas otro, apúntalo aquí.
PY="$PWD/.venv/Scripts/python.exe"

# 1) Transcribir (word-level, local)
"$PY" skill/helpers/transcribe.py "<video>" "<out_dir>" es

# 2) Autorar edl.json a partir de takes_packed.md  (paso de razonamiento del LLM)
#    formato: {"strategy": "...", "segments": [{"start","end","zoom","note"}, ...]}

# 3) Renderizar
"$PY" skill/helpers/vidorq_render.py "<video>" "<out_dir>/edl.json" "<out_dir>/transcript.json" "<out_dir>/final.mp4"
#    flags: --no-captions  --no-zoom
```

## helpers/

- **transcribe.py** — faster-whisper: `large-v3-turbo` en float16 sobre la GPU, y `small`
  int8 en CPU cuando no hay tarjeta o le faltan las librerías de CUDA. Escribe
  `transcript.json` (segmentos con
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

## Backend Resolve (funciona · 2026-07-07)

`helpers/build_resolve_timeline.py` habla HTTP con el puente (127.0.0.1:9876) y monta un `edl.json` como **timeline editable** dentro de Resolve. Es el PRIMER backend de Resolve, de julio, y se queda porque es lo más pequeño que demuestra que el puente funciona de punta a punta; lo que corre el producto hoy es `engine/server.py` (`output_resolve`), que hace todo esto y además subtítulos nativos, transiciones, rótulos y un punch zoom que se mueve. Se lanza con `python build_resolve_timeline.py edl.json "mi video.mp4"`:
- crea el timeline (a 29.97 fps para cuadrar con la fuente),
- inserta cada keep-segment con `startFrame`/`endFrame` (endpoint `/media/insert`, en orden estricto),
- aplica punch zoom estático por segmento (`/clip/properties` → ZoomX/ZoomY); el motor de hoy lo **anima** con un comp de Fusion sobre el propio clip,
- pone un marcador por cada pregunta del Q&A (`/marker/add`),
- guarda (`/project/save`).

Requisito: Resolve abierto con un proyecto y el puente arrancado (**Workspace > Scripts > Vidorq**, una sola entrada desde el 2026-08-17) una vez. A partir de ahí todo es por API. Verificación: `export_current_frame` desde el bridge (el viewport de Resolve se captura en negro en screenshots normales, pero el frame exportado por Resolve sí es válido).

## Pendiente (siguientes versiones)

- ~~Captions nativos en el timeline de Resolve~~ **hecho** (2026-08): Text+ editables en su
  propia pista, diez estilos y nueve entradas, los diez mirados fotograma a fotograma dentro
  de Resolve. Detalle en `docs/SUBTITULOS.md`.
- ~~Captions animados~~ **hecho**: las curvas viajan dentro del `.comp` y `ImportFusionComp`
  las conserva.
- Detección automática de énfasis para colocar los zooms sin autoría manual del EDL.
- Perfil de estilo por marca (colores, fuente, posición de captions configurables).
