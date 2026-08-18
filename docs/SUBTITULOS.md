# Subtítulos y presets de caption

> Documento interno en español (regla D). Todo lo que hay aquí está **medido** contra
> DaVinci Resolve **21.0.4.5 Free** exportando el fotograma y mirándolo, no leído en un foro.
> Cuando algo no funciona, lo dice con esas palabras.

## Lo que hay

Un preset de caption es **dato**, no código: vive en `skill/helpers/captions.py` y de ahí
salen las dos salidas de Vidorq, así que el estilo que se elige en la app es el mismo en
las dos.

**El look y el movimiento son dos elecciones separadas**, como en CapCut. Antes iban
empaquetados en el mismo preset, lo que escondía la mitad de las opciones: hoy hay
**10 estilos × 9 animaciones**. Cada estilo trae su animación por defecto (`animOf` en
`/captions/presets`), y la app puede pedir otra con `captionAnim`.

| función | para qué |
| --- | --- |
| `build_chunks(transcript, preset)` | trocea las palabras en subtítulos según el preset |
| `to_ass(...)` | el ASS que quema ffmpeg/libass en el MP4 |
| `to_comp(...)` | la composición Fusion que entra en el timeline de Resolve |

Los 10 estilos: `pop`, `punch`, `marker`, `bar`, `glass`, `minimal`, `neon`, `ember`,
`halo`, `mono`. Los tres con halo de verdad son `neon`, `ember` y `halo`.
La app los pide al motor en `GET /captions/presets?lang=es`, así que **añadir uno es
añadir un diccionario**: la interfaz se entera sola.

## Los tres muros de Resolve Free, y por dónde se pasa

Esto es lo que hace que los subtítulos animados sean posibles en la versión gratuita.

### 1. La API no pone keyframes → el archivo los trae puestos

`AGENTS.md` decía "no se pueden animar keyframes por API (solo valores estáticos)".
Es verdad **como llamada**, y falso **como resultado**: un `.comp` es texto, y
`TimelineItem.ImportFusionComp()` se traga lo que haya dentro, splines incluidas.
Vidorq escribe la animación en el archivo en vez de pedírsela a la API.

Comprobado: se importó un comp con un `BezierSpline` sobre `Size`, y
`ExportFusionComp` lo devolvió con sus keyframes intactos (Resolve solo le cambió el
nombre a `TemplateSize`). Los fotogramas 2 y 20 del mismo subtítulo salen de distinto
tamaño, o sea que **anima de verdad**.

También cae aquí el "no se puede editar el interior de nodos Fusion por API": no hace
falta editarlo si el comp ya viene escrito con el texto y el estilo dentro.

Y una simplificación de lo que dice `docs/ARQUITECTURA.md`: el baile documentado de
`AddFusionComp()` → `GetFusionCompNameList()` → `LoadFusionCompByName()` → borrar el comp
dummy **no fue necesario**. `ImportFusionComp` sobre un Text+ recién insertado funcionó
al primer intento, siempre con **ruta absoluta** (el puente corre dentro de Resolve, con
otro directorio de trabajo: una ruta relativa falla sin decir por qué).

### 2. La API no fija la duración de un título → la fija el siguiente título

`InsertFusionTitleIntoTimeline` mete siempre un Text+ de **150 fotogramas** y no hay forma
de decirle otra cosa. Pero insertar el siguiente **recorta el anterior**, así que
insertando en orden de tiempo cada subtítulo acaba con su duración exacta.

Dos detalles que hay que tratar:

- Si después de un subtítulo viene silencio, se inserta un título **de relleno** en su
  final solo para recortarlo, y luego se borra.
- El recorte es un **insert con ripple**: la cola del título anterior sobrevive y se va
  acumulando **detrás** de los buenos. Como se insertan en orden, los reales son siempre
  los primeros, y todo lo que hay a partir de `len(plan)` es basura que se borra de una
  llamada con `/timeline/clips/delete`.

### 3. Un título siempre cae en V1 y descoloca la edición → los subtítulos van anidados

Esta era la trampa peligrosa. Insertar un título con el cursor **dentro** de un clip de V1
no lo pisa: parte el clip y **empuja todo lo que viene detrás**. En una edición ya montada
eso la destroza.

