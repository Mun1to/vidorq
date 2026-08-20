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

## META C: se nota entrenado

**Hecho cuando**: le pasas 3 links de referencia y la siguiente edición se nota entrenada.

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
- **Pruebas**: de 681 a 754 casos, en cuatro archivos. Nuevas: los dos idiomas completos
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
