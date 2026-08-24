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

## Character Level Styling: RESUELTO (2026-08-24)

Aqui ponia que esto era una pared. No lo era, y el error de bulto merece quedar escrito:

> **El estilo por caracteres NO es un campo del `Text+`. Es un OPERADOR aparte,
> `StyledTextCLS`, colgado de la entrada `StyledText` del nodo.**

Por eso los dos intentos de antes salieron blancos: escribian `CharacterLevelStyling` dentro
del `Text+`, donde Resolve lo guarda (por eso volvia identico al exportar) y no lo mira nunca.
El campo se llama igual, pero vive en otro sitio.

Asi queda el comp, y esto renderiza:

```lua
Tools = {
    Letras = StyledTextCLS {
        CtrlWZoom = false,
        Inputs = {
            Text = Input { Value = "ROJO VERDE AZUL BLANCO", },   -- el texto vive AQUI
            CharacterLevelStyling = Input {
                Value = StyledText {
                    Array = {
                        { 2401, 0, 3, Value = 1 },   -- ROJO: R=1
                        { 2402, 0, 3 },              --       G=0
                        { 2403, 0, 3 },              --       B=0
                        { 2401, 5, 9 },              -- VERDE
                        { 2402, 5, 9, Value = 1 },
                        { 2403, 5, 9 },
                    },
                    Value = ""
                },
            }
        },
    },
    Template = TextPlus {
        Inputs = {
            StyledText = Input { SourceOp = "Letras", Source = "StyledText", },  -- cableado
            ...
        },
    },
}
```

### Como se descifro, que no fue adivinando

1. **Se le pregunto a Fusion desde dentro.** `resolve/VidorqCLS.py` se lanza con
   `Workspace > Scripts > Utility > VidorqCLS`, crea una comp aparte, prueba `AddTool` con
   cada identificador candidato y guarda el `.setting` que escribe RESOLVE. Contesto
   `StyledTextCLS` y dejo el cableado a la vista. La version Free no admite scripting externo,
   asi que este era el unico sitio desde donde se podia preguntar.
2. **Los codigos salieron de una plantilla de fabrica.** En `Simple Two Lines.setting`, el
   bloque `CharacterLevelStylingBase` trae los cinco codigos con `Index` 0, 1 y 2, y solo el
   `2404` da (1,1,1). Como esa plantilla pinta en blanco, `2404` parecia el relleno.
3. **Y un fotograma dijo que no.** Con seis palabras y un codigo por palabra, salieron
   **TRES en cian** y **CUATRO en magenta**, que no era lo escrito en ninguna lectura. Cian es
   blanco sin rojo y magenta es blanco sin verde: o sea que el codigo **no es un color entero,
   es UN CANAL**, y el `Index` no es el canal sino el **elemento**.

### La tabla, ya confirmada

| Codigo | Que es |
| ------ | ------ |
| `2000` | si el elemento esta encendido |
| `2401` | canal **rojo** |
| `2402` | canal **verde** |
| `2403` | canal **azul** |
| `2404` | canal **alfa** |
| `100` / `109` / `102` / `1300` | fuente, grosor, tamaño, espaciado |

- `Index` es el **elemento** del `Text+` empezando en 0, o sea que `Index = n` es el `Red<n+1>`
  del nodo: **0 relleno, 1 contorno, 2 sombra**. Se omite cuando es 0.
- Cada fila es `{ codigo, primerCaracter, ultimoCaracter, Index = elemento, Value = v }`, con
  los dos caracteres **inclusive** y contando desde 0.
- **Los tres canales se escriben siempre, tambien los que valen cero.** El color de partida es
  el del relleno del preset, asi que una fila que falta deja ese canal como estaba: pedir rojo
  puro sobre texto blanco y escribir solo el rojo devuelve blanco. Un cero se escribe
  **omitiendo `Value`**, que es como lo hace Blackmagic.

### La prueba, que es un fotograma y no un "deberia"

**Y se vuelve a sacar con un comando**, porque este baile se hizo tres veces a mano en una
noche: `python resolve/comprobar_cls.py`, con Resolve abierto y el puente puesto. Crea su
propio timeline (no descoloca el tuyo), importa el comp, saca el fotograma por la pagina de
Color y te dice donde esta el PNG y que tres colores tienen que verse.
`python resolve/comprobar_cls.py --limpiar` lo deja como estaba.


`captions.to_comp` lo escribe solo en cuanto una palabra del trozo trae `color`. Con
`{"w": "SI", "color": (1.0, 0.85, 0.10)}` y `{"w": "PINTA", "color": (0.10, 0.95, 0.55)}`,
el comp importado en un titulo de la timeline y sacado por la pagina de Color da
**ESTO en blanco, SI en amarillo y PINTA en verde**. Antes de esto se saco
`ROJO VERDE AZUL BLANCO` y salieron los cuatro exactos.

### Lo que sigue sin salir

El **barrido de karaoke**: que se pinte la palabra que SUENA y vaya cambiando. Hoy Vidorq
escribe **un solo reparto de colores por cartel**, el mismo del primer fotograma al ultimo, asi
que eso sigue siendo del MP4, donde libass tiene `\kf`.

**Cuidado con como esta escrito esto, que no es lo mismo que lo de arriba.** Que el reparto sea
fijo es un hecho de lo que hace el codigo hoy. Que ademas sea IMPOSIBLE moverlo esta
**razonado y NO PROBADO**: la entrada se llama `CharacterLevelStyling` y es de tipo
`StyledText`, o sea un valor con su array, mientras que todas las splines de esta casa cuelgan
de entradas `Number` con `Source = "Value"` (mira `_anim_splines` en `captions.py`). Es un
argumento bueno, pero **no se ha sacado un fotograma que lo demuestre**, y en este mismo
documento ya hubo una "pared" que resulto ser un error de sitio.

Las dos formas de cerrarlo, cuando toque:

1. **Intentarlo de verdad**: cablear una `BezierSpline` a `CharacterLevelStyling` y sacar dos
   fotogramas del mismo cartel. Cuesta lo que costo lo de arriba.
2. **Rodearlo sin pelearse**: un cartel es un clip, asi que N comps cortos con el reparto
   corrido dan el barrido sin animar nada. Es mas trabajo de montaje, pero no depende de que
   Fusion ceda.

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
