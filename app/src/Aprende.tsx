import { useState } from "react";
import { apiGet, apiPost, BrandProfile, CaptionStyle, ENGINE } from "./api";
import { useLang } from "./i18n";
import { IconCheck } from "./Icons";

// Lo que contesta GET /aprende. Los numeros vienen medidos del video ajeno.
interface Sub {
  y: number;
  size: number;
  fill: [number, number, number] | null;
  outline: [number, number, number] | null;
  // Lo que hay detras de las letras. Es un COLOR, no una etiqueta: no se
  // puede saber si es una plancha o un contorno grueso, y esta medido.
  fondo: [number, number, number] | null;
}
interface Ritmo {
  planos: number;
  plano_tipico_s: number;
  mas_corto_s: number;
  mas_largo_s: number;
  cortes: number;
  cortes_en_golpe: number;
  planos_quietos: number;
}
interface Arranque {
  segundos: number;
  cortes: number;
  primer_plano_s: number;
}
export interface Ficha {
  ok?: boolean;
  why?: string;
  ancho: number;
  alto: number;
  duracion: number;
  vertical: boolean;
  subtitulo: Sub | null;
  ritmo: Ritmo | null;
  arranque: Arranque | null;
  parecidos?: { id: string; distancia: number }[];
}

const rgb = (c: [number, number, number] | null) =>
  c ? `rgb(${c.map((v) => Math.round(v * 255)).join(",")})` : "transparent";

