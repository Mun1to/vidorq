# Visión de Vidorq

## La historia (por qué existe esto)

Cuando Munir era pequeño jugaba a Fortnite, Valorant y Rust, y le encantaba crear contenido sobre ello. La realidad de aquello:

- Un **vídeo corto** le llevaba **más de una hora** de edición.
- Un **montage / highlights** de sus mejores jugadas le llevaba **un día entero o más**.
- Y antes de todo eso, **una semana** buscando un programa gratuito que diera calidad de verdad.

Esa herramienta que le hubiera cambiado la vida no existía. Vidorq es esa herramienta.

Hoy la necesidad es todavía mayor: cualquier persona con una empresa o una marca personal necesita contenido orgánico en redes para llegar a más gente, y la edición sigue siendo la barrera. Aprender shortcuts, animaciones, elementos, ritmo… es abrumador (overwhelming). Vivimos en la era en la que se crean programas con un prompt, pero no hay una herramienta buena y libre en la que un prompt edite un vídeo de verdad, dentro de un editor profesional.

## Qué es Vidorq

Un **editor de vídeo con IA, open source y gratuito**, construido como capa de inteligencia sobre **DaVinci Resolve Free** (el editor gratuito más potente que existe). Describes la edición en lenguaje natural, en uno o varios prompts, y la IA la ejecuta dentro de Resolve:

> "Córtame este podcast larguísimo, y en cada cambio de tema añade un recuadro inferior súper bien animado que anuncie la siguiente pregunta."

Eso es un flujo real de Vidorq: transcribe, entiende los cambios de tema, corta en los límites de frase, genera las animaciones del recuadro con tu estilo de marca, las coloca, y se auto-revisa antes de enseñarte nada.

## Los tres pilares

### 1. Editar con prompts dentro de un NLE real
No un juguete web que exporta plantillas: la edición ocurre en tu timeline de Resolve, donde puedes retocar a mano cualquier cosa. La IA es un editor junior infatigable; tú eres el director.

### 2. Entrenamiento de gusto (anti-slop)
"Vídeo con IA" suele significar contenido genérico (slop). Vidorq se diferencia entrenándose con TU criterio:
- Onboarding inicial: cuestionario sobre tu marca, tono, referentes y objetivos.
- Le pasas **links de YouTube / TikTok / Reels** de vídeos que admiras y analiza su ritmo de corte, tipografías animadas, hooks, música y estructura.
- Todo se destila en un **perfil de estilo** versionado que guía cada edición.

Ver [ENTRENAMIENTO.md](ENTRENAMIENTO.md).

### 3. Animaciones cinematográficas como código
Crear animaciones es una obra de arte, como el efecto parallax de una buena web. Y el arte se puede escribir: React/CSS con Remotion, plantillas Fusion, speedramps limpios. Prompts → código → overlays con canal alfa → timeline. Reutilizables, consistentes con tu marca, y siempre editables.

## Para quién

1. **Creadores que empiezan** (el Munir de 14 años): gratis de verdad, sin curva de aprendizaje mortal.
2. **Empresas y marcas personales**: contenido orgánico constante sin contratar un editor a tiempo completo.
3. **Editores profesionales**: automatizan lo mecánico (cortar silencios, subtítulos, versiones por red social) y conservan el control creativo.

## Principios

1. **Open source y local-first.** Todo lo que pueda correr en tu máquina, corre en tu máquina (Whisper, Demucs, rembg, Ollama). Las APIs cloud (Claude, Gemini, OpenAI) son opcionales y con tus propias claves (BYOK).
2. **El LLM lee el vídeo, no lo ve.** Transcripción con timestamps como superficie de razonamiento; visión solo en puntos de decisión. Preciso y barato en tokens.
3. **Calidad sobre cantidad.** Mejor un vídeo que la gente quiera ver que diez que nadie vea. El anti-slop es un valor de producto.
4. **Preguntar → confirmar → ejecutar → auto-evaluar → persistir.** La IA propone estrategia y espera tu OK antes de tocar el corte.
5. **Tu marca es tuya.** El perfil de estilo te pertenece, es un archivo local, exportable y versionable.
6. **Easy tech (filosofía de la Fundación Orquio).** Vidorq no reinventa piezas: coge lo mejor que ya existe (el puente de Resolve, el pipeline de video-use, el patrón de captions de AutoSubs, los motores MIT de animación), lo potencia y lo interconecta en UNA sola herramienta simple y funcional. La complejidad se queda dentro; al usuario le llega un prompt y un resultado.
