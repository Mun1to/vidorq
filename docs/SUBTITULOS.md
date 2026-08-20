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

## La galería: los 10 × 9 en una pared, y no en una lista de nombres

Una fila de botones dice «Brasa» y «Halo». Ninguno de los dos significa nada hasta que se
ve, que es la razón de que exista `skill/helpers/previews.py`. Hasta ahora solo se podía
ver **uno cada vez**: eliges, esperas, miras, vuelves a elegir.

La galería (`app/src/Gallery.tsx`, se abre desde la cabecera de la preview) enseña los
**10 estilos** a la vez y las **9 entradas** animándose sobre el look que tengas elegido.
Cada baldosa es un render de verdad sobre **tu** metraje: mismo ASS, mismo recorte, mismo
detector de caras.

### La baldosa es un primer plano, y tiene que serlo

Primera pared que se montó: **cinco de los diez estilos eran una mancha ilegible**.

El número: un subtítulo `minimal` mide un **3,4 % del ancho del cuadro** de alto. En una
baldosa de 198 px eso son **menos de siete píxeles**. Y como el subtítulo es una fracción
fija del cuadro, la única palanca para agrandarlo dentro de una baldosa de ancho fijo es
**enseñar menos cuadro**.

De ahí `BAND_W = 0.62` y `BAND_H = 0.70` en `previews.py`:

- **El ancho manda.** Es el que decide el tamaño de la letra, porque la baldosa está
  limitada por su ancho. La línea de muestra es corta y va centrada, y hasta `pop`, el más
  gordo, ocupa un 42 %: con un 62 % sobra sitio para el halo, que se pinta fuera de las
  letras.
- **El alto es gratis.** No cambia el tamaño de la letra, solo la forma de la baldosa. Con
  el recorte apretado a la mitad inferior, las diez baldosas de un vídeo hablando enseñaban
  **el mismo par de vaqueros**. Subirlo a dos tercios devuelve a la persona al cuadro sin
  coste.
- **El recorte va DESPUÉS del filtro `subtitles`**, nunca antes: libass coloca el subtítulo
  respecto al cuadro que le dan, así que recortar primero movería el subtítulo en vez de
  encuadrarlo.

El cuadro entero se sigue viendo en la preview de debajo, que responde a otra pregunta
(«¿cómo va a quedar?»). Son dos trabajos distintos y por eso se ven distinto.

### Dos cosas que se rompieron por el camino

**Diecinueve peticiones a la vez.** Una galería pide todo de golpe, y los diecinueve hilos
fallaban la caché de caras **en el mismo instante**: cada uno lanzaba su propia pasada de
siete detecciones sobre el mismo archivo. Además compartían una carpeta de trabajo por
salida, así que el primero en terminar la borraba debajo del segundo. Un `threading.Lock`
alrededor de la pasada y carpetas con `uuid`. Medido en frío sobre un clip de 10 minutos:
**19 previews en 3,5 s, una sola pasada de caras, cero carpetas huérfanas**.

**La clave de caché no llevaba la banda.** Solo decía «sí o no», no *cuánto*. Resultado:
cambiar `BAND_H` y seguir sirviendo el recorte de antes, o sea **una preview que miente**,
que es justo lo único que este módulo no puede hacer. Ahora las fracciones van dentro de
la clave (`_band_key`).

### Lo que cuesta

| | frío | después |
| --- | --- | --- |
| 10 estilos | 2,0 s | 0 |
| 9 entradas (WebP animado) | 4,4 s | 0 |
| las 19 en paralelo | **3,5 s** | 0 |

Todo cacheado en disco bajo una clave hecha con lo que entró, así que la galería solo se
paga la primera vez que se abre con ese vídeo.

## Los tres muros de Resolve Free, y por dónde se pasa

Esto es lo que hace que los subtítulos animados sean posibles en la versión gratuita.
El segundo ya no es un muro: se rodeó entero, y la vuelta salió **diez veces más rápida**
que el camino que atravesaba.

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

### 2. La API no fija la duración de un título → entonces no se usan títulos

Este muro se derribó entero el 2026-08-18, y de paso resultó ser el que hacía lento todo
lo demás.

**Lo de antes.** `InsertFusionTitleIntoTimeline` mete siempre un Text+ de **150
fotogramas** y no hay forma de decirle otra cosa. Pero insertar el siguiente **recorta el
anterior**, así que insertando en orden de tiempo cada uno acababa con su duración exacta.
Funcionaba, con dos apaños feos: un título **de relleno** después de cada silencio solo
para recortar, y una pasada final borrando las colas que el ripple dejaba detrás.

