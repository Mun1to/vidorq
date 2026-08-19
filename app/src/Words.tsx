import { useEffect, useMemo, useRef, useState } from "react";
import { ENGINE } from "./api";
import { useLang } from "./i18n";
import { IconScissors, IconSpark, IconZap } from "./Icons";

/**
 * Editar leyendo, que es la forma en que la gente edita de verdad.
 *
 * Buscar un momento arrastrando el cabezal es punteria; buscarlo leyendo es
 * lectura, y todo el mundo sabe leer. Es lo que hace que Descript se pague, y
 * aqui sale casi gratis porque la mitad cara ya estaba hecha: la transcripcion
 * de Vidorq trae el segundo de CADA palabra.
 *
 * Lo que no hace, a proposito: no borra nada por su cuenta. Marcar dos palabras
 * escribe la MISMA frase que se podria teclear ("quita un trozo del segundo 12
 * al 19") y la manda por el mismo camino que todo lo demas. Un segundo
 * mecanismo de corte seria un segundo sitio donde equivocarse, y este ya esta
 * medido.
 */
// `s`/`e` son del video original; `t` es el mismo instante en el MONTAJE, que
// es el reloj con el que hay que hablarle al motor una vez hay una edicion
// hecha. `t` es null cuando esa palabra ya no esta en el montaje.
type Word = { w: string; s: number; e: number; t: number | null };

function clock(t: number) {
  const s = Math.floor(t % 60);
  return `${Math.floor(t / 60)}:${s < 10 ? "0" : ""}${s}`;
}

export default function Words({
  video, onSend, onClose,
}: {
  video: string;
  onSend: (text: string) => void;
  onClose: () => void;
}) {
  const { t } = useLang();
  const [words, setWords] = useState<Word[] | null>(null);
  const [why, setWhy] = useState("");
  // Los dos extremos de la seleccion, por indice de palabra. `b` es null
  // mientras solo se ha marcado el principio.
  const [a, setA] = useState<number | null>(null);
  const [b, setB] = useState<number | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let vivo = true;
    fetch(`${ENGINE}/words?video=${encodeURIComponent(video)}`)
      .then((r) => r.json())
      .then((d) => {
        if (!vivo) return;
        if (d.ok) setWords(d.words as Word[]);
        else { setWords([]); setWhy(d.why || "no_transcript"); }
      })
      .catch(() => { if (vivo) { setWords([]); setWhy("no_engine"); } });
    return () => { vivo = false; };
  }, [video]);

  // El foco entra en el dialogo al abrirlo y Escape lo cierra, como los demas.
  useEffect(() => {
    boxRef.current?.focus();
    const esc = (ev: KeyboardEvent) => { if (ev.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  const [ini, fin] = useMemo(() => {
    if (a === null) return [null, null] as [number | null, number | null];
    if (b === null) return [a, a] as [number, number];
    return [Math.min(a, b), Math.max(a, b)] as [number, number];
  }, [a, b]);

  const span = useMemo(() => {
    if (!words || ini === null || fin === null) return null;
    const a0 = words[ini], b0 = words[fin];
    if (a0.t === null || b0.t === null) return null;
    const desde = Math.floor(a0.t);
    // El final se redondea hacia arriba: cortar en mitad de la ultima palabra
    // la deja a medias, y una palabra partida se oye como un fallo.
    const hasta = Math.ceil(b0.t + (b0.e - b0.s));
    return { desde, hasta: Math.max(desde + 1, hasta) };
  }, [words, ini, fin]);

  function pulsa(i: number) {
    // Una palabra que ya no esta en el montaje no puede ser un extremo: no
    // tiene segundo al que apuntar.
    if (words && words[i].t === null) return;
    if (a === null || b !== null) { setA(i); setB(null); }
    else setB(i);
  }

  function manda(verbo: string) {
    if (!span) return;
    onSend(`${verbo} del segundo ${span.desde} al ${span.hasta}`);
    onClose();
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal words" ref={boxRef} role="dialog" aria-modal="true"
           tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{t("words.title")}</h2>
          {span && (
            <button className="link" onClick={() => { setA(null); setB(null); }}>
              {t("words.clear")}
            </button>
          )}
        </div>

        <div className="modal-body">
          <p className="hint">{t("words.hint")}</p>
          {words === null && <p className="hint">{t("words.loading")}</p>}
          {words !== null && words.length === 0 && (
            <p className="hint">{why === "no_transcript" ? t("words.none") : t("words.off")}</p>
          )}
          <p className="wordbox">
            {(words || []).map((x, i) => {
              const dentro = ini !== null && fin !== null && i >= ini && i <= fin;
              const fuera = x.t === null;
              // El espacio va DENTRO del boton para que dos palabras marcadas
              // seguidas se vean como un trozo y no como dos cromos sueltos.
              return (
                <button key={i} className={`w${dentro ? " sel" : ""}${fuera ? " out" : ""}`}
                        title={clock(x.t === null ? x.s : x.t)}
                        aria-pressed={dentro} onClick={() => pulsa(i)}>
                  {x.w}{" "}
                </button>
              );
            })}
          </p>
        </div>

        <div className="modal-foot words-foot">
          {span ? (
            <>
              {/* El tramo se dice con reloj y con segundos: el reloj es para
                  reconocerlo en el video, los segundos son lo que se manda. */}
              <span className="span-say">
                {clock(span.desde)} - {clock(span.hasta)}
                <em>{span.hasta - span.desde}s</em>
              </span>
              <button onClick={() => manda("quedate solo")}>
                <IconScissors size={15} className="icon" />{t("words.keep")}
              </button>
              <button onClick={() => manda("haz un zoom")}>
                <IconZap size={15} className="icon" />{t("words.zoom")}
              </button>
              <button className="cta" onClick={() => manda("quita un trozo")}>
                <IconSpark size={15} className="icon" />{t("words.drop")}
              </button>
            </>
          ) : (
            <button className="cta" onClick={onClose}>{t("gal.done")}</button>
          )}
        </div>
      </div>
    </div>
  );
}
