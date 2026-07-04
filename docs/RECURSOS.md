# Recursos y referencias de Vidorq

> Material de estudio y piezas que Vidorq integra o imita. Documento vivo.

## Proyectos base (estudiar a fondo)

| Recurso | Qué es | Qué nos llevamos |
|---|---|---|
| [video-use](https://github.com/browser-use/video-use) (browser-use) | Edición de vídeo con Claude Code, 100% open source | El pipeline entero: transcript-first, EDL, self-eval, project.md, fades 30ms, subtítulos 2 palabras UPPERCASE. Es la validación de que el enfoque funciona |
| [davinci-resolve-mcp](https://github.com/hiteshK03/davinci-resolve-mcp) | Puente MCP para Resolve FREE (local: `C:\proyectos\davinci-resolve-mcp`) | La base de integración con Resolve: 162 herramientas + IA local (Whisper, Demucs, rembg) |
| [HyperFrames](https://github.com/heygen-com/hyperframes) (HeyGen) | Skill de generación de animaciones para agentes (`npx skills add heygen-com/hyperframes`) | Overlays de animación generados por sub-agentes en paralelo |
| [Motion Canvas](https://motioncanvas.io/) | Animación programática en TypeScript, licencia MIT | **Motor de overlays por defecto**: sin restricciones de licencia para empresas |
| [Revideo](https://github.com/redotvideo/revideo) | Fork MIT de Motion Canvas para pipelines automatizados | Render server-side pensado para generación automática — encaja exacto con Vidorq |
| [Remotion](https://www.remotion.dev/) | Vídeos programáticos con React | Excelente, pero ⚠️ verificado 2026-07-04: gratis solo para individuos/empresas ≤3 empleados; apps "prompt-to-video" necesitan Company License ($0,01/render, mín $100/mes) y quien EJECUTA Remotion queda sujeto a licencia → opcional, no motor por defecto |
| [Manim](https://www.manim.community/) | Animaciones matemáticas (las de 3Blue1Brown) | Diagramas y animaciones educativas |
| [AutoSubs](https://github.com/tmoroney/auto-subs) | Subtítulos automáticos open source (MIT) para Resolve FREE | **El blueprint de captions**: servidor Lua HTTP (puerto 56002) dentro de Resolve + macro Fusion .setting (Text+, StyledTextFollower, KeyStretcherMod, BezierSpline, XYPath) con animación en CustomData. Gotcha aprendido: usar cliente HTTP robusto (Tauri se colgaba con las respuestas Connection: close de Resolve) |
| [librosa](https://librosa.org/) + [Lighthouse](https://github.com/line/lighthouse) | Picos de audio / moment retrieval por lenguaje natural | Detección de momentos de énfasis en talking-head |
| [Crispy](https://github.com/Flowtter/crispy) + [VideoHighlighter](https://github.com/Aseiel/VideoHighlighter) | Kill detection (Valorant/OW/CS2/LoL) y highlights (YOLO+Whisper) | Detección de highlights en gameplay — el caso montage de la visión |
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

## Calidad óptima por red social (verificado 2026-07-04 por investigación, 253 fuentes)

> Regla general: subir a la máxima calidad que la plataforma acepte; ella recomprime siempre. Re-verificar cada pocos meses.

| Plataforma | Resolución | FPS | Bitrate | Notas verificadas |
|---|---|---|---|---|
| YouTube (largo) | **4K siempre**, aunque el material sea 1080p | 24-60 | 35-45 Mbps (4K); subir 20-50% sobre el suelo oficial | Subir 4K fuerza el códec VP9/AV1 (mejor calidad); tests independientes 2026 confirman que "YT penaliza 1080p" |
| YouTube Shorts | 1080x1920 9:16 | 30-60 | ≥8 Mbps | Máx 3 min; primeros 3s deciden todo |
| TikTok | 1080x1920 9:16 | 30 constante (mejor que variable) | 6-8 Mbps | Sin 4K; re-encoda todo: contraste alto y texto grande sobreviven mejor |
| Instagram Reels | 1080x1920 9:16 | 30 | 4-15 Mbps según fuente | **NO soporta 4K** (máx 1080p); safe area inferior (~250px) para UI |
| Instagram Feed | 1080x1350 4:5 | 30 | 8-10 Mbps | El 4:5 ocupa más pantalla que el cuadrado |
| X / Twitter | máx 1920x1080 (recomendado 1280x720) | hasta 60 | 5-8 Mbps | Free: 140s/512MB; Premium+: hasta 4h/16GB (oficial help.x.com) |
| LinkedIn | 1080p (oficial admite 256x144-4096x2304) | 10-60 | 192Kbps-30Mbps (oficial) | Orgánico ≤5GB/15min; subtítulos quemados obligatorios (mucho mute) |

Estrategia de export: **master único ProRes/DNxHR 4K → presets H.264 por plataforma**. ProRes 4444 solo para overlays con alfa (intermedios, no para subir). Dato de fondo: 92% ve vídeo sin sonido en móvil (encuesta Verizon Media/Publicis, 5.616 personas) → captions quemados siempre.

## Investigación pendiente (radar)

- ~~Licencia exacta de Remotion~~ ✅ Resuelto 2026-07-04: solo gratis ≤3 empleados → Motion Canvas/Revideo por defecto.
- ~~AutoSubs internals~~ ✅ Resuelto 2026-07-04: servidor Lua HTTP + macro Fusion .setting (ver tabla de arriba).
- ~~Bitrates por plataforma~~ ✅ Verificados 2026-07-04 (re-verificar cada pocos meses).
- **Spike técnico prioritario**: probar en Resolve 20.3 Free el workaround de `ImportFusionComp` (comp dummy) con una comp animada simple — es la apuesta central del MVP y hay que confirmarla en ESTA versión.
- Probar AI Detect Music Beats de Resolve 20 (marcadores en cada beat): ¿accesible por API? Serviría para sincronizar cortes con música.
- PySceneDetect vs detect_scene_cuts del puente: cuál rinde mejor en gameplay.
- Análisis multimodal de referencia: ¿Gemini Flash basta o hace falta Pro?
