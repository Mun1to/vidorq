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
#
#    Los que casi siempre importan:
#      --export <destino>   a dónde va el archivo, y con eso el caudal, el audio
#                           y el volumen ya puestos. Uno de: youtube, youtube4k,
#                           shorts, instagram, x, mensajeria, master.
#                           Sin esto se usa `youtube`.
#      --ratio <forma>      source | vertical | portrait | square | wide
#      --preset <estilo>    el estilo de subtítulo (pop, punch, brasa...)
#      --detras             los subtítulos POR DETRÁS del sujeto. Cuesta unos
#                           6 minutos por minuto de vídeo, así que se pide.
#                           Si el vídeo no tiene un sujeto que recortar lo dice
#                           por `MASCARA_NO:` y entrega el vídeo con los
#                           subtítulos delante, en vez de con manchas encima.
#      --no-captions        sin subtítulos
#      --no-zoom            sin punch zoom
#
#    Escribe en stdout, una línea por cosa, para poder seguirlo desde fuera:
#      PROGRESS <hechos> <total>   avance; con --detras el total es el doble,
#                                  porque cada fotograma se toca dos veces
#      EXPORT: ...                 qué tamaño y qué caudal se van a usar
#      VIDEO_OK / AUDIO_OK / MUX_OK / DONE
#      SIN_AUDIO:                  el vídeo de origen es mudo y sale mudo
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
  - **Captions**: se escriben como un `.ass` por segmento y los quema libass dentro de
    ffmpeg, con el estilo que diga `--preset`. (Aquí ponía que se componían con PIL: eso
    era la v1 del motor, que tardaba 170 ms por fotograma y se cambió hace tiempo.)
  - **Destino de exportación**: `--export` decide tamaño, caudal, audio y volumen con los
    números que pide cada plataforma, normalizando a -14 LUFS donde toca. La tabla vive en
    `helpers/exportar.py` y es la MISMA para el MP4 y para los ajustes de Deliver de Resolve.
  - **Texto por detrás del sujeto**: `--detras` sigue la máscara de la persona y la compone
    encima de los subtítulos. Ver `helpers/mascara.py`.
  - Salida vídeo con **h264_nvenc** (GPU), cayendo a libx264 si falla. Vídeo y audio se
    renderizan por separado y se muxean.
- **mascara.py** — sigue una máscara por el vídeo: el fotograma anterior se arrastra con el
  flujo óptico y se mezcla con lo que propone el modelo, que es lo que evita el parpadeo.
  `recortar_sujeto()` escribe un `.mov` con canal alfa y devuelve cuánto ocupaba el sujeto en
  cada fotograma, para poder saber si el efecto merece la pena.
- **segmentador.py** — qué píxeles son el objeto en UN fotograma. Va aparte a propósito:
  seguir un objeto no cambia, y de modelos de segmentación sale uno mejor cada seis meses.
  Usa **U-2-Net (Apache 2.0)**, en `skill/models/`. Ojo con las licencias aquí:
  RobustVideoMatting es GPL-3.0 y YOLO-seg es AGPL, así que ninguno de los dos vale dentro de
  un producto que se vende.
- **exportar.py** — los siete destinos, con sus números y de dónde salen.

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