**Lo que costaba.** Poner un subtítulo salía por **518 ms**, y el 89% era una sola llamada.
Medido en 21.0.4.5 Free, con la conexión al puente ya abierta:

| llamada | coste |
| --- | --- |
| transporte (una petición que no hace nada) | 13,7 ms |
| `/title/insert` | 31,4 ms |
| escribir la `.comp` en disco | 0,6 ms |
| `/clip/fusion/import` | 32,3 ms |
| **`/playhead`** | **501,9 ms** |

`SetCurrentTimecode` cuesta medio segundo hagas lo que hagas. Igual en la página Edit, en
Cut y en Media. Igual con el timeline vacío que con 25 títulos Fusion dentro. **Igual
cuando no se mueve**, que es lo que lo cierra: no está buscando y no está renderizando, es
lo que cuesta esa llamada. Y estaba ahí solo porque un título no tiene duración propia.

**La salida.** `/media/insert` acepta `recordFrame` **y** una duración, así que un clip cae
donde toca, dura lo que tiene que durar y el cabezal no se mueve. Pide un archivo de medios
en vez de un título, y eso resulta que da igual: los comps de este programa son
`Text+ → Blur → Glow → Saver`, **sin MediaIn**, así que el clip de debajo nunca entra en el
gráfico.

Comprobado, no supuesto: con un soporte **rojo**, el clip sin comp se exporta como
`(255, 24, 0)` y el clip con comp se exporta como `(0, 0, 0)`. El rojo no llega nunca, que
es también la razón de que siga anidándose con su transparencia.

El soporte es un vídeo negro de 64×36 que se genera con ffmpeg una vez por frame rate. **Su
frame rate tiene que ser el del timeline**: `startFrame`/`endFrame` van en fotogramas del
ORIGEN, y un soporte de 30 fps en un timeline de 24 reparte subtítulos un 20% cortos, que
parece un error de redondeo en todas partes menos donde está.

| | 751 subtítulos (vídeo de 10 min) |
| --- | --- |
| antes, 518 ms cada uno | **389 s** solo en colocarlos |
| ahora, 52 ms cada uno | **39,5 s** medidos |

Y la edición entera de ese vídeo, con sus 751 subtítulos, tarda **111 s**: 39,5 s
colocando, 65 s importando los comps y 5 s anidando. El camino viejo sigue en el código
como `_place_slow`, para un puente que no tenga `/media/insert`; se elige solo, al primer
rechazo, cuando todavía no hay nada que deshacer.

**Lo siguiente que sobra**, ya que la cuenta cambió: ahora el que más pesa es
`/clip/fusion/import`, 86 ms por subtítulo sobre un timeline de 751 (medido; en uno de 20
son 32 ms, o sea que escala con el número de clips).

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

Afinado el 19-ago-2026 montando el rótulo, con tres grosores en el mismo timeline y mirando los tres fotogramas: con **0,30** todavía se ven las letras encajonadas una a una, con **0,55** ya es una barra pero le quedan muescas arriba y abajo, y con **0,80** cierra del todo. Las muescas que quedaban a 0,55 no eran del grosor: salían donde el texto llevaba **dos espacios seguidos**, porque el recuadro de un espacio es estrecho y deja un escalón. Se arregla en el texto (`\s+` a un espacio), no subiendo más el grosor.

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

## Overlays con texto: el rótulo y la chapa

Mismo mecanismo que un subtítulo (un `.comp` escrito desde cero, con sus `BezierSpline`
dentro), pero colocado con `/media/insert` en una pista de arriba en vez de como título:
un título cae siempre en V1 y hace ripple, y estos tienen que ir ENCIMA de la edición sin
moverla. V1 es la edición, V2 los subtítulos anidados, V3 las transiciones, V4 estos si V3
ya está ocupada.

Lo que se puede dar por sabido, verificado en Resolve 21.0.4.5 el 19-ago-2026 mirando los
fotogramas exportados:

- La comp **no lleva `MediaIn`**, así que el clip de debajo no entra en el grafo y lo que
  sale es el overlay sobre transparencia. Comprobado con un soporte rojo: el rojo se ve
  alrededor de la barra.