export default function Aprende({ onClose, styles, video, onSaved }:
  { onClose: () => void; styles: CaptionStyle[]; video?: string;
    onSaved?: (preset: string) => void }) {
  const { t, lang } = useLang();
  const [ruta, setRuta] = useState(video ?? "");
  // La ruta que se MIRO, congelada. Las imagenes salen de esta y no de `ruta`,
  // que cambia con cada tecla.
  const [mirada, setMirada] = useState("");
  const [mirando, setMirando] = useState(false);
  const [f, setF] = useState<Ficha | null>(null);
  const [error, setError] = useState("");
  const [elegido, setElegido] = useState("");
  const [nombre, setNombre] = useState("");
  const [guardado, setGuardado] = useState(false);

  async function mirar() {
    if (!ruta.trim()) return;
    setMirando(true);
    setError("");
    setF(null);
    setElegido("");
    setGuardado(false);
    // Tambien el nombre: si no, el que se escribio para un video se queda
    // puesto al mirar el siguiente y se guarda el estilo de B con el nombre
    // de A, sin que nada lo enseñe nunca.
    setNombre("");
    try {
      const r = await apiGet<Ficha>(`/aprende?video=${encodeURIComponent(ruta.trim())}`);
      if (!r?.ok) setError(r?.why === "sin_ffmpeg" ? t("learn.noffmpeg")
                                                   : t("learn.nofile"));
      else {
        setF(r);
        setMirada(ruta.trim());
        setElegido(r.parecidos?.[0]?.id ?? "");
      }
    } catch {
      setError(t("learn.nofile"));
    }
    setMirando(false);
  }

  // Lo aprobado entra en el perfil de la marca, que es de donde ya sale el
  // estilo de cada edicion. No se inventa un sitio nuevo donde guardarlo.
  //
  // El nombre que le pone el usuario se guarda con el, y no de adorno: si se
  // pide un nombre y luego se tira, la pantalla esta prometiendo algo que no
  // cumple, que es justo el fallo que esta casa persigue. Todavia NO sale en
  // el selector de la pantalla de editar; eso es lo siguiente.
  async function guardar() {
    if (!elegido) return;
    const p = await apiGet<BrandProfile>("/profile").catch(() => ({} as BrandProfile));
    await apiPost("/profile", {
      ...p,
      captionPreset: elegido,
      captionPresetName: nombre.trim() || undefined,
    });
    // Y se le dice al panel de editar. Sin esto el estilo se guardaba en la
    // marca y no llegaba a ninguna edicion: el panel manda SIEMPRE el suyo en
    // la peticion, y lo pedido gana sobre la marca. Se guardaba de verdad y no
    // servia para nada, que es la peor version de un fallo.
    onSaved?.(elegido);
    setGuardado(true);
  }

  // Con su red: apiPost resuelve con cualquier codigo HTTP, asi que un 500
  // tambien encendia el "Guardado en tu marca"; y con el motor apagado el
  // fetch reventaba, el boton no hacia nada y no salia ningun aviso.
  async function guardarConRed() {
    setError("");
    try {
      await guardar();
    } catch {
      setError(t("learn.nosave"));
      setGuardado(false);
    }
  }

  const cap = f?.subtitulo ?? null;
  const q = encodeURIComponent(mirada);
  const nombreDe = (id: string) => styles.find((s) => s.id === id)?.label ?? id;

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{t("learn.title")}</h2>
          <p className="hint">{t("learn.sub")}</p>
        </div>

        <div className="modal-body">
          <section className="field">
            <label>{t("learn.video")}</label>
            <div className="row">
              <input
                value={ruta}
                placeholder={t("learn.video.ph")}
                onChange={(e) => setRuta(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") mirar(); }}
              />
              <button className="primary" onClick={mirar} disabled={mirando || !ruta.trim()}>
                {mirando ? t("learn.looking") : t("learn.look")}
              </button>
            </div>
            <p className="hint">{t("learn.ajeno")}</p>
            {error && <p className="warn-line">{error}</p>}
          </section>

          {f && (
            <>
              <section className="field">
                <label>{t("learn.saw")}</label>
                {f.ritmo && (
                  <p className="hint">
                    <strong>{t("learn.cuts")} {f.ritmo.plano_tipico_s} {t("learn.seconds")}</strong>
                    {" · "}{f.ritmo.planos} {t("learn.shots")}
                  </p>
                )}
                {f.arranque && (
                  <p className="hint">
                    {t("learn.start")}{" "}
                    {f.arranque.cortes > 0
                      ? <><strong>{t("learn.start.cuts")} {f.arranque.cortes}</strong>
                          {" · "}{t("learn.start.first")}{" "}
                          <strong>{f.arranque.primer_plano_s} s</strong></>
                      : <strong>{t("learn.start.cuts.none")}</strong>}
                  </p>
                )}
                {f.ritmo && f.ritmo.cortes > 0 && f.ritmo.cortes_en_golpe > 0 && (
                  <p className="hint">
                    <strong>{f.ritmo.cortes_en_golpe} {t("learn.shots.of")}{" "}
                    {f.ritmo.cortes}</strong>{" "}{t("learn.beat")}
                  </p>
                )}
                {f.ritmo && f.ritmo.planos_quietos > 0 && (
                  <p className="hint">
                    {t("learn.still")} <strong>{f.ritmo.planos_quietos}</strong>{" "}
                    {t("learn.still.of")} {f.ritmo.planos} {t("learn.shots.word")}
                  </p>
                )}
                {!cap && <p className="hint">{t("learn.nocaption")}</p>}
                {cap && (
                  <p className="hint">
                    {t("learn.pos")} <strong>{Math.round(cap.y * 100)}%</strong>
                    {cap.fill && (
                      <>
                        {" · "}{t("learn.colour")}{" "}
                        <span className="muestra" style={{
                          background: rgb(cap.fill),
                          borderColor: cap.outline ? rgb(cap.outline) : undefined,
                        }} />
                      </>
                    )}
                    {/* El color de detras se enseña sin ponerle nombre: puede
                        ser una plancha o un contorno grueso y no se puede
                        saber cual (medido, en color_de_fondo). El color si es
                        de fiar, y viendolo se decide igual. */}
                    {cap.fondo && (
                      <>
                        {" · "}{t("learn.behind")}{" "}
                        <span className="muestra"
                              style={{ background: rgb(cap.fondo) }} />
                      </>
                    )}
                  </p>
                )}
              </section>

              {cap && (
                <section className="field">
                  <label>{t("learn.offer")}</label>
                  <p className="hint">{t("learn.offer.sub")}</p>
                  {/* El suyo arriba, el nuestro debajo. Comparar mirando es lo
                      unico que desempata cuatro estilos de letra blanca que por
                      numeros son casi el mismo. */}
                  <div className="suyo">
                    <span className="tile-name">{t("learn.theirs")}</span>
                    <div className="tile-shot">
                      <img src={`${ENGINE}/aprende/captura?video=${q}&banda=1`}
                           alt={t("learn.theirs")} />
                    </div>
                  </div>
                  <span className="tile-name">{t("learn.ours")}</span>
                  <div className="grid">
                    {(f.parecidos ?? []).map((p) => (
                      <button
                        key={p.id}
                        className={`tile${elegido === p.id ? " sel" : ""}`}
                        onClick={() => { setElegido(p.id); setGuardado(false); }}
                      >
                        <div className="tile-shot">
                          {/* Apaisado a proposito, aunque el video sea
                              vertical: aqui se compara la LETRA, y en un cuadro
                              9:16 metido en una baldosa el texto sale a 85 px
                              de ancho y no se lee. El encuadre de verdad se
                              elige en la pantalla de editar, no en esta. */}
                          <img
                            src={`${ENGINE}/preview?kind=style&id=${p.id}` +
                                 `&video=${q}&lang=${lang}&ratio=wide&band=1`}
                            alt={nombreDe(p.id)} />
                          {elegido === p.id && (
                            <span className="tile-tick"><IconCheck /></span>
                          )}
                        </div>
                        <span className="tile-name">{nombreDe(p.id)}</span>
                      </button>
                    ))}
                  </div>
                </section>
              )}

              {cap && elegido && (
                <section className="field">
                  <label>{t("learn.name")}</label>
                  <div className="row">
                    <input value={nombre} placeholder={t("learn.name.ph")}
                           onChange={(e) => setNombre(e.target.value)} />
                    <button className="primary" onClick={guardarConRed} disabled={guardado}>
                      {guardado
                        ? <><IconCheck className="icon" />{t("learn.kept")}</>
                        : t("learn.keep")}
                    </button>
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
