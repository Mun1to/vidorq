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

## Cómo se abre (2026-07-07: lanzador fácil, siempre actualizado)

**Acceso directo en el Escritorio: `Vidorq.lnk`** (icono real de la app). Doble clic y
listo — no hace falta terminal ni comandos.

Por debajo, el acceso directo apunta a `app/Abrir_Vidorq.vbs`, que:
1. Comprueba si el motor local (puerto 9877) ya está encendido; si no, lo arranca oculto.
2. Lanza la app con `pnpm tauri dev` (oculto, sin ventana de consola).

**Por qué modo dev y no un instalador**: `tauri dev` compila siempre desde el código
fuente actual. Así, cada vez que se edite el proyecto (yo o Munir), la próxima vez que
se abra el acceso directo ya lleva los cambios — no hace falta reinstalar nada. Es el
equivalente a "se actualiza sola". El primer arranque compila Rust desde cero (~2-4 min
la primera vez); los siguientes son rápidos porque Cargo cachea el build.

Si algo falla y no se ve nada (el modo silencioso oculta la consola), usar
`Abrir_Vidorq_debug.bat` (misma carpeta) en su lugar: mismo lanzador pero con consola
visible para ver el error.

Cuando el producto esté "consistente y funcione bien de verdad" (regla de Munir), se
generará un instalador de verdad con `pnpm tauri build` → `bundle/nsis/Vidorq_x64-setup.exe`
(ya se generó una vez como prueba antes del logo/workspaces — quedó desactualizado y
hay que regenerarlo cuando toque congelar una versión).

Nota técnica: el paquete Rust se renombró de `app` a `vidorq` (2026-07-07) para que el
proceso/binario se llame `vidorq.exe` y no choque con Vidorq Core (`vidorq-core.exe`)
en el Administrador de tareas.

## Pendiente v1.x

- Sidecar: que la app arranque/pare el engine sola.
- Icono propio (ahora usa el de Tauri por defecto).
- Preset Montage: detección de highlights de gameplay (Crispy) además de energía.
- Estimación de tiempo restante y cancelar trabajo.
- Selector de archivo con diálogo nativo (plugin dialog) además del drag & drop.
