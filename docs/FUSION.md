# Recrear un estilo dentro de Fusion

> Documento interno en español (regla D). Lo medido aquí sale de la máquina de Munir el
> 2026-08-23, con **DaVinci Resolve 21.0.4.5 Free**, y de los ficheros que reparte la propia
> instalación. Lo que no se ha podido comprobar está marcado como tal y no se disimula.

## Qué es "recrear un estilo", y qué no

No es copiar la frase del vídeo ajeno y pegarla. Eso copia el **texto**, y es lo que ya hacía
`captions.to_comp()`: un comp con una frase dentro, que sirve para ese subtítulo y para nada
más.

Recrear el estilo es dejar el **estilo suelto**, como un título que aparece en
`Effects Library > Titles` y se arrastra al timeline para escribirle encima cualquier frase.
Eso es un **Fusion Title Template**, y es un fichero `.setting`.

La diferencia la marcó Munir y es la que decide si esto sirve para el vídeo siguiente.

## Dónde vive

```
%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Templates\Edit\Titles\
```

**Medido:** en una instalación limpia la carpeta `Templates` existe pero llega **vacía**, sin
subcarpetas. `Edit\Titles` hay que crearla, y por eso `fusion.carpeta()` la crea.

Lo que el usuario ve en Effects Library es el **nombre del fichero**, no el del nodo de
dentro. Por eso el fichero puede llamarse "Copiado del Short" con espacios y acentos, y el
nodo se llama `Copiado_del_Short`.

## El formato, que no está inventado

Sale de los **417 ficheros `.setting`** que Blackmagic reparte dentro de
`Fusion\Templates\Templates.drfx` de la propia instalación (un `.drfx` es un zip), más los
tres ejemplos oficiales de `ProgramData\...\Support\Developer\Fusion Templates\`.

El esqueleto de un título de fábrica es exactamente este:

```
{
    Tools = ordered() {
        <Nombre> = GroupOperator {
            Inputs = ordered() {
                Input1 = InstanceInput { SourceOp = "Text_1", Source = "StyledText", },
                ...
            },
            Outputs = { MainOutput1 = InstanceOutput { SourceOp = "...", Source = "Output", } },
            ViewInfo = GroupInfo { ... },
            Tools = ordered() { Text_1 = TextPlus { ... }, ... },
        }
    }
}
```

Cuatro cosas que hay que tener presentes, y las cuatro costaron encontrarlas:

1. **Los `InstanceInput` son los mandos públicos.** Es lo que el usuario ve en el Inspector al
   soltar el título. El texto entra por ahí y no como un valor fijo: si no, la plantilla lleva
   la frase clavada dentro y no sirve para el vídeo siguiente.
2. **El grupo y el nodo de dentro NO pueden llamarse igual.** Los `SourceOp` de los mandos
   apuntan al nodo interior, y con los dos nombres iguales Resolve no sabe a cuál. Blackmagic
   usa `Text_1` en todos sus títulos, y aquí se copia.
3. **Los nodos internos van a CUATRO tabuladores.** No es cosmético: con tres, el fichero
   sigue teniendo las llaves equilibradas, así que mirarlo no lo delata, pero los nodos quedan
   fuera del grupo. Se pilla comprobando que ningún `SourceOp` cite un nodo que no existe, y
   eso es lo que hace `tests/test_fusion.py`.
4. **Los `BezierSpline` van en ese mismo `Tools`, a cuatro tabuladores.** Comprobado contra
   `Background Reveal Lower Third.setting`, que pone ahí sus `Text_1Alpha` y `Text_1Opacity`.
   Es la única forma de que un keyframe sobreviva, porque la API de Resolve no los pone.

## Comprobado contra Resolve, no supuesto (2026-08-23, 22:0x)

Con Resolve 21.0.4.5 Free abierto y el puente puesto. Comandos y salida real:

```
POST /timeline/create  {"name":"Vidorq_ProbaFusion"}
  -> {"success": true, "timeline": "Vidorq_ProbaFusion"}

POST /title/insert     {"titleName":"Vidorq Pop","fusionTitle":true}
  -> {"success": true, "title": "Vidorq Pop", "clipName": "Vidorq Pop"}

