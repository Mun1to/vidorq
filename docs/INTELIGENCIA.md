# Lo que Vidorq entiende del vídeo

> Documento interno en español (regla D). Todo lo de aquí está **medido** ejecutándolo
> sobre vídeo real. Lo que no se ha probado lo dice con esas palabras.

Hasta ahora Vidorq solo sabía **lo que se decía**. Con eso basta para tirar los silencios y
no basta para cortar bien: un corte que cae en mitad de un gesto queda mal por muy limpio
que esté el audio. Estas son las tres capas nuevas, y todas corren **en local**, sin API key
y sin subir el vídeo a ninguna parte.

## 1. La vista (`skill/helpers/vision.py`)

Dos pasadas, la barata primero. **El modelo no mira el vídeo, lo lee**, que es la filosofía
que ya estaba escrita en `docs/VISION.md`: darle todos los fotogramas costaría horas y no
compraría nada, y en esta máquina además pelearía con DaVinci por los 8 GB de VRAM.

| pasada | qué hace | coste medido |
| --- | --- | --- |
| `shots()` | aritmética sobre fotogramas reducidos a 64×36: dónde cambia la imagen, cuánto se mueve, cuánta luz tiene | 3,5 s para 40 s de vídeo; **83 s para 10:42** |
| `describe()` | un modelo de visión local, **un fotograma por plano** | ~10 s por fotograma con `qwen3-vl:8b` |

Y una tercera cosa que ahorra la mitad del gasto: cada plano lleva una **firma** de 16
números, y un plano que se parece a otro ya preguntado **no se pregunta otra vez**. Medido
en cámara en mano: 12 planos → **7 preguntas**.

### Qué modelo usa

El primero que encuentre en Ollama, mejor primero. Todos estaban ya en `D:\Stashai\modelos`:

| modelo | veredicto |
| --- | --- |
| **`qwen3-vl:8b`** | el que usa. Llegó a leer un cartel de «Barnes & Noble» dentro del plano |
| `granite3.2-vision:2b` | más rápido y más pobre: dijo «sentado en el suelo» de alguien que camina |
| `moondream:1.8b` | **el último de la lista**: contestó `!!!PASSABLE!!! PASSABLE!!!` a dos de tres fotogramas |

**Trampa medida, y cuesta una tarde encontrarla:** `qwen3-vl` es un modelo **pensante**. Con
un presupuesto de 120 tokens gasta todo el presupuesto razonando y devuelve `response`
**vacío**, con la descripción perfecta abandonada en el campo `thinking`. Pedirle a Ollama
`think: false` **no lo desactiva**. Lo que lo arregla es darle **400 tokens**.

**Segunda trampa, y esta te la vas a encontrar tú:** si tienes la **aplicación con interfaz**
de Ollama instalada, guarda la carpeta de modelos en su propia base de datos
(`%LOCALAPPDATA%\Ollama\db.sqlite`, tabla `settings`, columna `models`) y **pisa la variable
de entorno `OLLAMA_MODELS`**. El síntoma es inconfundible: `ollama list` sale vacío y la API
dice `{"models":[]}` aunque tengas los modelos en el disco. Pasó aquí con 44 modelos
descargados.

Se arregla cambiando la carpeta **dentro de la app** de Ollama, no con la variable. Vidorq
no toca esa configuración de nadie: respeta `OLLAMA_HOST`, así que también se le puede
apuntar a otra instancia que sí vea los modelos.

## 2. Los cortes, ahora con ojo

El audio decide **dónde** cortar; la imagen decide **cuándo exactamente**. Cada límite se
desliza hasta 0,30 s al instante más quieto que tenga cerca, así que un corte deja de caer
en mitad de un latigazo de cámara.

Con una condición que importa: **solo se mueve si hay motivo**. En metraje uniformemente
tranquilo el instante «más quieto» es una moneda al aire, y desplazar todos los cortes un
tercio de segundo para nada es peor que dejarlos. Probado en los dos casos.

El corte nunca invade al vecino ni invierte el tramo.

## 3. La traducción (`skill/helpers/translate.py`)

Whisper traduce, pero **solo al inglés**, que no es lo que pide nadie. Esto usa un modelo
multilingüe local (`aya-expanse:8b` por defecto) sobre la transcripción del vídeo **ya
cortado**.

**Se traducen frases, no trozos de subtítulo.** Traducir los trozos directamente es lo
obvio y está mal: con el estilo `pop` (dos palabras), «muchísimas preguntas» partido en dos
subtítulos volvió como `so many of` / `them arrived`. Traduciendo la frase entera sale
«Wow, I received so many, many questions.», y **después** se vuelve a trocear.

Los tiempos de las palabras nuevas se reparten en proporción a lo larga que es cada
palabra. No es exacto (otro idioma coloca las palabras en otro orden) y nunca se sale de
su propia frase, que es lo que importa.

**Seguro contra desalineación:** un lote que vuelve con menos líneas de las que fue, o
renumerado, **se repite línea a línea**. Saltó en la primera pasada real («lote 4
desalineado»), así que no es teórico: una traducción que se desplaza una línea pondría
todos los subtítulos sobre la palabra equivocada.

Salen dos `.srt` (origen y destino) con **los mismos tiempos**, verificado, y cualquiera de
los dos puede ser el que se quema en el vídeo.

## 4. Transiciones (solo en la salida MP4)

Siete, dibujadas por `xfade` de ffmpeg encadenado: corte seco, disolvencia, fundido a negro,
fundido a blanco, deslizamiento, barrido y zoom. Verificadas mirando el fotograma de en
medio de cada una.

El **corte seco sigue siendo el de por defecto** a propósito: sobre voz, una disolvencia
emborrona las palabras. Esto es para el montaje, no para el hablado. Si `xfade` falla por lo
que sea, el render **vuelve al concat sin pérdida** en vez de tirar la edición entera.

**En Resolve no hay transiciones por API**, y esa parte de la limitación sigue en pie: no se
puede añadir una transición a un corte por script. Pero eso no quiere decir que en Resolve solo
haya cortes, que es lo que decía aquí antes y era falso desde agosto: las tres que solo **tapan**
el corte (fundido a negro, a blanco y destello) se montan como una capa animada encima, en su
propia pista, y las tres están medidas fotograma a fotograma. Las que tienen que **mezclar** los
dos planos siguen siendo imposibles. El detalle está en 8e, más abajo.

## Transcribir: la parte lenta, y lo que la arregla

Es el primer paso y el mas largo, asi que es el que el usuario se queda mirando.
Estaba escrito a fuego con `device="cpu"` en un equipo con una RTX 5060 al lado.

Medido sobre el mismo video de **10 minutos 43**, solo el tiempo de transcribir:

