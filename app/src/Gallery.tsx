import { useEffect, useMemo, useState } from "react";
import { CaptionStyle, ENGINE } from "./api";
import { useLang } from "./i18n";
import { IconCheck, IconDrop, IconPlay, IconSpark } from "./Icons";

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
export default function Gallery({
  styles, anims, animOf, style, anim, ratio, video, colours, colour,
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
  onStyle: (id: string) => void;
  onAnim: (id: string) => void;
  onColour: (id: string) => void;
  onClose: () => void;
}) {
  const { t, lang } = useLang();
  const [tab, setTab] = useState<"style" | "anim" | "look">("style");
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
  const gridClass = tab === "look" ? "grid full" : "grid";

  const url = useMemo(() => (kind: "style" | "anim" | "look", id: string) => {
    // band=1: la baldosa es un primer plano de la banda del subtitulo. El
    // fotograma entero lo ensena la preview de abajo, que responde a otra
    // pregunta; aqui se comparan letras y a tamano de baldosa un estilo fino
    // sobre el cuadro completo no se ve.
    // El color se juzga sobre el cuadro ENTERO, no sobre la banda del
    // subtitulo: lo que hay que ver es la piel y el cielo, no las letras.
    const q = new URLSearchParams({ ratio, lang, video, kind });
    if (kind !== "look") q.set("band", "1");
    if (kind === "anim") { q.set("id", id); q.set("preset", style); }
    else q.set("id", id);
    return `${ENGINE}/preview?${q.toString()}`;
  }, [ratio, lang, video, style]);

  // En movimiento, "la del estilo" va primero y es la opcion por defecto: es la
  // que el autor del look eligio para el, y casi siempre es la buena.
  const own = anims.find((a) => a.id === animOf[style]);
  const items: { id: string; label: string; note: string; pick: string }[] =
    tab === "look"
      ? colours.map((c) => ({ ...c, pick: c.id }))
      : tab === "style"
      ? styles.map((s) => ({ ...s, pick: s.id }))
      : [{ id: animOf[style] || "pop",
           label: t("captions.anim.own") + (own ? ` · ${own.label}` : ""),
           note: t("captions.anim.ownNote"), pick: "" },
         ...anims.map((a) => ({ ...a, pick: a.id }))];

  const chosen = tab === "look" ? (colour || "none")
    : tab === "style" ? style : anim;

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal gallery" onClick={(e) => e.stopPropagation()}>
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
          </div>
        </div>

        <div className="modal-body">
          <p className="hint">
            {tab === "look" ? t("gal.colour.sub")
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
                  onClick={() => (tab === "look" ? onColour(it.pick)
                    : tab === "style" ? onStyle(it.pick) : onAnim(it.pick))}
                  title={it.note}
                >
                  <div className={`tile-shot ${ready[key] ? "" : "loading"}`}>
                    <img
                      src={url(tab, it.id)}
                      alt=""
                      loading="lazy"
                      onLoad={() => setReady((r) => ({ ...r, [key]: true }))}
                      onError={() => setReady((r) => ({ ...r, [key]: true }))}
                    />
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