- El estilo lo elige **la palabra que usa Munir** (`director.title_style`), no el modelo:
  un cartel, un rótulo y una chapa son tres cosas y él las nombra distinto.
- El segundo que dice se traduce a **tiempo de montaje** antes de colocarlo, porque los
  cortes de delante ya han movido ese segundo.
- **En el MP4 también sale la barra**, por libass y no por Fusion: en `BorderStyle 3`
  libass rellena la caja con el color del contorno y usa `Outline` como relleno alrededor
  del texto. El rótulo va en su PROPIO `.ass` (uno por tipo, porque un ASS lleva un estilo
  por nombre y la barra de abajo y la etiqueta de arriba son dos pintas a la vez), encadenado
  detrás del de los subtítulos, o sea encima. `overlays.as_preset()` traduce el overlay a la
  forma que espera `to_ass`, y `to_ass` acepta `p=<dict>` para que no haya que meter un
  rótulo en el catálogo de estilos de subtítulo.
  **Una diferencia que queda**, medida renderizando los dos: en Resolve las esquinas de la
  barra son redondas y en el MP4 son rectas, porque libass dibuja un rectángulo y redondearlo
  pediría una figura `\p1` a mano. El color, el alfa, el sitio y el segundo sí coinciden.

## El fundido de entrada no iba, y no era la curva

Comprobado el 19-ago-2026 con las **nueve** entradas dentro de Resolve, midiendo el ancho de
las letras en dos fotogramas. Las nueve asientan en el mismo tamaño (869 px), o sea que
ninguna curva se prolonga mas alla de su ultima clave. Pero **el fundido no ocurria**.

El alfa de un Text+ se escribia en sus `Alpha<n>`, y eso Fusion no lo mueve. Medirlo costo
dos intentos y el primero **no valia**: el fotograma que exporta Resolve trae solo RGB, asi
que un texto al 20% de alfa sale igual de blanco que uno al 100%. Compuesto sobre un clip
rojo si se ve: el fotograma 0 (que deberia ser invisible) daba **41,31%** de pixeles blancos
y el 20 daba 41,41%. Ninguno.

Y no era que la comp estuviera congelada, que es lo primero que hay que descartar: la curva
del TAMAÑO del mismo clip movia las letras de 538 px a 921 y las asentaba en 869, exactamente
lo que dice la curva.

El arreglo es un **Merge** detras del texto sobre un `Background` transparente, con el
`Blend` animado. El `Blend` de un Merge si anima, y funde el grupo entero de una vez, que es
lo que se queria al fundir cada elemento por separado. Medido despues: 0% en los fotogramas
0, 1 y 2; 39,49% en el 3; 41,41% del 5 en adelante.

Afecta a **cuatro** de las nueve entradas (`fade`, `zoom`, `rise`, `focus`), que son las que
tienen `fade: True`.

## El Glow de Fusion se come las letras que no tienen contorno

Comprobado el 19-ago-2026 metiendo los **diez** estilos en un timeline y mirando los diez
fotogramas, que era justo lo que nunca se había hecho: las baldosas de la galería salen del
renderizador del MP4 (libass) y eso no dice nada de cómo salen en Resolve.

Nueve estaban bien. **`halo` salía como tres manchas blancas**, ilegible. Quién lo hacía se
midió descartando: el mismo estilo sin el nodo Blur seguía siendo una mancha, y sin el Glow
salía nítido. O sea, el Glow. La razón es que `halo` es el único con brillo y **sin
contorno**: en libass el halo se dibuja detrás y la letra encima, pero el Glow de Fusion
florece la propia imagen, así que sin un borde oscuro la letra desaparece dentro de su
resplandor. `neon` y `ember` se salvan por su contorno.

El arreglo es `Blend`, que mezcla de vuelta la imagen sin brillo. Probados 1.0, 0.6 y
**0.35**; el último deja el halo Y las letras. Se aplica solo cuando el preset no tiene
contorno, porque los que lo tienen no lo necesitan.

**La primera hipótesis era otra y estaba mal:** que la curva del desenfoque se prolongaba
más allá de su última clave. Se descartó mirando el mismo clip en los fotogramas 2, 9, 18,
27 y 34: salían todos igual de borrosos, y una extrapolación habría ido a peor.

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

## Las transiciones de Resolve son una capa encima del corte, y tapan de verdad

