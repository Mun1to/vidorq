import { useEffect, useMemo, useRef, useState } from "react";
import { CaptionStyle, ENGINE } from "./api";
import { useLang } from "./i18n";
import { IconCheck, IconDrop, IconPlay, IconSpark, IconVideo, IconZap } from "./Icons";

// Las que Resolve SI puede hacer por su API: son solidos con opacidad animada.
// Las otras tres necesitan mezclar los dos planos, y eso Resolve no lo da.
/**
 * La pared de estilos, como la de CapCut.
 *
 * La fila de botones con nombres sigue estando para quien ya sabe cual quiere,
 * pero "Brasa" y "Halo" no significan nada hasta que se ven. Aqui cada baldosa
 * es un fotograma de VERDAD sobre el metraje del usuario, hecho por el mismo
 * renderizador que hace el video final: mismo ASS, mismo recorte, mismo
 * detector de caras. Dibujarlas en CSS seria mas rapido y mentiria.
 *
 * Las dos pestanas son dos elecciones distintas y por eso se ensenan distinto:
 * el LOOK es una foto, porque un look es un look; el MOVIMIENTO es un bucle
 * animado, porque el fotograma en reposo de "Rebote" es identico al de
 * "Ninguna" y ensenarlo quieto es prometer algo que no se ve.
 */
type Tab = "style" | "anim" | "look" | "ratio" | "transition" | "card";

