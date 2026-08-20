import { useEffect, useState } from "react";
import { apiGet, apiPost } from "./api";
import { useLang } from "./i18n";
import { IconAlert, IconCheck } from "./Icons";

// Un proveedor tal y como lo sirve el motor en /providers.
export interface Provider {
  id: string;
  label: string;
  needsKey: boolean;
  keyUrl: string;
  default: string;
  custom: boolean;
  cli: boolean;
  installed: boolean;
  /* Por que no se puede usar, cuando `installed` es false. Un boton apagado y
     mudo no dice si le falta algo a el o al ordenador. */
  why?: string;
  note: string;
}

interface Chosen {
  list: Provider[];
  provider: string;
  model: string;
  baseUrl: string;
  hasKey: string[];
}

/**
 * Quien piensa el prompt: proveedor, modelo y su clave.
 *
 * La lista de modelos se pide al proveedor en el momento y no viene escrita
 * aqui, porque una lista de modelos a mano lleva razon tres semanas y luego le
 * miente al usuario sobre lo que puede elegir.
 */
export default function Providers() {
  const { t, lang } = useLang();
  const [data, setData] = useState<Chosen | null>(null);
  const [provider, setProvider] = useState("local");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [key, setKey] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiGet<Chosen>(`/providers?lang=${lang}`).then((d) => {
      setData(d);
      setProvider(d.provider);
      setModel(d.model);
      setBaseUrl(d.baseUrl);
    });
  }, [lang]);

  const info = data?.list.find((p) => p.id === provider);
  // El motor nunca devuelve la clave, solo si la tiene. Asi que el campo se
  // deja vacio con un aviso, en vez de fingir puntitos que no son la clave.
  const stored = data?.hasKey.includes(provider) ?? false;

  async function loadModels() {
    setLoading(true);
    const q = new URLSearchParams({ provider });
    if (key) q.set("key", key);
    if (baseUrl) q.set("baseUrl", baseUrl);
    const r = await apiGet<{ models: string[] }>(`/models?${q.toString()}`);
    setModels(r.models || []);
    setLoading(false);
  }

  // Al cambiar de proveedor el modelo anterior deja de tener sentido.
  function pick(id: string) {
    setProvider(id);
    setModels([]);
    setKey("");
    const p = data?.list.find((x) => x.id === id);
    setModel(p?.default ?? "");
    if (!p?.custom) setBaseUrl("");
  }

  async function save() {
    const body: Record<string, unknown> = {
      aiProvider: provider,
      aiModel: model,
      aiBaseUrl: baseUrl,
    };
    // Solo se manda la clave que se acaba de escribir: el motor las mezcla, asi
    // que guardar una no borra las otras.
    if (key) body.keys = { [provider]: key };
    await apiPost("/config", body);
    setKey("");
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
    apiGet<Chosen>(`/providers?lang=${lang}`).then(setData);
  }

  if (!data) return <p className="hint">{t("prov.loading")}</p>;

  return (
    <>
      <p className="hint">{t("prov.sub")}</p>

      <section className="field">
        <label>{t("prov.who")}</label>
        <div className="opt out wrap">
          {data.list.map((p) => (
            <button
              key={p.id}
              className={provider === p.id ? "sel" : ""}
              onClick={() => pick(p.id)}
              disabled={!p.installed}
              title={p.installed ? p.note : (p.why || t("prov.cli.missing"))}
            >
              {p.label}
              {data.hasKey.includes(p.id) && <span className="dot" />}
            </button>
          ))}
        </div>
        {/* El proveedor de fabrica es Ollama local, y un ordenador sin
            ningun modelo descargado lo tiene apagado. Salia elegido, en violeta
            y con su nota de "gratis y sin clave": el motivo real vivia solo en
            el `title` de un boton deshabilitado, o sea en ningun sitio para
            quien abre el programa por primera vez. */}
        {info && !info.installed ? (
          <p className="warn-line under">
            <IconAlert size={13} className="icon" />
            {info.why || t("prov.cli.missing")}
          </p>
        ) : (
          info && <small className="under">{info.note}</small>
        )}
      </section>

      {info?.custom && (
        <section className="field">
          <label>{t("prov.base")}</label>
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.groq.com/openai/v1"
          />
        </section>
      )}

      {info?.needsKey && (
        <section className="field">
          <label>
            {t("prov.key")}
            {stored && <span className="opt-tag">{t("prov.stored")}</span>}
          </label>
          <small className="under">
            {stored ? t("prov.replace") : t("prov.local")}
            {info.keyUrl && (
              <>
                {" "}
                <a href={info.keyUrl} target="_blank" rel="noreferrer">
                  {t("prov.get")}
                </a>
              </>
            )}
          </small>
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={stored ? "••••••••" : "sk-..."}
          />
        </section>
      )}

      {info?.cli ? (
        <p className="hint">{t("prov.cli.model")}</p>
      ) : (
      <section className="field">
        <label>{t("prov.model")}</label>
        <div className="row">
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={info?.default || t("prov.model.ph")}
            list="vidorq-models"
          />
          <button className="ghost small" onClick={loadModels} disabled={loading}>
            {loading ? t("prov.loading.models") : t("prov.list")}
          </button>
        </div>
        <datalist id="vidorq-models">
          {models.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        {models.length > 0 && (
          <small className="under">{models.length} {t("prov.found")}</small>
        )}
      </section>
      )}

      <div className="modal-foot inline-foot">
        <button className="cta" onClick={save}>
          {saved ? (
            <>
              <IconCheck size={15} className="icon" />
              {t("saved")}
            </>
          ) : (
            t("prov.save")
          )}
        </button>
      </div>
    </>
  );
}
