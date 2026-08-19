import { useState } from "react";
import { useLang } from "./i18n";
import { IconKey, IconMic, IconPlug } from "./Icons";
import Providers from "./Providers";
import Voice from "./Voice";

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
    how: 'Add C:\\proyectos\\Vidorq to the workspace, then ask: "read skill/SKILL.md and edit my video with vidorq"',
  },
  {
    name: "OpenCode",
    how: 'mklink /J "%USERPROFILE%\\.opencode\\skills\\vidorq" "C:\\proyectos\\Vidorq\\skill"',
  },
  {
    name: "Antigravity",
    how: "Open C:\\proyectos\\Vidorq as a project and point the agent at skill/SKILL.md",
  },
];

export default function Settings({ onClose }: { onClose: () => void }) {
  const { t } = useLang();
  const [tab, setTab] = useState<"keys" | "voice" | "agents">("keys");
  const [copied, setCopied] = useState("");

  function copy(name: string, text: string) {
    navigator.clipboard?.writeText(text).catch(() => {});
    setCopied(name);
    setTimeout(() => setCopied(""), 1200);
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{t("set.title")}</h2>
          <div className="opt out inline">
            <button className={tab === "keys" ? "sel" : ""} onClick={() => setTab("keys")}>
              <IconKey size={14} className="icon" />{t("set.keys")}
            </button>
            <button className={tab === "voice" ? "sel" : ""} onClick={() => setTab("voice")}>
              <IconMic size={14} className="icon" />{t("set.voice")}
            </button>
            <button className={tab === "agents" ? "sel" : ""} onClick={() => setTab("agents")}>
              <IconPlug size={14} className="icon" />{t("set.agents")}
            </button>
          </div>
        </div>

        <div className="modal-body">
          {tab === "keys" ? (
            <Providers />
          ) : tab === "voice" ? (
            <Voice />
          ) : (
            <>
              <p className="hint">{t("set.agents.sub")}</p>
              {AGENTS.map((a) => (
                <div key={a.name} className="agent">
                  <div className="agent-head">
                    <strong>{a.name}</strong>
                    <button className="ghost small" onClick={() => copy(a.name, a.how)}>
                      {copied === a.name ? t("set.copied") : t("set.copy")}
                    </button>
                  </div>
                  <code>{a.how}</code>
                </div>
              ))}
            </>
          )}
        </div>

        {/* A la izquierda, y no debajo de "Guardar": las dos pegadas al mismo
            lado y en dos filas parecian un fallo de maquetacion, no dos
            acciones distintas. Guardar es del formulario; cerrar es del
            dialogo. */}
        <div className="modal-foot foot-left">
          <button className="ghost" onClick={onClose}>{t("close")}</button>
        </div>
      </div>
    </div>
  );
}