Medido, además: no se puede elegir la pista. Con V2 creada y vacía, el título siguió
cayendo en V1; **bloquear** V1 no lo desvía, hace que la inserción falle; y **apagar** V1
tampoco lo desvía.

La salida es no discutir con la API: los subtítulos se montan en su **propio timeline**, y
ese timeline se **anida** en V2 de la edición real con
`/media/insert` + `trackIndex: 2` + `recordFrame`, que es una colocación exacta y sin
ripple. Comprobado que el alfa se respeta: el vídeo de V1 se ve debajo del texto.

Regalo de hacerlo así: cada subtítulo sigue siendo un **Text+ que puedes abrir y
editar a mano**, y cambiar de estilo es regenerar el timeline de subtítulos.

## Los parámetros de Text+ que importan

Medidos pintándolos. El que más engaña es `ElementShape`:

| `ElementShape<n>` | qué pinta de verdad |
| --- | --- |
| `0` | una copia de las letras; con `Offset` + `Softness` es la **sombra** buena |
| `1` | el **contorno** pegado a la letra (esto es lo que se quiere para el look Hormozi) |
| `2` | un **recuadro por letra** |
| `3` | una **placa redondeada por letra**, que solo se suelda en una placa por línea a partir de ~0,5 de `Thickness` |

El elemento 1 se dibuja delante, así que el orden es relleno, contorno, sombra, placa.
`Softness<n>` está limitado a 0-1 (Resolve recorta un 2 a 1). `TrackingSpacing` es el
espaciado entre letras, con 1.0 como normal.

## Glow, desenfoque y animación: qué nodos aguantan dentro del comp

Un comp de título no está limitado al Text+. Probado importando y mirando el fotograma:

| nodo | estado | para qué |
| --- | --- | --- |
| `Merge` | funciona | apilar capas dentro del mismo subtítulo |
| `Glow` (con `Red`/`Green`/`Blue`, `GlowSize`, `Gain`, `Threshold`, `Blend`) | funciona | el halo de verdad de `neon`, `ember` y `halo` |
| `Blur` (con `XBlurSize` + `LockXY`) | funciona | la animación `focus`, que entra desenfocada |
| `BezierSpline` sobre cualquier entrada **numérica** | funciona | todas las animaciones |
| `Background` en modo degradado | **TIRA RESOLVE** | nada, ver abajo |
| `Angle` de Text+ | acepta el valor y no gira nada | nada |

El glow tiene un tope práctico: con `Gain` por encima de ~2,2 el halo se come las letras y
el subtítulo deja de leerse. El primer intento (blanco, `Gain` 1,6, sin `Threshold`) salió
así; con `Threshold` 0,15 y el halo **tintado** el texto se mantiene nítido.

Todas las animaciones son splines sobre entradas **numéricas**, y eso no es pereza: un
input de tipo punto (`Center`) necesita un tool de camino aparte, así que **no hay
deslizamiento** de subtítulos. Lo que queda (`pop`, `bounce`, `zoom`, `rise`, `fade`,
`throb`, `focus`, `ignite`) cubre las entradas que la gente usa de verdad.

En el MP4 no hay nodo Glow, así que el halo se pinta con un contorno del color del glow y
`\blur` de libass, y `focus` es un `\blur` animado a 0. Las mismas cifras de escala del
catálogo se replican como `\t`, para que un look se mueva igual en las dos salidas.

## Lo que NO se puede hacer, dicho claro

**Máquina de escribir: no.** Ni en Resolve ni en el MP4, y se intentó por dos caminos
distintos:

- Text+ acepta `WriteOnStart` y `WriteOnEnd`, e incluso **conserva sus splines** al
  exportar el comp, pero **no cambian nada en pantalla**: renderizado con `WriteOnEnd`
  fijo en `0.0` la frase entera sigue viéndose.
- En ASS, libass pinta un span `\k` con el color primario aunque el secundario sea
  transparente, así que tampoco revela la línea palabra a palabra.

Por eso el preset dejó de llamarse `type` y se llama `mono`: promete lo que hace.

