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
