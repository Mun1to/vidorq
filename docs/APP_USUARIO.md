# App de usuario (Tauri + React)

> Decisión de Munir (2026-07-07): interfaz sencilla para el usuario, instalable y anclable
> a la barra de tareas. Stack Tauri+React (patrón AutoSubs). Presets gratis, y el prompt libre
> también: funciona con el modelo local o con la herramienta de IA que ya tengas instalada, y
> la clave de API es solo uno de los caminos.

## Arquitectura

```
Vidorq.exe (Tauri + React)  ←  app/
        │ HTTP localhost:9877
        ▼
Vidorq Engine (Python, stdlib puro)  ←  engine/server.py
        │                    │
        │ subprocess         │ HTTP localhost:9876
        ▼                    ▼
skill/helpers/         CursorBridge (dentro de Resolve)
transcribe.py            → timeline editable
vidorq_render.py         → mp4 directo (GPU)
```

- La app NO contiene lógica de edición: todo vive en el engine (el mismo motor que usa
  Claude Code). Un solo cerebro, tres interfaces: app, Claude Code, y futura app Core.
- El engine es stdlib puro (patrón CursorBridge): cero dependencias nuevas.

## Pantalla única (v1)

1. **Dropzone**: drag & drop nativo (rutas reales vía Tauri) o pegar la ruta.
2. **Presets** (gratis, 100% local, sin API key):
   - ✂️ Limpieza: conserva el habla, corta silencios y momentos muertos (VAD de Whisper + fusión de huecos <0.6s).
   - 🎙️ Podcast Q&A: limpieza + detecta preguntas (heurística: "?" o arranque interrogativo) → zoom 1.05 y marcador por pregunta.
   - 🎮 Montage (beta): conserva los tramos de más energía de audio (RMS por segundo, top tercio, mínimo 3s).
3. **Opciones**: captions on/off · salida "MP4 directo" (render GPU) o "Timeline en Resolve"
   (requiere el puente activo: **Workspace > Scripts > Vidorq**).
4. **El prompt libre**, en la misma pantalla y sin llamarse nada: escribes lo que quieres y el
   motor decide el montaje entero (formato, estilo de subtítulo, entrada, transición y corte).
   Lo que la frase dice con **números puestos** ("quita un trozo del segundo 5 al 9", "pon un
   rótulo en el segundo 3 que diga X") no pasa por ningún modelo: es aritmética. Para lo demás
   elige el proveedor en Ajustes: el Ollama de tu máquina, la herramienta de IA que ya tengas
   instalada y con sesión iniciada (Claude Code, Codex, Gemini CLI), o una clave de API. Las
   claves se guardan en `%APPDATA%/Vidorq/config.json`, solo local, y el motor nunca las
   devuelve.
5. **Progreso**: barra con pasos (Transcribiendo → Decidiendo cortes → Renderizando) vía polling a `/progress`.

## Endpoints del engine (127.0.0.1:9877)

| Endpoint | Qué hace |
|---|---|
| `GET /health` | latido; la app muestra "motor conectado/apagado" |
| `GET /progress` | paso, %, detalle, resultado o error |
| `GET /resolve` | si Resolve está abierto, con qué proyecto y timeline; sin puente al menos dice si el programa está corriendo, mirando los procesos |
| `GET /clips` | los vídeos que ya hay en el proyecto abierto |
| `GET /probe` | si la ruta que has escrito lleva de verdad a un vídeo, antes de aceptarla |
| `POST /profile` | guarda tu perfil de marca, dejando la versión anterior en `brand.anterior.json` por si el guardado fue un accidente |
| `GET /session` | la conversación de ese vídeo en ese proyecto, sus ajustes y si hay algo que deshacer |
| `GET /words` | cada palabra con su segundo, para editar leyendo |
| `GET /aprende` | mira un vídeo de referencia y dice cómo está editado, con los estilos de la casa que más se le parecen |
| `GET /aprende/captura` | un fotograma de ese vídeo de referencia, para poder enseñar lo que se ha visto en vez de contarlo |
| `GET /tramos` | el montaje partido en tramos, con lo que se dice en cada uno |
| `GET /history` | todas las ediciones hechas, la última primero |
| `GET /preview` | una foto de lo que hace una elección, sobre tu propio metraje |
| `GET /captions/presets` | el catálogo: estilos, entradas, colores, formatos, transiciones y cuáles sabe hacer Resolve |
| `GET /providers` · `/models` · `/voices` | quién puede pensar tu frase y quién puede ponerle voz |
| `GET /workspaces` · `/profile` | el workspace activo y el perfil de marca |
| `POST /edit` | `{video, preset, captions, output, prompt, ...}` → trabajo en un hilo |
| `POST /stop` | corta el trabajo en marcha; lo ya hecho se queda |
| `POST /seek` | mueve el cabezal de Resolve a un segundo del montaje |
| `POST /config` · `/profile` · `/workspaces` | guardan ajustes, marca y workspaces |
| `POST /history` | vacía la lista de ediciones (los vídeos no se tocan) |
| `POST /shutdown` | apaga el motor |

Todos contestan **solo a una ventana de esta máquina**: una petición con un `Origin` de fuera
se lleva un 403 antes de hacer nada, porque detrás de `/history` y `/words` hay material del
usuario y cualquier web abierta en su navegador puede llamar a un puerto local.

## Cómo se abre (desde el 2026-08-17: una sola entrada en Resolve)

**`Workspace > Scripts > Vidorq`**, dentro de DaVinci Resolve. Ese clic enciende el motor
(oculto, sin consola), arranca el puente y abre la ventana. No hace falta terminal, ni acceso
directo en el escritorio, ni tener Resolve y la app sincronizados a mano.

Lo que se instala en Resolve es un **cargador sin lógica** que lee un puntero y ejecuta el
código de la carpeta de instalación, así que **actualizar la app actualiza la extensión** y no
hay que volver a instalar nada en Resolve nunca más. Se pone una vez con
`resolve/instalar.ps1`.

**Trampa medida (2026-08-18)**: la ventana es un `vidorq.exe` compilado con Tauri, y un binario
de release **lleva la interfaz incrustada dentro**. `pnpm build` solo regenera `app/dist`, que
ese exe ni mira. Cualquier cambio de interfaz que tenga que ver una persona termina en
`pnpm tauri build` (con `CARGO_TARGET_DIR=C:\ct`), cerrando antes la ventana porque si el exe
está corriendo no se puede reemplazar. Sale en `C:\ct\release\vidorq.exe`, que es justo donde
lo busca el cargador.

Nota técnica: el paquete Rust se llama `vidorq` (renombrado de `app` el 2026-07-07) para que el
proceso sea `vidorq.exe` y no choque con Vidorq Core (`vidorq-core.exe`) en el Administrador de
tareas.

## Pendiente v1.x

- Sidecar: que la app arranque/pare el engine sola.
- Icono propio (ahora usa el de Tauri por defecto).
- Preset Montage: detección de highlights de gameplay (Crispy) además de energía.
- Estimación de tiempo restante y cancelar trabajo.
- Selector de archivo con diálogo nativo (plugin dialog) además del drag & drop.
