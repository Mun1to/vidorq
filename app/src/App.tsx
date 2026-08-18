import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiPost, CaptionStyle, ENGINE, Workspaces } from "./api";
import { useLang, Key } from "./i18n";
import Brand from "./Brand";
import Settings from "./Settings";
import Guia from "./Guia";
import logo from "./assets/logo.png";
import {
  IconAlert, IconBook, IconBrand, IconCheck, IconChevron, IconClock, IconDrop,
  IconFilm, IconFolder, IconFolderOpen, IconMic, IconPlay, IconScissors, IconSliders,
  IconSpark, IconVideo, IconZap,
} from "./Icons";
import "./App.css";

type Preset = "clean" | "podcast" | "montage";
type Output = "mp4" | "resolve";
type Phase = "idle" | "running" | "done" | "error";
type View = "edit" | "history";

interface Progress {
  step: string;
  percent: number;
  detail?: string;
  result?: string;
  error?: string;
}

const PRESETS: { id: Preset; Icon: typeof IconScissors; name: Key; desc: Key; beta?: boolean }[] = [
  { id: "clean", Icon: IconScissors, name: "preset.clean", desc: "preset.clean.desc" },
  { id: "podcast", Icon: IconMic, name: "preset.podcast", desc: "preset.podcast.desc" },
  { id: "montage", Icon: IconZap, name: "preset.montage", desc: "preset.montage.desc", beta: true },
];

