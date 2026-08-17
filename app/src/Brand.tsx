import { useEffect, useState } from "react";
import { apiGet, apiPost, BrandProfile } from "./api";
import { useLang, Key } from "./i18n";
import { IconCheck } from "./Icons";

// El valor guardado es el mismo en los dos idiomas; solo cambia como se muestra.
const VIBES: { id: string; label: Key }[] = [
  { id: "cercano", label: "vibe.cercano" },
  { id: "premium", label: "vibe.premium" },
  { id: "energico", label: "vibe.energico" },
  { id: "calmado", label: "vibe.calmado" },
  { id: "tecnico", label: "vibe.tecnico" },
  { id: "divertido", label: "vibe.divertido" },
];

export default function Brand({ onClose }: { onClose: () => void }) {
  const { t } = useLang();
  const [p, setP] = useState<BrandProfile>({
    vibes: [], references: ["", "", ""], pace: 6,
    color1: "#6c5ce7", color2: "#2b82f0", captionStyle: "hormozi",
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

  const paceKey: Key = (p.pace ?? 6) <= 3 ? "brand.pace.slow"
    : (p.pace ?? 6) >= 8 ? "brand.pace.fast" : "brand.pace.mid";

  async function save() {
    await apiPost("/profile", p);
    setSaved(true);
    setTimeout(onClose, 700);
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{t("brand.title")}</h2>
          <p className="hint">{t("brand.sub")}</p>
        </div>

        <div className="modal-body">
          <section className="field">
            <label>{t("brand.name")}</label>
            <input value={p.brandName ?? ""} onChange={(e) => set("brandName", e.target.value)}
                   placeholder="Orquio, MiCanal..." />
          </section>

          <section className="field">
            <label>{t("brand.about")}</label>
            <textarea value={p.about ?? ""} onChange={(e) => set("about", e.target.value)}
                      placeholder={t("brand.about.ph")} />
          </section>

          <section className="field">
            <label>{t("brand.vibes")}</label>
            <div className="chips">
              {VIBES.map((v) => (
                <button key={v.id} className={`chip ${p.vibes?.includes(v.id) ? "sel" : ""}`}
                        onClick={() => toggleVibe(v.id)}>{t(v.label)}</button>
              ))}
            </div>
          </section>

          <section className="field">
            <label>{t("brand.pace")}</label>
            <div className="pace">
              <input type="range" min={1} max={10} value={p.pace}
                     onChange={(e) => set("pace", Number(e.target.value))} />
              <div className="pace-read"><b>{p.pace}/10</b><span>{t(paceKey)}</span></div>
            </div>
          </section>

          <section className="field">
            <label>{t("brand.colors")}</label>
            <div className="colors">
              <label className="swatch">
                <input type="color" value={p.color1} onChange={(e) => set("color1", e.target.value)} />
                <span>{t("brand.color1")}<b>{p.color1}</b></span>
              </label>
              <label className="swatch">
                <input type="color" value={p.color2} onChange={(e) => set("color2", e.target.value)} />
                <span>{t("brand.color2")}<b>{p.color2}</b></span>
              </label>
            </div>
          </section>

          <section className="field">
            <label>{t("brand.caption")}</label>
            <div className="opt out inline">
              <button className={p.captionStyle === "hormozi" ? "sel" : ""}
                      onClick={() => set("captionStyle", "hormozi")}>Hormozi</button>
              <button className={p.captionStyle === "minimal" ? "sel" : ""}
                      onClick={() => set("captionStyle", "minimal")}>Minimal</button>
            </div>
            <small className="under">
              {t(p.captionStyle === "hormozi" ? "brand.caption.hormozi" : "brand.caption.minimal")}
            </small>
          </section>

          <section className="field">
            <label>{t("brand.refs")}</label>
            <small className="under">{t("brand.refs.sub")}</small>
            {(p.references ?? ["", "", ""]).map((r, i) => (
              <input key={i} value={r} placeholder={`https://...  ${t("brand.ref")} ${i + 1}`}
                     onChange={(e) => {
                       const refs = [...(p.references ?? ["", "", ""])];
                       refs[i] = e.target.value;
                       set("references", refs);
                     }} />
            ))}
          </section>

          <section className="field">
            <label>{t("brand.anti")} <span className="opt-tag">{t("optional")}</span></label>
            <small className="under">{t("brand.anti.sub")}</small>
            <input value={p.antiReference ?? ""} onChange={(e) => set("antiReference", e.target.value)}
                   placeholder={t("brand.anti.ph")} />
          </section>

          <section className="field">
            <label>{t("brand.rules")} <span className="opt-tag">{t("optional")}</span></label>
            <small className="under">{t("brand.rules.sub")}</small>
            <textarea value={p.hardRules ?? ""} onChange={(e) => set("hardRules", e.target.value)}
                      placeholder={t("brand.rules.ph")} />
          </section>
        </div>

        <div className="modal-foot">
          <button className="ghost" onClick={onClose}>{t("cancel")}</button>
          <button className="cta" onClick={save}>
            {saved ? <><IconCheck size={15} className="icon" />{t("saved")}</> : t("brand.save")}
          </button>
        </div>
      </div>
    </div>
  );
}
