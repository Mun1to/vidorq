# AGENTS.md — Reglas de trabajo en Vidorq

> Documento interno en español (regla D). Aplica a cualquier agente de IA que trabaje en este repo.

## Reglas heredadas de `C:\proyectos\Reglas_de_los_proyectos.md`

1. **Nunca** poner `Co-Authored-By` en los commits.
2. **Siempre preguntar antes de hacer push** a GitHub.
3. **README y commits en inglés**; documentación interna (docs/, AGENTS.md, HANDOFF.md, FEEDBACK.md) en **español**.
4. **pnpm siempre** en proyectos Node/JS (nunca npm ni yarn). Fijar `"packageManager"` en package.json.
5. **Guion normal `-` en lo público** (README, commits, código, UI), nunca la raya `—`.
6. **Seguridad primero**: las API keys (Claude, Gemini, OpenAI, ElevenLabs…) van SIEMPRE en `.env` fuera de git. Validar toda entrada externa, incluido **prompt injection** (crítico aquí: los vídeos de referencia y transcripciones son entrada no confiable que se inyecta en prompts).
7. **Diagnóstico antes que parche**: reproducir y aislar la causa raíz antes de tocar código.
8. **Lluvia de ideas + preguntas críticas antes de decisiones de arquitectura** con entidad; esperar respuesta de Munir.
9. **Munir dicta por voz** (VoCript): interpretar la intención, no lo literal; preguntar ante ambigüedad.
10. **Metas, no fechas**: el roadmap se organiza por niveles tipo videojuego (ver `docs/METAS.md`). Nunca proponer fechas internas.
11. **Cerrar tareas con entidad explicando**: qué se hizo, cómo, y 2-3 preguntas de seguimiento para que Munir aprenda.
12. **Confirmar la intención antes de ejecutar** (regla I, jul-2026): en tareas con entidad, decir qué se ha entendido y qué se asume; ante varias interpretaciones, preguntar en vez de elegir en silencio; empezar solo al estar seguro (ahorra errores y tokens).
13. **Simplicidad primero, cambios quirúrgicos** (regla J, jul-2026): código mínimo que resuelva el problema, nada especulativo; tocar solo lo que la tarea pide, sin "mejorar" código adyacente ni refactorizar lo que no está roto; nada está terminado sin verificarlo contra el objetivo.
14. **Arranque estructurado, primero el plano** (regla K, jul-2026): antes de programar un proyecto nuevo (o de ordenar uno a medias), investigar el stack en vez de copiarlo por inercia (2-3 opciones con pros/contras), encuadrar con preguntas, decidir con criterio, montar los cimientos (`AGENTS.md`, `README`, `docs/METAS.md`, carpetas) y dejar el mapa a la vista (qué es, con qué, cómo, metas por orden con la próxima acción); no programar hasta que el plano esté claro.
15. **Cerrar en una frase** (regla L, jul-2026): al terminar algo con entidad, primera línea = una frase de lo hecho sin muletillas ("bueno", "básicamente"), debajo los pasos siguientes (1-3), y el detalle largo solo después y si aporta (refina la regla C/11).
16. **Saber el día y la hora reales** (regla N, jul-2026): no asumas la fecha ni la hora, consúltalas (`Get-Date`) cuando importen. Obligatorio al fechar algo que se escribe en un documento, en memoria o en un commit; al triar notas dictadas que traen hora; y antes de dar por buena cualquier convocatoria, plazo o ventana externa (si algo dice "anual" o "ver web", comprueba si ya pasó).
17. **Ambición por defecto** (regla O, jul-2026): la meta de Munir no se negocia, se critica el riesgo concreto y la secuencia, nunca su capacidad. Todo lo que se aparque sale con su **condición de desbloqueo** ("todavía no, y esto es lo que lo abre"), nunca un "no" seco; el aparcadero de `docs/METAS.md` se escribe así. Nada de proyectar plazos de meses como techo, y lo bueno se dice primero y sin peros.

## Contexto imprescindible del proyecto

- **Vidorq = editor de vídeo IA open source sobre DaVinci Resolve FREE.** La versión gratuita de Resolve NO permite scripting externo (eso es de Studio, 295 USD); se esquiva con el puente CursorBridge que corre DENTRO de Resolve (Workspace > Scripts) y expone HTTP local. Ese puente ya existe en `C:\proyectos\davinci-resolve-mcp` (162 herramientas MCP).
- **Limitaciones duras de la API de scripting de Resolve** (condicionan toda la arquitectura):
  - No se pueden animar keyframes por API (solo valores estáticos).
  - No se pueden añadir transiciones por API.
  - No se puede editar el contenido interno de nodos Fusion por API.
  - → Por eso las animaciones van por dos vías: comps Fusion pre-animadas cargadas con el workaround de `ImportFusionComp` (patrón AutoSubs, probado en Free), y overlays con canal alfa generados fuera con Motion Canvas/Revideo (MIT; Remotion descartado como default por licencia). Detalle en docs/ARQUITECTURA.md e informe en Vidorq-Core/informes/.
- **Filosofía de percepción (de video-use)**: el LLM no "ve" el vídeo, lo LEE. Transcripción con timestamps a nivel de palabra como superficie principal + vistas visuales (filmstrip) solo en puntos de decisión. Nunca volcar frames masivamente.
- **Repo hermano privado**: `Vidorq-Core` (estrategia, marca, conocimiento interno). Lo público va aquí; lo estratégico va allí.

## Hardware de desarrollo de Munir

- Windows 11 Pro, RTX 5060 8GB VRAM, 32GB RAM.
- 42 modelos Ollama locales en `C:\proyectos\Stashai` (OLLAMA_MODELS).
- DaVinci Resolve 20.3 (versión gratuita, NO Studio).

## froede (edición visual de webs)

Munir edita las webs de sus proyectos en localhost con **froede** (`C:\proyectos\froede`): extensión de navegador + companion local que escriben los cambios DIRECTAMENTE en los archivos fuente. Si aparecen diffs sin commit con `style={{ ... }}` inline nuevos, atributos `style="..."`/`href`/`alt`/`title` cambiados o textos editados, seguramente son ediciones intencionales de Munir hechas con froede: acéptalas y consérvalas, NO las reviertas ni las "normalices" (p. ej. moverlas a clases CSS) salvo que él lo pida. Notas: `data-froede-loc` solo existe en el DOM en dev (nunca llega a los archivos); `.froede-token` es un secreto local que debe estar en `.gitignore` y jamás commitearse. Regla completa: `C:\proyectos\Reglas_de_los_proyectos.md` (regla M).
