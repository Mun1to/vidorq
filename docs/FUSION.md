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

## Character Level Styling: el nudo que sigue sin abrirse

Un color distinto por palabra dentro de **un solo** `Text+` se hace con el modificador
**Character Level Styling** (clic derecho sobre el campo de texto).

Lo que se sabe, medido:

- Aparece en el fichero como `["Text1.CharacterLevelStylingBase"]`, con esta forma:

  ```
  Input { Value = StyledText { Array = { { codigo, inicio, fin, Index = n, Value = v }, ... },
                               Value = "" } }
  ```

- Los códigos son numéricos y algunos están **correlacionados y confirmados** cruzando el
  array con los valores explícitos del mismo nodo: `100` es la fuente, `109` el grosor, `102`
  el tamaño, `1300` el espaciado entre letras.
- Los códigos `2000` y `2401`-`2404` llevan `Index = 0/1/2`, que tiene toda la pinta de ser
  R/G/B, pero **no está confirmado**.

**La pared, y por qué se para aquí.** De las 417 plantillas de fábrica:

- **ninguna** pinta por rango de caracteres: el campo `CharacterLevelStyling` (sin `Base`)
  llega siempre vacío;
- las **tres** que tocan `CharacterLevelStylingBase` traen el **mismo bloque de color por
  defecto**, así que no hay variación de la que deducir qué código es el relleno;
- la tabla de códigos no está en ningún binario suelto de la instalación.

O sea que no hay de dónde copiarlo, y adivinarlo produciría un fichero que Resolve no abre y
que además no avisa: simplemente no aparece en la lista. Por eso no se inventa.

**Cómo se abre el nudo** (necesita a Munir, un minuto):

1. Abrir Resolve, pestaña **Fusion**, y añadir un nodo **Text+**.
2. Escribir dos palabras, por ejemplo `HOLA MUNDO`.
3. Clic derecho sobre el campo de texto → **Character Level Styling**.
4. Seleccionar solo la segunda palabra y ponerle **otro color**.
5. Clic derecho sobre el nodo → **Settings** → **Save As**, y guardarlo donde sea.

Con ese fichero delante se lee cómo escribe Resolve el rango, y el nudo queda resuelto sin
adivinar nada.

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

Con Resolve delante (esto lo tiene que hacer Munir, la Free no admite scripting externo):

1. Abrir Resolve.
2. `Effects Library > Titles`, y buscar el nombre del estilo.
3. Arrastrarlo al timeline y escribirle **cualquier** frase.
4. Mirar que salga con el tamaño, la posición, el color y la entrada del vídeo original.

Hasta ese paso 4, lo honesto es decir **NO PROBADO EN RESOLVE**, con esas palabras.
