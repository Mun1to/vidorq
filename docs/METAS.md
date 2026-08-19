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
- [ ] Spike `ImportFusionComp` con comp dummy en 21 Free (AddFusionComp,
      GetFusionCompNameList, LoadFusionCompByName, ImportFusionComp, borrar el dummy).
- [ ] Captions nativos en el timeline vía macro Fusion (patrón AutoSubs), estilo Hormozi.
- [ ] Zoom suave con easing vía comp Fusion pre-animada (el punch zoom estático ya funciona).

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
- [ ] Auditoría de consistencia de punta a punta (ambas apps, ambos backends).
- [ ] README público reescrito: todavía cuenta la instalación vieja de tres scripts.
- [ ] Firmar los instaladores para que Windows no los marque como origen desconocido.
- [ ] README público en inglés con GIF del flujo real.
- [ ] Landing con el copy que salió de la investigación: analogía-ancla en el hero,
      contraste explícito "viven fuera / Vidorq vive dentro", CTA final participativo con
      prompts de ejemplo (Gaming montage es literalmente nuestra historia), y sección
      changelog (patrón del ecosistema: changelog = pasado, "próximamente" en bloque aparte).
- [ ] Vídeo de lanzamiento editado CON Vidorq (dogfooding: la demo es el producto).
- [ ] Barrido de seguridad: sin secretos, sin keys, sin rutas personales (regla B).
- [ ] Levantar la congelación del push público (OK explícito de Munir) + vidorq.com.

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

### Producto
- Dos apps de escritorio (Tauri + React): Vidorq (producto, engine 9877) y Vidorq Core
  (privada, engine 9878). Lanzadores en el escritorio, modo dev que se actualiza solo.
- Captions Hormozi quemados y sincronizados, presets, Modo Pro BYOK, workspaces, wizard de
  marca, ajustes multi-IA (Claude Code, Codex, Cursor, OpenCode, Antigravity).
- Identidad visual: anillo violeta con puntos, neuronas al play azul. Un asset para logo e icono.
- Landing one-page con parallax en `web/`.
