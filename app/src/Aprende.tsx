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
  panel: [number, number, number] | null;
}
interface Ritmo {
  planos: number;
  plano_tipico_s: number;
  mas_corto_s: number;
  mas_largo_s: number;
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
  parecidos?: { id: string; distancia: number }[];
}

const rgb = (c: [number, number, number] | null) =>
  c ? `rgb(${c.map((v) => Math.round(v * 255)).join(",")})` : "transparent";

export default function Aprende({ onClose, styles, video }:
  { onClose: () => void; styles: CaptionStyle[]; video?: string }) {
  const { t, lang } = useLang();
  const [ruta, setRuta] = useState(video ?? "");
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
    try {
      const r = await apiGet<Ficha>(`/aprende?video=${encodeURIComponent(ruta.trim())}`);
      if (!r?.ok) setError(t("learn.nofile"));
      else {
        setF(r);
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
    setGuardado(true);
  }

  const cap = f?.subtitulo ?? null;
  const q = encodeURIComponent(ruta.trim());
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
                onDrop={(e) => {
                  e.preventDefault();
                  const file = e.dataTransfer.files?.[0] as (File & { path?: string });
                  if (file?.path) setRuta(file.path);
                }}
                onDragOver={(e) => e.preventDefault()}
              />
              <button className="primary" onClick={mirar} disabled={mirando || !ruta.trim()}>
                {mirando ? t("learn.looking") : t("learn.look")}
              </button>
            </div>
            <p className="hint">{t("learn.ajeno")}</p>
            {error && <p className="hint warn">{error}</p>}
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
                    <button className="primary" onClick={guardar} disabled={guardado}>
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
