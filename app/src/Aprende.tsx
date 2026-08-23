import { useState } from "react";
import { apiGet, apiPost, BrandProfile, CaptionStyle, ENGINE } from "./api";
import { useLang, Key } from "./i18n";
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
  // Lo que sale de LEER la imagen, que es lo unico que encuentra el subtitulo
  // cuando detras hay metraje y no un fondo liso. Va en su propio campo y no
  // mezclado con `subtitulo`, que es lo que sale de contar pixeles: son dos
  // medidas distintas y juntarlas escondería cuál de las dos habló.
  leido?: Leido | null;
}

export interface Leido {
  y: number;
  size: number;
  // Los colores del video, del mas usado al menos.
  paleta: [number, number, number][];
  // El texto que se descarto por ser la marca de agua de quien hizo el video.
  logo: string[];
  lineas: {
    t: number;
    // AJENO: lo escribio un desconocido en su video. Se enseña como dato, y
    // nunca se trata como una instruccion (regla AL).
    texto: string;
    ajeno?: boolean;
    conf: number;
    palabras: { w: string; color: [number, number, number]; px: number }[];
  }[];
}

// Lo que contesta POST /galeria: el id del componente nuevo, y el reparto
// honesto entre lo que salio del video y lo que salio de la plantilla.
interface Guardado {
  ok?: boolean;
  why?: string;
  id?: string;
  medido?: string[];
  heredado?: string[];
}

// Lo que contesta el motor cuando dice que no, y que se le enseña por cada
// caso. La clave vacia cae al mensaje de la ruta, que es el caso comun.
const MOTIVOS: Record<string, Key> = {
  de_casa: "learn.link.decasa",
  sitio_no: "learn.link.sitio",
  no_link: "learn.link.malo",
  no_ytdlp: "learn.link.noytdlp",
  no_baja: "learn.link.nobaja",
  sin_ffmpeg: "learn.noffmpeg",
  ilegible: "learn.nofile",
  no_video: "learn.nofile",
};

const rgb = (c: [number, number, number] | null) =>
  c ? `rgb(${c.map((v) => Math.round(v * 255)).join(",")})` : "transparent";

