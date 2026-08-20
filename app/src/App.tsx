import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiPost, CaptionStyle, ENGINE, Workspaces } from "./api";
import { useLang, Key } from "./i18n";
import Brand from "./Brand";
import Settings from "./Settings";
import Guia from "./Guia";
import Gallery from "./Gallery";
import Words from "./Words";
import History from "./History";
import Chat, { Settings as ChatState, Turn } from "./Chat";
import logo from "./assets/logo.png";
import {
  IconAlert, IconBook, IconBrand, IconCheck, IconChevron, IconClock, IconDrop,
  IconFilm, IconFolder, IconFolderOpen, IconMic, IconPlay, IconScissors, IconSliders,
  IconSpark, IconStop, IconVideo, IconZap,
} from "./Icons";
import "./App.css";

type Preset = "clean" | "podcast" | "montage";
type Output = "mp4" | "resolve";
type Phase = "idle" | "running" | "done" | "error" | "stopped";
type View = "edit" | "history";

interface Progress {
  step: string;
  percent: number;
  detail?: string;
  result?: string;
  error?: string;
  stopped?: boolean;
}

// Lo que se le puede pedir, de un toque. Un campo de texto vacio no enseña lo
// que sabe hacer; tres ejemplos si, y se rellenan solos para poder tocarlos.
const SAY_EXAMPLES = ["say.eg1", "say.eg2", "say.eg3"] as const;

const PRESETS: { id: Preset; Icon: typeof IconScissors; name: Key; desc: Key; beta?: boolean }[] = [
  { id: "clean", Icon: IconScissors, name: "preset.clean", desc: "preset.clean.desc" },
  { id: "podcast", Icon: IconMic, name: "preset.podcast", desc: "preset.podcast.desc" },
  { id: "montage", Icon: IconZap, name: "preset.montage", desc: "preset.montage.desc", beta: true },
];

interface PoolClip {
  name: string;
  path: string;
  resolution: string;
  fps: number | string;
  duration: string;
}

