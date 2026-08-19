import { useEffect, useRef } from "react";
import { useLang } from "./i18n";
import {
  IconAlert, IconCheck, IconFolder, IconPlay, IconSliders, IconSpark, IconStop,
  IconUndo, IconVideo,
} from "./Icons";
import logo from "./assets/logo.png";

/** Un turno de la conversacion, tal y como lo guarda el motor en sesion.json. */
export interface Ask {
  what: string;
  question: string;
  /* `send` es la frase entera que manda esa opcion, cuando la respuesta no es
     un ajuste del menu sino un sitio del montaje: "haz un zoom en el segundo 9".
     Asi el boton no sabe nada que el chat no sepa y entra por el mismo camino
     que el texto escrito, que es el que esta probado. */
  options: { id: string; label: string; send?: string }[];
}

export interface Turn {
  you: string;
  did?: string[];
  cannot?: { what: string; value?: string; why: string }[];
  unknown?: string[];
  ask?: Ask[];
  offer?: { kind?: string };
  result?: string;
  ok?: boolean;
}

/** Atajos sobre el redactor: lo que la gente pide una y otra vez, a un toque.
 *
 *  Cada uno manda una frase normal, la misma que se podria escribir. Asi no hay
 *  dos caminos que mantener: el boton no sabe nada que el chat no sepa, y lo
 *  que pasa despues es lo mismo que si lo hubieras tecleado. Los que nombran
 *  una categoria sin decir cual acaban en la pregunta con sus opciones, que es
 *  justo lo que se quiere de un atajo: enseñarte lo que hay. */
export const SHORTCUTS: { key: string; send: string }[] = [
  { key: "sc.transition", send: "pon transiciones en cada corte" },
  { key: "sc.look", send: "ponle un filtro de color" },
  { key: "sc.captions", send: "ponle subtitulos" },
  { key: "sc.anim", send: "cambia la animacion de los subtitulos" },
  { key: "sc.shake", send: "ponle temblor de impacto en los cortes" },
  { key: "sc.vertical", send: "ponlo en vertical" },
  // Estos dos ya no dejan la frase a medias para que la remates con un numero:
  // se mandan enteros y el motor contesta con los tramos del montaje para que
  // señales uno. Saberse el segundo de memoria no era trabajo del usuario.
  { key: "sc.zoom", send: "haz un zoom" },
  { key: "sc.piece", send: "quita un trozo" },
  // Estos dos SI dejan la frase a medias, y es lo correcto: un rotulo sin texto
  // no es un rotulo a medio pedir, es un rotulo vacio. Lo unico que falta es lo
  // que tiene que decir, asi que se deja el cursor justo ahi.
  { key: "sc.rotulo", send: "pon un rotulo que diga " },
  { key: "sc.chapa", send: "pon una chapa que diga " },
];

/** Lo que la edicion tiene puesto ahora mismo, tal y como lo guarda el motor. */
export interface Settings {
  ratio?: string;
  transition?: string;
  captions?: boolean;
  captionPreset?: string;
  captionAnim?: string;
  cuts?: string;
  look?: string;
  shake?: boolean;
  output?: string;
}

/* Las pastillas del estado. Solo lo que esta PUESTO: una fila con "sin filtro",
   "sin temblor" y "sin transicion" no informa de nada y ocupa el doble. */
function StateRow({ now, label }: { now: Settings; label?: Props["label"] }) {
  const say = label || ((_k: string, id: string) => id);
  const bits: string[] = [];
  if (now.ratio && now.ratio !== "source") bits.push(say("ratio", now.ratio));
  if (now.cuts) bits.push(say("cuts", now.cuts));
  if (now.captions) {
    bits.push(now.captionPreset ? say("captionPreset", now.captionPreset) : "subs");
  }
  if (now.look) bits.push(say("look", now.look));
  if (now.transition && now.transition !== "none") {
    bits.push(say("transition", now.transition));
  }
  if (now.shake) bits.push("temblor");
  if (!bits.length) return null;
  return (
    <div className="chat-state">
      {bits.map((b) => <span key={b}>{b}</span>)}
    </div>
  );
}

