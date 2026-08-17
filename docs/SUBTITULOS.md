# Subtítulos y presets de caption

> Documento interno en español (regla D). Todo lo que hay aquí está **medido** contra
> DaVinci Resolve **21.0.4.5 Free** exportando el fotograma y mirándolo, no leído en un foro.
> Cuando algo no funciona, lo dice con esas palabras.

## Lo que hay

Un preset de caption es **dato**, no código: vive en `skill/helpers/captions.py` y de ahí
salen las dos salidas de Vidorq, así que el estilo que se elige en la app es el mismo en
las dos.

| función | para qué |
| --- | --- |
| `build_chunks(transcript, preset)` | trocea las palabras en subtítulos según el preset |
| `to_ass(...)` | el ASS que quema ffmpeg/libass en el MP4 |
| `to_comp(...)` | la composición Fusion que entra en el timeline de Resolve |

Los 8 presets: `pop`, `punch`, `marker`, `bar`, `glass`, `minimal`, `neon`, `mono`.
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

Regalo de hacerlo así: cada subtítulo sigue siendo un **Text+ que Munir puede abrir y
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

## Lo que NO se puede hacer, dicho claro

**Máquina de escribir: no.** Ni en Resolve ni en el MP4, y se intentó por dos caminos
distintos:

- Text+ acepta `WriteOnStart` y `WriteOnEnd`, e incluso **conserva sus splines** al
  exportar el comp, pero **no cambian nada en pantalla**: renderizado con `WriteOnEnd`
  fijo en `0.0` la frase entera sigue viéndose.
- En ASS, libass pinta un span `\k` con el color primario aunque el secundario sea
  transparente, así que tampoco revela la línea palabra a palabra.

Por eso el preset dejó de llamarse `type` y se llama `mono`: promete lo que hace.

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

De mirar qué vende [rystal.shop](https://www.rystal.shop/) y quedarse con la idea, no con
el archivo: TypeFlow (59 USD, animación de texto sin keyframes, se instala como efecto
`.drfx` de la página Edit y funciona en Free), Background Engine (39), TypeFlow Paper (29),
y presets sueltos de 6 a 10 USD: One-Click Pop, Liquid Glass, Frosted Glass, Dynamic Bar,
Easy Highlighter, Title Scroll.

Lo que enseña esa tienda es que **el mercado ya paga por esto y que en Free se puede**, y
que su truco es el mismo que aquí: la animación va dentro de un macro de Fusion, no en
llamadas a la API. La diferencia de Vidorq no es tener el look, es que **no hay que
arrastrar nada**: el agente coloca los subtítulos ya sincronizados con la voz.

Correspondencias: `pop` ← One-Click Pop, `bar` ← Dynamic Bar, `marker` ← Easy Highlighter,
`glass` ← Frosted/Liquid Glass. `punch`, `neon`, `minimal` y `mono` son de casa.

## Cómo se prueba

No hay atajo: se pinta y se mira.

1. Resolve abierto con un proyecto y el puente en marcha (`Workspace > Scripts > Vidorq`).
2. `POST /edit` con `output: "resolve"`, `captions: true` y `captionPreset: "<id>"`.
3. Mover el cursor a la mitad de un subtítulo y `POST /project/export-frame`, y **abrir el
   PNG**. Que compile no dice nada de cómo se ve.

Última comprobación real: vídeo de 22 s, 32 subtítulos con `marker` en el timeline
`Vidorq_prueba`, V1 con el vídeo (653 fotogramas) y V2 con `Vidorq_prueba_Subs` anidado
(653 fotogramas). Acentos correctos (`INCÓMODO`, `VÍDEO MÍO`).

## Cabos sueltos

- La placa de `marker` es gordita, porque `Thickness` por debajo de ~0,5 deja ver las
  juntas entre las placas de cada letra. Si se quiere más fina hay que volver al camino de
  `Background` + `RectangleMask` + `Merge`, que obliga a **estimar el ancho del texto**
  (Fusion no lo mide desde el comp) y por eso se descartó.
- Timelines con **drop frame** (timecode con `;`): `frame_to_tc` cuenta sin drop. Sin
  probar.
- El puente solo cambia de timeline **por índice**, así que `switch_to()` los recorre
  buscando el nombre. Funciona, pero un `/timelines` en CursorBridge lo dejaría limpio.
