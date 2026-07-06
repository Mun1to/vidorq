# App de usuario (Tauri + React)

> Decisión de Munir (2026-07-07): interfaz sencilla para el usuario, instalable y anclable
> a la barra de tareas. Stack Tauri+React (patrón AutoSubs). Presets gratis + Modo Pro BYOK desde v1.

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
3. **Opciones**: captions on/off · salida "MP4 directo" (render GPU) o "Timeline en Resolve" (requiere CursorBridge activo).
4. **✨ Modo Pro**: textarea de prompt libre → el engine llama a la API de Anthropic
   (claude-sonnet-5) con la transcripción empaquetada y devuelve el EDL. Requiere la API key
   del usuario (Ajustes ⚙️; se guarda en `%APPDATA%/Vidorq/config.json`, solo local).
5. **Progreso**: barra con pasos (Transcribiendo → Decidiendo cortes → Renderizando) vía polling a `/progress`.

## Endpoints del engine (127.0.0.1:9877)

| Endpoint | Qué hace |
|---|---|
| `GET /health` | latido; la app muestra "motor conectado/apagado" |
| `GET /progress` | paso, %, detalle, resultado o error |
| `POST /config` | guarda la API key |
| `POST /edit` | `{video, preset, captions, output, prompt}` → job en hilo |

## Cómo se ejecuta

- **Desarrollo**: `pnpm --dir app tauri dev` + `engine/start_engine.bat`.
- **Instalada**: instalador NSIS/MSI generado con `pnpm tauri build`
  (`app/src-tauri` → target release `bundle/nsis/Vidorq_x64-setup.exe`). Tras instalar,
  clic derecho en Vidorq → anclar a la barra de tareas.
- El engine de momento se arranca con `engine/start_engine.bat`; integrarlo como sidecar
  de Tauri (arranque automático con la app) está en la lista.

## Pendiente v1.x

- Sidecar: que la app arranque/pare el engine sola.
- Icono propio (ahora usa el de Tauri por defecto).
- Preset Montage: detección de highlights de gameplay (Crispy) además de energía.
- Estimación de tiempo restante y cancelar trabajo.
- Selector de archivo con diálogo nativo (plugin dialog) además del drag & drop.