| motor | modelo | tiempo |
| --- | --- | --- |
| CPU 16 hilos | `small` | **~16 minutos** |
| tarjeta | `small` | 34 s |
| tarjeta | `medium` | 49 s |
| **tarjeta** | **`large-v3-turbo`** | **42 s de punta a punta** (23 s de transcripcion) |

La sorpresa es que **`large-v3-turbo` es mas rapido que `small`** y ademas mucho mas
preciso, asi que en tarjeta no hay discusion: `GPU_MODEL = "large-v3-turbo"`, y el camino
de CPU se queda en `small` porque el grande alli seria insoportable. Lo que se maximiza es
**calidad por segundo**, no la calidad sola ni los segundos solos.

### Tres trampas, las tres medidas

**Cargar el modelo en CUDA no demuestra nada.** `WhisperModel(device="cuda")` se construye
tan tranquilo en una maquina sin las librerias de calculo, y revienta **a mitad** de la
primera transcripcion con `cublas64_12.dll is not found`. La prueba de verdad es el primer
trozo de audio, asi que la vuelta a CPU se decide ahi y no antes.

**Las DLL de pip no estan en ninguna ruta de busqueda.** `pip install nvidia-cublas-cu12
nvidia-cudnn-cu12` las deja en `site-packages/nvidia/<lib>/bin`, y ctranslate2 sigue
diciendo que no las encuentra teniendolas al lado. **`os.add_dll_directory` NO basta**:
solo cubre las cargas que pasan por el cargador de Python, y ctranslate2 se lo pide a
Windows directamente. Lo que lee Windows es el `PATH`, y hay que ponerlo **antes** de
importar `faster_whisper`, por eso se hace arriba del modulo y no dentro de una funcion.

**El modo por lotes esta apagado a proposito.** Es mas rapido, y sobre el mismo clip de 40
segundos devolvia **2 frases donde salen 12**: pega el habla por encima de los silencios.
Vidorq corta en limites de frase y el director lee la lista de frases, asi que frases mas
gordas son cortes mas gordos y menos material para razonar. Velocidad que estropea la
edicion no es velocidad.

### La barra ahora se mueve

El motor lanzaba la transcripcion con `capture_output`, asi que **todas** las lineas de
progreso morian dentro de la tuberia y la barra se quedaba en el 10% durante minutos. Una
barra que no se mueve es peor que no tener barra: es la unica prueba que tiene el usuario
de que el programa sigue vivo. Ahora se relee en directo y ademas dice que motor le ha
tocado.

## Lo que cuesta, en números reales

Sobre un recorte de 40 s con voz y cámara en mano:

```
transcribir (Whisper small, CPU)   ~40 s
mirar (planos + movimiento)         3,5 s
describir 7 fotogramas             ~50 s
buscar la cara en 4 cortes          0,3 s  (12 fotogramas a ~20 ms)
traducir 10 frases                 ~16 s   (la primera incluye cargar el modelo)
renderizar 1075 fotogramas         ~30 s   (NVENC)
```

La vista y la traducción son **opcionales** (`vision`, `translate` en `/edit`), porque en un
vídeo de una hora la parte del modelo se va a minutos y no todo el mundo la quiere siempre.

## Cortar sobre el movimiento (`vision.beats` + `cut_on_beats`)

El habla dice **donde se puede** cortar; no dice donde se **quiere**. Un salto, un latigazo
de camara, una mano lanzada al objetivo: ahi es donde corta un editor, y el corte queda
invisible porque el movimiento lo tapa. Es el mismo hecho en el que se apoya el punto 5,
usado hacia delante en vez de a la defensiva.

Sin esto Vidorq solo cortaba en los silencios, asi que una toma de diez segundos con un
salto en medio se quedaba en un bloque plano.

**Como se encuentra el golpe:** maximos locales del movimiento por encima de **4 veces la
mediana del propio video**, que es su nivel de reposo, asi que vale igual para un tripode
que para un vlog a pulso. Y separados **1,2 s**, porque un salto son un aterrizaje, un
bamboleo y un asiento, y merece un corte, no tres. Medido sobre 40 s reales: **7 golpes**,
uno cada 5,7 segundos, y el mas fuerte (12 veces la mediana) era la camara yendose a la
cara. Comprobado exportando el fotograma y mirandolo.

**El corte solo no se ve, y eso costo un intento.** Los dos lados de un corte sobre un
golpe son **contiguos**, no se ha quitado nada, asi que se renderizan identicos y el corte
no existe. Lo que lo hace visible es alternar el encuadre a los dos lados (`BEAT_ZOOM =
1.09`), que es el punch-in que hace cualquier editor de vlog sobre una accion. Verificado
sacando los dos fotogramas del corte y comparandolos.

### Temblor de impacto (solo MP4)

Opcional, y apagado salvo que se pida: es un **look**, no una correccion, y un podcast no
quiere que su camara pegue botes. Sobre el trozo que empieza **en** el golpe, un temblor que
se apaga en **0,20 s** a **17 Hz**, con los dos ejes decayendo juntos pero a frecuencias
distintas (1,0 y 1,37) para que el movimiento no sea una linea diagonal.

Va escrito como **una expresion de ffmpeg**, no moviendo el recorte fotograma a fotograma
desde Python: eso ultimo es lo que hacia la v1 del renderizador y por lo que tardaba
cincuenta minutos en renderizar diez. Una expresion se evalua en C y no cuesta nada medible.

**Un temblor necesita sitio donde moverse.** El recorte solo puede deslizarse dentro del
margen que deja el zoom, asi que un tramo con temblor y zoom 1.0 tiene margen cero y sale
completamente quieto: medido, **la mitad de los cortes salian sin temblar** hasta que un
tramo que tiembla paso a llevar `SHAKE_MIN_ZOOM = 1.05` como minimo.

**Solo en el MP4.** En Resolve haria falta animar la posicion del clip, y los keyframes por
API no existen (el mismo muro que las transiciones).

## 5. Tapar los jump cuts

Lo que más separa un vídeo cortado de un vídeo **editado**. Si quitas un silencio de un
plano fijo, los dos lados del corte enseñan lo mismo desde el mismo sitio y el sujeto
teletransporta. La solución de cualquier montador es cambiar el encuadre a través del
corte, y eso es lo que hace ahora: **zoom 1.07 alternado** en los cortes que lo necesitan.

Y solo en los que lo necesitan: las firmas dicen si los dos lados se parecen, así que un
**cambio de plano de verdad se deja intacto**. Alterna, para que tres cortes seguidos no
acaben todos con el mismo encuadre.

Verificado fabricando un clip de **plano congelado** (donde sin esto los dos lados del
corte serían idénticos byte a byte): salieron 4 tramos con zoom `1.00 / 1.07 / 1.00 / 1.07`
y en el vídeo renderizado se ve el cambio de encuadre a los dos lados del corte.

