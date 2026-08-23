# Sistema de entrenamiento de gusto (anti-slop)

> El diferenciador de Vidorq: la IA no edita "en genérico", edita con TU criterio.
> Este documento define cómo el usuario entrena a su editor.

## El problema del slop

Las herramientas de "IA + vídeo" actuales producen contenido genérico: mismas plantillas, mismos subtítulos amarillos, mismo ritmo. El espectador lo detecta en 2 segundos y hace scroll. La calidad no está en el modelo, está en el **criterio** — y el criterio se entrena.

## Los tres canales de entrenamiento

### 1. Onboarding inicial (cuestionario de marca)

Al crear un perfil, Vidorq hace una entrevista corta y concreta (no un formulario infinito). Borrador de preguntas:

1. **Identidad**: ¿Qué haces y para quién? ¿Qué sensación debe dejar tu contenido (cercano, premium, enérgico, calmado, técnico, divertido)?
2. **Referentes**: pega 3-5 links de vídeos que te encantaría haber hecho tú (YouTube/TikTok/Reels). *Este es el input más valioso.*
3. **Anti-referentes**: 1-2 links de vídeos que NO quieres parecer. Definir por negación funciona muy bien contra el slop.
4. **Marca visual**: colores (hex si los tienes), tipografías, logo (archivo), ¿subtítulos siempre / a veces / nunca?
5. **Formato objetivo**: ¿shorts verticales, YouTube largo, ambos? ¿Duración típica?
6. **Ritmo**: ¿cortes rápidos tipo hype o respiración tipo documental? (se ofrece una escala con ejemplos en vídeo)
7. **Música**: géneros que sí / que no. ¿Con o sin beat drops sincronizados al corte?
8. **Reglas duras**: cosas que jamás debe hacer (p. ej. "nunca zoom punch en mi cara", "nunca emojis en subtítulos").

### 2. Análisis de vídeos de referencia (links)

El usuario pega links de YouTube / TikTok / Instagram Reels. Pipeline:

```
Link → yt-dlp (descarga local, calidad máxima disponible)
     → ffmpeg (extraer audio + frames clave)
     → Whisper (transcripción con timestamps)
     → detección de cortes (PySceneDetect / detect_scene_cuts)
     → LLM multimodal (Gemini o Claude): análisis estructurado
```

Del análisis se extrae un informe por vídeo:

- **Ritmo de corte**: duración media de plano, distribución (¿acelera en el clímax?).
- **Estructura del hook**: qué pasa en los primeros 3 segundos (texto, pregunta, resultado adelantado).
- **Texto en pantalla**: tipografía aproximada, posición, animación de entrada/salida, cuántas palabras por bloque.
- **Zoom/movimiento**: zoom-in/zoom-out en énfasis, speedramps, shakes.
- **Sonido**: música (género, energía, ¿drop sincronizado?), SFX en transiciones (whoosh, click).
- **Psicología**: qué retiene al espectador (loops abiertos, listas, "espera al final"), efecto construcción (el vídeo va montando algo).
- **Color**: look general (cálido cinematográfico, neutro punchy, teal & orange).

> Nota legal: los vídeos de referencia se analizan localmente para extraer PATRONES de estilo (ritmo, estructura), nunca para copiar contenido. El material descargado no se redistribuye.

#### Lo que de esa lista hace hoy de verdad (medido el 2026-08-23)

Esa lista de arriba es lo que hay que construir. Esto es lo que existe, para que nadie lea el
documento y se crea que ya está:

| De la lista | Hoy |
|---|---|
| Ritmo de corte | **Sí.** Planos, duración típica, si acelera, cuántos cortes caen en un golpe |
| Estructura del hook | **Sí**, los 3 primeros segundos aparte |
| Texto en pantalla | **A medias y solo con fondo liso.** Posición, tamaño y color, pero no la tipografía ni la animación, y con metraje de película detrás falla del todo |
| Zoom/movimiento | **No.** Solo cuántos planos están quietos |
| Sonido | **No.** Detecta golpes de imagen, no música ni SFX |
| Psicología | **No** |
| Color | **No** |

Y hay una diferencia de fondo, más importante que la tabla: **Vidorq no extrae un estilo, lo
empareja**. Compara lo medido con sus diez presets de `captions.PRESETS` y ofrece los tres más
cercanos. Al guardar, lo que queda en el perfil es el NOMBRE del preset, no lo medido, así que
todo lo que se midió se pierde. Mientras eso siga así, cualquier cosa nueva que aprenda el
analizador acaba en la basura al pulsar Guardar.

**El caso que lo dejó claro**, un Short de YouTube que trajo Munir: cada palabra de su
subtítulo lleva un color distinto (blanco, cian, amarillo, verde), una palabra usa otra
tipografía y las letras entran animadas. Vidorq montó texto de un solo color, plano y sacado
del audio en vez de la imagen, o sea peor que el original. El plan para arreglarlo, ordenado,
está en la **META C** de `METAS.md`.

**Y el texto sale del audio, no del vídeo.** Whisper transcribe lo que se oye; los subtítulos
quemados dicen lo que dicen. En ese Short, Whisper escribió "Charvis" donde el vídeo pone
JARVIS. Para recrear los subtítulos de dentro de un vídeo hace falta leer la imagen.

### 3. Feedback continuo (el gimnasio)

Cada edición entregada se puede corregir en lenguaje natural ("los subtítulos más pequeños", "ese corte del minuto 2 es brusco"). Las correcciones:

1. Se aplican al vídeo actual.
2. Se destilan a la regla general correspondiente del perfil ("prefiere subtítulos discretos") **previa confirmación** del usuario.
3. Quedan versionadas en git: puedes ver cómo evoluciona tu gusto.

## El perfil de estilo (formato)

Un directorio local por marca, legible y versionable:

```
perfil/
├── style.md            # el "system prompt" de tu marca: tono, ritmo, reglas duras
├── brand.json          # colores, fuentes, logo, safe areas
├── subtitles.json      # estilo de subtítulos (bloques de 2 palabras UPPERCASE, etc.)
├── animations/         # biblioteca de animaciones aprobadas (código Remotion + preview)
├── references/         # informes de análisis de vídeos de referencia
└── music.md            # géneros, energía, prompt de búsqueda musical personalizado
```

`style.md` se inyecta en cada sesión de edición. Las animaciones aprobadas se reutilizan antes de generar nuevas: consistencia > novedad.

## Por qué esto gana a la competencia

| | Herramientas genéricas | Vidorq |
|---|---|---|
| Estilo | Plantillas fijas | Perfil entrenado con TUS referentes |
| Mejora con el uso | No | Sí (feedback destilado y versionado) |
| Propiedad | Tu estilo vive en su cloud | Archivo local tuyo, exportable |
| Coste | Suscripción | Gratis + tus API keys si quieres cloud |