interface Props {
  title: string;
  turns: Turn[];
  /** Los ajustes de ahora, para la fila de estado de la cabecera. */
  now?: Settings;
  /** Como se lee cada valor: lo trae el motor y lo tiene ya la ventana. */
  label?: (key: string, id: string) => string;
  /** De que proyecto de Resolve es esta conversacion. */
  scope?: string;
  /** El archivo o el timeline del ultimo resultado, y como abrirlo. */
  made?: string;
  onOpen?: (what: "file" | "folder") => void;
  draft: string;
  onDraft: (v: string) => void;
  onSend: (text?: string) => void;
  onOffer: (kind: string) => void;
  onPick: (what: string, id: string, send?: string) => void;
  onSetup: () => void;
  onNewVideo: () => void;
  onWords: () => void;
  /** Si hay un paso atras al que volver, y como se pide. */
  canUndo?: boolean;
  onUndo?: () => void;
  onStop: () => void;
  running: boolean;
  step: string;
  detail?: string;
  percent: number;
  error?: string;
}

/**
 * Seguir editando, como una conversacion.
 *
 * Antes esto era una lista numerada de las frases del propio usuario, sin una
 * sola respuesta, debajo de un tick verde que decia "Listo". O sea: hablabas y
 * no contestaba nadie, y no habia forma de saber si te habia entendido. Ahora
 * cada turno tiene sus dos lados, y el que esta en marcha ensena su progreso
 * DENTRO de su propia burbuja, que es donde se esta mirando.
 *
 * Lo que Vidorq no puede hacer se dice aqui, con el boton de la alternativa al
 * lado. Un limite que ademas te ofrece la salida deja de ser un muro.
 */