GET  /timeline/clips?trackType=video&trackIndex=1
  -> {"clips":[{"name":"Vidorq Pop","duration":120,...}]}
```

Tres cosas quedan probadas con eso:

1. **Resolve encuentra la plantilla en Effects Library > Titles.**
   `InsertFusionTitleIntoTimeline("Vidorq Pop")` la mete por su nombre, que es lo
   mismo que hace arrastrarla a mano.
2. **No hizo falta reiniciar Resolve.** Llevaba horas abierto y aun asi vio el `.setting`
   recien escrito.
3. **La duracion es la que se escribio** (120 fotogramas, el `dur` por defecto).

Y exportando el comp de ese clip, Resolve devuelve el estilo entero:

```
Center   = Input { Value = { 0.5, 0.2 }, }      <- la altura del preset
Enabled2 = Input { Value = 1, }                 <- contorno encendido
Enabled3 = Input { Value = 1, }                 <- sombra encendida
Thickness2 = Input { Value = 0.22, }            <- su grosor
Red2     = Input { Value = 0, }                 <- contorno negro
Alpha3   = Input { Value = 0.7, }               <- alfa de la sombra
Softness3= Input { Value = 0.35, }
Offset3  = Input { Value = { 0.048, -0.072 }, }
Size     = Input { SourceOp = "Text_1Size", }   <- atado al spline
Text_1Size = BezierSpline { KeyFrames = { ... } }  <- la ENTRADA sobrevivio
```

**Y escribiendole otra frase, sale con ese estilo.** Se cambio el `StyledText` a
"Y HAY OTRA PERSONA", se volvio a importar y se saco un fotograma de la pagina de Color:
sale en Arial Black, blanca, con su contorno y su sombra, a la altura del preset.

## Character Level Styling: la pared, ahora MEDIDA

Antes aqui ponia que el formato "no esta documentado". Eso era verdad pero se quedaba corto.
Lo que pasa de verdad es peor y es mas util saberlo:

> **Un Text+ acepta `CharacterLevelStyling` y `CharacterLevelStylingBase`, los conserva
> enteros al ir y volver del comp, y los IGNORA al renderizar.**

Como se midio, dos intentos y un fotograma cada uno:

1. **Con los rangos en `CharacterLevelStyling`.** Se escribio una frase de seis palabras y se
   le puso a cada palabra un codigo candidato distinto (2000, 2401, 2402, 2403, 2404) con un
   color distinto, para que un solo fotograma dijera cual de los cinco es el relleno. Resolve
   devolvio el array **palabra por palabra, identico**. El fotograma salio **blanco entero**.
2. **Con los rangos en `CharacterLevelStylingBase`**, precedidos del bloque por defecto
   copiado de `Simple Two Lines.setting`, que es como lo escribe Blackmagic. Resolve tambien
   lo conservo (`{ 2000, 4, 6` sigue ahi al exportar). El fotograma, **blanco otra vez**.

Es el mismo caso que `WriteOnStart` / `WriteOnEnd`, que tambien se conservan y tampoco hacen
nada al renderizar. El modificador lo aplica la interfaz; un comp escrito desde fuera no lo
enciende.

**Por eso se para aqui** (regla X: dos intentos y se nombra la pared). Un tercer micro-ajuste
seria el mismo intento con otra sintaxis.

### Los caminos que quedan, que no son micro-ajustes

1. **Un Text+ por palabra, unidos con Merge.** Cada palabra su nodo, su color y su X. Solo usa
   lo que esta probado que renderiza. Lo que hay que resolver es la posicion, y para eso ya
   hay un dato medido en `captions.py`: un caracter avanza unos 0.41 del `Size`
   (`CHAR_ADVANCE`). Es el camino mas corto a "los mismos colores en las mismas palabras"
   dentro de Resolve.
2. **El overlay con alfa, que ya estaba decidido en `AGENTS.md`.** Generar el subtitulo fuera
   con Motion Canvas o Revideo (MIT) y dejarlo en V2. Da color por palabra y cualquier
   animacion, sin pelearse con Fusion. A cambio, el texto deja de ser editable dentro de
   Resolve.
3. **Que Munir haga UNO a mano y se lea.** Ahora esto significa otra cosa que antes: no se
   trata de aprender el formato (ya se sabe), sino de ver **que hace la interfaz ademas de
   escribir esos campos**, porque escribirlos no basta. Es un minuto y cierra la duda del
   todo. Los pasos: Fusion > Text+ > escribir dos palabras > clic derecho en el campo de texto
   > Character Level Styling > pintar la segunda de otro color > clic derecho en el nodo >
   Settings > Save As.

### Lo que ya no hay que volver a mirar

- El nombre del campo: es `CharacterLevelStyling` y `CharacterLevelStylingBase`, sin prefijo
  en un `TextPlus` suelto (con prefijo `Text1.` en un `MultiText`).
- La forma de cada fila: `{ codigo, primerCaracter, ultimoCaracter, Index = canal, Value = v }`,
  con `Index` 0/1/2 y el 0 implicito, y los valores 0 omitidos. Resolve la acepta y la devuelve
  igual, asi que la sintaxis es esa.
- Los codigos que SI estan confirmados, cruzando el array con los valores explicitos del mismo
  nodo: `100` fuente, `109` grosor, `102` tamaño, `1300` espaciado entre letras.
- Los codigos de color siguen sin identificar, y **ya no importa mientras no renderice**.

## Otro limite, tambien medido

**Un Text+ no ajusta el texto.** Una frase larga no se parte en dos lineas: se sale por los dos
bordes. En un comp eso se tapa encogiendo la letra contra la linea mas larga, pero una
plantilla no sabe que frase le van a escribir, asi que no puede hacerlo por ti. El mando de
tamaño esta expuesto en el Inspector, y `faltantes()` lo avisa.

## Lo que Vidorq NO recrea, y lo dice

`fusion.faltantes(estilo)` devuelve la lista de lo que no sale con nodos nativos, con el
motivo escrito. Hoy solo hay una entrada, la de arriba: el color por palabra sobre texto
arbitrario.

Se avisa a propósito. **Un estilo a medias que no avisa es una mentira**, y es exactamente lo
que este proyecto lleva una semana quitando.

## Plugins de terceros: ninguno, y está comprobado

`Text+`, `Character Level Styling`, `Glow`, `Merge`, `Transform` y los Templates son
**nativos** y funcionan en la versión **Free**. **Reactor NO está instalado** en esa máquina y
no se instala.

Los plugins profesionales de terceros son para más tarde. Se diseña contando con que
llegarán: cuando un estilo pida algo que los nodos de casa no den, `faltantes()` dirá cuál es
la pieza en su campo `pieza`, en vez de aproximarlo en silencio.

## Cómo se comprueba

Sin Resolve (lo hace la suite, `python tests/test_fusion.py`):

- que las llaves cuadran, que es lo que decide si Resolve abre el fichero;
- que ningún `SourceOp` cuelga;
- que el texto es un mando público;
- que la entrada viaja como `BezierSpline` con sus keyframes;
- que `desinstalar()` se niega a borrar un `.setting` que no escribimos nosotros.

Con Resolve delante, y **esto ya se hizo el 2026-08-23** (la salida real está más arriba).
No hace falta que lo haga Munir a mano: con Resolve abierto y el puente puesto, el agente
puede hacerlo entero por el puerto 9876. La receta, para repetirlo:

```
POST 9876/timeline/create   {"name":"Vidorq_ProbaFusion"}
POST 9876/title/insert      {"titleName":"<el nombre>","fusionTitle":true}
POST 9876/clip/fusion/export {"trackType":"video","trackIndex":1,"clipIndex":0,"path":"..."}
   (clipIndex empieza en 0, no en 1)
```

Y para VER el fotograma, que es lo único que cierra la cosa:

```
POST 9876/playhead              {"timecode":"01:00:03:00"}
POST 9876/page                  {"page":"color"}      <- GrabStill exige la página de Color
POST 9876/gallery/grab          {}
POST 9876/gallery/stills/export {"folderPath":"...","filePrefix":"f","format":"png"}
POST 9876/page                  {"page":"edit"}       <- y se deja como estaba
```

**Lo único que sigue necesitando a Munir** es el punto 3 de los caminos de arriba: hacer un
Character Level Styling a mano en la interfaz y guardar ese `.setting`, para ver qué hace la
interfaz que no hace escribir el campo.
