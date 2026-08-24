# Metas de Vidorq

> Regla: METAS, no fechas. La única presión temporal válida son ventanas externas
> (convocatorias, movimientos de terceros), y se anotan como tales.

## La decisión que ordena todo (2026-07-16)

**La v0.1 pública de Vidorq es "el agente que edita dentro de Resolve".**

No es "el editor que aprende tu estilo" ni "el que saca shorts verticales". Esas dos cosas
llegan después, y llegan como roadmap visible, no como requisito para publicar.

Por qué, tras la investigación de mercado (informe completo en
`Vidorq-Core/informes/2026-07-15-competencia-diseno-safezones.md`):

- **Palmier Pro** (YC S24, GPL-3.0, 10.2k estrellas en 3 meses) es el gemelo conceptual de
  Vidorq: agente que opera un editor vía MCP local. Valida la categoría entera. Pero es
  solo macOS 26 Apple Silicon. **Windows + Resolve está libre.**
- **Cardboard, Mosaic, Martini y Palmier exportan XML hacia Resolve/Premiere. Ninguno vive
  DENTRO del NLE.** Vidorq es el único con timeline nativo editable en la herramienta que
  los profesionales ya tienen abierta.
- Ese es el foso: un competidor no lo copia sin tirar su producto a la basura. El
  entrenamiento de estilo, en cambio, sí es copiable (Cardboard lo tiene en su roadmap
  público: "prediction engine como el tab de Cursor"). Se hace porque es nuestro anti-slop,
  no como reacción a ellos.

**Analogía-ancla del producto**: "Tu agente de edición, dentro de un NLE de verdad."
**Contraste de posicionamiento**: "Ellos exportan XML a Resolve. Vidorq vive en Resolve."

---

## META A: el único que vive dentro de Resolve

**Hecho cuando**: sobre un vídeo real, un prompt produce en Resolve 21 un timeline editable
con cortes, zooms y **captions nativos**, y todo se ve pasar en pantalla en directo.

- [x] **Renombrado a "VidorqBridge"** en Workspace > Scripts (2026-07-18). El puente sigue
      siendo el de `davinci-resolve-mcp`; solo cambia la etiqueta que ve el usuario. La
      entrada vieja se aparta como `.bak` para no tener dos en el menú. Instalador
      reproducible: `resolve/instalar.ps1`.
- [x] **Una sola entrada en el menú de Resolve** (2026-08-17): `Workspace > Scripts > Vidorq`.
      Lo que se instala es un cargador sin lógica que lee un puntero y ejecuta el código de la
      carpeta de instalación, así que **actualizar la app actualiza la extensión** y no hay que
      reinstalar nada en Resolve nunca más. Un clic enciende el motor (oculto, sin consola),
      abre la ventana y arranca el puente.
- [~] **Panel dibujado dentro de Resolve**: APARCADO. `resolve/VidorqPanel.py` existe, pero al
      lanzarlo la versión Free responde con el cartel de limitación de Studio: **la API de
      scripting funciona, lo que está capado es dibujar interfaz con UIManager**. Decisión de
      Munir el 2026-08-17: "trabaja más en el backend". Condición de desbloqueo: que alguien
      con Studio confirme que el panel se dibuja, o que Blackmagic lo abra en Free.
      `resolve/VidorqProbe.py` queda en el repo para medir en qué llamada exacta corta.
- [x] **Historial de ediciones** (2026-08-19): la entrada de la barra lateral ya no está
      vacía. Cada edición se anota en `%APPDATA%\Vidorq\ediciones.json` (las tres salidas:
      terminada, parada por ti y fallida) y se sirve en `GET /history`. La lista agrupa por
      día y **cada fila abre su vídeo**, con su conversación entera detrás. Va aparte de
      `sesion.json` a propósito: esa responde "qué le pedí a este vídeo en este proyecto",
      y el historial responde "qué hice el martes", que es lo que se pregunta cuando ya no
      te acuerdas ni del nombre del archivo. Verificado con las tres salidas en pantalla.
- [x] **Compatibilidad de Resolve 21 verificada por API** (2026-08-17, versión 21.0.4.5 Free).
      El puente responde `{"connected": true, "product": "DaVinci Resolve", "version": "21.0.4.5"}`
      y devuelve proyecto y timeline reales. La actualización del instalador no se llevó por
      delante los scripts, porque viven en `%APPDATA%` y no en la carpeta de la app.
      Precedente que obligaba a comprobarlo: Blackmagic rompe el scripting de la versión Free
      sin avisar (UIManager 19.1).
- [x] **El estado de Resolve que ve la interfaz, arreglado** (2026-08-17): el motor preguntaba
      el nombre del proyecto a `/status`, que nunca lo trae. Va en `/project` y `/timeline`.
      El tutorial guiado se quedaba clavado en "no hay proyecto abierto" con uno abierto delante.
- [x] **Editar leyendo, las dos mitades** (2026-08-19): el panel pinta las 1440 palabras con
      su segundo, y marcar un tramo escribe la misma frase que se podría teclear (quitar,
      quedarse, zoom). La segunda mitad es **reordenar**: la pestaña Orden enseña el montaje
      partido en tramos con lo que se dice en cada uno, se arrastran o se mueven con flechas,
      y `GET /tramos` + el campo `order` de `POST /edit` lo aplican como una permutación, sin
      pasar por el modelo. Los dos relojes aguantan el orden nuevo (`to_edited` preguntaba
      "¿ya lo hemos pasado?", que en un montaje reordenado no quiere decir nada) y los
      subtítulos siguen al montaje, no al original. Medido: el MP4 exportado empieza por el
      tramo que estaba al final (diferencia media 0,26 contra el fotograma del original en el
      42,41, y 81,62 contra el que estaba antes ahí).
