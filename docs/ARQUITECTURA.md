# Arquitectura de Vidorq

> Documento vivo. Define los componentes del sistema y las decisiones técnicas que los justifican.

## Restricción fundadora: Resolve Free no permite scripting externo

Blackmagic reserva el scripting externo para Studio (295 USD). La solución (ya probada en `davinci-resolve-mcp`, base de este proyecto) es un **puente que corre DENTRO de Resolve**:

```
Asistente IA (Claude Code / Cursor / cualquier cliente MCP)
      │  MCP (stdio)
      ▼
Servidor MCP de Vidorq (Python, en tu máquina)
      │  HTTP (localhost)
      ▼
CursorBridge.py (corre DENTRO de Resolve: Workspace > Scripts)
      │
      ▼
API de scripting de DaVinci Resolve (lectura + escritura completa)
```

Esto ya da 162 herramientas sobre Resolve Free: timeline, clips, marcadores, media pool, color, Fusion, render, y reemplazos locales de las funciones "Neural Engine" de Studio.

### Limitaciones duras de la API de Resolve (y cómo las esquivamos)

| Limitación | Consecuencia | Solución de Vidorq |
|---|---|---|
| No se pueden animar keyframes por API | Imposible "animar" clips desde código | Animaciones renderizadas fuera (Remotion) como vídeo con canal alfa, importadas como media |
| No se pueden añadir transiciones por API | Sin cortinillas automáticas | Plantillas Fusion (.drfx/.setting) instaladas + macros; o transiciones "cocinadas" en el overlay |
| No se puede editar el interior de nodos Fusion por API | Sin cambiar textos de Text+ complejos | Plantillas Text+ con parámetros publicados + `insert_title`; overlays Remotion para lo avanzado |
| Free no exporta >4K ni ciertas opciones de render | Techo de calidad de export | 4K H.264/H.265 cubre el 100% de redes sociales (ver RECURSOS.md) |

## Componentes del sistema

### 1. Puente Resolve (existe: `davinci-resolve-mcp`)
- CursorBridge.py dentro de Resolve + servidor MCP Python fuera.
- Vidorq lo consume como dependencia/submódulo y le aporta mejoras upstream.

### 2. Orquestador (el "cerebro editor")
El agente que convierte "córtame este podcast" en un plan de edición ejecutable (EDL) y lo aplica con las herramientas MCP. Pipeline (adoptado de video-use, que lo tiene validado):

```
Transcribir → Empaquetar → Razonar (LLM) → EDL → Aplicar en Resolve → Auto-evaluar
                                                        │
                                                        └─ ¿problema? corregir y repetir (máx 3)
```

- **Proveedores de IA (BYOK, bring your own key):**
  - **Claude (Anthropic)** — prioridad 1: razonamiento de edición, tool use con MCP nativo.
  - **Gemini (Google)** — multimodal barato para análisis de vídeo de referencia; da acceso a Veo/Imagen.
  - **OpenAI** — alternativa; da acceso a Sora/voz.
  - **Local (Ollama)** — tareas simples sin coste: clasificar segmentos, resumir, etiquetar.
- Las claves van en `.env`, nunca en código ni en logs (regla B).

### 3. Capa de percepción (el LLM LEE el vídeo)
- **Transcripción**: faster-whisper local (gratis, ya en el puente) o ElevenLabs Scribe (cloud, mejor diarización y eventos de audio como `(risas)`). Timestamps a nivel de palabra.
- **Empaquetado**: todas las tomas en un `takes_packed.md` compacto (~12KB) que el LLM lee entero. Nada de volcar 30.000 frames.
- **Vista visual bajo demanda** (`timeline_view`): filmstrip + forma de onda + palabras para un rango temporal, solo en puntos de decisión (pausas ambiguas, comparar retakes, sanity-check de cortes).
- **Detección de escenas**: `detect_scene_cuts` (ya en el puente) para material sin habla (gameplay, b-roll).

### 4. Motor de animaciones (la "obra de arte")
- **Remotion** (`npx create-video@latest`): animaciones como componentes React/CSS renderizadas a vídeo con canal alfa (ProRes 4444 / secuencia PNG). Es el equivalente al parallax en web: código limpio → animación limpia.
- **HyperFrames** (HeyGen): overlays de animación generados por agentes, uno por animación en paralelo.
- **Plantillas Fusion** (.drfx): para lo que debe vivir nativo en Resolve (Text+ de marca, lower thirds paramétricos).
- **Manim / PIL**: animaciones matemáticas/diagramas para contenido educativo.
- Biblioteca de animaciones del usuario: cada animación generada se guarda con nombre + preview + código, para reutilizar y mantener consistencia de marca.

### 5. Sistema de gusto (anti-slop) — el diferenciador
- Perfil de estilo por marca (archivo local versionado) alimentado por el onboarding y por análisis de vídeos de referencia (yt-dlp + Gemini/Claude). Detalle completo en [ENTRENAMIENTO.md](ENTRENAMIENTO.md).

### 6. Generación multimedia (opcional, BYOK)
- **Imagen**: Nano Banana / Imagen (Google), gpt-image (OpenAI) — miniaturas, fondos, texturas.
- **Vídeo**: Veo 3 (Google), Sora (OpenAI) — b-roll imposible de grabar.
- **Voz/TTS**: ElevenLabs — narración, doblaje.
- **Música**: búsqueda estructurada de música sin copyright con prompt guiado (ver RECURSOS.md).

### 7. Memoria de proyecto
- `project.md` por proyecto de vídeo: decisiones, estilo aplicado, feedback del usuario. La sesión de la semana que viene continúa donde se quedó.

### 8. Auto-evaluación (control de calidad automático)
- Tras aplicar la edición, se inspecciona cada frontera de corte (filmstrip + audio) buscando saltos visuales, pops de audio y subtítulos tapados. Fades de ~30ms en cada corte. Máximo 3 ciclos de corrección antes de enseñar el resultado.

## Formato del plan de edición (EDL interno)

El LLM produce un plan declarativo y auditable (JSON) antes de tocar nada:

```json
{
  "strategy": "Podcast de 90 min → corte dinámico de 22 min con tarjetas de tema",
  "cuts": [
    {"keep": [12.52, 95.30], "reason": "presentación fuerte"},
    {"drop": [95.30, 110.02], "reason": "silencio + divagación"}
  ],
  "overlays": [
    {"type": "topic_card", "at": 95.30, "text": "¿Por qué fracasan las startups?", "style": "brand/lower-third-v2"}
  ],
  "subtitles": {"style": "brand/subs-uppercase-2words"}
}
```

El usuario aprueba la estrategia ANTES de ejecutar (principio: preguntar → confirmar → ejecutar).

## Stack

| Capa | Tecnología |
|---|---|
| Servidor MCP / puente | Python 3.11+ |
| Motor de animaciones | Node + pnpm + Remotion (React/TS) |
| Procesado de media | ffmpeg, yt-dlp |
| IA local | faster-whisper, Demucs v4, rembg/BiRefNet, Ollama |
| IA cloud (BYOK) | Anthropic, Google (Gemini/Veo/Imagen), OpenAI, ElevenLabs |
| Host | DaVinci Resolve 18+ (Free o Studio), Windows/macOS/Linux |