Comprobado el 19-ago-2026 sobre un clip de 90 s que el corte automático parte en cuatro
tramos, o sea tres uniones. Resolve **no tiene transiciones por API**, así que las tres que
solo TAPAN se hacen con una capa animada centrada en cada unión, en su propia pista
(`overlays.at_cuts()` + `resolve_captions.place_overlays()`). Las que tienen que mezclar los
dos planos a la vez (disolvencia, barrido, deslizamiento) siguen siendo imposibles y la
tabla `CAPABILITIES` del motor lo dice antes de empezar, en vez de callarse.

Medido exportando el fotograma de cada unión con `ExportCurrentFrameAsStill` y sacándole el
brillo medio:

| transición | unión 8,09 s | unión 17,81 s | unión 38,53 s | control a 6,00 s |
| --- | --- | --- | --- | --- |
| `dip` (a negro) | 0,00 | 0,00 | 0,00 | 102,60 |
| `white` (a blanco) | 255,00 | 255,00 | - | - |

Y funde, no da un salto. Cruzando la misma unión fotograma a fotograma con `dip`, que dura
0,5 s: **138,60 → 92,81 → 22,78 → 56,03 → 139,57**. Baja y vuelve a subir, que es lo que
tiene que hacer una curva.

Detalle que ahorra un susto al medirlo: los tres fotogramas de las uniones salen **idénticos
byte a byte**, porque un negro puro es un negro puro. Eso no es que el exportador devuelva
una imagen cacheada; el control a 6,00 s sí es distinto.

## La misma barra no mide lo mismo en las dos salidas

Comprobado el 19-ago-2026 restando fotogramas, que es la unica forma de aislar un overlay
del video que tiene detras: el mismo montaje con rótulo y sin él, y el de solo subtítulos
contra el fotograma crudo del original.

| | caja del rótulo | subtítulo `punch` |
| --- | --- | --- |
| MP4 (libass) | 52 px | de la fila 842 a la 1022 |
| Resolve (Fusion) | **203 px** | de la fila 785 a la 939 |

Cuatro veces más alta en Resolve, y no es un fallo suelto: en Fusion la placa se dibuja
**por letra** y solo se cierra en una barra continua a partir de `Thickness 0.80`, que ya
estaba medido. A esa gruesura la caja crece hacia arriba y hacia abajo.

La consecuencia práctica es que **el rótulo no se puede colocar mirando una sola salida**.
Puesto a 0.30 sobraban 22 px en el MP4 y se comía 76 px del subtítulo en Resolve. A **0.40**
las dos van bien: 130 px de hueco en el MP4 y 32 px en Resolve.

Y antes de eso, el 0.06 de la ronda anterior lo sacaba del cuadro por abajo en el MP4: el
texto blanco llegaba a la fila 1079 de 1080. Se arregló mirando una salida y se rompió la
otra, que es exactamente lo que esta tabla existe para evitar.

**Cabo suelto**: unificar el alto de la placa entre libass y Fusion. Mientras no se haga, un
cambio en `y` o en `size` del rótulo hay que medirlo en las dos.

## El cuarto muro que no lo era: un clip de vídeo también admite keyframes

Comprobado el 19-ago-2026. La regla que ordena todo esto es que la API no pone keyframes
pero un `.comp` los lleva dentro, y hasta ahora eso solo se usaba en clips **generados**
(subtítulos, transiciones, rótulos). Para animar el encuadre de un plano de verdad hacía
falta lo contrario: meterle una curva a un clip que ya tiene material.

Sí se puede, y el camino es corto:

1. `AddFusionComp` sobre el `TimelineItem` (`POST /clip/fusion/add`). Resolve devuelve un
   comp con su `MediaIn1 = Loader` **ya atado al material del clip** y su `MediaOut1`.
2. `ExportFusionComp` a un archivo y se lee.
3. Se le mete un `Transform` con `Size` conectado a un `BezierSpline`, entre el `MediaIn1`
   y el `MediaOut1`, y se cambia la entrada del `Saver` para que beba del `Transform`.
   Ojo: la referencia a `MediaIn1` que hay que cambiar es la **última** del archivo; las de
   más arriba son del propio Loader y tocarlas lo desconecta del material.
4. `ImportFusionComp` y ya está.

Medido contra el original escalado, en un timeline real: en el segundo 0,05 el fotograma que
exporta Resolve gana con ×1.00 (diferencia 13,14) y en el 0,75 gana con ×1.06 (10,17), que es
exactamente donde acaba la curva. O sea que se mueve, y llega donde dice.

