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

**Otra trampa, esta de la máquina de Munir:** la interfaz de Ollama guarda la carpeta de
modelos en su propio sqlite (`%LOCALAPPDATA%\Ollama\db.sqlite`, tabla `settings`, columna
`models`) y **pisa la variable `OLLAMA_MODELS`**. La suya apunta a
`C:\proyectos\Stashai\modelos` y los modelos están en `D:\Stashai\modelos`, así que Ollama
dice que tiene **cero modelos** teniendo 44. Ya estaba avisado en el `AGENTS.md` de Stashai.

Vidorq **no toca esa configuración**: respeta `OLLAMA_HOST`, así que se le puede apuntar a
otra instancia. Para arreglarlo de verdad hay que cambiar la carpeta de modelos en la app de
Ollama, y eso lo decide Munir.

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
traducir 10 frases                 ~16 s   (la primera incluye cargar el modelo)
renderizar 1075 fotogramas         ~30 s   (NVENC)
```

La vista y la traducción son **opcionales** (`vision`, `translate` en `/edit`), porque en un
vídeo de una hora la parte del modelo se va a minutos y no todo el mundo la quiere siempre.

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