- [x] **Deshacer el último cambio** (2026-08-19): la sesión guarda el montaje Y los ajustes
      de antes de cada turno (`edl_prev`, `settings_prev`), y el botón del chat vuelve a
      ellos. Solo aparece cuando hay a dónde volver, porque un botón de deshacer que no
      deshace nada se pulsa igual. Un paso, no una pila: pulsarlo dos veces te devuelve
      donde estabas, porque el paso anterior de un deshacer es lo que se acaba de deshacer.
      Medido: reordenado al revés, deshecho, vuelto a reordenar; y con `transition` de `dip`
      a `none`, que es la mitad que se olvida (deshacer el corte y dejarte el ajuste puesto
      no es deshacer).
- [x] **`ImportFusionComp` en 21 Free** (2026-08): el spike se quedó sin sentido porque el
      camino entero está en producción. Un `.comp` escrito desde cero, con sus `BezierSpline`
      dentro, entra y conserva las curvas; verificado por ida y vuelta con `ExportFusionComp`.
      Es lo que mueve subtítulos, transiciones, rótulos y chapas.
- [x] **Captions nativos en el timeline** (2026-08): Text+ editables en su propia pista, diez
      estilos y nueve entradas, los diez mirados fotograma a fotograma DENTRO de Resolve.
      Detalle medido en `docs/SUBTITULOS.md`.
- [x] **Zoom suave con easing** (2026-08-19): el punch ya no es un número fijo, se mueve.
      El comp NO se genera de cero: se le pide a Resolve el del clip (que trae su `MediaIn`
      atado al material), se le mete un `Transform` con el tamaño animado entre el `MediaIn`
      y el `MediaOut`, y se vuelve a importar. La curva es `1-(1-t)³` escrita como siete
      claves lineales, porque las tangentes de Fusion cambian de sintaxis entre versiones y
      a esa resolución no se distinguen. Medido en un timeline real comparando el fotograma
      exportado contra el original escalado: en el segundo 0,05 gana ×1.00 (13,14) y en el
      0,75 gana ×1.06 (10,17), que es justo donde acaba la curva. Si el comp no entra, el
      zoom se queda quieto como antes en vez de perderse.

**Sesión**: 🎬 Sesión 3 de `Vidorq-Core/SESIONES.md`. Solo está bloqueada por 2 clics de UI.

## META B: existe para alguien

**Hecho cuando**: una persona que no es Munir instala Vidorq y edita su primer vídeo en
menos de 30 minutos.

- [x] **Interfaz rediseñada** (2026-07-18): barra lateral fija, iconos de trazo propios en vez
      de emojis del sistema, un violeta plano sin degradados, y modales con cabecera y pie
      fijos que ya no se salen de la ventana.
- [x] **Tutorial guiado** (2026-07-18): "Empezar con Resolve" no explica los pasos, los
      COMPRUEBA (motor, proyecto abierto, puente) contra el endpoint `/resolve` del motor.
      Se abre solo la primera vez.
- [x] **Español e inglés** (2026-07-18): interfaz, motor y panel de Resolve. Reglas del skill
      SmartDefaults: el idioma del sistema decide solo en el primer arranque, la elección
      manual manda para siempre, selector siempre visible. El motor responde en el idioma
      que le manda la interfaz para que no se mezclen los dos en pantalla.
- [x] **Instalador real** (2026-08-17): `pnpm tauri build` en 3m16s produce
      `C:\ct\release\vidorq.exe` (8,7 MB) más `Vidorq_0.1.0_x64-setup.exe` y el `.msi`. Ojo, el
      binario sale en `CARGO_TARGET_DIR`, no en `app/src-tauri/target`. **Sin firmar todavía**:
      Windows los marca como de origen desconocido. GOTCHA: `cargo clean -p vidorq` tras tocar iconos.
- [x] **Push público descongelado** (2026-08-17): 14 commits publicados en `Mun1to/vidorq` tras
      el OK explícito de Munir, con barrido previo de visibilidad y de docs internos.
- [x] **Auditoría de consistencia de punta a punta** (2026-08-19): el mismo encargo por los
      dos caminos, con todo encendido a la vez (vertical, subtítulos, destello, rótulo y
      zoom). MP4: 92 s, 1080x1920, 1669 fotogramas, con el rótulo encima del subtítulo, el
      destello blanco en la unión y las tildes puestas. Resolve: 34 s, timeline 1080x1920 de
      3 pistas, 3 transiciones y 158 subtítulos editables, con el zoom visible donde se pidió.
      La auditoría encontró, y se arreglaron: el cuadro de texto se comía lo elegido en el
      panel; el panel enseñaba ajustes viejos después de hablar por el chat; el motor
      contestaba a cualquier web (`Access-Control-Allow-Origin: *`); el estilo y el ritmo de
      "Tu marca" no llegaban a la edición; pedir un rótulo encendía los subtítulos; y el
      rótulo salía o no según el humor del modelo local.
- [x] **README público al día** (2026-08-19): ya cuenta la instalación de un clic
      (`resolve\instalar.ps1` + `Workspace > Scripts > Vidorq`), no la vieja de tres scripts,
      y lleva editar leyendo, reordenar, deshacer e historial con sus medidas.