**Lo que esto abre**: cualquier movimiento de encuadre sobre el material del usuario, no solo
el punch. Lo que NO cambia: el `fill` de un 16:9 dentro de un 9:16 sigue siendo una propiedad
del clip y no un efecto, porque ahí moverse sería el fallo.

## Los subtítulos cuadran con la voz, medido sobre el vídeo final

Comprobado el 20-ago-2026, y es la comprobación que más vale de todas: **se transcribe el MP4
ya editado** y se compara cuándo se OYE cada palabra con cuándo se PINTA su subtítulo. Cierra
el círculo entero (transcribir, cortar, retimar, agrupar, quemar) sin fiarse de ningún paso
intermedio.

Sobre 30 s de habla espontánea, 35 líneas quemadas y 34 comparables:

| | |
| --- | --- |
| desfase mediano | **+0,020 s** |
| peor por abajo | -0,100 s |
| peor por arriba | +0,240 s |
| dentro de 0,25 s | **34 de 34** |

Se hizo justo después de tocar `retime_transcript` (que ahora recorre el MONTAJE y no la
transcripción, para que un montaje reordenado no baraje las frases), porque ese es el punto
donde un fallo no revienta: desplaza. Y un subtítulo medio segundo tarde no parece un error
de reloj, parece que el programa es malo.

Y lo mismo por el otro camino, que es el que de verdad importa porque es el del producto:
se montó el timeline en Resolve, se **renderizó desde Resolve** (`/render/format`,
`/render/settings`, `/render/job/add`, `/render/start`) y se midió sobre ESE archivo. 23
líneas, 22 comparables:

| | MP4 (libass) | Resolve (Fusion, renderizado por Resolve) |
| --- | --- | --- |
| desfase mediano | +0,020 s | **-0,020 s** |
| peor por abajo | -0,100 s | -0,200 s |
| peor por arriba | +0,240 s | +0,180 s |
| dentro de 0,25 s | 34 de 34 | **22 de 22** |

Es la primera vez que el camino de Resolve se comprueba **a la salida** y no mirando
fotogramas sueltos. Un fotograma dice que el subtítulo está bien dibujado; esto dice que está
en el segundo que le toca, que es otra cosa.

**Cómo repetirla**: renderizar un MP4 con subtítulos (o el timeline, desde el puente), sacar
los `chunks` con `cap.build_chunks(server.retime_transcript(transcript, edl), preset)`,
transcribir el archivo de salida con `word_timestamps=True` y emparejar la primera palabra de
cada línea con la palabra oída más cercana.

## Estado de la verificación

Lo que se ha visto renderizado, y lo que no. Compilar no cuenta.

| qué | MP4 (libass) | Resolve (Fusion) |
| --- | --- | --- |
| `pop`, `punch`, `marker`, `bar`, `glass`, `minimal`, `mono` | visto | visto |
| `neon` (glow) | **visto** | **visto**, halo cian real del nodo `Glow`, en vertical 1080x1920 |
| `ember`, `halo` (glow) | **visto** | **visto** (19-ago): los diez presets en un timeline y los diez fotogramas mirados; ahí salió lo de `halo` |
| `ignite` | visto | **visto** |
| las nueve entradas (`pop`, `bounce`, `zoom`, `rise`, `fade`, `throb`, `focus`, `ignite`, `none`) | **visto moviéndose** en dos fotogramas | **visto** (19-ago): ancho de letra en dos fotogramas y alfa medido sobre rojo |
| transiciones `dip` y `white` | visto | **visto** (19-ago), medido abajo |

Ya no queda columna pendiente. Lo que sigue sin verse en Resolve es lo que Resolve no puede
hacer, que está en "Lo que NO se puede hacer".

## Cabos sueltos

- La placa de `marker` es gordita, porque `Thickness` por debajo de ~0,5 deja ver las
  juntas entre las placas de cada letra. Si se quiere más fina hay que volver al camino de
  `Background` + `RectangleMask` + `Merge`, que obliga a **estimar el ancho del texto**
  (Fusion no lo mide desde el comp) y por eso se descartó.
- Timelines con **drop frame** (timecode con `;`): `frame_to_tc` cuenta sin drop. Sin
  probar.
- El puente solo cambia de timeline **por índice**, así que `switch_to()` los recorre
  buscando el nombre. Funciona, pero un `/timelines` en CursorBridge lo dejaría limpio.
