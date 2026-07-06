import { useEffect, useMemo, useState } from "react";
import "./App.css";

const ENGINE = "http://127.0.0.1:9877";

type Preset = "clean" | "podcast" | "montage";
type Output = "mp4" | "resolve";
type Phase = "idle" | "running" | "done" | "error";

interface Progress {
  step: string;
  percent: number;
  detail?: string;
  result?: string;
  error?: string;
}

const PRESETS: { id: Preset; icon: string; name: string; desc: string; beta?: boolean }[] = [
  { id: "clean", icon: "✂️", name: "Limpieza", desc: "Corta silencios, muletillas y momentos muertos" },
  { id: "podcast", icon: "🎙️", name: "Podcast Q&A", desc: "Corta y marca cada pregunta o cambio de tema" },
  { id: "montage", icon: "🎮", name: "Montage", desc: "Se queda los momentos de más energía", beta: true },
];

function App() {
  const [video, setVideo] = useState<string>("");
  const [preset, setPreset] = useState<Preset>("clean");
  const [captions, setCaptions] = useState(true);
  const [output, setOutput] = useState<Output>("mp4");
  const [proOpen, setProOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState<Progress>({ step: "", percent: 0 });
  const [engineUp, setEngineUp] = useState<boolean | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Drag & drop nativo de Tauri (da rutas reales de archivo).
  // En un navegador normal (dev/preview) simplemente no está: se usa el campo de ruta.
  useEffect(() => {
    let unsub: (() => void) | undefined;
    (async () => {
      try {
        const { getCurrentWebview } = await import("@tauri-apps/api/webview");
        unsub = await getCurrentWebview().onDragDropEvent((e) => {
          if (e.payload.type === "over") setDragOver(true);
          else if (e.payload.type === "drop") {
            setDragOver(false);
            const p = e.payload.paths?.[0];
            if (p && /\.(mp4|mov|mkv|webm|avi)$/i.test(p)) setVideo(p);
          } else setDragOver(false);
        });
      } catch { /* fuera de Tauri no hay drag&drop nativo */ }
    })();
    return () => { unsub?.(); };
  }, []);

  // Latido del motor local
  useEffect(() => {
    const check = () =>
      fetch(`${ENGINE}/health`).then(() => setEngineUp(true)).catch(() => setEngineUp(false));
    check();
    const t = setInterval(check, 4000);
    return () => clearInterval(t);
  }, []);

  // Progreso mientras edita
  useEffect(() => {
    if (phase !== "running") return;
    const t = setInterval(async () => {
      try {
        const r = await fetch(`${ENGINE}/progress`);
        const p: Progress = await r.json();
        setProgress(p);
        if (p.error) setPhase("error");
        else if (p.percent >= 100 && p.result) setPhase("done");
      } catch { /* motor ocupado */ }
    }, 800);
    return () => clearInterval(t);
  }, [phase]);

  const fileName = useMemo(() => video.split(/[\\/]/).pop() ?? "", [video]);
  const canEdit = video !== "" && engineUp === true && phase !== "running";

  async function startEdit() {
    setPhase("running");
    setProgress({ step: "Enviando al motor...", percent: 2 });
    try {
      const r = await fetch(`${ENGINE}/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video, preset, captions, output, prompt: proOpen ? prompt : "" }),
      });
      const j = await r.json();
      if (j.error) { setProgress({ step: "", percent: 0, error: j.error }); setPhase("error"); }
    } catch (e) {
      setProgress({ step: "", percent: 0, error: "No se pudo hablar con el motor. ¿Está encendido?" }); setPhase("error");
    }
  }

  async function saveKey() {
    await fetch(`${ENGINE}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anthropicKey: apiKey }),
    }).catch(() => {});
    setSettingsOpen(false);
  }

  return (
    <main className="shell">
      <header className="top">
        <div className="brand">
          <span className="logo">V</span>
          <div>
            <h1>Vidorq</h1>
            <p>Describe la edición. El resto es nuestro.</p>
          </div>
        </div>
        <div className="top-right">
          <span className={`engine ${engineUp ? "ok" : "down"}`}>
            {engineUp === null ? "..." : engineUp ? "motor conectado" : "motor apagado"}
          </span>
          <button className="ghost" onClick={() => setSettingsOpen(true)} title="Ajustes">⚙️</button>
        </div>
      </header>

      {phase === "idle" || phase === "error" ? (
        <>
          <section className={`drop ${dragOver ? "over" : ""} ${video ? "loaded" : ""}`}>
            {video ? (
              <>
                <span className="file-icon">🎬</span>
                <strong>{fileName}</strong>
                <button className="ghost small" onClick={() => setVideo("")}>cambiar</button>
              </>
            ) : (
              <>
                <span className="file-icon">⬇️</span>
                <strong>Arrastra tu vídeo aquí</strong>
                <input
                  className="path-input"
                  placeholder="...o pega la ruta del archivo y pulsa Enter"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") setVideo((e.target as HTMLInputElement).value.replace(/^"|"$/g, ""));
                  }}
                />
              </>
            )}
          </section>

          <section className="presets">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                className={`preset ${preset === p.id ? "sel" : ""}`}
                onClick={() => setPreset(p.id)}
              >
                <span className="p-icon">{p.icon}</span>
                <span className="p-name">{p.name}{p.beta && <em> beta</em>}</span>
                <span className="p-desc">{p.desc}</span>
              </button>
            ))}
          </section>

          <section className="options">
            <label className="opt">
              <input type="checkbox" checked={captions} onChange={(e) => setCaptions(e.target.checked)} />
              <span>Captions animados</span>
            </label>
            <div className="opt out">
              <button className={output === "mp4" ? "sel" : ""} onClick={() => setOutput("mp4")}>MP4 directo</button>
              <button className={output === "resolve" ? "sel" : ""} onClick={() => setOutput("resolve")}>Timeline en Resolve</button>
            </div>
          </section>

          <section className={`pro ${proOpen ? "open" : ""}`}>
            <button className="pro-toggle" onClick={() => setProOpen(!proOpen)}>
              ✨ Modo Pro {proOpen ? "▲" : "▼"}
            </button>
            {proOpen && (
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder='Describe la edición con tus palabras: "córtame este podcast y añade una tarjeta en cada cambio de tema..." (requiere API key en Ajustes ⚙️)'
              />
            )}
          </section>

          {phase === "error" && <div className="error">⚠️ {progress.error}</div>}

          <button className="cta" disabled={!canEdit} onClick={startEdit}>
            EDITAR VÍDEO
          </button>
          {engineUp === false && (
            <p className="hint center">El motor local no está encendido. Arráncalo con <code>vidorq-engine</code> o desde la carpeta del proyecto.</p>
          )}
        </>
      ) : (
        <section className="run">
          <div className="bar"><div className="fill" style={{ width: `${progress.percent}%` }} /></div>
          <h2>{progress.step}</h2>
          {progress.detail && <p className="detail">{progress.detail}</p>}
          {phase === "done" && (
            <div className="done">
              <h2>✅ Listo</h2>
              <p className="result-path">{progress.result}</p>
              <button className="cta" onClick={() => { setPhase("idle"); setProgress({ step: "", percent: 0 }); }}>
                Editar otro vídeo
              </button>
            </div>
          )}
        </section>
      )}

      {settingsOpen && (
        <div className="modal-bg" onClick={() => setSettingsOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Ajustes</h2>
            <label>API key de Anthropic (Modo Pro)</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-ant-..."
            />
            <p className="hint">Se guarda solo en tu equipo. Sin key, los presets funcionan igual: gratis y en local.</p>
            <button className="cta" onClick={saveKey}>Guardar</button>
          </div>
        </div>
      )}
    </main>
  );
}

export default App;