- [x] **Copiar el estilo de un vídeo que te gustó** (2026-08-22): pantalla nueva al lado de
      "Tu marca". Le das un vídeo, lo mira y te dice cada cuánto corta y cómo son sus
      subtítulos, te enseña el subtítulo RECORTADO de su propio fotograma, y te ofrece los
      tres estilos de la casa que más se le parecen para que elijas mirando. Piezas:
      `skill/helpers/aprende.py`, `GET /aprende` y `GET /aprende/captura` en el motor, y
      `app/src/Aprende.tsx`. La ficha que sale tiene la MISMA forma que una entrada de
      `captions.PRESETS`, y esa es la decisión que lo sostiene todo: extraer y reconstruir
      son la misma estructura, sin traducir nada por el camino.
      **Medido, probándolo en el navegador de verdad**: un vídeo de seis planos de 2,5 s se
      lee como "corta cada 2.5 segundos, 6 planos"; uno hecho con `punch` propone Punch el
      primero; elegir el segundo guarda `ember` con su nombre; cero errores de consola. La
      posición del subtítulo se recupera con error menor de 0,006 en los diez estilos.
      La pantalla cuenta además **el arranque aparte** (qué pasa en los 3 primeros
      segundos, que es donde se decide si alguien sigue viendo), **cuántos cortes caen
      justo en un golpe de imagen** (la diferencia entre un montaje al ritmo y uno que
      corta por reloj) y **cuántos planos están quietos**.
      **El círculo entero está probado**: se mira el vídeo de un desconocido, se guarda el
      estilo que propone, la siguiente edición lo coge sin que nadie le diga nada, y el
      resultado se vuelve a analizar para comprobar que lleva la misma letra. Es
      `_circulo()` en `tests/test_aprende.py`, con las constantes del motor desviadas a
      temp y devueltas en un `finally`.
      **Dos cosas que se aprendieron midiendo, y las dos empezaron culpando al código:**
      un vídeo de prueba de doce COLORES perdía planos y parecía un fallo del detector;
      lo que pasa es que `vision.shots()` mira en **escala de gris**, y rojo, azul,
      morado, oliva y teal dan los cinco 85. Con los planos separados por **luminancia**
      salen los doce y `acelera` da 0,96 en vez de 0,69. Y la pantalla decía "Cámara
      quieta en 1 de sus 9 planos" con la cámara clavada, porque un subtítulo quemado que
      aparece y desaparece ya es movimiento en la imagen: el número estaba bien y la
      etiqueta mal, así que ahora dice "Imagen quieta".
      **Lo que NO hace todavía**, y está escrito en el código con su causa: acierta el
      estilo exacto 4 de 10 veces (7 de 10 entre los tres que ofrece), porque cuatro de los
      diez son letra blanca abajo y ninguna cuenta los separa; no detecta la plancha de
      color detrás del texto; el nombre que le pones se guarda pero aún no sale en el
      selector de editar (esto último ya SÍ funciona, ver abajo).
- [x] **El estilo copiado llega hasta el final** (2026-08-22): tres cosas que estaban a
      medias y se cerraron. **El link** ya entra: `skill/helpers/descargar.py` acepta
      TikTok, Reels, Shorts, Vimeo, X, Facebook y Twitch, con lista blanca que rechaza
      cualquier URL que apunte a la propia máquina; el caso que más importa es
      `http://127.0.0.1:9877/shutdown`, que es el interruptor de apagado del propio motor,
      y está probado en la ventana. yt-dlp entro en `requirements.txt` el 2026-08-23: su rueda de
      PyPI es Unlicense y vale dentro de un producto de pago, y lo que lleva GPLv3+ son
      los ejecutables que ellos empaquetan, que no se redistribuyen (medido, en
      `docs/RECURSOS.md`). Los Shorts de YouTube bajan en 3 segundos; un video largo de
      YouTube da 403 y Vimeo da 401, porque hacen falta piezas extra que no se instalan
      sin decidirlo. **El nombre** que le pones al estilo ya sustituye a la etiqueta
      de la casa en el selector de editar. Y **el círculo se cierra en la app**: el panel
      estaba en Pop, se elige Brasa en la pantalla nueva y el panel pasa a Brasa. Antes se
      guardaba en la marca y no llegaba a ninguna edición, porque el panel manda siempre el
      suyo y lo pedido gana.