**Relleno en degradado: no, y además es peligroso.** Es lo que la tienda se reserva para su
versión de pago, y se intentó por dos caminos:

1. `Type1 = 1` + `Gradient1` dentro del Text+. Resolve **conserva los dos nombres** al
   exportar el comp y el texto sigue saliendo blanco: no hace nada.
2. Un `Background` en modo degradado combinado con el alfa del texto (`Merge` con
   `Operator = "In"`). **Esto tiró DaVinci Resolve**, con el informe de fallos y todo. El
   log muestra un bucle de `Main view page is changed to 2` cada 500 ms hasta morir.
   Lo bueno: guardó el proyecto 0,3 s antes de caer, así que no se perdió nada.

**No reintentar.** Si algún día hace falta degradado, el camino es otro: un `.drfx` con la
macro ya hecha e instalada en la biblioteca de efectos, no un comp generado.

**Palabra resaltada dentro de una línea: solo en el MP4.** libass sabe barrer un `\kf` del
color secundario al primario, así que ahí el karaoke es real (se ve la palabra a medio
pintar). En Resolve no hay forma de dar color a una palabra dentro de un Text+, así que
`marker` resuelve lo mismo por otro lado: trozos de dos palabras sobre una placa que se
ajusta sola al texto.

## Los recortes

`edl_from_speech()` en `engine/server.py` trabajaba por frases y ahora trabaja por
**palabra**, que es lo que permite quitar una duda sin tocar lo que la rodea:

- **Muletillas**: solo sonidos de duda (`eh`, `em`, `mmm`...), y solo si están **aisladas**
  por una pausa de 0,12 s a un lado. La lista **no** lleva `bueno`, `pues`, `vale`,
  `entonces`, `esto`, `nada` ni `tipo`: son palabras normales, y cortarlas por cómo se
  escriben destroza frases de verdad. Se vio en una prueba, cortando el sujeto de
  "**esto** es lo que nadie te cuenta". Decidir si una de ésas es muletilla exige leer la
  frase, y eso es trabajo del Modo Pro, no de una lista.
- **Tomas repetidas**: si dos frases seguidas se parecen en un 82% se queda la **última**,
  que es casi siempre la buena. Solo compara vecinas, así que una frase que vuelve más
  adelante en el vídeo sobrevive.
- **Nada más corto de 0,45 s**: se funde con el corte anterior en vez de tirarlo, así que
  las palabras no se pierden.
- **fps de verdad**: `output_resolve` usaba 29,97 clavado a fuego. Ahora lee el fps del
  archivo, porque con un vídeo a 24 o a 60 **todos** los cortes caían en el fotograma
  equivocado y el error crecía a lo largo del timeline.
- Los subtítulos se calculan sobre el **vídeo ya cortado** (`retime_transcript`), no sobre
  el original, o irían desplazados por todo lo que se quitó antes.

## De dónde salieron los estilos

