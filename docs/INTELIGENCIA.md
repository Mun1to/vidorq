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

**En Resolve no hay transiciones**, y esa limitación de la API sigue en pie tal cual: no hay
forma de añadirlas por script. Lo que Vidorq monta en Resolve son cortes.

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

### Las claves

Viven en `%APPDATA%/Vidorq/config.json`, **fuera del repositorio**, una por proveedor para
que cambiar de uno a otro no pierda la anterior ni le mande a un proveedor el secreto de
otro. El motor **nunca las devuelve**: `/providers` dice *que proveedores tienen clave*, no
cual es, porque un endpoint que la devuelve esta a un fallo de distancia de filtrarla.

Si la clave es mala, la edicion **no se cae**: se apunta el motivo real que dio el
proveedor (`openrouter.ai respondio 401. Missing Auth`) y se sigue con las reglas de
palabras, que en la prueba seguian acertando el vertical en 0,3 s.

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