export default function Gallery({
  styles, anims, animOf, style, anim, ratio, video, colours, colour,
  ratios, transitions, resolveTrans, transition, onRatio, onTransition,
  cards, onCard,
  onStyle, onAnim, onColour, onClose,
}: {
  styles: CaptionStyle[];
  anims: CaptionStyle[];
  animOf: Record<string, string>;
  style: string;
  anim: string;
  ratio: string;
  video: string;
  colours: CaptionStyle[];
  colour: string;
  ratios: Record<string, string>;
  transitions: Record<string, string>;
  /* Cuales sabe hacer Resolve. Viene del motor y no escrito aqui: estaba
     copiado a mano en este fichero y en App.tsx, y las dos copias ya se habian
     separado (esta contaba el destello y la otra no). */
  resolveTrans: string[];
  transition: string;
  onRatio: (id: string) => void;
  onTransition: (id: string) => void;
  cards: CaptionStyle[];
  onCard: (id: string) => void;
  onStyle: (id: string) => void;
  onAnim: (id: string) => void;
  onColour: (id: string) => void;
  onClose: () => void;
}) {
  const { t, lang } = useLang();
  const boxRef = useRef<HTMLDivElement>(null);

  /* Al abrir, el foco entra en la galeria; al cerrar, vuelve a donde estaba.
     Medido: se quedaba en el boton de detras, asi que quien navega con teclado
     abria la galeria y seguia tabulando por una pantalla que ya no puede ver. */
  useEffect(() => {
    const antes = document.activeElement as HTMLElement | null;
    boxRef.current?.focus();
    return () => antes?.focus?.();
  }, []);
  const [tab, setTab] = useState<Tab>("style");
  // Cuales han terminado de cargar. Sin esto la cuadricula aparece a trozos y
  // parece rota; con esto cada hueco tiene su latido hasta que llega su imagen.
  const [ready, setReady] = useState<Record<string, boolean>>({});

  // Escapar cierra. Un modal a pantalla casi completa sin salida de teclado es
  // una trampa para quien no usa el raton.
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  // Al cambiar de pestana o de estilo base, las baldosas de movimiento son
  // otras: se pintan sobre el look elegido.
  useEffect(() => { setReady({}); }, [tab, style, ratio, video]);
  const gridClass = (tab === "look" || tab === "ratio" || tab === "card")
    ? "grid full" : "grid";

  const url = useMemo(() => (kind: Tab, id: string) => {
    // band=1: la baldosa es un primer plano de la banda del subtitulo. El
    // fotograma entero lo ensena la preview de abajo, que responde a otra
    // pregunta; aqui se comparan letras y a tamano de baldosa un estilo fino
    // sobre el cuadro completo no se ve.
    // El color se juzga sobre el cuadro ENTERO, no sobre la banda del
    // subtitulo: lo que hay que ver es la piel y el cielo, no las letras.
    // La pestaña de formato pide el cuadro con ESE encuadre, no con el actual.
    const q = new URLSearchParams({ ratio: kind === "ratio" ? id : ratio,
                                    lang, video, kind });
    // Un rotulo tampoco se recorta a la banda: lo que hay que ver es DONDE cae
    // en el cuadro, y la banda esconde justo eso. Una transicion, menos aun:
    // pasa por todo el cuadro, y recortada a la franja del subtitulo no se
    // distingue de la de al lado.
    if (kind !== "look" && kind !== "ratio" && kind !== "card"
        && kind !== "transition") q.set("band", "1");
    if (kind === "anim") { q.set("id", id); q.set("preset", style); }
    else q.set("id", id);
    return `${ENGINE}/preview?${q.toString()}`;
  }, [ratio, lang, video, style]);

  // En movimiento, "la del estilo" va primero y es la opcion por defecto: es la
  // que el autor del look eligio para el, y casi siempre es la buena.
  const own = anims.find((a) => a.id === animOf[style]);
  const items: { id: string; label: string; note: string; pick: string }[] =
    tab === "card"
      ? cards.map((c) => ({ ...c, pick: c.id }))
      : tab === "ratio"
      ? Object.entries(ratios).map(([id, label]) => ({
          id, label, note: t("gal.ratio.sub"), pick: id }))
      : tab === "transition"
      ? Object.entries(transitions).filter(([id]) => id !== "none")
          .map(([id, label]) => ({
            id, label,
            // Lo unico que hace falta saber para elegir una: donde funciona.
            note: resolveTrans.includes(id) ? t("gal.tr.both") : t("gal.tr.mp4"),
            pick: id }))
      : tab === "look"
      ? colours.map((c) => ({ ...c, pick: c.id }))
      : tab === "style"
      ? styles.map((s) => ({ ...s, pick: s.id }))
      : [{ id: animOf[style] || "pop",
           label: t("captions.anim.own") + (own ? ` · ${own.label}` : ""),
           note: t("captions.anim.ownNote"), pick: "" },
         ...anims.map((a) => ({ ...a, pick: a.id }))];

  // Un efecto no es un ajuste puesto: no hay ninguno "elegido" que marcar.
  const chosen = tab === "card" ? ""
    : tab === "look" ? (colour || "none")
    : tab === "ratio" ? ratio
    : tab === "transition" ? transition
    : tab === "style" ? style : anim;

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal gallery" ref={boxRef} role="dialog" aria-modal="true"
           tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{t("gal.title")}</h2>
          <div className="opt out inline">
            <button className={tab === "style" ? "sel" : ""} onClick={() => setTab("style")}>
              <IconSpark size={14} className="icon" />{t("gal.looks")}
            </button>
            <button className={tab === "anim" ? "sel" : ""} onClick={() => setTab("anim")}>
              <IconPlay size={14} className="icon" />{t("gal.moves")}
            </button>
            <button className={tab === "look" ? "sel" : ""} onClick={() => setTab("look")}>
              <IconDrop size={14} className="icon" />{t("gal.looks.tab")}
            </button>
            <button className={tab === "ratio" ? "sel" : ""} onClick={() => setTab("ratio")}>
              <IconVideo size={14} className="icon" />{t("gal.ratio")}
            </button>
            <button className={tab === "transition" ? "sel" : ""}
                    onClick={() => setTab("transition")}>
              <IconZap size={14} className="icon" />{t("gal.tr")}
            </button>
            <button className={tab === "card" ? "sel" : ""} onClick={() => setTab("card")}>
              <IconSpark size={14} className="icon" />{t("gal.card")}
            </button>
          </div>
        </div>

        <div className="modal-body">
          <p className="hint">
            {tab === "card" ? t("gal.card.hint")
              : tab === "look" ? t("gal.colour.sub")
              : tab === "ratio" ? t("gal.ratio.hint")
              : tab === "transition" ? t("gal.tr.hint")
              : tab === "style" ? t("gal.looks.sub") : t("gal.moves.sub")}
          </p>
          <div className={gridClass}>
            {items.map((it, i) => {
              const key = `${tab}-${it.pick}-${i}`;
              const sel = it.pick === chosen;
              return (
                <button
                  key={key}
                  className={`tile ${sel ? "sel" : ""}`}
                  onClick={() => (tab === "card" ? onCard(it.pick)
                    : tab === "look" ? onColour(it.pick)
                    : tab === "ratio" ? onRatio(it.pick)
                    : tab === "transition" ? onTransition(it.pick)
                    : tab === "style" ? onStyle(it.pick) : onAnim(it.pick))}
                  title={it.note}
                >
                  {/* La transicion tambien se ve. Antes era una caja vacia con
                      la etiqueta flotando en medio, con el argumento de que una
                      foto fija no enseña movimiento; pero su MITAD si dice lo
                      que hace, que es lo que hay que decidir: si mezcla los dos
                      planos, si pasa por negro, o si uno empuja al otro. La
                      etiqueta de donde funciona se queda, en una esquina. */}
                  <div className={`tile-shot ${ready[key] ? "" : "loading"}`}>
                    <img
                      src={url(tab, it.id)}
                      alt=""
                      loading="lazy"
                      onLoad={() => setReady((r) => ({ ...r, [key]: true }))}
                      onError={() => setReady((r) => ({ ...r, [key]: true }))}
                    />
                    {tab === "transition" && (
                      <span className={`tile-where ${resolveTrans.includes(it.id) ? "ok" : "only"}`}>
                        {resolveTrans.includes(it.id) ? t("gal.tr.both") : t("gal.tr.mp4")}
                      </span>
                    )}
                    {sel && <span className="tile-tick"><IconCheck size={13} /></span>}
                  </div>
                  <span className="tile-name">{it.label}</span>
                </button>
              );
            })}
          </div>
          <small className="under">{t("gal.note")}</small>
        </div>

        <div className="modal-foot">
          <button className="cta" onClick={onClose}>{t("gal.done")}</button>
        </div>
      </div>
    </div>
  );
}