## Encuadrar el recorte vertical sobre la cara (`skill/helpers/faces.py`)

Recortar un 16:9 a 9:16 tira **dos tercios del ancho**, así que la única pregunta que
importa es qué tercio se queda. Las dos respuestas baratas fallaron y están medidas más
abajo; la que funciona es la herramienta hecha para esto: **YuNet**, un detector de caras
de 227 KB que corre en la CPU.

| método | resultado |
| --- | --- |
| centroide de detalle + movimiento | 3 aciertos de 6. Un fallo puso el recorte en un **coche aparcado** |
| preguntarle la posición a un modelo de visión | contesta «50» mire lo que mire |
| **YuNet** (lo que hay hoy) | **7 de 7 fotogramas**, 13-24 ms cada uno |

**No añade ninguna dependencia**: el venv del motor ya trae `onnxruntime`, y el modelo va
dentro del repo con su licencia MIT (`skill/models/`), así que esto funciona con el cable
de red desenchufado.

### Cómo se enchufa

El motor solo lo llama cuando la salida tiene **otra forma** que el original, porque un
16:9 dentro de un 16:9 no recorta nada y no hay nada que apuntar. Mira **tres momentos por
corte**, se queda con la **mediana** (para que un brazo cruzando el objetivo no arrastre el
plano entero) y escribe `frame_x` en cada tramo del EDL. El renderizador ya leía ese campo.

Un valor **por corte y no por fotograma**, a propósito: un recorte fijo se lee como un plano
elegido, mientras que uno que va siguiendo a la persona necesita suavizado o marea. Y si
mueves la **barra `cropX`** a mano, el detector no se ejecuta: quien ha encuadrado ya ha
contestado a la pregunta.

### Dos umbrales que no son de adorno

**`CONF = 0.4`.** Barrido sobre siete fotogramas con la respuesta sabida a ojo: a 0,6 y 0,5
se pierde una cara que camina a media distancia; a 0,4 salen las siete y todas bien; a 0,2
un falso positivo crece **más que la cara real** y se queda con el encuadre.

**`SAME_LEAGUE = 0.85`.** Quedarse con la caja más grande parecía obvio y era el fallo: en
un plano de selfie **el brazo estirado que sujeta la cámara se detecta como cara** con 0,60
a 0,71, la cara real puntúa 0,85 a 0,88, y el brazo es **más grande**. El primer render
vertical salió encuadrado sobre un codo. Ahora se descartan las detecciones muy por debajo
de la mejor del fotograma y solo después gana la más cercana. Dos caras de verdad en un
plano puntúan las dos alto y las dos sobreviven.

### Qué NO hace

No sigue a la persona **dentro** de un corte, no distingue de quién es la cara (en un plano
con dos personas se queda con la más cercana) y **sin caras recorta por el centro**, que es
lo correcto para un plano de recurso. El centroide de detalle y movimiento sigue guardado en
el track como `x` porque es gratis y sirve para ponderar decisiones, pero `subject_x()`
avisa en su docstring de que es una **pista y no un seguimiento**.

### Preguntarle la posición a un modelo de visión no funciona, y está medido

La idea era buena y sale gratis: el modelo de visión ya mira un fotograma por plano, así
que basta con pedirle también dónde está la persona. **No sirve.** Prueba con dos
fotogramas del mismo vídeo elegidos justo porque discriminan: en uno la cabeza está al
**66%** del ancho (un recorte vertical centrado la deja fuera) y en el otro al **45%**
(centrada). Presupuesto de 1200 tokens, temperatura 0, se pide solo un número:

| modelo | cabeza al 66% | cabeza al 45% |
| --- | --- | --- |
| `qwen3-vl:8b` | dice 50 (8 s) | dice 50 (6 s) |
| `granite3.2-vision:2b` | «aproximadamente el 50%» (10 s) | «aproximadamente el 50%» (3 s) |
| `moondream:1.8b` | devuelve una caja que no corresponde | otra caja que tampoco |

Los tres dan **la misma respuesta a dos imágenes distintas**, así que no están mirando:
están diciendo el centro porque es la respuesta segura. Es la debilidad conocida de los
modelos de lenguaje con visión, que describen bien y **ubican mal**. Además cuesta entre 6
y 31 segundos por fotograma. **No reintentar con otro prompt**: cambiar la redacción es el
mismo intento (regla X).

Que un modelo describa bien una imagen no quiere decir que sepa **dónde** están las cosas
dentro de ella. Para ubicar se usa un detector, y para contar se usa un modelo de lenguaje.

## 6. Editar con un prompt (`skill/helpers/director.py`)

Antes el prompt solo decidia los **cortes**, asi que pedir "en vertical estilo short con
subtitulos animados" daba un video horizontal con lo que estuviera puesto en la interfaz.
Ahora el prompt decide **formato, subtitulos si o no, estilo, animacion, transicion y tipo
de corte**, y funciona **sin API key**, con un modelo local.

Tres capas, cada una pisando a la anterior:

1. valores por defecto sensatos,
2. lo que **juzga** un modelo (que estilo pega con lo que has pedido),
3. lo que **dice literalmente** el prompt, que gana siempre.

La capa 3 no es pereza, es lo que hace que funcione: preguntarle a un modelo si la palabra
"vertical" aparece cuesta 13 segundos de GPU y **se midio fallando**, con su propio
razonamiento diciendo en voz alta *"User asked for vertical, so vertical is appropriate"*
mientras devolvia `source`. Las reglas de palabras tardan **0,003 s** y no se equivocan en
lo que esta escrito.

Los **cortes** los intenta el modelo y, si no devuelve tramos usables, manda el motor
determinista: un modelo que no cuaja no puede costarte la edicion.

### Que modelo dirige, y por que ese

| modelo | veredicto |
| --- | --- |
| `qwen3.5:27b` | **HTTP 500**: son 17 GB y la tarjeta tiene 8. Ni carga |
| `qwen3.5:9b` | acierta, pero **130 s**: razona tanto que se queda sin presupuesto para escribir el JSON |
| **`llama3.1:8b`** | el que usa: **13 s** y JSON valido a la primera |
| `granite4.1:3b` | **7 s**, tambien valido. El de respaldo |
| `qwen2.5:3b` | no devuelve JSON |

Si uno falla se prueba el siguiente, en vez de dar la edicion por perdida.

### Quien piensa el prompt (`skill/helpers/providers.py`)

Se elige en Ajustes, y **de fabrica es el Ollama de tu equipo**: gratis, sin clave y sin
que el video ni la transcripcion salgan de la maquina. Encima de eso, cualquiera de estos:

