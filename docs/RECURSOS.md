# Recursos y referencias de Vidorq

> Material de estudio y piezas que Vidorq integra o imita. Documento vivo.

## Proyectos base (estudiar a fondo)

| Recurso | Qué es | Qué nos llevamos |
|---|---|---|
| [video-use](https://github.com/browser-use/video-use) (browser-use) | Edición de vídeo con Claude Code, 100% open source | El pipeline entero: transcript-first, EDL, self-eval, project.md, fades 30ms, subtítulos 2 palabras UPPERCASE. Es la validación de que el enfoque funciona |
| [davinci-resolve-mcp](https://github.com/hiteshK03/davinci-resolve-mcp) | Puente MCP para Resolve FREE (local: `C:\proyectos\davinci-resolve-mcp`) | La base de integración con Resolve: 162 herramientas + IA local (Whisper, Demucs, rembg) |
| [HyperFrames](https://github.com/heygen-com/hyperframes) (HeyGen) | Skill de generación de animaciones para agentes (`npx skills add heygen-com/hyperframes`) | Overlays de animación generados por sub-agentes en paralelo |
| [Remotion](https://www.remotion.dev/) (`npx create-video@latest`) | Vídeos programáticos con React | El motor de animaciones: código CSS/React limpio → render con canal alfa. Analizar bien su licencia (gratis para individuos/open source, empresas pagan) |
| [Manim](https://www.manim.community/) | Animaciones matemáticas (las de 3Blue1Brown) | Diagramas y animaciones educativas |
| AutoSubs | Subtítulos automáticos open source para Resolve | Referencia de UX de subtítulos dentro de Resolve |
| [ElevenLabs](https://elevenlabs.io/) | Scribe (transcripción con diarización + eventos de audio) y TTS | Transcripción premium opcional; voces para narración |

## IA generativa conectable (BYOK - el usuario pone su clave)

| Proveedor | Modelos | Uso en Vidorq |
|---|---|---|
| Anthropic (Claude) | claude-fable-5, claude-opus-4-8, claude-sonnet-5 | El cerebro editor: razonamiento de cortes, tool use MCP |
| Google | Gemini (multimodal), **Nano Banana** (imagen), **Veo 3** (vídeo), Imagen | Análisis de vídeos de referencia (multimodal barato), b-roll generado, miniaturas |
| OpenAI | GPT, Sora, TTS | Alternativa de razonamiento y generación |
| Local (Ollama) | Los 42 modelos de Stashai | Tareas simples sin coste ni latencia de red |

## Técnicas de edición a implementar (el lenguaje del editor)

- **Zoom in / zoom out** en énfasis (zoom punch sincronizado con la frase clave).
- **Speedramps** limpios (aceleración/deceleración suave, no lineal).
- **Efecto construcción**: el vídeo va montando algo visualmente; el espectador quiere ver el final.
- **Psicología del espectador**: hook en <3s, loops abiertos, ritmo que respira antes del clímax.
- **Cortes en fronteras de palabra** + fades de audio ~30ms (nunca un pop).
- **Estilo único por marca** (perfil de estilo), no plantillas genéricas.

## Assets gratuitos/premium para vídeos

| Fuente | Qué tiene |
|---|---|
| [acidbite.com](https://acidbite.com/) | Packs de transiciones/SFX con estética agresiva |
| [premiumbeat.com](https://www.premiumbeat.com/) | Música con licencia |
| [cinepacks.com](https://cinepacks.com/) | Packs de efectos cinematográficos |
| Mixkit, Pexels Video, Pixabay | B-roll y música gratuitos |
| YouTube Audio Library | Música sin copyright básica |

## Prompt de búsqueda musical (plantilla)

Prompt único para encontrar canciones sin copyright, únicas y diferenciadoras (no genéricas):

```
Music piece for my video about [TEMA, p.ej. gym training].
Style: [GÉNERO, p.ej. hip hop]. Mood: [p.ej. motivational, dark, uplifting].
Must be copyright-free / royalty-free with license for social media monetization.
List 20 iconic options that match these criteria as easy-to-scan bullet points:
[artist - track - source/license - why it fits - energy 1-10].
Avoid generic stock-sounding tracks; prioritize distinctive, memorable pieces.
```

## Calidad óptima por red social (2026)

> Verificar periódicamente: las plataformas cambian specs. Regla general: subir a la máxima calidad que la plataforma acepte; ella recomprime siempre.

| Plataforma | Resolución | FPS | Bitrate recomendado | Notas |
|---|---|---|---|---|
| YouTube (largo) | 4K (3840x2160) 16:9 | 24-60 | 35-45 Mbps (4K) / 8-12 (1080p) | 4K recibe mejor códec (VP9/AV1) incluso visto en 1080p: sube 4K siempre que puedas |
| YouTube Shorts | 1080x1920 9:16 | 30-60 | 10-12 Mbps | Máx 3 min; primeros 3s deciden todo |
| TikTok | 1080x1920 9:16 | 30-60 | ~10 Mbps | Comprime agresivo: contraste alto y texto grande sobreviven mejor |
| Instagram Reels | 1080x1920 9:16 | 30-60 | ~10 Mbps | Safe area: deja margen inferior (~250px) para UI |
| Instagram Feed | 1080x1350 4:5 | 30 | 8-10 Mbps | El 4:5 ocupa más pantalla que el cuadrado |
| X / Twitter | 1080p máx | 30-60 | recomprime fuerte | No confiar detalles finos |
| LinkedIn | 1080p | 30 | 8-10 Mbps | Subtítulos obligatorios (mucho mute) |

Export desde Resolve Free: H.264/H.265 hasta 4K cubre todo lo anterior. ProRes 4444 solo para overlays con alfa (intermedios, no para subir).

## Investigación pendiente (radar)

- Licencia exacta de Remotion para un proyecto open source con posible open-core.
- PySceneDetect vs detect_scene_cuts del puente: cuál rinde mejor en gameplay.
- Análisis multimodal de referencia: ¿Gemini Flash basta o hace falta Pro?
- AutoSubs internals: cómo dibuja subtítulos nativos en Resolve Free.
- Especificaciones de bitrate por plataforma: re-verificar cada pocos meses.
