import { useEffect, useState, ReactNode } from "react";
import { apiGet, ENGINE } from "./api";
import { useLang } from "./i18n";
import { IconAlert, IconCheck, IconRefresh } from "./Icons";

/* `app` lo contesta el motor mirando los procesos, no el puente: es lo unico
   que se puede saber de Resolve cuando el puente esta apagado. null = no se
   ha podido mirar. */
interface ResolveState { bridge: boolean; project?: string | null;
                         timeline?: string | null; app?: boolean | null }

type Status = "ok" | "pending" | "checking";

export default function Guia({ onClose }: { onClose: () => void }) {
  const { t } = useLang();
  const [engine, setEngine] = useState<Status>("checking");
  const [resolve, setResolve] = useState<ResolveState | null>(null);
  const [checking, setChecking] = useState(false);

  async function check() {
    setChecking(true);
    try {
      await fetch(`${ENGINE}/health`);
      setEngine("ok");
    } catch {
      setEngine("pending");
      setResolve(null);
      setChecking(false);
      return;
    }
    try {
      setResolve(await apiGet<ResolveState>("/resolve"));
    } catch {
      setResolve({ bridge: false });
    }
    setChecking(false);
  }

  useEffect(() => {
    check();
    const timer = setInterval(check, 4000);
    return () => clearInterval(timer);
  }, []);

  const bridgeOk = resolve?.bridge === true;
  const projectOk = bridgeOk && !!resolve?.project;
  const allOk = engine === "ok" && projectOk;

  const steps: { title: string; body: ReactNode; state: Status }[] = [
    {
      title: t("guide.s1.title"),
      state: engine === "ok" ? "ok" : engine,
      body: engine === "ok" ? t("guide.s1.ok") : t("guide.s1.pending"),
    },
    {
      title: t("guide.s2.title"),
      state: projectOk ? "ok" : "pending",
      /* Con el puente apagado este paso no se puede contestar, y salia "sin
         hacer": le decia a alguien que abriera un programa que ya tenia
         delante. Visto en vivo con Resolve abierto en un proyecto y el puente
         parado. Si el motor ve el proceso, se dice eso en vez de acusar. */
      body: projectOk
        ? <>{t("guide.s2.project")} <b>{resolve?.project}</b>
            {resolve?.timeline ? <> · {t("guide.s2.timeline")} <b>{resolve.timeline}</b></> : null}</>
        : resolve?.app ? t("guide.s2.open") : t("guide.s2.pending"),
    },
    {
      title: t("guide.s3.title"),
      state: bridgeOk ? "ok" : "pending",
      body: bridgeOk ? t("guide.s3.ok") : t("guide.s3.pending"),
    },
  ];

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal wide guide" onClick={(e) => e.stopPropagation()}>
        <div className="guide-head">
          <div>
            <h2>{t("guide.title")}</h2>
            <p className="hint">{t("guide.sub")}</p>
          </div>
          <button className="ghost small" onClick={check} disabled={checking}>
            <IconRefresh size={13} className="icon" />
            {checking ? t("guide.checking") : t("guide.check")}
          </button>
        </div>

        <ol className="steps">
          {steps.map((s, i) => (
            <li key={i} className={`step ${s.state}`}>
              <span className="step-mark">
                {s.state === "ok" ? <IconCheck size={14} className="icon" /> : i + 1}
              </span>
              <div className="step-body">
                <b>{s.title}</b>
                <p>{s.body}</p>
              </div>
            </li>
          ))}
        </ol>

        {allOk ? (
          <div className="guide-ok">
            <IconCheck size={16} className="icon" />
            <span>{t("guide.allOk")}</span>
          </div>
        ) : (
          <div className="guide-wait">
            <IconAlert size={16} className="icon" />
            <span>{t("guide.waiting")}</span>
          </div>
        )}

        <button className="cta" onClick={onClose}>{t("guide.close")}</button>
      </div>
    </div>
  );
}