| proveedor | protocolo | notas |
| --- | --- | --- |
| Ollama local | `ollama` | lo de fabrica, sin clave |
| Anthropic | `anthropic` | `/v1/messages` |
| OpenAI | `openai` | `/v1/chat/completions` |
| OpenRouter | `openai` | una clave, **413 modelos** medidos en la prueba |
| Google Gemini | `gemini` | `:generateContent` |
| Compatible con OpenAI | `openai` | pones la URL base: Groq, DeepSeek, xAI, LM Studio, llama.cpp |

Son **cuatro protocolos, no seis integraciones**, porque el de OpenAI lo habla medio
sector. Por eso "compatible con OpenAI" mas una URL base llega a cualquier cosa que salga
manana sin tocar codigo.

**La lista de modelos se pide al proveedor en el momento**, no viene escrita en el codigo:
una lista a mano lleva razon tres semanas y despues le miente al usuario sobre lo que puede
elegir.

**Que NO es un proveedor.** Codex, opencode, Antigravity y Claude Code son **agentes**, no
endpoints: programas que manejan un editor, no sitios a los que Vidorq pueda mandar un
prompt y recibir JSON. Su sitio es la otra pestana de Ajustes, "Vincular con tu IA", donde
son ellos los que leen `skill/SKILL.md` y manejan a Vidorq, que es justo al reves. Y la
**suscripcion de Claude.ai no da acceso a la API**: eso es una clave de
`console.anthropic.com` que se paga por tokens aparte.

### Gastar la suscripcion que ya pagas (`protocol: "cli"`)

Este archivo decia, en su propia cabecera, que los agentes de codigo *«son programas que
manejan un editor, no endpoints que contesten a un prompt, y no hay nada que Vidorq pueda
llamar»*. Era **falso**, y falso en la direccion cara: mandaba a la gente a comprar credito
de API mientras una suscripcion ya pagada estaba sin usar.

| proveedor | invocacion | medido |
| --- | --- | --- |
| `claude-cli` | `claude -p --tools "" --permission-mode plan` | **16,4 s**, acierta |
| `codex-cli` | `codex exec --skip-git-repo-check --sandbox read-only` | contesta limpio |
| `gemini-cli` | `gemini --skip-trust --approval-mode plan` | **28,3 s**, acierta |

Ni clave ni campo de modelo: la herramienta ya sabe las dos cosas.

**Una trampa medida:** a `gemini` NO se le pasa `-p`. Ese flag *quiere* el prompt pegado
detras, y con el prompt en stdin muere con `Not enough arguments following: p`.

### Esto son AGENTES con herramientas, y el prompt lleva texto de un desconocido

Tres cosas, y las tres cargan peso:

1. **El prompt entra por STDIN**, nunca como argumento. Ademas de lo obvio, una
   transcripcion son decenas de kilobytes y Windows tiene un tope duro de longitud de linea
   de comandos con el que un video largo se choca de frente.
2. **Las herramientas se apagan** con el flag de cada uno (`--tools ""`, `--sandbox
   read-only`, `--approval-mode plan`).
3. **Se ejecuta en una carpeta temporal vacia**, asi que el agente no tiene proyecto
   alrededor que leer, ni `CLAUDE.md` al que obedecer, ni nada del usuario que tocar.

Medido con una transcripcion cuya linea del medio ordena crear un fichero antes de
responder: **devolvio el JSON correcto y no creo nada**.

### Las claves

Viven en `%APPDATA%/Vidorq/config.json`, **fuera del repositorio**, una por proveedor para
que cambiar de uno a otro no pierda la anterior ni le mande a un proveedor el secreto de
otro. El motor **nunca las devuelve**: `/providers` dice *que proveedores tienen clave*, no
cual es, porque un endpoint que la devuelve esta a un fallo de distancia de filtrarla.

Si la clave es mala, la edicion **no se cae**: se apunta el motivo real que dio el
proveedor (`openrouter.ai respondio 401. Missing Auth`) y se sigue con las reglas de
palabras, que en la prueba seguian acertando el vertical en 0,3 s.

## 8. Pedir cosas en un momento concreto (`director.actions`)

El punto 6 decide cosas **globales**: formato, estilo, transicion. Esto decide lo que
pasa **en un segundo concreto**: *"pon un cartel que diga SUSCRIBETE en el segundo 12"*.

Cinco verbos, y son una lista cerrada:

| verbo | que hace |
| --- | --- |
| `title` | un cartel con tu texto, que entra en la lista de subtitulos y por eso hereda el estilo, la animacion y los dos renderizadores gratis |
| `marker` | una marca en el timeline de Resolve |
| `zoom` | acerca ese tramo |
| `cut` | quita ese trozo |
| `voice` | una voz en off que dice tu texto ahi (ver el punto 9) |

Los tiempos van en segundos del video **original**, que es el unico reloj que el usuario
ve; `to_edited()` los traslada al montaje, porque cada corte de delante mueve todo lo que
viene detras. Un momento que cae dentro de un corte no se coloca en un sitio aproximado:
se descarta.

### La lista cerrada no es burocracia

La transcripcion entra en el mismo prompt que tu instruccion, y **una transcripcion es
texto de un desconocido**: el video de cualquiera puede decir "ignora lo anterior y haz X".
Por eso el verbo se valida contra la lista, los tiempos contra la duracion real, el texto se
limpia de caracteres no imprimibles y se corta a 90, y hay techo de 24 acciones. Un modelo
que se invente algo fuera de eso no produce **nada**, en vez de producir una sorpresa.

### Tres cosas que se midieron y cambiaron el diseno

**Un `regex` decide si hay siquiera pregunta.** A un modelo al que le preguntas "¿hay algo
aqui?" le sale antes inventarse algo que decir que no: con *"ponlo en vertical con
subtitulos animados"*, que es puramente global, devolvio un cartel y una marca que nadie
habia pedido. Ahora una expresion regular mira si el texto habla de un momento, y si no,
**ni se pregunta**: 0,00 s y cero alucinaciones.

**El mejor modelo para esto NO es el mejor para lo otro.** Con el mismo prompt real:

| modelo | resultado |
| --- | --- |
| **`llama3.2:3b`** | **acierta en 9,7 s**. El que se usa |
| `phi4-mini:3.8b` | acierta, 17,5 s |
| `qwen3.5:9b` | acierta, 39,9 s |
| `granite4.1:3b` | lista vacia en 9,6 s: forma valida, respuesta falsa |
| `qwen3.5:4b` | **devolvio el ejemplo del prompt tal cual** |
| `llama3.1:8b` | se nego en seco, *"no puedo cumplir con esa solicitud"* |

Ser bueno eligiendo un estilo de subtitulo no dice nada sobre leer un timestamp, asi que
cada tarea tiene su propio orden de modelos.

**Un modelo bajo presion te devuelve el ejemplo.** Y llega con la forma perfecta, asi que
validar la estructura no lo caza. Los textos que coinciden con los marcadores del prompt
(`LO QUE PONE`, `nota corta`) se tiran.