- [x] **Visto montado dentro de Resolve** (2026-08-23). Es lo único del producto que
      ninguna prueba cubre, y no por falta de ganas:
      - **Lo que se vio en su pantalla**, con el puente arrancado desde
        `Workspace > Scripts > Vidorq`: `python resolve/comprobar_timeline.py` creó
        `Vidorq_PruebaVidorq` con 7 subtítulos, y el puente confirma
        `trackCount: video 2`, con **V1 = los 2 cortes** de la fuente y
        **V2 = `Vidorq_PruebaVidorq_Subs` anidado**. En el visor, con el cabezal en
        `01:00:01:12`, se lee **MONTO en amarillo con contorno negro**, que es `punch`
        exacto. Sale "Media Offline" detrás porque el script borra su vídeo temporal al
        terminar, y el subtítulo se ve igual: es una composición de Fusion y no depende
        del clip.
      - **Los dos timelines de prueba se quedaron en el proyecto "Prueba Vidorq"**
        (`Vidorq_PruebaVidorq` y `Vidorq_PruebaVidorq_Subs`). No se borran desde aquí:
        borrar cosas dentro del Resolve de alguien tiene más riesgo que dejar dos
        timelines con nombre reconocible en un proyecto que ya se llama de pruebas.
      - El diálogo entero con el puente **sí está probado**, contra un puente de mentira que
        habla su protocolo (`_hasta_resolve` en `tests/test_aprende.py`). Monta los dos
        timelines, coloca los cortes, anida los subtítulos, y se abre la composición de
        Fusion para comprobar que lleva dentro el estilo aprendido: Arial, Black y
        `(1.0000, 0.8400, 0.0000)`, que es `punch` exacto.
      - Lo que falta es que **Resolve dibuje** lo que se le entrega, y eso solo se ve en su
        pantalla. Con Resolve abierto, en un proyecto, y el puente puesto desde
        `Workspace > Scripts > Vidorq`: `python resolve/comprobar_timeline.py` monta un
        timeline de prueba y dice las cuatro cosas que mirar.
      - **Cómo se llegó hasta el clic**: no hay carpeta `Scripts/Startup`, y Resolve no
        expone sus menús por accesibilidad, así que lo que funcionó fue traer la ventana
        al frente con `AttachThreadInput` (un `SetForegroundWindow` a secas lo bloquea
        Windows), y navegar el menú por coordenadas MIRANDO una captura en cada paso.
        Eso solo se hace con permiso, porque le tapa la pantalla a quien esté delante.
        El detalle de los dos primeros intentos, por si vuelve a hacer falta: no
        existe carpeta `Scripts/Startup` que Resolve ejecute sola, y Resolve **no expone sus
        menús por accesibilidad** (UIAutomation devuelve 0 barras de menú; es una app Qt).
        Al arrancar además se queda en el *Project Manager*, que ni siquiera tiene barra de
        menús. Lo único que quedaría es hacer clics por coordenadas a ciegas, y eso no se
        hace en la máquina de Munir mientras la está usando.
      - **Trampa que costó una afirmación falsa:** Resolve 21.0.4.5 está en
        `C:\Apps\Random APPS\Davinci\`, **no** en `C:\Program Files\Blackmagic Design\`,
        donde solo quedan restos de una instalación vieja. Buscar por las rutas habituales
        lleva a concluir que no está instalado. La forma fiable es leer el destino del
        acceso directo del escritorio.
- [ ] Firmar los instaladores para que Windows no los marque como origen desconocido.
- [ ] GIF del flujo real en el README (el texto en inglés ya está; falta la imagen que
      enseña el timeline montándose solo dentro de Resolve, que es lo que no se puede contar).
- [x] **Landing con el copy de la investigación** (2026-08-20): el **contraste
      explícito** ya es una sección propia con el titular *"Los demás exportan XML a Resolve.
      Vidorq vive en Resolve"*, y el **cierre participativo con prompts de ejemplo** también,
      con las cuatro frases que el programa entiende de verdad (tres de ellas sin pasar por
      ningún modelo). De paso se quitó de la página una función que no existe: la sección
      central vendía el entrenamiento de estilo en presente y ahora va como "En camino".
      Cerrado el mismo día: el hero ya abre con la **analogía-ancla** ("tu agente de edición,
      dentro de un editor de verdad") en vez de con la categoría, y hay **sección de
      novedades** con las tres últimas entradas fechadas por sus commits. El titular decía
      "todas las semanas" y se cambió a "esto no está parado", porque entre el 22-jul y el
      10-ago hubo diecinueve días sin un solo commit y el dato es público.
- [x] **La web, viva** (2026-08-21): la landing de `web/` ya se sirve en
      **https://mun1to.github.io/vidorq/**. GitHub Pages en modo rama solo sabe servir desde
      la raíz o desde `docs/`, así que en vez de mover la web se publica con un workflow
      (`.github/workflows/pages.yml`) que despliega `web/` tal cual y se redispara solo al
      tocar esa carpeta. Comprobado sirviendo: HTML 200, y `styles.css`, `app.js` y
      `logo.png` también. Munir la dio por buena tal como está ("es solo por tener una web,
      aunque sea"), así que no se rediseñó nada.
- [x] **El render se prueba mirando el resultado** (2026-08-21): `tests/test_render.py`
      fabrica un vídeo de cuatro colores planos (rojo, verde, azul y amarillo, cinco segundos
      cada uno), lo edita con el motor de verdad y **abre el MP4 que sale a leer los
      fotogramas**. Un corte medio segundo desviado enseña otro color, y la prueba lo ve. 18
      casos en 8,6 s, se salta sola si no hay ffmpeg y borra sus vídeos al terminar. Con esto
      el camino del **MP4** está probado de punta a punta; el de **Resolve** sigue sin
      probar, porque hace falta que Munir abra `Workspace > Scripts > Vidorq`.
- [ ] Vídeo de lanzamiento editado CON Vidorq (dogfooding: la demo es el producto).
- [x] **Barrido de seguridad** (2026-08-19): ni una clave, ni en el árbol de ahora ni en el
      historial entero (los dos `sk-ant-...` y `AIza...` que saltaron son los *placeholders*
      del formulario de ajustes). Ningún doc interno publicado, ningún carácter invisible, el
      `.gitignore` acaba en salto de línea. **Un hallazgo**: `build_resolve_timeline.py`
      llevaba escrita dentro la carpeta de Descargas de Munir y el nombre de su vídeo, así
      que en cualquier otro ordenador reventaba al IMPORTARLO, y en el suyo montaba un
      timeline entero con solo ejecutarlo. Ahora pide el EDL y el clip por la línea de
      comandos. En el historial se queda: es una ruta, no una credencial, y lo publicado no
      se reescribe (regla AH).
- [ ] **`vidorq.com`, y con prisa** (la parte del push ya está hecha, arriba). El nombre
      lleva publicado en GitHub desde el 2026-08-17 y ahí es donde a VoCript le pillaron el
      `.com` treinta y siete días después de publicarlo (regla AK). El plazo no lo pone
      nadie de aquí: comprobar y comprar.

**Sesión**: 📦 Sesión 5. Depende de META A.

## Lo que Vidorq es de verdad, dicho por Munir (2026-08-23)

> "El objetivo es crear un **harness**, una estructura para dársela bien masticada a los agentes
> que vayan a editar en DaVinci Resolve. Una estructura sobre la cual puedan trabajar todos los
> agentes y modelos de inteligencia artificial que conectes, y puedan copiar contenido de vídeos
> que importes y crear los componentes, animaciones, transiciones, color, decirte también qué
> efectos se utilizan en ese vídeo, cortar vídeos automáticamente, poner subtítulos
> automáticamente, y muchísimo más."

Esto no es una pantalla, es una plataforma, y reencuadra todo lo de abajo. **Vidorq no es una
herramienta con un agente dentro: es la base sobre la que trabaja el agente que sea.** Cuatro
capas, con lo que hay medido el 2026-08-23:

| Capa | Qué es | Estado |
|---|---|---|
| **1. Percepción** | leer el vídeo ajeno | subtítulos quemados (dónde, qué dicen, color por palabra, contorno, halo, grosor), planos, ritmo, arranque, caras. **Falta** transiciones, efectos, zooms, grading, movimiento de cámara |
| **2. Componentes** | el almacén de lo copiado | `skill/helpers/galeria.py`, con campo `tipo` para que quepan animaciones y transiciones. **Solo sabe guardar un tipo**, el estilo de subtítulo |
| **3. Ejecución** | el puente de Resolve | **18 endpoints de 152**. Sin tocar: `/timeline/scene-cuts` (Resolve detecta los cortes él solo), `/clip/smart-reframe`, `/clip/stabilize`, `/clip/magic-mask`, `/color/copy-grades`, `/color/export-lut`, `/render/*` (12) |
| **4. Superficie para agentes** | cómo pregunta un agente | `skill/helpers/agente.py` y `GET /agente/informe` + `/agente/capacidades`. **Recién empezada** |

La capa 4 es la que convierte lo demás en lo que Munir describe. Su pieza clave no es el informe,
es **`capacidades()`, que dice lo que Vidorq NO sabe hacer**: sin esa lista un agente promete lo
que no puede cumplir, que es literalmente el fallo que abrió este trabajo.

### Recrear un estilo en Fusion: qué es exactamente (investigado el 2026-08-23)

Munir lo corrigió y la diferencia no es un matiz: **no es copiar la frase del vídeo ajeno y
pegarla, eso es copiar el TEXTO.** Es recrear el **ESTILO** como una pieza de Fusion que
después sirve para cualquier frase y cualquier vídeo.

- **Un estilo recreado es un Fusion Title Template**: un archivo `.setting` en la carpeta
  `Templates/Edit/Titles` que cuelga de `Support/Fusion` dentro del `Blackmagic Design/DaVinci
  Resolve` de `%APPDATA%`. Ahí Resolve lo enseña en **Effects Library > Titles** como un
  título más, y se arrastra al timeline con cualquier texto.
- **MEDIDO**: esa carpeta `Templates` **existe y está completamente vacía**, sin subcarpetas
  ni ficheros. Hay que crear `Edit/Titles`. Resolve es 21.0.4.5 **Free**.
- **Los colores por palabra salen de UN SOLO Text+**, con el modificador **Character Level
  Styling**. No hacen falta varios Text+ ni calcular posiciones a mano, que era el plan caro.
  Lo que **no está documentado** es cómo se escribe ese modificador dentro de un `.comp` y de
  un `.setting`: ese es el nudo.
- **No hace falta ningún plugin de terceros, comprobado**: Text+, Character Level Styling,
  Glow, Merge, Transform y los Templates son nativos y funcionan en Free. **Reactor NO está
  instalado** y no se instala.
- **Los plugins profesionales de terceros son para más tarde**, pero se diseña contando con
  ellos: cuando un estilo pida algo que los nodos de casa no dan, **se dice cuál es la pieza
  que falta y se anota**, en vez de aproximarlo en silencio.

**Hecho cuando**: copias el estilo de un vídeo, abres Resolve, y en Effects Library > Titles
hay un título nuevo con tu nombre. Lo arrastras, escribes CUALQUIER frase, y sale con los
colores por palabra, el tamaño, la posición y la entrada del original.

#### Estado a 2026-08-23 por la noche: PROBADO EN RESOLVE

Con Resolve 21.0.4.5 Free abierto y el puente puesto. No es "compila", es que se vio.

- **Resolve encuentra la plantilla y la inserta por su nombre.**
  `POST /title/insert {"titleName":"Vidorq Pop","fusionTitle":true}` devuelve
  `{"success": true}`, que es lo mismo que arrastrarla desde Effects Library > Titles. **No
  hizo falta reiniciar Resolve**, que llevaba horas abierto.
- **El estilo llega entero.** El comp que devuelve Resolve trae el tipo de letra, el encuadre
  (`Center 0.5/0.2`), el contorno (`Enabled2`, `Thickness2 0.22`, `Red2 0`), la sombra
  (`Alpha3 0.7`, `Softness3 0.35`, `Offset3`) y el tamaño atado a su `BezierSpline`.
- **Y con la plantilla del halo, igual:** `Vidorq_Neon` vuelve con su nodo `Glow` y sus DOS
  splines, el de la entrada y el del encendido del halo.
- **Escribirle CUALQUIER frase funciona.** Se le puso "MIRA ESTO", que no está en la plantilla,
  y el fotograma sale con el halo cian del preset. Eso era el criterio.
- **Los estilos se exportan y se importan** (`POST /galeria/exportar` e `importar`), con lista
  blanca al entrar: si un valor no pasa la revisión cae a la plantilla **y se cae de la lista
  de medido**, para que un estilo importado no presuma de algo que perdió por el camino.

- **Y un color por palabra dentro de un solo `Text+`, que estuvo dos días dado por imposible**
  (2026-08-24). No era la sintaxis, era el **operador**: el estilo por caracteres no es un
  campo del `Text+`, es un modificador aparte, `StyledTextCLS`, colgado de su entrada
  `StyledText`. Escrito en el nodo, Resolve lo guarda y lo ignora al pintar; colgado del
  modificador, pinta. El fotograma de `ROJO VERDE AZUL BLANCO` salió con los cuatro colores
  exactos, y el que genera `captions.to_comp` desde el código, también. Cómo se descifró y la
  tabla de códigos, en `docs/FUSION.md`.

**Lo único que NO sale:** el **barrido de karaoke**, o sea que se pinte la palabra que SUENA y
vaya cambiando con el audio. Hoy Vidorq escribe un solo reparto de colores por cartel, el
mismo del primer fotograma al último, y eso sigue siendo del MP4, donde libass tiene `\kf`.
Que además sea **imposible** moverlo está **razonado y NO PROBADO** (la entrada es un valor de
tipo `StyledText`, no una entrada `Number` como las que llevan splines): las dos formas de
cerrarlo están en `docs/FUSION.md`, y `fusion.faltantes()` lo dice con ese mismo cuidado. Se
escribe así a propósito, porque la "pared" anterior de este mismo apartado resultó ser un
error de sitio.

**Decisiones abiertas** (se le enseñaron en el navegador el 2026-08-23 y no ha contestado):

1. Por dónde seguir: la capa 4 (recomendada), más percepción, o abrir el puente.
2. Cómo hablan los agentes con Vidorq: **servidor MCP propio** (recomendado), solo HTTP, o los dos.
3. Si el agente decide y Vidorq solo mide (recomendado), o si Vidorq también decide.
4. Si esto amplía la v0.1 o si la v0.1 se cierra como está y el harness es la v0.2 (recomendado,
   por la regla Z).

---

## META C: se nota entrenado

**Hecho cuando**: le pasas 3 links de referencia y la siguiente edición se nota entrenada.

### Lo que Munir quiere de verdad, dicho por él (2026-08-23)

> "Pegas un link o importas un vídeo, lo analiza, coge los efectos, los subtítulos y los
> componentes de ese vídeo, y los recrea en DaVinci con la capacidad del MCP, con funciones
> profesionales de Fusion, color, etcétera."

Y sobre los subtítulos, después de ver lo que montó Vidorq encima de su vídeo de referencia:

> "Yo me refería a que tenías que recrear los subtítulos de dentro del vídeo. Esos subtítulos
> son mucho peores que los del vídeo."

Tenía razón, y la distancia con lo que hay construido es la meta:

**Vidorq no extrae, empareja.** Mide siete cosas de un vídeo ajeno (`ancho`, `alto`,
`duracion`, `vertical`, `subtitulo`, `ritmo`, `arranque`), las compara con sus DIEZ estilos de
catálogo y ofrece los tres más cercanos. Al guardar, lo que queda en la marca es el NOMBRE del
preset (`"ember"`), no lo medido, así que todo lo que se midió se tira. El propio docstring de
`aprende.parecidos` lo dice sin rodeos: *"propone los estilos que Vidorq sabe reconstruir de
verdad"*. Es un buscador de parecidos en un cajón cerrado, no un extractor.

**Medido con un Short de verdad** (metraje de película detrás, no el fondo liso de
laboratorio): el detector devolvió una banda del 73% del cuadro y se inventó un subtítulo que
no existía (`y=0,889`, `size=0,974`). Ese Short pinta **cada palabra de un color distinto**
(blanco `0.95/0.94/0.96`, cian `0.07/0.83/0.94`, amarillo `0.92/0.85/0.11`), **cambia de
tipografía** en una palabra (JARVIS) y **anima la entrada** letra a letra. Vidorq no sabe
reconstruir ninguna de las tres.

**Y de efectos no detecta nada**: no existe un solo campo para transiciones, zooms, grading o
nodos de Fusion. Del puente de Resolve se usan **18 herramientas de 155**; Fusion se usa solo
para los `Text+` de los subtítulos y de Color solo un CDL básico.

### La meta, por orden de lo que más se nota

- [x] **Guardar LO MEDIDO y no un nombre de plantilla.** HECHO el 2026-08-23. Un estilo
      copiado es ahora un componente de la galería (`skill/helpers/galeria.py`): lleva
      dentro lo medido, hereda de la plantilla base lo que todavía no se sabe medir, y
      **dice cuál es cuál** (`medido` / `heredado`, y la pantalla lo enseña al guardar).
      A partir de ahí existe solo: mover la plantilla no mueve el estilo copiado, y hay
      una prueba que lo comprueba moviéndola. El id viaja por argv hasta otros dos
      intérpretes (el render de MP4 y el que corre dentro de Resolve), así que el almacén
      es un archivo que los tres leen. 80 comprobaciones en `tests/test_galeria.py`.
- [~] **Un color por palabra**, con la paleta sacada del vídeo. **Medido ya, falta
      reconstruirlo.** `skill/helpers/leer.py` saca el color de cada palabra del vídeo
      real: en el Short de referencia devuelve `Y`/`HAY`/`PERSONA` en blanco y `OTRA` en
      amarillo `(0.93, 0.98, 0.07)`. Lo que falta es el otro lado: `captions.PRESETS`
      todavía no sabe pintar varias palabras con colores FIJOS distintos a la vez (tiene
      `word_fx` y `accent`, y `marker` pinta la palabra que suena, que no es lo mismo).
- [x] **Leer el texto de la IMAGEN y no del audio.** HECHO el 2026-08-23, en
      `skill/helpers/leer.py`. Lee `JARV!` en amarillo donde Whisper escribía "Charvis".

  **Lo que costó y por qué está escrito aquí:** contar píxeles por filas
  (`aprende.banda_de_texto`) **no puede** encontrar un subtítulo sobre metraje de
  película, y no es cuestión de umbral. Busca un pico de detalle, y en una película hay
  detalle en todas partes: sobre el Short devuelve una banda del 71% del cuadro. Se probó
  además una variante que pesaba la presencia de tinta y la sale **peor** (pone la banda
  arriba del todo, donde no hay una sola letra). La razón de fondo es que para ver que un
  texto está quieto hay que comparar fotogramas **seguidos**, y se miran 40 repartidos por
  todo el vídeo, con casi un segundo entre uno y otro.

  Así que se usa un detector de texto (`rapidocr-onnxruntime`, Apache-2.0, ~55 MB, corre
  sobre el `onnxruntime` que ya estaba). Es **opcional**: sin él, `leer.py` dice que no
  puede y el resto sigue igual. Tres cosas más que salieron de mirar las imágenes, no de
  razonar sobre ellas:

  - La **marca de agua** del creador se separa sola: repite el mismo texto una y otra vez
    en el mismo sitio, y un subtítulo vuelve al mismo sitio con palabras distintas.
  - Los cortes entre palabras se reparten **por letras**, no por huecos de contraste. Con
    contraste, en `UNA DE CADA CINCO` la palabra amarilla tapa a las grises y el corte de
    `CADA` acababa encima de la E de `DE`, midiendo 14 px en vez de 60. Ninguna fórmula de
    color arregla un corte mal puesto, y se gastaron tres en intentarlo.
  - Las letras de ese vídeo están **huecas** (solo contorno, y por dentro se ve el fondo),
    así que todo lo que mire "el interior de la letra" devuelve el fondo. El color se
    saca del BORDE, y se coge el que más se repite y no el promedio.
- [~] **Detectar la animación de entrada** de las palabras. Se detecta la FAMILIA
      (`efectos.entrada`): si el texto entra **creciendo**, **apareciendo** o **de golpe**.
      Calibrado contra LAS NUEVE entradas de la casa renderizadas: creciendo son bounce
      0,641, pop 0,415, ignite 0,275 y zoom 0,170; apareciendo son focus 0,690, fade 0,655
      y rise 0,631; de golpe son throb 0,071 y none 0,000. **Lo que NO se sabe** es cuál de
      las que crecen es, porque las cuatro crecen igual. El Short de referencia dice que su
      texto **entra creciendo**, que es lo que se ve en los recortes: las letras entran
      huecas y se rellenan.

      Dos cosas que solo salieron al probar con vídeo real. Los fotogramas hay que pedirlos
      **seguidos**, porque una entrada dura tres o cuatro y el muestreo normal se la salta
      entera. Y la mancha de texto se busca **por color**, no por brillo: sobre metraje el
      cuadro entero pasa cualquier umbral de brillo, la mancha nunca desaparece y entonces
      no hay forma de ver dónde empieza el texto.
- [~] **Detectar transiciones y efectos.** Las TRANSICIONES ya se detectan
      (`skill/helpers/efectos.py`): distingue un corte seco de una transicion, dice cuanto
      dura, y separa el fundido a negro del fundido a blanco. Calibrado con transiciones
      fabricadas por ffmpeg, o sea de tipo conocido, y la separacion no admite discusion:
      un corte da ancho 1 (un pico de 110 entre valores de 0,1) y todas las transiciones
      dan de 3 a 6. **Lo que NO distingue**, y se dice en vez de fingirlo: una disolvencia
      de un barrido de un circulo, porque los tres reparten el cambio igual y lo que los
      separa es la forma de la mezcla. **Faltan los efectos, los zooms y el grading**, que
      siguen sin tener ni un campo.

**Cómo se sabe que está hecho**: se coge un vídeo de redes con subtítulos de colores, se pasa
por Vidorq, y en la pantalla de Resolve el subtítulo reconstruido tiene los mismos colores en
las mismas palabras, en la misma posición y del mismo tamaño que el original. Se comprueba
mirando los dos juntos, no leyendo un log en verde.

### Lo de antes, que sigue en pie

- [ ] Procesar 5-10 vídeos reales elegidos por Munir (ingesta, informe, confirmación).
- [ ] Calibrar el detector de cortes con material real (luma-diff, umbral 42) contando
      cortes a mano en un tramo de 1 min.
- [ ] Cuantificar el coste Gemini por vídeo con el primero, ANTES de procesar el resto.
- [ ] Destilar la memoria a los presets del editor: que el estilo aprendido cambie el EDL.
- [ ] Caso real: un montage de gaming editado al estilo de un referente.

**Sesión**: 🧠 Sesión 4. Bloqueada en Munir: hay que elegir los vídeos.

---

## Aparcadero (post v0.1, escrito aquí para que deje de pesar)

Nada de esto entra antes de publicar. Está anotado para no perderlo, no para hacerlo ahora.

- **El logo: APARCADO por Munir el 2026-08-24.** Hay SEIS marcas dibujadas y numeradas, en los
  dos temas y a los tres tamaños que importan (56 px la ventana, 28 la barra de tareas, 16 el
  favicon): **1 El corte, 2 Las pistas, 3 La V de pistas, 4 El cabezal, 5 Monograma Vq,
  6 Anidado**. Están en SVG dentro de un solo HTML, guardado en el repo privado en
  `Vidorq-Core/marca/logos.html` (aquí no, por la regla P), así que volver a enseñarlas cuesta
  abrirlo. **Condición de desbloqueo: cuando haya algo público que necesite una cara** (la
  landing, el instalador del producto de pago, o el primer release que se anuncie). Hasta
  entonces el logo no bloquea nada, porque la ventana no lo usa. **Ojo con la regla AK cuando
  se retome:** el nombre Vidorq ya es público, pero cualquier nombre NUEVO que salga de esa
  conversación no se publica hasta tener el dominio comprado.
- **Reframe 9:16 + safe zones de captions**: van JUNTAS. Ojo, la recomendación del informe
  ("safe zones ya, es barato") no es ejecutable sola: el motor hace `scale={w}:{h}` del
  origen, 16:9 entra y 16:9 sale. Vidorq no produce vertical todavía. Las safe zones en sí
  son cambiar el `0.74` hardcodeado de `write_segment_ass()` por una tabla por plataforma
  (zona segura universal: rectángulo centrado de 900x1400 en 1080x1920; el bloque empieza
  en Y≈1200-1300 y nunca baja de 370 px del borde inferior). Datos por plataforma en el §3
  del informe.
- **Motor de overlays** con Motion Canvas/Revideo (MIT, no Remotion por licencia).
- **Workflows de edición reutilizables** tipo mosaic.so (metáfora Zapier/nodos, validada).
- **Multi-modelo generativo** tipo martini.film (Veo, Kling, Nano Banana en el timeline).
- **Skill de música** con mini-formulario y librería personal descrita por el usuario.
- **Sonido inteligente (nota 2026-07-18):** presets de SFX profesionales + una sección de
  edición de sonido por prompts (mismo patrón que el resto de Vidorq). Fuentes de SFX
  gratuitas: Freesound, Pixabay, Zapsplat. Referencia de UX: "Botanica v4" (Gumroad, de
  pago: 520+ SFX + extensión de Premiere con preview, pitch/reverse y drop al timeline en
  un clic; en Vidorq ese flujo se haría vía el puente de Resolve). Complementa el skill de
  música de arriba.
- **Que el agente "vea" el vídeo: skill claude-video (`/watch`, gratis, OSS).** Descarga
  con yt-dlp, extrae frames adaptativos + transcripción con timestamps y se los pasa a
  Claude. Repo: bradautomates/claude-video (alternativa: alexlarcheveque/claude-watch).
  **Decisión 2026-07-16: NO va al pipeline de ingesta de META C.** Motivo: `core_engine.py`
  ya hace yt-dlp + sampleo de frames + transcripción + análisis multimodal, y su análisis
  va por Gemini BYOK (coste medible en la cuenta de Munir, se destila a memoria).
  claude-video mete los frames en el CONTEXTO de la sesión de Claude Code → gasta cuota de
  SESIÓN (el mismo patrón que fundió la cuota el 2026-07-04 y el 2026-07-15). Meter 5-100
  vídeos de referencia por ahí = repetir ese error. Uso legítimo PUNTUAL (no en pipeline):
  que la sesión madre "vea" UN vídeo para razonar en vivo sobre él, consciente del coste.
- **Descripción por asset + búsqueda semántica del footage** (patrón Cardboard).
- **Presets de captions con nombre** (referencia: "Stacked", "Word Pop").
- Detección de cambios de tema en podcasts, biblioteca de animaciones por marca, comunidad.

---

## Ya conseguido

### Fundación
- Nombre, carpeta, repo público (`vidorq`) y privado (`vidorq-core`), documentación.
- Investigación técnica (2026-07-04, 253 fuentes) y de mercado (2026-07-15).

### El primer corte mágico
- Pipeline transcribir, empaquetar, razonar, EDL, aplicar. Vídeo real de Luisito: 10:43 a
  4:26 con cortes limpios y fades de audio.
- **Backend Resolve**: el mismo EDL monta un timeline editable vía el puente. 16 cortes,
  6 punch zooms y 16 marcadores verificados por API. Crash de OpenCL resuelto por el camino.
- **Backend directo** (no estaba planeado): mp4 final sin Resolve. Cortes, punch zoom y
  captions en una pasada.
- **Rendimiento**: el compositing pasó de PIL/numpy frame a frame (más de 1h) a filtros
  ffmpeg con progreso real. Falta medir la cifra en una prueba end-to-end.

### Lo que falla cuando falla (2026-08-20)

Una tanda entera dedicada a lo que pasa cuando algo va mal, que es donde se pierde a la
gente. Todo reproducido antes de tocar nada y medido después.

- **Nada se rompe en silencio**. El menú de Resolve fallaba con un `print` a la consola F6
  (los tres caminos: sin config, config rota, carpeta movida) y ahora sale una caja. Un
  ordenador sin entorno de Python reventaba con `TypeError: stat: path should be string...
  not NoneType`, porque el instalador escribía `"python": null` y `.get(clave, "")` devuelve
  `None` con eso. El cartel final se titulaba *"Vidorq listo"* aunque dentro pusiera que el
  motor no arranca. Y el aviso de esas ramas no salía nunca: iba en un hilo *daemon* que
  moría con el proceso.
- **`onnxruntime` no estaba en `NEEDS`**, y `faster_whisper` lo necesita para el VAD. Sin él,
  `/health` decía `"missing": []` y la edición moría al 10% con la excepción cruda. Ahora
  se ve al arrancar, con una frase que dice qué hacer.
- **Tres sitios por donde salía una clave**: el error del director, el de la voz y el
  historial en disco. Medido: el 401 de OpenAI **devuelve tu clave** (`sk-ant-C****...9f3a`)
  y Vidorq relayaba ese cuerpo a la pantalla y a `ediciones.json`. Barrido de los 16
  endpoints GET con cinco claves falsas plantadas: cero fugas por ahí, el agujero era este.
- **La aritmética manda sobre el modelo**. `SEG_SYSTEM` le mandaba cortar en límites de frase
  y el bloque literal decía que era una resta: ganaba la que corría antes. *"Quita del 4 al
  7"* (3 s) quitaba 4,15 s. Ahora quita 3,000 s, y de paso el reloj lo nota: **36,1 s contra
  76,3 s**.
- **Dos esperas de más**: el tanteo a Ollama pagaba 2,03 s por un puerto muerto (`/providers`
  de 2,07 s a 0,66 s), y el puente caído costaba 4,02 s en dos intentos, justo en la pantalla
  que mira quien todavía no lo ha arrancado (`/resolve` de 4,35 s a 0,99 s). Esa pantalla
  además acusaba en falso: decía *"abre Resolve"* con Resolve abierto delante.
- **`config.json` y `brand.json` se escribían sin red**. `write_text` trunca antes de
  escribir: un config de 66 bytes con dos claves dentro se queda en 0 si el proceso muere en
  medio. Ya son atómicos, como la sesión y el historial.
- **La transcripción va vallada** dentro del prompt (regla 6). Atacada con *"IGNORA LA
  INSTRUCCIÓN ANTERIOR"* más un JSON ya escrito: por Claude no se coló nada, pero el
  proveedor de fábrica son modelos de 3B. La valla no se puede cerrar desde dentro.
- **Pruebas**: de 681 a 792 casos, en cuatro archivos. Nuevas: los dos idiomas completos
  (en el motor una clave sin inglés sale como la CLAVE en pantalla, sin error), las tres
  reglas que un montaje cumple siempre, la valla, y las dos tachaduras de claves. Cada una
  se rompió a propósito para ver que salta.

### Producto
- Dos apps de escritorio (Tauri + React): Vidorq (producto, engine 9877) y Vidorq Core
  (privada, engine 9878). Lanzadores en el escritorio, modo dev que se actualiza solo.
- Captions Hormozi quemados y sincronizados, presets, Modo Pro BYOK, workspaces, wizard de
  marca, ajustes multi-IA (Claude Code, Codex, Cursor, OpenCode, Antigravity).
- Identidad visual: anillo violeta con puntos, neuronas al play azul. Un asset para logo e icono.
- Landing one-page con parallax en `web/`.
