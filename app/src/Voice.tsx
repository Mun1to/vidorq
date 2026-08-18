import { useEffect, useState } from "react";
import { apiGet, apiPost } from "./api";
import { useLang } from "./i18n";
import { IconCheck } from "./Icons";

// Un motor de voz tal y como lo sirve el motor en /voices.
export interface VoiceEngine {
  id: string;
  label: string;
  needsKey: boolean;
  keyId: string;
  keyUrl: string;
  note: string;
}

interface Chosen {
  list: VoiceEngine[];
  engine: string;
  voice: string;
  baseUrl: string;
  hasKey: string[];
  voices: { id: string; label: string }[];
  error?: string;
}

/**
 * Quien pone la voz: motor, voz concreta y su clave.
 *
 * Mismo trato que los proveedores de texto, incluida la regla de que el motor
 * nunca devuelve una clave: dice cuales tiene guardadas y nada mas. Las voces
 * se piden en vivo donde el proveedor las publica, porque una lista escrita a
 * mano deja de ser verdad en cuanto alguien clona la suya.
 */
export default function Voice() {
  const { t, lang } = useLang();
  const [data, setData] = useState<Chosen | null>(null);
  const [engine, setEngine] = useState("windows");
  const [voice, setVoice] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [key, setKey] = useState("");
  const [saved, setSaved] = useState(false);

  function load(which?: string) {
    const q = new URLSearchParams({ lang });
    if (which) q.set("engine", which);
    apiGet<Chosen>(`/voices?${q.toString()}`).then((d) => {
      setData(d);
      if (!which) {
        setEngine(d.engine);
        setVoice(d.voice);
        setBaseUrl(d.baseUrl);
      }
    });
  }

  useEffect(() => { load(); }, [lang]);

  const info = data?.list.find((e) => e.id === engine);
  const stored = (info?.keyId && data?.hasKey.includes(info.keyId)) ?? false;

  function pick(id: string) {
    setEngine(id);
    setVoice("");
    setKey("");
    if (id !== "custom") setBaseUrl("");
    load(id);
  }

  async function save() {
    const body: Record<string, unknown> = {
      voiceEngine: engine, voiceId: voice, voiceBaseUrl: baseUrl,
    };
    if (key && info?.keyId) body.keys = { [info.keyId]: key };
    await apiPost("/config", body);
    setKey("");
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
    load(engine);
  }

  if (!data) return <p className="hint">{t("prov.loading")}</p>;

  return (
    <>
      <p className="hint">{t("voice.sub")}</p>

      <section className="field">
        <label>{t("voice.engine")}</label>
        <div className="opt out wrap">
          {data.list.map((e) => (
            <button key={e.id} className={engine === e.id ? "sel" : ""}
                    onClick={() => pick(e.id)}>
              {e.label}
              {e.keyId && data.hasKey.includes(e.keyId) && <span className="dot" />}
            </button>
          ))}
        </div>
        {info && <small className="under">{info.note}</small>}
      </section>

      {engine === "custom" && (
        <section className="field">
          <label>{t("prov.base")}</label>
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
                 placeholder="https://api.openai.com/v1" />
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
              <> <a href={info.keyUrl} target="_blank" rel="noreferrer">{t("prov.get")}</a></>
            )}
          </small>
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)}
                 placeholder={stored ? "••••••••" : "sk-..."} />
        </section>
      )}

      <section className="field">
        <label>{t("voice.which")}</label>
        {data.voices.length > 0 ? (
          <div className="opt out wrap">
            {data.voices.map((v) => (
              <button key={v.id} className={voice === v.id ? "sel" : ""}
                      onClick={() => setVoice(v.id)}>
                {v.label}
              </button>
            ))}
          </div>
        ) : (
          <small className="under">
            {info?.needsKey && !stored ? t("voice.needKey") : t("voice.none")}
          </small>
        )}
        {data.error && <small className="under bad">{data.error}</small>}
      </section>

      <small className="under">{t("voice.how")}</small>

      <div className="modal-foot inline-foot">
        <button className="cta" onClick={save}>
          {saved ? (<><IconCheck size={15} className="icon" />{t("saved")}</>)
                 : t("prov.save")}
        </button>
      </div>
    </>
  );
}