De mirar ficha por ficha qué vende [rystal.shop](https://www.rystal.shop/) y quedarse con
la idea, no con el archivo.

| producto | precio | qué es |
| --- | --- | --- |
| TypeFlow | 59 USD | animación de texto sin keyframes, efecto `.drfx` de la página Edit, 48 estilos, **funciona en Free** |
| Background Engine | 39 USD | 13 motores de fondo animado, 80+ presets |
| TypeFlow Paper | 29 USD | texto recortado en papel |
| One-Click Pop | 9,99 | **no es de captions**: es un look (glow, viñeta, grano, parpadeo, ondas) |
| Liquid Glass | 9,99 | cristal con **refracción** del vídeo, sombras interior y exterior, y glow |
| Frosted Glass | 6,99 | panel que **desenfoca el fondo**, más «edge shine» |
| Dynamic Bar | 5,99 | barra con posición inicial y final, velocidad, retardo, espejo, invertir |
| Easy Highlighter | 5,99 | rotulador con **textura**, curva de easing y glow |
| Title Scroll | 5,99 | texto que se desplaza |

Tres cosas que aprendí de ahí y que cambiaron el código:

1. **El glow es un nodo, no un truco.** Su Liquid Glass expone «Glow: Opacity, Invert Glow,
   Gain, Glow Size, Threshold, Glow Color», que es literalmente el nodo `Glow` de Fusion con
   sus entradas publicadas. Eso me dijo dónde mirar, y de ahí salen `neon`, `ember` y `halo`.
2. **Dónde está la raya de su versión de pago.** TypeFlow Lite regala slide y fade a nivel
   palabra o línea; el de pago se queda **letra a letra, 48 estilos, zoom/blur/rotate,
   degradados y contadores**. De esa lista, `focus` (blur) y `zoom` están ya aquí; letra a
   letra y degradado no se pueden con un comp generado.
3. **Sus efectos van sobre el CLIP, no sobre un título.** Por eso pueden refractar y
   desenfocar lo que hay debajo, y Vidorq no: un comp de título no recibe el vídeo. Esa es
   la condición de desbloqueo del cristal de verdad, y está en el aparcadero.

Lo que enseña la tienda es que **el mercado ya paga por esto y que en Free se puede**, y que
su truco es el mismo que aquí: la animación vive dentro de Fusion, no en llamadas a la API.
La diferencia de Vidorq no es tener el look, es que **no hay que arrastrar nada**: el agente
coloca los subtítulos ya sincronizados con la voz.

Correspondencias: `pop` ← One-Click Pop, `bar` ← Dynamic Bar, `marker` ← Easy Highlighter,
`glass` ← Frosted Glass, `neon`/`ember`/`halo` ← el glow de Liquid Glass, `focus` ← el blur
que TypeFlow cobra. `punch`, `minimal` y `mono` son de casa, y las animaciones (`bounce`,
`throb`, `zoom`) están calcadas del repertorio de CapCut, que es lo que la gente reconoce.

## Cómo se prueba

No hay atajo: se pinta y se mira.

1. Resolve abierto con un proyecto y el puente en marcha (`Workspace > Scripts > Vidorq`).
2. `POST /edit` con `output: "resolve"`, `captions: true` y `captionPreset: "<id>"`.
3. Mover el cursor a la mitad de un subtítulo y `POST /project/export-frame`, y **abrir el
   PNG**. Que compile no dice nada de cómo se ve.

Última comprobación real: vídeo de 22 s, 32 subtítulos con `marker` en el timeline
`Vidorq_prueba`, V1 con el vídeo (653 fotogramas) y V2 con `Vidorq_prueba_Subs` anidado
(653 fotogramas). Acentos correctos (`INCÓMODO`, `VÍDEO MÍO`).

## Estado de la verificación

Lo que se ha visto renderizado, y lo que no. Compilar no cuenta.

| qué | MP4 (libass) | Resolve (Fusion) |
| --- | --- | --- |
| `pop`, `punch`, `marker`, `bar`, `glass`, `minimal`, `mono` | visto | visto |
| `neon` (glow) | **visto** | **visto**, halo cian real del nodo `Glow`, en vertical 1080x1920 |
| `ember`, `halo` (glow) | **visto** | pendiente; comparten el mismo nodo que `neon`, que sí está visto |
| `ignite` | visto | **visto** |
| `bounce`, `zoom`, `focus`, `throb` | **visto moviéndose** en dos fotogramas | pendiente |

Lo pendiente de la columna de Resolve es que no se ha exportado un fotograma de **ese**
preset concreto; el mecanismo que usan (el nodo `Glow`, las splines importadas) sí está
visto funcionando con `neon` e `ignite`.

## Cabos sueltos

- La placa de `marker` es gordita, porque `Thickness` por debajo de ~0,5 deja ver las
  juntas entre las placas de cada letra. Si se quiere más fina hay que volver al camino de
  `Background` + `RectangleMask` + `Merge`, que obliga a **estimar el ancho del texto**
  (Fusion no lo mide desde el comp) y por eso se descartó.
- Timelines con **drop frame** (timecode con `;`): `frame_to_tc` cuenta sin drop. Sin
  probar.
- El puente solo cambia de timeline **por índice**, así que `switch_to()` los recorre
  buscando el nombre. Funciona, pero un `/timelines` en CursorBridge lo dejaría limpio.
