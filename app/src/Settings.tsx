import { useState } from "react";
import { apiPost } from "./api";

const AGENTS: { name: string; how: string }[] = [
  {
    name: "Claude Code",
    how: 'mklink /J "%USERPROFILE%\\.claude\\skills\\vidorq" "C:\\proyectos\\Vidorq\\skill"',
  },
  {
    name: "Codex",
    how: 'mklink /J "%USERPROFILE%\\.codex\\skills\\vidorq" "C:\\proyectos\\Vidorq\\skill"',
  },
  {
    name: "Cursor",
    how: "Añade la carpeta C:\\proyectos\\Vidorq al workspace y pide: \"lee skill/SKILL.md y edita mi video con vidorq\"",
  },
  {
    name: "OpenCode",
    how: 'mklink /J "%USERPROFILE%\\.opencode\\skills\\vidorq" "C:\\proyectos\\Vidorq\\skill"',
  },
  {
    name: "Antigravity",
    how: "Abre C:\\proyectos\\Vidorq como proyecto y apunta al agente a skill/SKILL.md",
  },
];

export default function Settings({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<"keys" | "agents">("keys");
  const [anthropic, setAnthropic] = useState("");
  const [gemini, setGemini] = useState("");
  const [openai, setOpenai] = useState("");
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState("");

  async function save() {
    await apiPost("/config", { anthropicKey: anthropic, geminiKey: gemini, openaiKey: openai });
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  function copy(name: string, text: string) {
    navigator.clipboard?.writeText(text).catch(() => {});
    setCopied(name);
    setTimeout(() => setCopied(""), 1200);
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <h2>Ajustes</h2>
        <div className="opt out inline">
          <button className={tab === "keys" ? "sel" : ""} onClick={() => setTab("keys")}>🔑 API keys</button>
          <button className={tab === "agents" ? "sel" : ""} onClick={() => setTab("agents")}>🤖 Vincular con tu IA</button>
        </div>

        {tab === "keys" ? (
          <>
            <p className="hint">Las keys se guardan solo en tu equipo. Sin keys, los presets funcionan igual: gratis y en local.</p>
            <label>Anthropic (Claude) — Modo Pro con prompt</label>
            <input type="password" value={anthropic} onChange={(e) => setAnthropic(e.target.value)} placeholder="sk-ant-..." />
            <label>Google (Gemini) — análisis de vídeos de referencia</label>
            <input type="password" value={gemini} onChange={(e) => setGemini(e.target.value)} placeholder="AIza..." />
            <label>OpenAI — alternativa</label>
            <input type="password" value={openai} onChange={(e) => setOpenai(e.target.value)} placeholder="sk-..." />
            <button className="cta" onClick={save}>{saved ? "✅ Guardado" : "Guardar keys"}</button>
          </>
        ) : (
          <>
            <p className="hint">
              Vidorq también se puede usar desde el agente de IA que ya tienes: tu agente lee el skill
              y controla el mismo motor que esta app (puerto 9877) y DaVinci Resolve. Copia el comando de tu agente:
            </p>
            {AGENTS.map((a) => (
              <div key={a.name} className="agent">
                <div className="agent-head">
                  <strong>{a.name}</strong>
                  <button className="ghost small" onClick={() => copy(a.name, a.how)}>
                    {copied === a.name ? "✅ copiado" : "copiar"}
                  </button>
                </div>
                <code>{a.how}</code>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