**Un corte de tres centesimas no es un corte.** A *"quita los ultimos 5 segundos"* contesto
39,98 a 40,01 en un video de 40 s: no encontro el momento y devolvio el numero mas cercano
que tenia. Por debajo de medio segundo se descarta, y manda el motor determinista.

## 7. Formato de salida (vertical, cuadrado, 4:5)

`ratio` en `/edit`, y en la interfaz. Recorta la imagen a la forma pedida (no deforma ni
pone barras) y ajusta los subtitulos: en un short caben **10 caracteres por linea** en vez
de 22, con el texto **del mismo tamano fisico** que en horizontal, que es como se ven los
shorts de verdad. En Resolve ademas cambia la resolucion del timeline, sube el zoom de los
clips lo justo para tapar el cuadro (3,16 al pasar de 1920x1080 a 1080x1920) y **desplaza
cada clip con `Pan`** para que el trozo que sobrevive sea el de la cara, igual que en el MP4.

### Cuatro cosas que solo se vieron abriendo Resolve

Los cuatro fallos de abajo convivian a la vez y ninguno daba error. Estan aqui porque
comparten una moraleja: **el motor leia por encima de lo que le contestaba el puente.**

| lo que se veia | la causa |
| --- | --- |
| el timeline salia 1920x1080 pidiendo vertical | el puente quiere `{"key","value"}` de uno en uno y se le mandaba `{"settings":{...}}`; contestaba `key is required` y nadie lo leia |
| el subtitulo salia al 56% y en mitad del pecho | el timeline **anidado** de subtitulos se quedaba en 16:9, asi que Resolve lo encajaba dentro del vertical como a cualquier clip |
| el subtitulo salia a la mitad de tamano | el `Size` de Text+ es una fraccion del **ancho** del cuadro, no del alto. Medido: el mismo subtitulo ocupa 0,0573 del ancho en 16:9 y 0,0574 en 9:16 |
| a la segunda edicion del mismo video se apilaba todo | Resolve rechaza un nombre repetido y el motor seguia, insertando el segundo montaje detras del primero |

Ahora cada una de esas llamadas **comprueba la respuesta y para si Resolve dice que no**.
Un puente que contesta y no le hacen caso es peor que un puente caido, porque el caido se
nota.

### El tamano del subtitulo en Fusion

`Text+` **no parte lineas**: una linea larga se sale por los dos lados en vez de doblarse,
que es lo que si hace libass en el MP4. Asi que el MP4 es la referencia y la comp se ajusta
a el. Con el mismo preset y el mismo subtitulo, medido sobre los fotogramas:

```
"VER TODOS"    MP4 895 px de ancho   Fusion 986 px    Fusion dibuja un 10,2% mas
```

De ahi sale la constante. Y encima hay un techo: el troceador corta por **numero de
caracteres**, pero diez letras estrechas no ocupan lo que diez anchas, asi que la linea mas
larga marca el tamano maximo (`CHAR_ADVANCE = 0.41` del `Size` por caracter, `FIT = 0.94`
del ancho). Antes de eso, `MUCHISIMAS` perdia una letra por cada lado.

**El recorte se apunta a la cara**, con el detector del apartado anterior: tres miradas por
corte y la mediana. Antes iba al centro y se veia, porque en el segundo 3 de la prueba real
el sujeto quedaba cortado por el borde derecho; ahora entra entero. Sigue habiendo barra de
**recorte manual** (`cropX`) y tiene prioridad: si la mueves, el detector ni se ejecuta.

Un aviso medido: para vertical, el estilo de subtitulo se sube a `pop` si el elegido era
demasiado fino, porque un short se ve en un movil a un brazo de distancia y un `minimal` de
53 px alli no es un subtitulo, es una nota al pie.

## 8b. Seguir editando: la segunda frase y las siguientes

Vidorq no editaba una vez, editaba **UNA sola vez**. La pantalla del final ofrecia
«editar otro vídeo» y nada más, que es un montador que se levanta y se va en cuanto pone el
primer corte. Cualquier cambio significaba empezar de cero, transcripción incluida.

Ahora la pantalla del final **es** donde se sigue trabajando. Lo que se escribe ahí se
aplica **encima** del montaje que ya hay.

| | clip de 30 s |
| --- | --- |
| primera pasada | **98 s** |
| cada cambio después | **7,5 s** |

La diferencia es que un retoque no vuelve a transcribir, no vuelve a decidir los cortes y no
vuelve a preguntar al director por los ajustes globales.

### El estado: `sesion.json`

Al lado del `transcript.json`, en el workdir. Guarda el EDL definitivo, los ajustes que se
acabaron usando, la lista de lo que se ha pedido y los nombres de los timelines creados.
Se escribe **al final**, con el EDL ya cerrado.

### Dos cosas que tenían que estar bien para que la segunda ronda signifique algo

**Los tiempos se leen en el reloj del MONTAJE.** Después de una pasada el usuario está
mirando la edición, así que *«quita el trozo del minuto tres»* es el minuto tres de lo que
tiene en pantalla, no del archivo que arrastró. Al director se le da la transcripción ya
recortada (`retime_transcript`) y sus respuestas vuelven por **`to_original()`**, el inverso
de `to_edited()`. Se traducen **todas de golpe y antes de tocar el EDL**: en cuanto se aplica
el primer corte el mapa ha cambiado debajo de las demás. Una acción cuyo segundo ya no
existe se descarta, no se mueve a un sitio parecido; un cartel dos segundos desplazado es
peor que un cartel que no salió, porque solo uno de los dos se nota.

**Los ajustes globales salen de las palabras, sin modelo.** Un modelo al que le pides un plan
completo a partir de *«ponlo en vertical»* rellena todos los demás campos con su opinión y
deshace en silencio el estilo que elegiste dos rondas antes. `from_words()` informa
**solo de lo que la frase dice literalmente**, cuesta 0,00 s y no puede inventar. Para los
momentos concretos se usa el modelo **solo cuando hace falta leer la transcripción**: si la
frase ya trae el verbo y los dos segundos, es una resta y no se pregunta a nadie.

**Y desde el 20-ago-2026 eso vale también para el montaje entero, no solo para la acción.**
Antes el modelo construía el EDL de todas formas y la acción literal se aplicaba encima, o
sea sobre un montaje al que ya le faltaba ese trozo: no llegaba a corregir nada. Medido sobre
un clip de 18,018 s con *«quita un trozo del segundo 4 al 7»* (tres segundos): salían 13,866 s,
o sea **4,15 s fuera**, porque el modelo cortaba de 4,0 a 8,16 para caer en un límite de frase
y anotaba *«Continuación tras el corte solicitado (4s-7s)»*. Las dos conductas estaban escritas
a propósito y se contradecían: `SEG_SYSTEM` le manda cortar en límites de frase, y el bloque
literal del motor dice que es aritmética. Ganaba la que corría antes.