export default function Chat({
  title, turns, now, label, scope, made, onOpen, draft, onDraft, onSend, onOffer,
  onPick, onSetup, onNewVideo, onWords, canUndo, onUndo, onStop, running, step,
  detail, percent, error,
}: Props) {
  const { t } = useLang();
  const bodyRef = useRef<HTMLDivElement>(null);
  // El redactor, para poder dejar el cursor dentro cuando un atajo escribe una
  // frase a medias. Sin esto hay que ir a pulsar la caja antes de escribir, que
  // es justo el clic que el atajo venia a ahorrar.
  const askRef = useRef<HTMLInputElement>(null);

  /* Siempre al ultimo mensaje: una conversacion que se queda mirando el
     principio es una conversacion en la que no te enteras de lo que acaba de
     pasar, que es justo lo que se viene a ver.

     Se mueve el contenedor a mano y no con scrollIntoView sobre un ancla:
     la burbuja que trabaja CRECE despues (le entra el detalle, la barra, el
     boton de parar), asi que el ancla ya se habia colocado y la burbuja
     quedaba medio tapada por los atajos, con el boton de parar debajo del
     corte. Medido en pantalla el 2026-08-19. */
  useEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    const alFondo = () => { el.scrollTop = el.scrollHeight; };
    alFondo();
    // Y otra vez cuando el navegador haya pintado el alto nuevo.
    const r = requestAnimationFrame(alFondo);
    return () => cancelAnimationFrame(r);
  }, [turns.length, running, step, detail, percent]);

  return (
    <section className="chat">
      <header className="chat-head">
        <div className="chat-title">
          <img src={logo} alt="" className="chat-logo" />
          <div className="chat-who">
            <strong>{title}</strong>
            {/* De que proyecto es esta conversacion. Va aqui porque el mismo
                video en dos proyectos son dos conversaciones distintas, y sin
                verlo escrito parece que el programa se ha vuelto loco. */}
            {scope && <span className="chat-scope">{scope}</span>}
            {/* Lo que tiene puesto AHORA, de un vistazo. Sin esto habia que
                leer la conversacion hacia atras para saber si seguia en
                vertical, y con quince turnos eso no se puede hacer. */}
            {now && <StateRow now={now} label={label} />}
          </div>
        </div>
        <div className="chat-acts">
          {/* Solo cuando hay a donde volver. Un boton de deshacer que no
              deshace nada es peor que no tenerlo: se pulsa igual. */}
          {canUndo && onUndo && (
            <button className="ghost small" onClick={onUndo} disabled={running}>
              <IconUndo size={14} className="icon" />{t("chat.undo")}
            </button>
          )}
          {/* Primero, y no al final: leer el texto es la forma en que la gente
              encuentra un momento. Arrastrar el cabezal es punteria. */}
          <button className="ghost small" onClick={onWords}>
            <IconSpark size={14} className="icon" />{t("chat.words")}
          </button>
          <button className="ghost small" onClick={onSetup}>
            <IconSliders size={14} className="icon" />{t("chat.setup")}
          </button>
          <button className="ghost small" onClick={onNewVideo}>
            <IconVideo size={14} className="icon" />{t("run.again")}
          </button>
        </div>
      </header>

      <div className="chat-body" ref={bodyRef}>
        {turns.map((turn, i) => (
          <div className="turn" key={i}>
            <p className="bubble you">{turn.you}</p>

            {(turn.did?.length || turn.cannot?.length || turn.unknown?.length
              || turn.ask?.length || turn.result) && (
              <div className="bubble them">
                <img src={logo} alt="" className="bubble-logo" />
                <div className="bubble-text">
                  {turn.did && turn.did.length > 0 && (
                    <p className="done-line">
                      <IconCheck size={13} className="icon ok" />
                      {turn.did.join(" · ")}
                    </p>
                  )}
                  {turn.cannot?.map((c, k) => (
                    <p className="warn-line" key={k}>
                      <IconAlert size={13} className="icon" />{c.why}
                    </p>
                  ))}
                  {turn.unknown && turn.unknown.length > 0 && (
                    <p className="warn-line">
                      <IconAlert size={13} className="icon" />
                      {t("chat.unknown")} {turn.unknown.join("; ")}
                    </p>
                  )}
                  {turn.ask?.map((a, k) => (
                    <div className="ask" key={k}>
                      <span className="ask-q">{a.question}</span>
                      <div className="ask-opts">
                        {a.options.map((o) => (
                          <button key={o.id} className="offer small"
                                  onClick={() => onPick(a.what, o.id, o.send)}>
                            {o.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                  {turn.result && i === turns.length - 1 && (
                    made && made.startsWith("http") === false
                      && /\.(mp4|mov|mkv|webm)$/i.test(made) && onOpen ? (
                      // El momento en que el programa demuestra que funciona no
                      // puede acabar en una ruta que no se puede pulsar.
                      <div className="made">
                        <button className="offer" onClick={() => onOpen("file")}>
                          <IconPlay size={13} className="icon" />{t("chat.open")}
                        </button>
                        <button className="ghost small" onClick={() => onOpen("folder")}>
                          <IconFolder size={13} className="icon" />{t("chat.folder")}
                        </button>
                      </div>
                    ) : (
                      <code className="bubble-path">{turn.result}</code>
                    )
                  )}
                  {turn.offer?.kind === "mp4" && (
                    <button className="offer" onClick={() => onOffer("mp4")}>
                      <IconSpark size={13} className="icon" />{t("chat.offer.mp4")}
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}

        {running && (
          <div className="turn" aria-live="polite" aria-atomic="true">
            <div className="bubble them working">
              <img src={logo} alt="" className="bubble-logo" />
              <div className="bubble-text">
                <p className="done-line">{step || t("run.working")}</p>
                <div className="track"><i style={{ width: `${percent}%` }} /></div>
                {detail && <small className="under">{detail}</small>}
                {/* El boton de parar va aqui, dentro del turno que trabaja, y
                    no en una esquina: es donde ya estas mirando. */}
                <button className="stop small" onClick={onStop}>
                  <IconStop size={12} className="icon" />{t("run.stop")}
                </button>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="turn" role="alert">
            <div className="bubble them bad">
              <img src={logo} alt="" className="bubble-logo" />
              <div className="bubble-text"><p className="done-line">{error}</p></div>
            </div>
          </div>
        )}

      </div>

      <div className="chips">
        {SHORTCUTS.map((sc) => (
          <button key={sc.key} onClick={() => {
            // Los que acaban en espacio piden un numero: se dejan escritos en
            // el redactor para que solo haya que completarlos.
            if (sc.send.endsWith(" ")) {
              onDraft(sc.send);
              // Al final del texto, no al principio: lo que falta va detras.
              const el = askRef.current;
              if (el) { el.focus(); requestAnimationFrame(() =>
                el.setSelectionRange(el.value.length, el.value.length)); }
            }
            else onSend(sc.send);
          }}>{t(sc.key as never)}</button>
        ))}
      </div>

      <div className="chat-foot">
        <input
          ref={askRef}
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSend(); }}
          placeholder={t("more.ph")}
          autoFocus
        />
        {/* Mientras trabaja, lo que escribas se pone en la fila y se hace
            despues. Decirlo en el propio boton evita el "no me ha hecho nada":
            antes ponia "Aplicar" y parecia que lo aplicaba ya. */}
        <button className="cta inline" onClick={() => onSend()} disabled={!draft.trim()}>
          <IconSpark size={15} className="icon" />
          {running ? t("more.queue") : t("more.go")}
        </button>
      </div>
    </section>
  );
}