function App() {
  const { t, lang, setLang } = useLang();
  const [video, setVideo] = useState<string>("");
  const [preset, setPreset] = useState<Preset>("clean");
  const [captions, setCaptions] = useState(true);
  // Los estilos de caption los sirve el motor, que es donde estan definidos:
  // asi anadir uno no obliga a tocar la interfaz.
  const [capStyles, setCapStyles] = useState<CaptionStyle[]>([]);
  const [capStyle, setCapStyle] = useState("pop");
  // El look y el movimiento son dos elecciones, como en CapCut. Vacio = la
  // animacion con la que viene ese estilo.
  const [capAnims, setCapAnims] = useState<CaptionStyle[]>([]);
  const [capAnim, setCapAnim] = useState("");
  const [animOf, setAnimOf] = useState<Record<string, string>>({});
  // Mirar el video y traducir cuestan minutos, asi que van apagados de serie.
  const [seeVideo, setSeeVideo] = useState(false);
  const [transLang, setTransLang] = useState("");
  const [burnTrans, setBurnTrans] = useState(false);
  const [langs, setLangs] = useState<Record<string, string>>({});
  const [transition, setTransition] = useState("none");
  const [transitions, setTransitions] = useState<Record<string, string>>({});
  const [ratio, setRatio] = useState("source");
  const [ratios, setRatios] = useState<Record<string, string>>({});
  // El recorte no sigue a la persona (no es fiable), asi que se mueve a mano.
  const [cropX, setCropX] = useState(0.5);
  const [output, setOutput] = useState<Output>("mp4");
  const [proOpen, setProOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [brandOpen, setBrandOpen] = useState(false);
  // La guia se abre sola la primera vez, para que nadie tenga que adivinar los pasos de Resolve.
  const [guiaOpen, setGuiaOpen] = useState(() => !localStorage.getItem("vidorq.guiaVista"));
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState<Progress>({ step: "", percent: 0 });
  const [engineUp, setEngineUp] = useState<boolean | null>(null);
  const [retry, setRetry] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [ws, setWs] = useState<Workspaces>({ active: "Principal", list: ["Principal"] });
  const [wsOpen, setWsOpen] = useState(false);
  const [view, setView] = useState<View>("edit");
  const wsRef = useRef<HTMLDivElement>(null);

  // Drag & drop nativo de Tauri (rutas reales); en navegador normal se usa el campo de ruta
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
      } catch { /* fuera de Tauri */ }
    })();
    return () => { unsub?.(); };
  }, []);

  // Latido del motor + workspaces
  useEffect(() => {
    const check = () =>
      fetch(`${ENGINE}/health`).then(() => setEngineUp(true)).catch(() => setEngineUp(false));
    check();
    apiGet<Workspaces>("/workspaces")
      .then((w) => { if (w && Array.isArray(w.list)) setWs(w); })
      .catch(() => {});
    const t = setInterval(check, 4000);
    return () => clearInterval(t);
  }, []);

  // Estilos de caption. Se vuelven a pedir al cambiar de idioma porque las
  // descripciones vienen del motor ya traducidas.
  useEffect(() => {
    apiGet<{
      default: string; list: CaptionStyle[];
      anims?: CaptionStyle[]; animOf?: Record<string, string>;
      langs?: Record<string, string>; transitions?: Record<string, string>;
      ratios?: Record<string, string>;
    }>(`/captions/presets?lang=${lang}`)
      .then((c) => {
        if (!c || !Array.isArray(c.list)) return;
        setCapStyles(c.list);
        setCapStyle((cur) => (c.list.some((s) => s.id === cur) ? cur : c.default));
        if (Array.isArray(c.anims)) setCapAnims(c.anims);
        if (c.animOf) setAnimOf(c.animOf);
        if (c.langs) setLangs(c.langs);
        if (c.transitions) setTransitions(c.transitions);
        if (c.ratios) setRatios(c.ratios);
      })
      .catch(() => {
        // El motor puede estar arrancando todavia. Sin este reintento, una
        // ventana abierta medio segundo antes de tiempo se queda sin estilos,
        // sin idiomas y sin formatos, y parece que la app viene rota.
        setTimeout(() => setRetry((n) => n + 1), 2000);
      });
  }, [lang, retry]);

  // Progreso
  useEffect(() => {
    if (phase !== "running") return;
    const t = setInterval(async () => {
      try {
        const p = await apiGet<Progress>("/progress");
        setProgress(p);
        if (p.error) setPhase("error");
        else if (p.percent >= 100 && p.result) setPhase("done");
      } catch { /* ocupado */ }
    }, 800);
    return () => clearInterval(t);
  }, [phase]);

  // Cerrar el desplegable de workspace al pulsar fuera
  useEffect(() => {
    if (!wsOpen) return;
    const away = (e: MouseEvent) => {
      if (wsRef.current && !wsRef.current.contains(e.target as Node)) setWsOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [wsOpen]);

  const fileName = useMemo(() => video.split(/[\\/]/).pop() ?? "", [video]);
  const canEdit = video !== "" && engineUp === true && phase !== "running";

  async function startEdit() {
    setPhase("running");
    setProgress({ step: t("run.working"), percent: 2 });
    try {
      const j = await apiPost<{ ok?: boolean; error?: string }>("/edit", {
        video, preset, captions, output, prompt: proOpen ? prompt : "", lang,
        captionPreset: capStyle, captionAnim: capAnim,
        vision: seeVideo, translate: transLang, translateCaptions: burnTrans,
        transition, ratio, cropX,
      });
      if (j.error) { setProgress({ step: "", percent: 0, error: j.error }); setPhase("error"); }
    } catch {
      setProgress({ step: "", percent: 0, error: t("alert.noEngine") });
      setPhase("error");
    }
  }

  async function switchWs(name: string) {
    setWsOpen(false);
    const req = name === "__new__"
      ? (() => {
          const n = window.prompt(t("ws.prompt"));
          return n ? { create: n, activate: n } : null;
        })()
      : { activate: name };
    if (!req) return;
    try {
      const w = await apiPost<Workspaces>("/workspaces", req);
      if (w && Array.isArray(w.list)) setWs(w);
    } catch { /* motor antiguo o apagado */ }
  }

  const working = phase === "running" || phase === "done";

  return (
    <main className="shell">
      <aside className="side">
        <div className="logo">
          <img src={logo} alt="" />
          <b>Vidorq</b>
        </div>

        <div className="ws-wrap" ref={wsRef}>
          <button className="ws-btn" onClick={() => setWsOpen(!wsOpen)}>
            <IconFolder size={15} className="icon" />
            {ws.active}
            <IconChevron size={15} className="icon chev" />
          </button>
          {wsOpen && (
            <div className="ws-menu">
              {ws.list.map((w) => (
                <button key={w} className={w === ws.active ? "sel" : ""} onClick={() => switchWs(w)}>
                  <IconFolder size={14} className="icon" />{w}
                </button>
              ))}
              <button onClick={() => switchWs("__new__")}>
                <IconFolderOpen size={14} className="icon" />{t("ws.new")}
              </button>
            </div>
          )}
        </div>

        <nav className="nav">
          <button className={view === "edit" ? "sel" : ""} onClick={() => setView("edit")}>
            <IconFilm className="icon" />{t("nav.edit")}
          </button>
          <button onClick={() => setBrandOpen(true)}>
            <IconBrand className="icon" />{t("nav.brand")}
          </button>
          <button className={view === "history" ? "sel" : ""} onClick={() => setView("history")}>
            <IconClock className="icon" />{t("nav.history")}
          </button>
          <button onClick={() => setGuiaOpen(true)}>
            <IconBook className="icon" />{t("nav.guide")}
          </button>
          <button onClick={() => setSettingsOpen(true)}>
            <IconSliders className="icon" />{t("nav.settings")}
          </button>
        </nav>

        <div className="side-foot">
          <div className="lang" role="group" aria-label={t("lang")}>
            <button className={lang === "es" ? "sel" : ""} onClick={() => setLang("es")}>ES</button>
            <button className={lang === "en" ? "sel" : ""} onClick={() => setLang("en")}>EN</button>
          </div>
          <span className="ver">{t("ver")}</span>
        </div>
      </aside>

      {view === "history" ? (
        <section className="run">
          <IconClock size={40} className="icon" />
          <h2>{t("history.title")}</h2>
          <p className="stepn">{t("history.sub")}</p>
        </section>
      ) : working ? (
        <section className="run">
          {phase === "running" ? (
            <>
              <div className="spin" />
              <h2>{progress.step || t("run.working")}</h2>
              <div className="track"><i style={{ width: `${progress.percent}%` }} /></div>
              <p className="stepn">
                {progress.detail ? `${progress.detail} · ` : ""}{progress.percent}%
              </p>
            </>
          ) : (
            <>
              <div className="done-ic"><IconCheck size={46} className="icon" /></div>
              <h2>{t("run.done")}</h2>
              <p className="stepn">
                {output === "resolve" ? t("run.doneResolve") : t("run.doneMp4")}
              </p>
              <div className="path">{progress.result}</div>
              <div className="run-actions">
                <button className="cta inline" onClick={() => {
                  setPhase("idle"); setProgress({ step: "", percent: 0 }); setVideo("");
                }}>
                  <IconVideo size={15} className="icon" />{t("run.again")}
                </button>
              </div>
            </>
          )}
        </section>
      ) : (
        <section className="main">
          <div className="mhead">
            <div>
              <h1>{t("head.title")}</h1>
              <p>{t("head.sub")}</p>
            </div>
            <div className="seg">
              <button className={output === "mp4" ? "sel" : ""} onClick={() => setOutput("mp4")}>{t("out.mp4")}</button>
              <button className={output === "resolve" ? "sel" : ""} onClick={() => setOutput("resolve")}>{t("out.resolve")}</button>
            </div>
          </div>

          {engineUp === false && (
            <div className="alert">
              <IconAlert size={16} className="icon" />
              <span>{t("alert.engineOff")} <code>engine\start_engine.bat</code></span>
            </div>
          )}
          {phase === "error" && progress.error && (
            <div className="alert">
              <IconAlert size={16} className="icon" />
              <span>{progress.error}</span>
            </div>
          )}

          <div className={`drop ${dragOver ? "over" : ""} ${video ? "loaded" : ""}`}>
            {video ? (
              <>
                <IconVideo size={22} className="icon" />
                <b>{fileName}</b>
                <button className="ghost small" onClick={() => setVideo("")}>{t("drop.change")}</button>
              </>
            ) : (
              <>
                <IconDrop size={22} className="icon" />
                <b>{t("drop.title")}</b>
                <small>{t("drop.sub")}</small>
                <input
                  className="path-input"
                  placeholder="C:\...\video.mp4"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") setVideo((e.target as HTMLInputElement).value.replace(/^"|"$/g, ""));
                  }}
                />
              </>
            )}
          </div>

          <div className="presets">
            {PRESETS.map(({ id, Icon, name, desc, beta }) => (
              <button key={id} className={`preset ${preset === id ? "sel" : ""}`} onClick={() => setPreset(id)}>
                <Icon className="icon" />
                <b>{t(name)}{beta && <span className="tag">{t("beta")}</span>}</b>
                <small>{t(desc)}</small>
              </button>
            ))}
          </div>

          <div className="optrow">
            <button
              className={`chk ${captions ? "on" : ""}`}
              onClick={() => setCaptions(!captions)}
              role="switch"
              aria-checked={captions}
            >
              <span className="box"><IconCheck size={12} className="icon" /></span>
              {t("captions")}
            </button>
            <button
              className={`chk ${seeVideo ? "on" : ""}`}
              onClick={() => setSeeVideo(!seeVideo)}
              role="switch"
              aria-checked={seeVideo}
              title={t("vision.note")}
            >
              <span className="box"><IconCheck size={12} className="icon" /></span>
              {t("vision")}
            </button>
            <span className="profile-note">{t("workspace")} <b>{ws.active}</b></span>
          </div>

          {seeVideo && <small className="capnote">{t("vision.note")}</small>}

          {captions && capStyles.length > 0 && (
            <div className="capstyles">
              {capStyles.map((s) => (
                <button
                  key={s.id}
                  className={`capstyle ${capStyle === s.id ? "sel" : ""}`}
                  onClick={() => setCapStyle(s.id)}
                  title={s.note}
                >
                  {s.label}
                </button>
              ))}
              <small className="capnote">{capStyles.find((s) => s.id === capStyle)?.note}</small>
            </div>
          )}

          {captions && capAnims.length > 0 && (
            <div className="capstyles anims">
              <span className="caplabel">{t("captions.anim")}</span>
              <button
                className={`capstyle ${capAnim === "" ? "sel" : ""}`}
                onClick={() => setCapAnim("")}
                title={t("captions.anim.own")}
              >
                {t("captions.anim.own")}
                {animOf[capStyle] ? ` · ${capAnims.find((a) => a.id === animOf[capStyle])?.label ?? ""}` : ""}
              </button>
              {capAnims.map((a) => (
                <button
                  key={a.id}
                  className={`capstyle ${capAnim === a.id ? "sel" : ""}`}
                  onClick={() => setCapAnim(a.id)}
                  title={a.note}
                >
                  {a.label}
                </button>
              ))}
              <small className="capnote">
                {capAnim ? capAnims.find((a) => a.id === capAnim)?.note : t("captions.anim.ownNote")}
              </small>
            </div>
          )}

          {captions && Object.keys(langs).length > 0 && (
            <div className="capstyles anims">
              <span className="caplabel">{t("captions.lang")}</span>
              <button className={`capstyle ${transLang === "" ? "sel" : ""}`}
                      onClick={() => { setTransLang(""); setBurnTrans(false); }}>
                {t("captions.lang.same")}
              </button>
              {Object.entries(langs).map(([id, label]) => (
                <button key={id} className={`capstyle ${transLang === id ? "sel" : ""}`}
                        onClick={() => setTransLang(id)}>
                  {label}
                </button>
              ))}
              <small className="capnote">
                {transLang ? t("captions.lang.note") : t("captions.lang.sameNote")}
              </small>
              {transLang && (
                <button className={`chk ${burnTrans ? "on" : ""}`}
                        onClick={() => setBurnTrans(!burnTrans)}
                        role="switch" aria-checked={burnTrans}>
                  <span className="box"><IconCheck size={12} className="icon" /></span>
                  {t("captions.lang.burn")}
                </button>
              )}
            </div>
          )}

          {Object.keys(ratios).length > 0 && (
            <div className="capstyles anims">
              <span className="caplabel">{t("ratio")}</span>
              {Object.entries(ratios).map(([id, label]) => (
                <button key={id} className={`capstyle ${ratio === id ? "sel" : ""}`}
                        onClick={() => setRatio(id)}>
                  {label}
                </button>
              ))}
              <small className="capnote">
                {ratio === "source" ? t("ratio.sourceNote") : t("ratio.note")}
              </small>
              {ratio !== "source" && (
                <label className="cropx">
                  {t("ratio.crop")}
                  <input type="range" min={0} max={1} step={0.05} value={cropX}
                         onChange={(e) => setCropX(parseFloat(e.target.value))} />
                  <b>{cropX === 0.5 ? t("ratio.center") : `${Math.round(cropX * 100)}%`}</b>
                </label>
              )}
            </div>
          )}

          {output === "mp4" && Object.keys(transitions).length > 0 && (
            <div className="capstyles anims">
              <span className="caplabel">{t("transition")}</span>
              {Object.entries(transitions).map(([id, label]) => (
                <button key={id} className={`capstyle ${transition === id ? "sel" : ""}`}
                        onClick={() => setTransition(id)}>
                  {label}
                </button>
              ))}
              <small className="capnote">
                {transition === "none" ? t("transition.noneNote") : t("transition.note")}
              </small>
            </div>
          )}

          <div className="pro">
            <button className="pro-toggle" onClick={() => setProOpen(!proOpen)}>
              <IconSpark size={15} className="icon" />
              {t("pro")}
              <IconChevron size={15} className={`icon chev ${proOpen ? "up" : ""}`} />
            </button>
            {proOpen && (
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={t("pro.placeholder")}
              />
            )}
          </div>

          <button className="cta" disabled={!canEdit} onClick={startEdit}>
            <IconPlay size={15} className="icon" />{t("cta.edit")}
          </button>
        </section>
      )}

      {settingsOpen && <Settings onClose={() => setSettingsOpen(false)} />}
      {brandOpen && <Brand onClose={() => setBrandOpen(false)} styles={capStyles} />}
      {guiaOpen && (
        <Guia onClose={() => { localStorage.setItem("vidorq.guiaVista", "1"); setGuiaOpen(false); }} />
      )}
    </main>
  );
}

export default App;
