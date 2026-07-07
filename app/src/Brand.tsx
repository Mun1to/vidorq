import { useEffect, useState } from "react";
import { apiGet, apiPost, BrandProfile } from "./api";

const VIBES = ["cercano", "premium", "enérgico", "calmado", "técnico", "divertido"];

export default function Brand({ onClose }: { onClose: () => void }) {
  const [p, setP] = useState<BrandProfile>({
    vibes: [], references: ["", "", ""], pace: 6,
    color1: "#6c5ce7", color2: "#b06ab3", captionStyle: "hormozi",
  });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiGet<BrandProfile>("/profile").then((prof) => {
      if (prof && Object.keys(prof).length) {
        setP({ references: ["", "", ""], vibes: [], ...prof });
      }
    }).catch(() => {});
  }, []);

  const set = (k: keyof BrandProfile, v: unknown) => setP((old) => ({ ...old, [k]: v }));
  const toggleVibe = (v: string) =>
    set("vibes", p.vibes?.includes(v) ? p.vibes.filter((x) => x !== v) : [...(p.vibes ?? []), v]);

  async function save() {
    await apiPost("/profile", p);
    setSaved(true);
    setTimeout(onClose, 700);
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <h2>🎨 Tu marca, tu estilo</h2>
        <p className="hint">Vidorq usa este perfil para que cada edición sea tuya y de nadie más. Se guarda en el workspace activo.</p>

        <label>¿Cómo se llama tu marca o canal?</label>
        <input value={p.brandName ?? ""} onChange={(e) => set("brandName", e.target.value)}
               placeholder="Ej: Orquio, MiCanal..." />

        <label>¿Qué haces y para quién?</label>
        <textarea value={p.about ?? ""} onChange={(e) => set("about", e.target.value)}
                  placeholder="Ej: enseño herramientas de IA a emprendedores que empiezan..." />

        <label>¿Qué sensación debe dejar tu contenido?</label>
        <div className="chips">
          {VIBES.map((v) => (
            <button key={v} className={`chip ${p.vibes?.includes(v) ? "sel" : ""}`}
                    onClick={() => toggleVibe(v)}>{v}</button>
          ))}
        </div>

        <div className="row2">
          <div>
            <label>Color principal</label>
            <input type="color" value={p.color1} onChange={(e) => set("color1", e.target.value)} />
          </div>
          <div>
            <label>Color secundario</label>
            <input type="color" value={p.color2} onChange={(e) => set("color2", e.target.value)} />
          </div>
          <div className="grow">
            <label>Ritmo de edición: {p.pace}/10 {p.pace! <= 3 ? "🎬 documental" : p.pace! >= 8 ? "⚡ hype" : "🎯 equilibrado"}</label>
            <input type="range" min={1} max={10} value={p.pace}
                   onChange={(e) => set("pace", Number(e.target.value))} />
          </div>
        </div>

        <label>3 vídeos que te encantaría haber hecho tú (links de YouTube / TikTok / Reels)</label>
        {(p.references ?? ["", "", ""]).map((r, i) => (
          <input key={i} value={r} placeholder={`https://... referente ${i + 1}`}
                 onChange={(e) => {
                   const refs = [...(p.references ?? ["", "", ""])];
                   refs[i] = e.target.value;
                   set("references", refs);
                 }} />
        ))}

        <label>Anti-referente: un vídeo o estilo que NO quieres parecer (opcional)</label>
        <input value={p.antiReference ?? ""} onChange={(e) => set("antiReference", e.target.value)}
               placeholder="link o descripción" />

        <label>Estilo de captions</label>
        <div className="opt out inline">
          <button className={p.captionStyle === "hormozi" ? "sel" : ""}
                  onClick={() => set("captionStyle", "hormozi")}>HORMOZI (2 palabras, bold)</button>
          <button className={p.captionStyle === "minimal" ? "sel" : ""}
                  onClick={() => set("captionStyle", "minimal")}>Minimalista premium</button>
        </div>

        <label>Reglas duras: cosas que Vidorq JAMÁS debe hacer con tu contenido (opcional)</label>
        <textarea value={p.hardRules ?? ""} onChange={(e) => set("hardRules", e.target.value)}
                  placeholder='Ej: "nunca emojis en subtítulos", "nunca zoom en mi cara"...' />

        <button className="cta" onClick={save}>{saved ? "✅ Guardado" : "Guardar mi estilo"}</button>
      </div>
    </div>
  );
}