function App() {
  const { t, lang, setLang } = useLang();
  const [video, setVideo] = useState<string>("");
  // Por que no vale la ruta que se acaba de escribir. "" = no hay nada que decir.
  const [pathWhy, setPathWhy] = useState("");
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
  const [shake, setShake] = useState(false);
  const [transLang, setTransLang] = useState("");
  const [burnTrans, setBurnTrans] = useState(false);
  const [langs, setLangs] = useState<Record<string, string>>({});
  const [transition, setTransition] = useState("none");
  const [transitions, setTransitions] = useState<Record<string, string>>({});
  // Cuales de ellas sabe hacer Resolve. Lo dice el motor, que es quien tiene la
  // tabla; tenerlo escrito aqui es como se separo de la galeria.
  const [resolveTrans, setResolveTrans] = useState<string[]>(["none"]);
  // El filtro de color. Vacio es "sin filtro", igual que en el motor.
  const [colours, setColours] = useState<CaptionStyle[]>([]);
  const [colour, setColour] = useState("");
  const [ratio, setRatio] = useState("source");
  const [ratios, setRatios] = useState<Record<string, string>>({});
  // El recorte no sigue a la persona (no es fiable), asi que se mueve a mano.
  const [cropX, setCropX] = useState(0.5);
  // Cuantas previews se han pedido ya. Solo sirve para saber si esta la primera.
  const [previewReady, setPreviewReady] = useState(false);
  // Se recuerda entre sesiones. Reiniciarlo a MP4 cada vez que se abre la
  // ventana es como se llega a pulsar "editar" esperando un timeline y recibir
  // un archivo: la eleccion se veia hecha en la sesion anterior, no en esta.
  const [output, setOutput] = useState<Output>(
    () => (localStorage.getItem("vidorq.output") === "resolve" ? "resolve" : "mp4"));
  useEffect(() => { localStorage.setItem("vidorq.output", output); }, [output]);
  const [moreOpen, setMoreOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  // La conversacion sobre ESTE video: lo que ya se ha pedido y lo que se esta
  // escribiendo ahora. Vidorq no editaba una vez, editaba UNA sola vez: al
  // terminar solo se podia empezar otro video, que es como un editor que se
  // levanta y se va en cuanto pone el primer corte.
  const [chat, setChat] = useState<Turn[]>([]);
  const [followUp, setFollowUp] = useState("");
  // Lo que has escrito y todavia no ha corrido. El motor hace un trabajo cada
  // vez, y antes el segundo mensaje se comia un 409 y desaparecia: la burbuja
  // se quedaba puesta y no contestaba nadie. Ahora se hacen en fila.
  const [queue, setQueue] = useState<string[]>([]);
  const [setup, setSetup] = useState(false);
  const [galOpen, setGalOpen] = useState(false);
  const [wordsOpen, setWordsOpen] = useState(false);
  // Si hay un paso atras al que volver. Lo dice el motor, que es quien guarda
  // el montaje de antes.
  const [canUndo, setCanUndo] = useState(false);
  const [cards, setCards] = useState<CaptionStyle[]>([]);
  // La caja de "cuentale que quieres", para poder dejar el cursor dentro cuando
  // una baldosa de la galeria escribe media frase.
  const sayRef = useRef<HTMLTextAreaElement>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [brandOpen, setBrandOpen] = useState(false);
  // La guia se abre sola la primera vez, para que nadie tenga que adivinar los pasos de Resolve.
  const [guiaOpen, setGuiaOpen] = useState(() => !localStorage.getItem("vidorq.guiaVista"));
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState<Progress>({ step: "", percent: 0 });
  // Lo que la edicion tiene puesto ahora, y el ultimo archivo que salio. Los dos
  // los servia /session desde el principio; la ventana simplemente no los leia,
  // asi que no habia forma de saber en que estado estaba tu propio video.
  const [now, setNow] = useState<ChatState>({});
  const [made, setMade] = useState("");
  // De que proyecto de Resolve es la conversacion que se esta viendo.
  const [scope, setScope] = useState("");
  const [engineUp, setEngineUp] = useState<boolean | null>(null);
  const [retry, setRetry] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  // Los videos que ya estan en el proyecto de Resolve abierto.
  const [poolClips, setPoolClips] = useState<PoolClip[]>([]);
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
      resolveTransitions?: string[];
      ratios?: Record<string, string>; looks?: CaptionStyle[];
      cards?: CaptionStyle[];
    }>(`/captions/presets?lang=${lang}`)
      .then((c) => {
        if (!c || !Array.isArray(c.list)) return;
        setCapStyles(c.list);
        setCapStyle((cur) => (c.list.some((s) => s.id === cur) ? cur : c.default));
        if (Array.isArray(c.anims)) setCapAnims(c.anims);
        if (c.animOf) setAnimOf(c.animOf);
        if (c.langs) setLangs(c.langs);
        if (c.transitions) setTransitions(c.transitions);
        if (c.resolveTransitions) setResolveTrans(c.resolveTransitions);
        if (c.ratios) setRatios(c.ratios);
        if (Array.isArray(c.looks)) setColours(c.looks);
        if (Array.isArray(c.cards)) setCards(c.cards);
      })
      .catch(() => {
        // El motor puede estar arrancando todavia. Sin este reintento, una
        // ventana abierta medio segundo antes de tiempo se queda sin estilos,
        // sin idiomas y sin formatos, y parece que la app viene rota.
        setTimeout(() => setRetry((n) => n + 1), 2000);
      });
  }, [lang, retry]);

  // El estilo de subtitulo de TU MARCA, que es lo que la pantalla "Tu marca"
  // sirve para elegir. Sin esto no llegaba nunca: el panel mandaba siempre su
  // propio valor con cada edicion, asi que la eleccion de la marca se pisaba y
  // aquella pantalla decidia nada. Se aplica al arrancar y al cambiar de
  // workspace, que es cuando cambia la marca; despues manda lo que toques.
  useEffect(() => {
    let alive = true;
    apiGet<{ captionPreset?: string; captionAnim?: string }>("/profile")
      .then((p) => {
        if (!alive || !p) return;
        if (p.captionPreset) setCapStyle(p.captionPreset);
        if (typeof p.captionAnim === "string") setCapAnim(p.captionAnim);
      })
      .catch(() => { /* motor apagado: el panel se queda con lo suyo */ });
    return () => { alive = false; };
  }, [ws.active]);

  // Los clips del proyecto abierto. Se piden al arrancar y al volver de una
  // edicion, que es cuando el proyecto puede haber cambiado.
  useEffect(() => {
    let alive = true;
    // Se reintenta porque "vacio" y "todavia no" se ven igual desde aqui, y al
    // arrancar la ventana Resolve suele estar abriendo el proyecto. Sin esto, un
    // segundo de mas y la lista no aparece nunca, sin decir nada.
    let quedan = 4;
    const pedir = () => {
      apiGet<{ clips?: PoolClip[] }>("/clips")
        .then((r) => {
          if (!alive) return;
          const c = Array.isArray(r?.clips) ? r.clips : [];
          setPoolClips(c);
          if (!c.length && quedan-- > 0) setTimeout(pedir, 1500);
        })
        .catch(() => { if (alive && quedan-- > 0) setTimeout(pedir, 1500); });
    };
    pedir();
    return () => { alive = false; };
  }, [phase]);

  // La preview de la combinacion elegida AHORA: estilo, entrada, formato y el
  // recorte real sobre el video del usuario. Se pide animada cuando hay entrada,
  // porque un movimiento no se ve en una foto quieta.
  const [previewOk, setPreviewOk] = useState(true);
  const previewUrl = useMemo(() => {
    if (!captions && ratio === "source") return "";
    const q = new URLSearchParams({ ratio, lang, video });
    if (colour) q.set("look", colour);
    if (!captions) {
      q.set("kind", "ratio");
    } else if (capAnim && capAnim !== "none") {
      q.set("kind", "anim");
      q.set("id", capAnim);
      q.set("preset", capStyle);
    } else {
      q.set("kind", "style");
      q.set("id", capStyle);
    }
    return `${ENGINE}/preview?${q.toString()}`;
  }, [captions, capStyle, capAnim, ratio, video, lang, colour]);

  // Si la foto no llega (el motor apagado, sobre todo), la seccion entera se
  // va. Antes se quedaba el titulo "Asi va a quedar" con una caja vacia debajo
  // y una raya de un pixel, que es peor que no prometer nada.
  useEffect(() => { setPreviewReady(false); setPreviewOk(true); }, [previewUrl]);

  // Al elegir un video se recupera lo que ya se le pidio, para poder seguir la
  // conversacion aunque la ventana se haya cerrado por el medio.
  // Tambien al terminar: una edicion NUEVA empieza la conversacion de cero en
  // el motor, y sin volver a preguntar la ventana seguia ensenando la lista de
  // la sesion anterior. Dos memorias que no coinciden son peor que ninguna.
  useEffect(() => {
    if (!video) { setChat([]); return; }
    if (phase === "running") return;
    apiGet<{ history: Turn[]; settings?: ChatState; result?: string; scope?: string;
             canUndo?: boolean }>(
      `/session?video=${encodeURIComponent(video)}`)
      .then((d) => {
        setNow(d.settings || {}); setMade(d.result || ""); setScope(d.scope || "");
        setCanUndo(!!d.canUndo);
        // Y el panel se pone al dia con lo que de verdad tiene el montaje. Sin
        // esto, decir "ponlo en vertical" por el chat dejaba el desplegable
        // diciendo "Como el original": la cabecera contaba una cosa y el panel
        // otra, sobre la misma edicion. Solo pasa al cargar o al terminar un
        // turno, nunca mientras estas tocando los botones.
        const st = d.settings || {};
        if (st.ratio) setRatio(st.ratio);
        if (st.transition) setTransition(st.transition);
        if (st.captionPreset) setCapStyle(st.captionPreset);
        if (typeof st.captionAnim === "string") setCapAnim(st.captionAnim);
        if (typeof st.captions === "boolean") setCaptions(st.captions);
        if (typeof st.shake === "boolean") setShake(st.shake);
        if (st.look !== undefined) setColour(st.look || "");
        if (st.cuts) setPreset(st.cuts as Preset);
        if (st.output) setOutput(st.output as Output);
        return d;
      })
      // Lo que sigue en la fila todavia no existe para el motor, asi que se
      // vuelve a poner detras: sin esto, tus mensajes en espera desaparecian de
      // la pantalla en cuanto contestaba el turno anterior.
      .then((d) => setChat([...(d.history || []), ...queue.map((y) => ({ you: y }))]))
      .catch(() => {});
  }, [video, phase]);

  // Lo que se ensena de un boton pulsado hasta que contesta el motor.
  function niceP(raw: string) {
    const [what, id] = raw.slice(5).split("=");
    const lista = what === "look" ? colours
      : what === "captionAnim" ? capAnims
      : what === "captionPreset" ? capStyles : [];
    const hit = lista.find((x) => x.id === id);
    return hit ? hit.label : (transitions[id] || ratios[id] || id);
  }

  /** El nombre de un ajuste tal y como se lee, no su id interno. */
  function labelOf(key: string, id: string) {
    const lista = key === "look" ? colours
      : key === "captionAnim" ? capAnims
      : key === "captionPreset" ? capStyles : [];
    const hit = lista.find((x) => x.id === id);
    if (hit) return hit.label;
    if (key === "transition") return transitions[id] || id;
    if (key === "ratio") return ratios[id] || id;
    if (key === "cuts") return t(`preset.${id}` as never) || id;
    return id;
  }

  /**
   * Abrir lo que ha salido. El vidorq corre dentro de una ventana de Tauri, que
   * SI puede abrir un archivo del disco; en un navegador normal (que es donde se
   * prueba el diseño) no hay nada que abrir y no pasa nada.
   */
  async function openMade(what: "file" | "folder", ruta?: string) {
    const donde = ruta || made;
    if (!donde) return;
    try {
      const mod = await import("@tauri-apps/plugin-opener");
      if (what === "folder") await mod.revealItemInDir(donde);
      else await mod.openPath(donde);
    } catch (e) {
      // Sin Tauri detras no hay abridor. Se dice en la consola y se sigue: no es
      // motivo para romper la conversacion.
      console.warn("no puedo abrirlo desde aqui:", e);
    }
  }

  function askMore(text?: string) {
    const q = (text ?? followUp).trim();
    if (!q) return;
    // Se pinta ya, sin esperar al motor: el mensaje propio tiene que aparecer
    // en el momento de enviarlo o parece que no se ha enviado. La respuesta la
    // trae despues /session, que es quien tiene la verdad.
    // La burbuja se pinta ya. Si es un boton, con su texto y no con el codigo
    // que viaja por debajo; el motor la reescribe igual al guardarla.
    setChat((c) => [...c, { you: q.startsWith("pick:") ? niceP(q) : q }]);
    setFollowUp("");
    if (phase === "running") setQueue((qq) => [...qq, q]);
    else startEdit(q);
  }

  // Al terminar un turno, el siguiente de la fila. Sin esto, escribir tres
  // cosas seguidas ejecutaba una y perdia dos.
  useEffect(() => {
    if (phase === "running" || queue.length === 0) return;
    const [next, ...rest] = queue;
    setQueue(rest);
    startEdit(next);
  }, [phase, queue]);

  // Un boton de la respuesta: "hazlo en MP4" relanza la MISMA frase con la otra
  // salida, en vez de obligar a escribirla de nuevo y a buscar el interruptor.
  function takeOffer(kind: string) {
    if (kind !== "mp4" || phase === "running") return;
    const last = [...chat].reverse().find((c) => c.you)?.you || "";
    setOutput("mp4");
    if (!last) return;
    // La salida va explicita en la llamada: setOutput no ha llegado todavia al
    // estado que lee startEdit, y esperar un render para eso es como se cuelan
    // los fallos que solo pasan la primera vez.
    setChat((c) => [...c, { you: last }]);
    setFollowUp("");
    startEdit(last, "mp4");
  }

  /**
   * Parar el turno en marcha.
   *
   * Una frase mal dicha costaba minuto y medio de espera, porque la unica forma
   * de cancelarla era esperar a que acabara. Parar tambien vacia la fila: si
   * paras porque te equivocaste, seguir con los siguientes mensajes en espera
   * seria justo lo contrario de lo que pediste.
   */
  function stopEdit() {
    if (phase !== "running") return;
    setQueue([]);
    setProgress((p) => ({ ...p, step: t("run.stopping") }));
    apiPost("/stop", {}).catch(() => {});
  }

  // Progreso
  useEffect(() => {
    if (phase !== "running") return;
    const t = setInterval(async () => {
      try {
        const p = await apiGet<Progress>("/progress");
        setProgress(p);
        if (p.error) setPhase("error");
        else if (p.stopped) setPhase("stopped");
        else if (p.percent >= 100 && p.result) setPhase("done");
      } catch { /* ocupado */ }
    }, 800);
    return () => clearInterval(t);
  }, [phase]);

  // Escape para parar. Es la tecla que la mano busca sola cuando algo esta
  // pasando y no lo querias.
  useEffect(() => {
    if (phase !== "running") return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") stopEdit(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
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
  /* Una ruta escrita a mano no se comprobaba. Con una letra de mas el nombre
     aparecia igual en su sitio, el boton de editar se encendia y el fallo no
     salia hasta la mitad de la edicion. Ahora se le pregunta al motor antes de
     aceptarla. Un video arrastrado o sacado del proyecto de Resolve ya existe,
     asi que ese camino no paga la vuelta; el del historial si, porque el
     archivo pudo borrarse despues. */
  async function pickVideo(raw: string) {
    const path = raw.trim().replace(/^"|"$/g, "");
    if (!path) { setPathWhy(""); setVideo(""); return; }
    try {
      const r = await apiGet<{ ok: boolean; why: string }>(
        `/probe?lang=${lang}&video=${encodeURIComponent(path)}`);
      if (!r.ok) { setPathWhy(r.why); return; }
    } catch { /* el motor caido ya tiene su aviso arriba */ }
    setPathWhy("");
    setVideo(path);
  }

  const canEdit = video !== "" && engineUp === true && phase !== "running";
  // El chat manda en cuanto este video tiene conversacion, aunque la ventana se
  // haya cerrado por el medio: para eso se guarda. La pantalla de "Listo" con su
  // tick se queda para la primera vez, que es cuando hace falta celebrar que ha
  // salido algo. `setup` es la puerta de vuelta a los ajustes, porque la galeria
  // de estilos vive alli y no se puede quedar encerrada detras del chat.
  const chatting = view === "edit" && chat.length > 0 && !setup;

  async function startEdit(refine = "", forceOutput?: Output, extra?: object) {
    setSetup(false);
    setPhase("running");
    setProgress({ step: t("run.working"), percent: 2 });
    try {
      const j = await apiPost<{ ok?: boolean; error?: string }>("/edit", {
        video, preset, captions, output: forceOutput || output,
        // En un retoque manda la frase nueva; el resto de ajustes los recuerda
        // el motor, que es quien tiene el montaje.
        // Sin condiciones: lo que se ve escrito en la pantalla es lo que se
        // manda. Antes iba atado a que el desplegable estuviera abierto, asi que
        // se podia escribir una frase, cerrarlo, y editar sin ella.
        prompt: refine || prompt, lang,
        // `extra` trae un retoque que no cabe en una frase (hoy, el orden nuevo
        // de los tramos), y por eso vale como retoque aunque no venga texto.
        refine: refine || extra ? true : undefined,
        ...(extra || {}),
        captionPreset: capStyle, captionAnim: capAnim,
        vision: seeVideo, shake, translate: transLang, translateCaptions: burnTrans,
        transition, ratio, cropX, look: colour,
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

  const working = phase === "running" || phase === "done" || phase === "stopped";

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
        // Pulsar una edicion vuelve a su video, que es lo unico que se puede
        // querer hacer con una fila del historial: seguir con aquello.
        <History
          onOpen={(v) => { pickVideo(v); setView("edit"); }}
          // El historial guardaba donde quedo cada video y no dejaba abrirlo:
          // para eso es un historial, para encontrar aquello de la semana
          // pasada sin acordarse de la carpeta.
          onFile={(ruta, what) => openMade(what, ruta)} />
      ) : chatting ? (
        <Chat
          title={fileName || t("head.title")}
          turns={chat}
          now={now}
          label={labelOf}
          made={made}
          scope={scope}
          onOpen={openMade}
          draft={followUp}
          onDraft={setFollowUp}
          onSend={(text) => askMore(text)}
          onOffer={takeOffer}
          onPick={(what, id, send) => {
            // Un boton puede llevar la salida dentro ("...&output=mp4"): es la
            // unica forma de pedir una transicion que Resolve no sabe hacer sin
            // acabar en la misma negativa otra vez. El desplegable se entera,
            // que si no la siguiente frase lo devolveria a Resolve en silencio.
            const salida = /output=(mp4|resolve)/.exec(send || "")?.[1] as Output | undefined;
            if (salida) setOutput(salida);
            askMore(send || `pick:${what}=${id}`);
          }}
          onSetup={() => setSetup(true)}
          onWords={() => setWordsOpen(true)}
          canUndo={canUndo}
          onUndo={() => {
            setChat((c) => [...c, { you: t("chat.undo") }]);
            if (phase === "running") return;
            startEdit("", undefined, { undo: true });
          }}
          onNewVideo={() => {
            setPhase("idle"); setProgress({ step: "", percent: 0 }); setVideo("");
            setChat([]); setFollowUp(""); setSetup(false);
            setNow({}); setMade(""); setScope("");
          }}
          running={phase === "running"}
          onStop={stopEdit}
          step={progress.step}
          detail={progress.detail}
          percent={progress.percent}
          error={progress.error}
        />
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
              <button className="stop" onClick={stopEdit}>
                <IconStop size={14} className="icon" />{t("run.stop")}
              </button>
            </>
          ) : phase === "stopped" ? (
            <>
              <div className="done-ic stopped"><IconStop size={40} className="icon" /></div>
              <h2>{t("run.stopped")}</h2>
              <p className="stepn">{progress.detail || t("run.stoppedSub")}</p>
              <div className="run-actions">
                <button className="ghost" onClick={() => {
                  setPhase("idle"); setProgress({ step: "", percent: 0 });
                }}>{t("run.back")}</button>
              </div>
            </>
          ) : (
            <>
              <div className="done-ic"><IconCheck size={46} className="icon" /></div>
              <h2>{t("run.done")}</h2>
              <p className="stepn">
                {output === "resolve" ? t("run.doneResolve") : t("run.doneMp4")}
              </p>
              <div className="path">{progress.result}</div>

              {/* Aqui no se acaba nada: es donde se sigue editando. En cuanto
                  hay un turno, la pantalla entera pasa a ser el chat. */}
              <div className="more-chat">
                <div className="row">
                  <input
                    value={followUp}
                    onChange={(e) => setFollowUp(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") askMore(); }}
                    placeholder={t("more.ph")}
                    autoFocus
                  />
                  <button className="cta inline" onClick={() => askMore()}
                          disabled={!followUp.trim()}>
                    <IconSpark size={15} className="icon" />{t("more.go")}
                  </button>
                </div>
                <small className="under">{t("more.note")}</small>
              </div>

              <div className="run-actions">
                <button className="ghost" onClick={() => {
                  setPhase("idle"); setProgress({ step: "", percent: 0 }); setVideo("");
                  setChat([]); setFollowUp("");
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
              {/* Primero lo que de verdad hace un usuario, que es un clic en
                  Resolve; el .bat es para quien tiene el repositorio delante.
                  Al reves mandaba a todo el mundo a buscar un archivo suelto. */}
              <span>
                {t("alert.engineOff")} <code>Workspace &gt; Scripts &gt; Vidorq</code>.{" "}
                {t("alert.engineOff2")} <code>engine\start_engine.bat</code>
              </span>
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
                  className={`path-input ${pathWhy ? "bad" : ""}`}
                  onChange={() => pathWhy && setPathWhy("")}
                  placeholder="C:\...\video.mp4"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") pickVideo((e.target as HTMLInputElement).value);
                  }}
                />
                {pathWhy && (
                  <small className="path-bad">
                    <IconAlert size={13} className="icon" />{pathWhy}
                  </small>
                )}
                {poolClips.length > 0 && (
                  <div className="pool">
                    <span className="pool-head">{t("drop.inproject")}</span>
                    {poolClips.map((c) => (
                      <button key={c.path} className="pool-clip" onClick={() => setVideo(c.path)}>
                        <IconVideo size={15} className="icon" />
                        <span className="pool-name">{c.name}</span>
                        <span className="pool-meta">{c.resolution} · {c.duration}</span>
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Lo primero despues del video, porque es lo que promete la cabecera.
              Escribir aqui es optativo: los tres presets de abajo son el atajo
              para quien no quiere escribir nada. */}
          <div className="say">
            <textarea
              ref={sayRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={t("say.ph")}
              rows={2}
            />
            <div className="say-eg">
              {SAY_EXAMPLES.map((k) => (
                <button key={k} type="button" onClick={() => setPrompt(t(k as never))}>
                  {t(k as never)}
                </button>
              ))}
            </div>
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
            {/* Solo aparece con la vista puesta: el temblor va sobre los golpes
                del movimiento, y sin mirar el video no hay golpes que encontrar.
                Ofrecerlo apagado seria ofrecer un boton que no hace nada. */}
            {seeVideo && (
              <button
                className={`chk ${shake ? "on" : ""}`}
                onClick={() => setShake(!shake)}
                role="switch"
                aria-checked={shake}
                title={t("shake.note")}
              >
                <span className="box"><IconCheck size={12} className="icon" /></span>
                {t("shake")}
              </button>
            )}
            <span className="profile-note">{t("workspace")} <b>{ws.active}</b></span>
          </div>

          {seeVideo && <small className="capnote">{t("vision.note")}</small>}

          {previewUrl && previewOk && (
            <section className="preview">
              <span className="preview-head">
                {t("preview.head")}
                {captions && capStyles.length > 0 && (
                  <button className="open-gal" onClick={() => setGalOpen(true)}>
                    <IconSpark size={13} className="icon" />{t("preview.gallery")}
                  </button>
                )}
              </span>
              <div className={`preview-box ${previewReady ? "" : "loading"}`}>
                <img
                  src={previewUrl}
                  alt=""
                  onLoad={() => setPreviewReady(true)}
                  onError={() => { setPreviewReady(true); setPreviewOk(false); }}
                />
              </div>
              {/* Sin video elegido esta foto es la de muestra, y la frase
                  decia "sobre tu propio metraje" igual: lo primero que ve
                  alguien al abrir el programa era una promesa falsa. */}
              <small className="under">
                {video ? t("preview.note") : t("preview.sample")}
              </small>
            </section>
          )}

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

          {/* Lo de todos los dias arriba; lo demas, guardado. Una pantalla que
              lo ensena todo a la vez no es potente, es ruidosa. */}
          <div className="more">
            <button className="more-toggle" onClick={() => setMoreOpen(!moreOpen)}>
              <IconSliders size={15} className="icon" />
              {t("more")}
              <IconChevron size={15} className={`icon chev ${moreOpen ? "up" : ""}`} />
            </button>
            {moreOpen && (
              <div className="more-body">
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

              {/* Con salida a Resolve esta fila estaba escondida entera, y no era
                  verdad: el fundido a negro y el de a blanco SI se hacen ahi, con
                  una capa animada encima del corte. Lo que no cabe se marca y se
                  dice donde sale, en vez de desaparecer. */}
              {Object.keys(transitions).length > 0 && (
                <div className="capstyles anims">
                  <span className="caplabel">{t("transition")}</span>
                  {Object.entries(transitions).map(([id, label]) => {
                    const fuera = output === "resolve" && !resolveTrans.includes(id);
                    return (
                      <button key={id}
                              className={`capstyle ${transition === id ? "sel" : ""}${fuera ? " elsewhere" : ""}`}
                              onClick={() => setTransition(id)}>
                        {label}
                        {fuera && <em className="opt-note">MP4</em>}
                      </button>
                    );
                  })}
                  <small className="capnote">
                    {transition === "none" ? t("transition.noneNote")
                     : output === "resolve" && !resolveTrans.includes(transition)
                       ? t("transition.mp4only") : t("transition.note")}
                  </small>
                </div>
              )}
              </div>
            )}
          </div>


          {/* Apagado y mudo no vale: el boton principal esta gris hasta que
              hay video, y quien abre el programa por primera vez lo pulsa y no
              pasa nada. Cuando falta el video lo dice el propio boton, que es
              el sitio donde ya esta mirando. El motor caido tiene su aviso
              arriba, asi que ese caso no se repite aqui. */}
          <button className="cta" disabled={!canEdit} onClick={() => startEdit()}>
            {video ? <IconPlay size={15} className="icon" />
                   : <IconVideo size={15} className="icon" />}
            {video ? t("cta.edit") : t("cta.needVideo")}
          </button>
        </section>
      )}

      {galOpen && (
        <Gallery
          styles={capStyles} anims={capAnims} animOf={animOf}
          style={capStyle} anim={capAnim} ratio={ratio} video={video}
          colours={colours} colour={colour}
          ratios={ratios} transitions={transitions} resolveTrans={resolveTrans}
          transition={transition}
          onRatio={setRatio} onTransition={setTransition}
          cards={cards}
          // Un efecto no se "pone": se pide, y lo unico que falta es lo que
          // tiene que decir. Asi que la baldosa cierra la galeria y deja la
          // frase empezada donde se escribe, con el cursor al final.
          onCard={(id) => {
            setGalOpen(false);
            const frase = id === "chapa"
              ? "pon una chapa que diga " : "pon un rotulo que diga ";
            if (chat.length) { setFollowUp(frase); return; }
            setPrompt(frase);
            // Tras el cierre del modal, para que el foco no se lo lleve el velo
            // al desmontarse.
            setTimeout(() => {
              const el = sayRef.current;
              if (!el) return;
              el.focus();
              el.setSelectionRange(el.value.length, el.value.length);
            }, 60);
          }}
          onStyle={setCapStyle} onAnim={setCapAnim}
          onColour={(id) => setColour(id === "none" ? "" : id)}
          onClose={() => setGalOpen(false)}
        />
      )}
      {wordsOpen && (
        <Words video={video} onSend={(text) => askMore(text)}
               onOrder={(order) => {
                 // Arrastrar no es una frase, asi que la burbuja la pone la
                 // interfaz y el motor la reescribe al guardarla, igual que con
                 // los botones del chat.
                 setChat((c) => [...c, { you: t("words.orderApply") }]);
                 if (phase === "running") return;
                 startEdit("", undefined, { order });
               }}
               onClose={() => setWordsOpen(false)} />
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