Ahora manda la resta. `es_aritmetica()` es la regla, y lo que la descalifica no son los
ajustes globales (esos los decide `look()`, por su cuenta) sino pedir que **elija otro**:
«lo mejor», «un resumen», «los mejores momentos». Con una de esas delante vuelve el modelo,
aunque la frase traiga números. Medido en el mismo clip: base del panel sola 11,830 s, con la
frase 8,830 s, tres segundos justos. Y de paso se nota en el reloj, porque la vuelta al modelo
no se paga: **36,1 s con la frase literal contra 76,3 s cuando hay que interpretarla**.

### En Resolve se sustituye, no se acumula

Cada ronda crea dos timelines (la edición y su pista de subtítulos anidada). Cinco cambios
serían diez timelines con el bueno enterrado entre ellos.

El puente **no tiene `/timeline/delete`**, y ahí se quedaba esto. Pero en Resolve un timeline
vive en el media pool como cualquier otro item, y **`MediaPool.DeleteClips` se lo lleva**:
dos nombres, `{"success": true, "deleted": 2}`, los dos fuera. Solo se borran nombres que
este programa creó y apuntó en la sesión; nunca se busca «lo que parezca nuestro», porque un
timeline hecho a mano puede parecerlo exactamente.

Medido: la primera edición lleva el proyecto de 5 timelines a 7, y el cambio siguiente lo
**deja en 7** reusando el mismo nombre.

## 8c. Que entienda, y que conteste (`director.change` + `CAPABILITIES`)

Munir escribió *«pon transiciones en cada corte»* y Vidorq rehizo la misma edición, volvió
a colocar los mismos subtítulos, y no dijo nada. Tres fallos encadenados:

1. **No entendió.** Los ajustes de un retoque salían solo de `from_words()`, y sus reglas
   para transiciones eran dos: *disolvencia* y *fundido a negro*. «Transiciones» no encajaba
   con **nada**.
2. **Aunque hubiera entendido, no se podía.** La transición solo se pasaba al render MP4; en
   la salida a Resolve se caía en silencio.
3. **Al no entender nada, trabajó igual.** Rehacer el montaje entero para entregar un vídeo
   idéntico.

### El delta, no el plano entero

`director.change(prompt, actual)` recibe **los ajustes que ya hay** y un **menú cerrado**, y
devuelve solo las claves que cambian. Es distinto de `look()` a propósito: allí no hay nada
elegido y se pide un plan completo; aquí ya hay un vídeo montado. Pedirle un plan entero a
un modelo por una frase de cuatro palabras es como pedir que rehaga la casa porque quieres
mover una silla: rellena todo lo demás con su opinión y te deshace el estilo de hace dos
rondas.

También se le pregunta **qué NO sabe hacer**. Un modelo con un sitio donde poner «eso no
está en la lista» deja de tener que inventarse algo, que es de donde salen las respuestas
raras.

Las **palabras siguen mandando** sobre el modelo: son exactas, cuestan cero y ya estaba
medido que aciertan donde el modelo se despista.

Medido con Claude Code, partiendo de vertical/neon/rebote:

| frase | qué devuelve |
| --- | --- |
| *pon transiciones en cada corte* | `{"transition": "dissolve"}` en 9,9 s, y **nada más** |
| *quita los subtitulos* | `{"captions": false}` |
| *ponle musica epica y subelo a youtube* | nada, y las dos cosas que no puede |
| *dejalo como esta* | nada |

### `CAPABILITIES`: una tabla, no una condición escondida

Qué sabe hacer cada salida, en un sitio. Un turno calcula qué ha cambiado, luego cuáles de
esos cambios **esta salida sabe llevar a cabo**, y si no sobrevive ninguno y no se pidió
nada en un momento concreto, **contesta y para**. No se rehace nada.

El aviso es **del turno que lo pidió**. Sin ese filtro, poner una transición en el turno 2
hacía que el turno 5 siguiera diciendo «no puedo poner transiciones» por un ajuste que nadie
había vuelto a mencionar, y un aviso que se repite es un aviso que se deja de leer.

## 8c-bis. Parar, preguntar cual, y señalar un tramo

Tres cosas que salieron de una sola captura de Munir: escribio *«cut the video»* y Vidorq
contesto *«esto no se hacerlo: cortar el video es muy ambiguo»*, con el texto cortado a
media frase y sin forma de cancelar el turno.

### Parar (`_stop`, `POST /stop`)

Un turno puede tardar minuto y medio, y hasta ahora la unica forma de cancelar una frase mal
dicha era esperar a que acabara.

La bandera se mira **dentro de `set_progress`**, y eso no es pereza: cada fase informa de su
progreso, asi que un solo `if` ahi cubre las cuarenta llamadas y para en el primer sitio
donde el trabajo levanta la cabeza. Lo que no pasa por ahi son los subprocesos largos
(Whisper, ffmpeg), y esos se **matan**: se apuntan en `_live` mientras viven.

La llamada final, la que trae `result` o `error`, **no se para**: es la que cuenta como acabo
la cosa, y tragarsela dejaria la ventana esperando para siempre.

Lo que ya estaba hecho **se queda**. Los subtitulos colocados estan en el timeline y
borrarlos seria una sorpresa peor que dejarlos. El turno parado se **escribe en la sesion**,
porque si no la ventana recarga el historial del motor, no encuentra tu frase y la hace
desaparecer: parece que no la escribiste nunca.

Medido: para en **1 segundo** desde una transcripcion en marcha, `killed: 1`, sin procesos
huerfanos, y el siguiente turno arranca normal.

### «Cortar el video» no es algo que no sepa hacer: es lo que hace

Ese *no se hacerlo* era **falso**. Hay tres formas de cortar en el menu (`clean`, `podcast`,
`montage`) y sabe hacer las tres, asi que la respuesta correcta es enseñarlas.

Y elegir una **vuelve a cortar de verdad**, que es la mitad que faltaba: un retoque reusaba
el EDL de siempre, asi que la pregunta habria tenido tres botones que no hacian nada, y eso
es peor que no preguntar. Cambiar `cuts` o `shake` es lo unico de un retoque que obliga a
recortar; el resto se pinta encima del mismo montaje.

### Señalar un tramo, sin saberse el segundo

*«Que sea facil decirle una parte del timeline»*, dos veces. Pedir un zoom o quitar un trozo
obligaba a saberse el segundo de memoria y teclearlo.

Ahora una frase que pide algo **en un sitio** y no dice en cual (`director.needs_where`)
se contesta con los **tramos del montaje**, cada uno con su reloj y con lo que se dice
dentro, **numerados** para poder dictar «la 2».

