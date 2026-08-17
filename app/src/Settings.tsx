import { useState } from "react";
import { apiPost } from "./api";
import { useLang } from "./i18n";
import { IconCheck, IconKey, IconPlug } from "./Icons";

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
        <div className="modal-head">
          <h2>{t("set.title")}</h2>
          <div className="opt out inline">
            <button className={tab === "keys" ? "sel" : ""} onClick={() => setTab("keys")}>
              <IconKey size={14} className="icon" />{t("set.keys")}
            </button>
            <button className={tab === "agents" ? "sel" : ""} onClick={() => setTab("agents")}>
              <IconPlug size={14} className="icon" />{t("set.agents")}
            </button>
          </div>
        </div>

        <div className="modal-body">
          {tab === "keys" ? (
            <>
              <p className="hint">{t("set.keys.sub")}</p>
              <section className="field">
                <label>Anthropic (Claude)</label>
                <small className="under">{t("set.anthropic.sub")}</small>
                <input type="password" value={anthropic} onChange={(e) => setAnthropic(e.target.value)}
                       placeholder="sk-ant-..." />
              </section>
              <section className="field">
                <label>Google (Gemini)</label>
                <small className="under">{t("set.gemini.sub")}</small>
                <input type="password" value={gemini} onChange={(e) => setGemini(e.target.value)}
                       placeholder="AIza..." />
              </section>
              <section className="field">
                <label>OpenAI <span className="opt-tag">{t("alternative")}</span></label>
                <input type="password" value={openai} onChange={(e) => setOpenai(e.target.value)}
                       placeholder="sk-..." />
              </section>
            </>
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

        <div className="modal-foot">
          <button className="ghost" onClick={onClose}>{t("close")}</button>
          {tab === "keys" && (
            <button className="cta" onClick={save}>
              {saved ? <><IconCheck size={15} className="icon" />{t("saved")}</> : t("set.save")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
