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

// Un tramo del montaje: lo que se mueve de sitio. `from`/`to` son segundos del
// MONTAJE, que es el reloj de lo que se esta viendo.
type Tramo = { i: number; from: number; to: number; text: string };

export default function Words({
  video, onSend, onOrder, onClose,
}: {
  video: string;
  onSend: (text: string) => void;
  onOrder: (order: number[]) => void;
  onClose: () => void;
}) {
  const { t } = useLang();
  const [words, setWords] = useState<Word[] | null>(null);
  const [why, setWhy] = useState("");
  // Los dos extremos de la seleccion, por indice de palabra. `b` es null
  // mientras solo se ha marcado el principio.
  const [a, setA] = useState<number | null>(null);
  const [b, setB] = useState<number | null>(null);
  const [busca, setBusca] = useState("");
  // Dos maneras de leer lo mismo. Las palabras sirven para QUITAR un trozo; los
  // tramos, para MOVERLO de sitio, que es la otra mitad de editar leyendo.
  const [modo, setModo] = useState<"palabras" | "orden">("palabras");
  const [tramos, setTramos] = useState<Tramo[] | null>(null);
  const [orden, setOrden] = useState<number[]>([]);
  const [arrastra, setArrastra] = useState<number | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const cuerpoRef = useRef<HTMLDivElement>(null);

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

  // Los tramos se piden al entrar en el modo, no al abrir el panel: quien viene
  // a buscar una palabra no paga la llamada.
  useEffect(() => {
    if (modo !== "orden" || tramos !== null) return;
    let vivo = true;
    fetch(`${ENGINE}/tramos?video=${encodeURIComponent(video)}`)
      .then((r) => r.json())
      .then((d) => {
        if (!vivo) return;
        const lista = (d.tramos || []) as Tramo[];
        setTramos(lista);
        setOrden(lista.map((x) => x.i));
        if (!d.ok) setWhy(d.why || "no_edit");
      })
      .catch(() => { if (vivo) { setTramos([]); setWhy("no_engine"); } });
    return () => { vivo = false; };
  }, [modo, tramos, video]);

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
    // Y el cabezal de Resolve se va ahi. Esto es lo que una web no puede hacer
    // y Vidorq si, porque corre DENTRO de Resolve: pulsas una palabra y ves el
    // fotograma. Sin Resolve delante no pasa nada y no se dice nada, porque en
    // el MP4 no hay cabezal que mover.
    const t = words?.[i].t;
    if (t !== null && t !== undefined) {
      fetch(`${ENGINE}/seek`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ at: t }),
      }).catch(() => { /* sin Resolve, sin cabezal */ });
    }
  }

  // Buscar es lo que convierte mil palabras en algo usable: nadie encuentra
  // "el trozo del precio" bajando con la rueda. Se marcan todas las que pegan y
  // se sube la primera a la vista.
  const pega = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q || !words) return null;
    const hits = new Set<number>();
    words.forEach((x, i) => { if (x.w.toLowerCase().includes(q)) hits.add(i); });
    return hits;
  }, [busca, words]);

  useEffect(() => {
    if (!pega || pega.size === 0) return;
    const primera = Math.min(...pega);
    const el = cuerpoRef.current?.querySelector(`[data-i="${primera}"]`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [pega]);

  const porIndice = useMemo(() => {
    const m = new Map<number, Tramo>();
    (tramos || []).forEach((x) => m.set(x.i, x));
    return m;
  }, [tramos]);

  const cambiado = useMemo(
    () => orden.some((x, i) => x !== i), [orden]);

  /** Saca el tramo de `desde` y lo mete en `hasta`. Lo demas se corre. */
  function mueve(desde: number, hasta: number) {
    if (desde === hasta || hasta < 0 || hasta >= orden.length) return;
    const nuevo = orden.slice();
    const [x] = nuevo.splice(desde, 1);
    nuevo.splice(hasta, 0, x);
    setOrden(nuevo);
  }

  // Pulsar un tramo lleva el cabezal de Resolve a donde EMPIEZA hoy, no a donde
  // acabara: el montaje que hay delante todavia es el de antes de moverlo.
  function ve(t: Tramo) {
    fetch(`${ENGINE}/seek`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ at: t.from }),
    }).catch(() => { /* sin Resolve, sin cabezal */ });
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
          {/* Las pestañas y el buscador en la MISMA fila. La cabecera del modal
              apila en columna, asi que el buscador con `margin-left: auto` se
              iba a su propio renglon y dejaba un hueco de aire debajo de las
              pestañas. */}
          <div className="head-row">
            <div className="tabs2">
              <button className={modo === "palabras" ? "sel" : ""}
                      onClick={() => setModo("palabras")}>{t("words.tabWords")}</button>
              <button className={modo === "orden" ? "sel" : ""}
                      onClick={() => setModo("orden")}>{t("words.tabOrder")}</button>
            </div>
            {modo === "palabras" && (
              <input className="find" value={busca} placeholder={t("words.find")}
                     onChange={(e) => setBusca(e.target.value)} />
            )}
            {modo === "palabras" && span && (
              <button className="link" onClick={() => { setA(null); setB(null); }}>
                {t("words.clear")}
              </button>
            )}
          </div>
        </div>

        {modo === "orden" ? (
        <div className="modal-body">
          <p className="hint">{t("words.orderHint")}</p>
          {tramos === null && <p className="hint">{t("words.loading")}</p>}
          {tramos !== null && tramos.length === 0 && (
            <p className="hint">{why === "no_edit" ? t("words.noEdit") : t("words.off")}</p>
          )}
          <ol className="tramos">
            {orden.map((id, pos) => {
              const x = porIndice.get(id);
              if (!x) return null;
              return (
                <li key={id}
                    className={`tramo${arrastra === pos ? " lifting" : ""}`}
                    draggable
                    onDragStart={() => setArrastra(pos)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      if (arrastra !== null) mueve(arrastra, pos);
                      setArrastra(null);
                    }}
                    onDragEnd={() => setArrastra(null)}>
                  <span className="tramo-n">{pos + 1}</span>
                  <button className="tramo-say" onClick={() => ve(x)}
                          title={`${clock(x.from)} - ${clock(x.to)}`}>
                    <span className="tramo-when">
                      {clock(x.from)} · {Math.round(x.to - x.from)}s
                    </span>
                    <span className="tramo-text">{x.text || t("words.silent")}</span>
                  </button>
                  {/* Con teclado y dictando por voz no se arrastra nada, asi que
                      las dos flechas no son un extra: son la forma normal. */}
                  <span className="tramo-move">
                    <button disabled={pos === 0} aria-label={t("words.up")}
                            onClick={() => mueve(pos, pos - 1)}>↑</button>
                    <button disabled={pos === orden.length - 1} aria-label={t("words.down")}
                            onClick={() => mueve(pos, pos + 1)}>↓</button>
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
        ) : (
        <div className="modal-body" ref={cuerpoRef}>
          <p className="hint">
            {t("words.hint")}
            {pega && <b className="hits"> {pega.size} {t("words.hits")}</b>}
          </p>
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
              const hit = pega?.has(i) ? " hit" : "";
              return (
                <button key={i} data-i={i}
                        className={`w${dentro ? " sel" : ""}${fuera ? " out" : ""}${hit}`}
                        title={clock(x.t === null ? x.s : x.t)}
                        aria-pressed={dentro} onClick={() => pulsa(i)}>
                  {x.w}{" "}
                </button>
              );
            })}
          </p>
        </div>
        )}

        <div className="modal-foot words-foot">
          {modo === "orden" ? (
            <>
              <span className="span-say">
                {cambiado ? t("words.orderChanged") : t("words.orderSame")}
              </span>
              {cambiado && (
                <button onClick={() => setOrden((tramos || []).map((x) => x.i))}>
                  {t("words.orderReset")}
                </button>
              )}
              <button className="cta" disabled={!cambiado}
                      onClick={() => { onOrder(orden); onClose(); }}>
                <IconSpark size={15} className="icon" />{t("words.orderApply")}
              </button>
            </>
          ) : span ? (
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