El truco es no inventar un estado nuevo: cada opcion **es la frase entera** que se enviaria
escribiendola, asi que el boton no sabe nada que el chat no sepa y entra por el camino que ya
estaba probado. Los tiempos son los del **montaje**, que es el reloj que se esta viendo.

Tres cosas que se midieron mal por el camino, y las tres importan:

| lo que pasaba | por que |
| --- | --- |
| *«haz un zoom»* cambiaba la **entrada de los subtitulos** | «zoom» es la misma palabra para un movimiento de camara y para una animacion de texto, y ganaba la equivocada |
| *«esto no se hacerlo: un zoom en el segundo 11»* | el modelo de AJUSTES vetaba algo que `director.actions` si hace |
| *«quita un trozo en el segundo 11»* no quitaba nada | un corte necesita los **dos** extremos; con un punto solo el modelo devolvia lista vacia |

Y lo que hizo se **cuenta**: `said_deeds` pone «1 zoom» o «1 trozo quitado» en la respuesta.
Antes contestaba «2 tramos» y hacer algo sin decirlo es indistinguible de no hacerlo, que es
literalmente lo que Munir dijo: *«no se que ha hecho»*.

### La CLI hablaba como su dueño

Con `claude-cli` como proveedor, la respuesta de Vidorq salio en el **dialecto que Munir
tiene configurado en su Claude Code**. Se le pregunto en neutro como cortar un video y
contesto *«Klk manito, tira ffmpeg... y caiga clavao, tas»*.

Una CLI de agente **lee la configuracion de su usuario**: su estilo de salida, su
`CLAUDE.md` global. Y ese texto va a dos sitios donde hace daño: la ventana, y un parser de
JSON. Se apaga con `--setting-sources ""` en Claude y `--ignore-user-config` en Codex, y de
paso la instruccion de Vidorq viaja como **prompt de sistema** (`--system-prompt`) en vez de
pegada delante del texto del usuario.

### La red: `tests/todas.py`

Tres archivos y un solo comando, porque tres comandos es un comando que alguien se salta y
el que se salta siempre es el ultimo que se anadio. Ninguna necesita modelo, ni red, ni
video, asi que caben en segundos y se pueden lanzar en cada cambio:

| archivo | qué fija |
| --- | --- |
| `test_relojes.py` | los dos relojes (original y montaje), el montaje reordenado y la curva del punch zoom |
| `test_understanding.py` | lo que entiende de una frase, y lo que se ve escrito al pulsar un botón |
| `test_castellano.py` | que el castellano que ve el usuario lleve sus tildes y sus eñes |

El tercero nació el 19-ago-2026 a la tercera vez de arreglar tildes a mano: 41 cadenas, luego
7 más media hora después, luego 3 más que solo salieron en un primer arranque limpio. Compara
439 textos contra una lista de palabras que en castellano SIEMPRE llevan tilde y no tienen
homógrafo sin ella; nada ambiguo entra (`esta`, `solo`, `aun`, `el`, `tu` son palabras
distintas según la tilde). Dos cosas que se aprendieron escribiéndolo: los plurales de la
familia `-ción` **pierden** la tilde (`transiciones`, `ediciones`, `botones`) y sacaron cinco
falsos positivos; y dejar `mas` fuera por prudencia se comía justo el fallo con el que nació,
que era «Mas ajustes» en el panel.

### `tests/test_understanding.py`

53 casos, sin modelo ni red, en milisegundos. Cada linea es un fallo que se publico, porque
las reglas son expresiones regulares sobre español, se solapan, y **el orden entre ellas
importa**: una regla añadida para una frase rompe otra en silencio. Dos veces volvio la misma
clase de fallo (*«quita los subtitulos»* los encendia; *«haz un zoom»* tocaba el texto).

Escribirlo encontro uno mas: el atajo **Animacion** preguntaba que **estilo** de subtitulo
querias, porque «animada, pero cual» contaba como una decision ya tomada. De ahi sale
`director.decided()`, que es `from_words` menos los `__any__`.

## 8c-ter. Lo que solo se ve con un video de verdad

Todo lo anterior se habia probado con **20 segundos de voz sintetica**. Repetido contra un
video real de **10,7 minutos** de habla espontanea (106 tramos, sin puntuar, con muletillas),
aparecieron tres contradicciones, y las tres con la misma raiz: **el modelo de ajustes
opinaba sobre cosas que no son suyas**.

| lo que dices | lo que contestaba |
| --- | --- |
| *hazme un resumen con los mejores momentos* | cambiaba el corte a montaje **y** decia «no puedo hacer un resumen». Lo acababa de hacer |
| *ponle un filtro de color* | preguntaba cual **y ademas** decia que no podia. O preguntas o declinas |
| *ponle temblor en los cortes* | preguntaba con que criterio cortar, porque leyo «cortes» como una peticion en vez de como un sitio |

Su «no puedo» solo vale para lo que **nadie mas va a atender**: ni lo que si se cambio, ni lo
que se esta a punto de preguntar, ni lo que hace `director.actions`. Eso es `_echoes()`.

**Bateria final: 14 frases reales, todas correctas, 4,5 s de media por frase** con
`claude-cli`. El unico «no puedo» que sobrevive es el verdadero: subir a YouTube y poner
musica.

**Y el flujo entero sobre esos 10,7 minutos**: primera edicion con subtitulos a MP4, y tres
retoques encima. El retoque que solo cambia el color **no vuelve a cortar**; el que cambia el
criterio de corte o el temblor **si**, porque son dos ediciones distintas.

## 8c-quater. Una foto de un fundido es una foto de nada

**Cinco de las diez baldosas de la galeria salian completamente vacias** (bar, glass,
minimal, halo, mono). No era la baldosa: era el fotograma, **1176 bytes de nada** frente a
los 8506 de uno con texto.

Cada estilo trae su animacion de entrada, y esas cinco entran con `\fad`. La foto se saca del
**primer fotograma**, que es justo el instante en el que un fundido de entrada vale **cero**.
La galeria enseñaba el fotograma en el que el subtitulo todavia no ha aparecido, y la galeria
existe **solo** para poder comparar estilos.

`to_ass(..., still=True)` dibuja el estilo **asentado**: sin fundido, con el tamaño en el que
acaba y con el resplandor ya puesto. Una foto no puede enseñar un movimiento, y el movimiento
tiene su propia pestaña, que renderiza video de verdad. El video final **no cambia**: alli el
fundido es correcto porque hay tiempo para verlo.

## 8d. Filtros de color (`skill/helpers/looks.py`)

Ocho miradas, cada una escrita **una sola vez** como cuatro números de CDL (pendiente,
desplazamiento, potencia, saturación). La fórmula es pública y determinista, y eso es lo que
permite lo importante: **las dos salidas salen de los mismos números**.

- **Resolve**: `item.SetCDL` por clip. Cae en la página de color como una corrección
  primaria normal, que se puede abrir y seguir tocando. Un LUT sería una caja negra encima
  del plano.
