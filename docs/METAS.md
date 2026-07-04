# Metas de Vidorq (niveles tipo videojuego)

> Regla: METAS, no fechas. Cada nivel se desbloquea al completar el anterior.
> La única presión temporal válida son ventanas externas (convocatorias, releases de terceros), y se anotan como tales.

## Nivel 0 — Fundación ✅
- [x] Nombre: Vidorq.
- [x] Carpeta + repo público (`vidorq`) + repo privado (`vidorq-core`).
- [x] Visión, arquitectura, sistema de entrenamiento y recursos documentados.
- [x] Decisiones respondidas por Munir (2026-07-04): interfaz = Claude Code con Resolve abierto en tiempo real; MVP = cortes + zooms + captions; dominio vidorq.com (el .ai se descarta por precio).

## Definición del MVP (decidida 2026-07-04)

Vidorq se usa DESDE Claude Code, **con DaVinci Resolve abierto al lado**: cada acción del puente aparece al instante en el timeline, y el usuario ve a Vidorq editar en tiempo real. El MVP está completo cuando, sobre un vídeo real:

1. **Cortes inteligentes**: silencios, muletillas y momentos flojos fuera; cortes en fronteras de palabra con fades de audio.
2. **Animaciones cinemáticas con zoom in/out**: énfasis visual sincronizado con el habla.
3. **Captions profesionales y diferenciadores**: subtítulos animados con el estilo de la marca del usuario, no los genéricos de siempre.
4. **Todo bien estructurado**: perfil de estilo aplicado, timeline limpio y retocable a mano después.

Equivale a completar los Niveles 1-3. Si la API de Resolve bloquea algo, se busca la vuelta (ver "escalera de técnicas" en [ARQUITECTURA.md](ARQUITECTURA.md)).

## Nivel 1 — El primer corte mágico
**Meta: un prompt corta un vídeo real en Resolve Free y el resultado se sostiene.**
- [ ] Puente Resolve integrado (davinci-resolve-mcp como base/submódulo) y estable en Resolve 20.3.
- [ ] Pipeline transcribir → empaquetar → razonar → EDL → aplicar cortes en timeline.
- [ ] Demo reproducible: "córtame los silencios y muletillas de este clip" funciona de punta a punta.

## Nivel 2 — Subtítulos y estilo propio
**Meta: el vídeo sale con subtítulos animados en el estilo de la marca del usuario.**
- [ ] Perfil de estilo v1 (style.md + brand.json + subtitles.json).
- [ ] Onboarding conversacional (cuestionario de marca).
- [ ] Subtítulos quemados con estilo configurable (bloques 2 palabras, uppercase, etc.).

## Nivel 3 — Animaciones cinematográficas
**Meta: "añade una tarjeta animada en cada cambio de tema" funciona.**
- [ ] Zooms cinemáticos: zoom punch en cortes (funciona hoy con la API) + zoom suave/speedramp (vía Fusion comps o import FCPXML, según resultado de la investigación).
- [ ] Motor Remotion: prompt → componente React → render con alfa → import a Resolve → colocación en timeline.
- [ ] Biblioteca de animaciones reutilizables por marca.
- [ ] Detección de cambios de tema en podcasts/entrevistas (el caso de uso ejemplo de la visión).

## Nivel 4 — Entrenamiento de gusto completo
**Meta: le pasas 3 links de referencia y la siguiente edición se nota entrenada.**
- [ ] Ingesta de links (yt-dlp) + análisis estructurado de referencia (ritmo, hooks, texto, música).
- [ ] Destilado de feedback a reglas del perfil (con confirmación).
- [ ] Caso real: un vídeo de gaming (montage/highlights) editado al estilo de un referente.

## Nivel 5 — Release pública v0.1
**Meta: una persona que no es Munir lo instala y edita su primer vídeo en menos de 30 minutos.**
- [ ] Instalador/setup guiado (un comando).
- [ ] Documentación de usuario en inglés.
- [ ] Vídeo de lanzamiento editado CON Vidorq (dogfooding: la demo es el producto).
- [ ] Publicación: GitHub + redes (contenido orgánico del ecosistema).

## Nivel 6 — Ecosistema
**Meta: Vidorq se conecta con el resto de herramientas del día a día.**
- [ ] Generación BYOK: Nano Banana / Veo / ElevenLabs integrados como herramientas opcionales.
- [ ] Multi-versión por red social (16:9 → 9:16) con recorte inteligente local.
- [ ] Skill de música: un clic abre un mini-formulario (dónde ocurre el momento, qué emoción transmitir, qué ritmo/energía) y propone ~20 canciones sin copyright acordes al vídeo.
- [ ] Comunidad: contribuciones externas, plantillas de animación compartidas.