export default function Aprende({ onClose, styles, video, onSaved }:
  { onClose: () => void; styles: CaptionStyle[]; video?: string;
    onSaved?: (preset: string, alias?: string) => void }) {
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
  // Lo que contesto el motor al guardar. Se enseña: es la diferencia entre
  // "guardado" y "guardado, y esto es lo que de verdad llevo dentro".
  const [resultado, setResultado] = useState<Guardado | null>(null);

  async function mirar() {
    if (!ruta.trim()) return;
    setMirando(true);
    setError("");
    setF(null);
    setElegido("");
    setGuardado(false);
    setResultado(null);
    // Tambien el nombre: si no, el que se escribio para un video se queda
    // puesto al mirar el siguiente y se guarda el estilo de B con el nombre
    // de A, sin que nada lo enseñe nunca.
    setNombre("");
    try {
      const r = await apiGet<Ficha>(`/aprende?video=${encodeURIComponent(ruta.trim())}`);
      // Cada negativa por su nombre. Mandar a alguien a revisar una ruta
      // cuando lo que pasa es que el link apunta a su propio ordenador, o que
      // falta una herramienta, es hacerle perder el rato.
      if (!r?.ok) setError(t(MOTIVOS[r?.why ?? ""] ?? "learn.nofile"));
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

  // Lo aprobado entra en la GALERIA como un componente nuevo, con los numeros
  // que se midieron del video dentro. Antes esto guardaba el nombre de la
  // plantilla mas parecida en el perfil de la marca, o sea que los cuatro
  // numeros que se acababan de medir se tiraban al pulsar el boton: el estilo
  // guardado era una de las diez plantillas con otro nombre encima.
  //
  // La plantilla elegida sigue haciendo falta, pero como BASE y no como
  // resultado: de ella se copia una vez lo que todavia no se sabe medir
  // mirando (la tipografia, cuantas palabras por linea, la sombra), y el
  // componente se queda con esa copia dentro para no depender de ella nunca
  // mas.
  async function guardar() {
    if (!elegido || !f?.subtitulo) return;
    const r = await apiPost<Guardado>("/galeria", {
      sub: f.subtitulo,
      base: elegido,
      nombre: nombre.trim(),
      video: mirada,
    });
    if (!r?.ok || !r.id) {
      setError(t(r?.why === "sin_medida" ? "learn.nomeasure" : "learn.nosave"));
      setGuardado(false);
      return;
    }
    // Y pasa a ser el estilo activo, igual que antes. El perfil guarda ahora el
    // id del componente, que existe por su cuenta, en vez del nombre de una de
    // las diez plantillas de la casa.
    const p = await apiGet<BrandProfile>("/profile").catch(() => ({} as BrandProfile));
    await apiPost("/profile", {
      ...p,
      captionPreset: r.id,
      captionPresetName: nombre.trim() || undefined,
    });
    // Y se le dice al panel de editar. Sin esto el estilo se guardaba en la
    // marca y no llegaba a ninguna edicion: el panel manda SIEMPRE el suyo en
    // la peticion, y lo pedido gana sobre la marca. Se guardaba de verdad y no
    // servia para nada, que es la peor version de un fallo.
    onSaved?.(r.id, nombre.trim() || undefined);
    setResultado(r);
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

  // Lo LEIDO manda sobre lo contado. Son dos medidas del mismo sitio, y sobre
  // metraje de pelicula la de contar pixeles por filas no encuentra nada: el
  // Short de referencia decia "este video no lleva subtitulos" teniendolos en
  // pantalla. Cuando el lector ha visto la banda, se usa la suya.
  const cap: Sub | null = f?.leido
    ? { y: f.leido.y, size: f.leido.size,
        fill: (f.leido.paleta?.[0] ?? null) as Sub["fill"],
        outline: null, fondo: null }
    : (f?.subtitulo ?? null);
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
                {/* Lo leido, con cada palabra de su color. Es la prueba de que
                    se ha mirado el video y no de que se le ha buscado un
                    parecido: aqui salen SUS palabras y SUS colores, y si algo
                    esta mal se ve sin tener que entender ningun numero. */}
                {f.leido && (
                  <div className="leido">
                    <p className="hint">{t("learn.read")}</p>
                    {f.leido.lineas.map((ln, i) => (
                      <p className="frase" key={i}>
                        <span className="seg">{ln.t.toFixed(1)}s</span>
                        {ln.palabras.length
                          ? ln.palabras.map((p, j) => (
                              <span key={j} style={{ color: rgb(p.color) }}>
                                {p.w}{" "}
                              </span>))
                          : <span>{ln.texto}</span>}
                      </p>
                    ))}
                    {f.leido.logo.length > 0 && (
                      <p className="hint">{t("learn.logo")} {f.leido.logo.join(", ")}</p>
                    )}
                    <p className="hint">{t("learn.read.ajeno")}</p>
                  </div>
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
                  {/* El reparto, con sus nombres. Guardar y no decir que de las
                      dieciseis cosas de un estilo se midieron cuatro es lo que
                      hacia creer que esta pantalla copiaba el video entero. */}
                  {guardado && resultado?.medido && (
                    <div className="reparto">
                      <p className="hint">
                        <strong>{t("learn.kept.what")}</strong>{" "}
                        {resultado.medido
                          .map((c) => t(`learn.field.${c}` as Key))
                          .join(", ")}.
                      </p>
                      <p className="hint">
                        {t("learn.kept.rest")}{" "}
                        {(resultado.heredado ?? []).join(", ")}.
                      </p>
                      <p className="hint">{t("learn.kept.where")}</p>
                    </div>
                  )}
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