- **MP4**: un `.cube` generado con esa misma fórmula, cacheado, y aplicado con `lut3d`.

**Lo que prueba que no mienten:** mismo filtro, mismo fotograma, y el peor canal se separa
**10 de 255**, el resto entre 2 y 5. La prueba de control lo cierra: **sin ningún filtro**,
el mismo fotograma ya se separa 10, 7, 1 y 5. Esa distancia es la gestión de color de
Resolve sobre el original, y el filtro **no añade nada**.

Dos trampas medidas por el camino: la ruta del `.cube` va con **una** barra delante de los
dos puntos (`file='C\:/...'`), porque sin escapar ffmpeg parte el filtro y con dos barras
tampoco vale; y `("look", "bn", ...)` chocaba con la regla del fundido a negro, así que
*«ponlo en blanco y negro»* pedía además una transición que nadie había pedido.

## 8e. Animaciones generadas (`skill/helpers/overlays.py`)

*«En Resolve no hay transiciones por API»* era verdad y era también el final de la
conversación. Solo es verdad para las que **mezclan los dos planos**. Un fundido a negro no
mezcla nada: **tapa**, y tapar es una capa encima del corte con su alfa animada.

Es el mismo mecanismo de los subtítulos rápidos: `/media/insert` en una pista propia, frame
exacto, duración exacta, sin mover el cabezal. Y funciona sobre un clip de vídeo cualquiera
por la misma razón: **estas comps no tienen MediaIn**, así que el clip de debajo no entra en
el grafo.

| | en Resolve | en MP4 |
| --- | --- | --- |
| fundido a negro, a blanco, destello | **sí**, capa encima del corte | sí |
| disolvencia, barrido, deslizamiento | no: hay que mezclar dos planos | sí |

Cada capa se **centra en la unión**, para que el plano cambie mientras la pantalla está
tapada, y se recorta a la mitad de su vecino más corto para que un corte rápido no se la
coma entera.

**El vocabulario es cerrado a propósito.** La IA elige de la lista y rellena parámetros;
nunca escribe Fusion. La frase que está leyendo salió de la transcripción del vídeo de otro
(regla AL), y a un modelo al que se le deja escribir nodos se le deja escribir cualquier
cosa.

Medido en una edición real: 6 trozos en V1, 5 capas en V3, y el fotograma del centro de la
primera se exporta con brillo **0,0** mientras los de 30 fotogramas a cada lado están en
51,7 y 60,0.

## 9. La voz en off (`skill/helpers/speech.py`)

*"pon una voz en off en el segundo 5 que diga: atento a esto que viene"*, y en el video
acabado hay alguien diciendolo.

Mismo reparto que los proveedores de texto: **lo que viene de fabrica funciona sin clave y
sin cuenta**, y pagar solo compra una version mejor de algo que ya esta.

| motor | clave | como suena |
| --- | --- | --- |
| **`windows`** | no | la del propio equipo, via `System.Speech`. Gratis, sin internet, y suena a 2009. **El de serie** |
| `elevenlabs` | si | la mejor del mercado hoy, y la que clona la tuya. Se paga por caracteres |
| `openai` | si | la misma clave que ya usas para los prompts. Barata |
| `custom` | si | cualquier endpoint con un `/audio/speech` al estilo de OpenAI |

### Una linea hablada es texto de un desconocido metido en un programa

La frase sale de la transcripcion, o de un modelo leyendo la transcripcion, o sea que sale
del **video de otro**, y acaba siendo argumento de un proceso. Por eso **no se interpola
nunca en una linea de comandos**: el texto, la voz y la ruta de salida se escriben en tres
archivos UTF-8 y a PowerShell se le dice que los lea. No hay comillas que escapar mal
porque no hay comillas.

Medido: con la linea `Hola`; Remove-Item -Recurse -Force ...docs ; $(New-Item ... pwned.txt)`
el sintetizador **leyo la puntuacion en voz alta**. Ni fichero creado ni carpeta borrada.

### Se hace despues de los cortes, no antes

Una voz en off se coloca por el reloj del video **ya montado**, y cada corte de delante ya
ha movido el segundo al que pertenece. Asi que se sintetiza cuando el EDL esta cerrado, y
el `at` pasa por `to_edited()` como todo lo demas. Una linea que caiga en un trozo cortado
se descarta; una que caiga pasado el final del video se descarta tambien, en vez de alargar
el video con una cola de alguien hablando sobre negro.

### El original se agacha debajo

`DUCK_TO = 0.30`, con `0.20 s` de rampa a cada lado y `0.15 s` de margen antes y despues.
Los tres numeros son de radio de toda la vida: una bajada seca se lee como un fallo del
archivo y una lenta se come la primera silaba. La curva se construye como un array de
numpy y se aplica de una multiplicacion, no en un bucle por muestras.

Un detalle que importa: la voz se suma **antes** del recorte a int16. Mezclar encima de una
senal ya recortada haria que los picos se doblen en vez de agacharse.

### Lo que no hace

**En Resolve no hay voz.** La API de scripting no admite meter audio, igual que no admite
transiciones. Se dice en pantalla al terminar (`voice_only_mp4`) en vez de devolver un
timeline con pinta de acabado y en silencio.

### Medido de punta a punta

Clip de 30 s, modelo local, prompt *"pon una voz en off en el segundo 5 que diga: atento a
esto que viene"*:

| paso | resultado |
| --- | --- |
| `director.actions` | `{"do":"voice","at":10.0,"text":"atento a esto"}` en **11 s** |
| `speech.say` | 0,8 s de proceso, 3,5 s de audio |
| el mp4 final | correlacion **0,608** con la linea sintetizada en su sitio |
| la cama debajo | **6907 -> 2882** de RMS mientras habla, y vuelve sola |

Una correlacion de 0,6 con la onda sintetizada no se consigue por casualidad: la voz esta
dentro del archivo, no en un log que dice que si.

## Cabos sueltos honestos

- `shots()` tarda **83 s en un vídeo de 10 minutos** porque descodifica todos los
  fotogramas aunque solo analice uno de cada cinco. Se puede acelerar saltando a los
  fotogramas clave, a costa de precisión en el instante del corte.
- El detector encuentra 264 «cortes» en metraje **sin editar**: son picos de movimiento de
  cámara, no montajes. Para lo que se usa (evitar cortar en movimiento) da igual, pero no
  hay que leerlo como «este vídeo tiene 264 planos».
- La vista **todavía no alimenta al preset `montage`**, que sigue eligiendo por energía de
  audio. Juntar energía de audio con movimiento de imagen es la mejora obvia siguiente.
- El reparto de tiempos de una frase traducida es proporcional a la longitud de cada
  palabra. Para un karaoke palabra a palabra en otro idioma no es suficientemente exacto.
