import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "./api";
import { useLang } from "./i18n";
import { IconClock, IconFilm, IconScissors, IconVideo } from "./Icons";

/**
 * El historial de ediciones: lo que hiciste, cuando, y sobre que video.
 *
 * Vive aparte de la conversacion de cada video a proposito. `sesion.json`
 * responde "que le pedi A ESTE video en ESTE proyecto", que es lo que hace
 * falta para retocarlo; esto responde "que hice el martes", que es lo que hace
 * falta cuando ya no te acuerdas ni de como se llamaba el archivo. Son dos
 * preguntas distintas y por eso son dos sitios.
 *
 * Cada fila abre su video: pulsarla es volver a donde estabas, no leer un
 * registro.
 */
interface Edit {
  at: number;          // segundos desde 1970, del reloj de este ordenador
  seconds: number;     // lo que tardo el turno
  video: string;
  name: string;
  prompt: string;
  output: string;      // "resolve" | "mp4"
  scope: string;       // el proyecto de Resolve, o el workspace
  did: string[];
  cuts: number;
  result: string;
  ok: boolean;
  stopped: boolean;
  error: string;
}

/** El dia al que pertenece un instante, en la zona de este ordenador. */
function dayOf(at: number) {
  const d = new Date(at * 1000);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function lasted(s: number) {
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  return s % 60 < 5 ? `${m} min` : `${m} min ${Math.round(s % 60)}s`;
}

export default function History({ onOpen }: { onOpen: (video: string) => void }) {
  const { t, lang } = useLang();
  const [edits, setEdits] = useState<Edit[] | null>(null);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    let vivo = true;
    apiGet<{ edits: Edit[] }>("/history")
      .then((d) => { if (vivo) setEdits(d.edits || []); })
      .catch(() => { if (vivo) setEdits([]); });
    return () => { vivo = false; };
  }, []);

  // Un dia por grupo, en el orden en que llegan (el motor ya los sirve del mas
  // nuevo al mas viejo), para no reordenar dos veces la misma lista.
  const days = useMemo(() => {
    const out: { key: string; when: number; rows: Edit[] }[] = [];
    for (const e of edits || []) {
      const k = dayOf(e.at);
      const last = out[out.length - 1];
      if (last && last.key === k) last.rows.push(e);
      else out.push({ key: k, when: e.at, rows: [e] });
    }
    return out;
  }, [edits]);

  const dayName = (at: number) => {
    const d = new Date(at * 1000);
    const hoy = new Date();
    const ayer = new Date(hoy.getTime() - 86400000);
    if (dayOf(at) === dayOf(hoy.getTime() / 1000)) return t("history.today");
    if (dayOf(at) === dayOf(ayer.getTime() / 1000)) return t("history.yesterday");
    return d.toLocaleDateString(lang, { weekday: "long", day: "numeric", month: "long" });
  };

  const hour = (at: number) =>
    new Date(at * 1000).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });

  const clear = () => {
    apiPost<{ ok: boolean }>("/history", { clear: true })
      .then(() => { setEdits([]); setAsking(false); })
      .catch(() => setAsking(false));
  };

  if (edits === null) return <section className="hist"><p className="stepn">{t("history.loading")}</p></section>;

  if (!edits.length) {
    return (
      <section className="run">
        <IconClock size={40} className="icon" />
        <h2>{t("history.title")}</h2>
        <p className="stepn">{t("history.empty")}</p>
      </section>
    );
  }

  return (
    <section className="hist">
      <div className="hist-head">
        <div>
          <h2>{t("history.title")}</h2>
          <p className="stepn">
            {edits.length} {edits.length === 1 ? t("history.one") : t("history.many")}
          </p>
        </div>
        {asking ? (
          <div className="hist-ask">
            <span>{t("history.sure")}</span>
            <button className="danger" onClick={clear}>{t("history.yes")}</button>
            <button onClick={() => setAsking(false)}>{t("cancel")}</button>
          </div>
        ) : (
          <button onClick={() => setAsking(true)}>{t("history.clear")}</button>
        )}
      </div>

      <div className="hist-list">
        {days.map((d) => (
          <div key={d.key} className="hist-day">
            <div className="hist-date">{dayName(d.when)}</div>
            {d.rows.map((e, i) => (
              <button
                key={`${e.at}-${i}`}
                className={`hist-row${e.ok ? "" : e.stopped ? " stopped" : " bad"}`}
                onClick={() => e.video && onOpen(e.video)}
                title={e.video}
              >
                <span className="hist-hour">{hour(e.at)}</span>
                <span className="hist-body">
                  <span className="hist-title">
                    <b>{e.name || t("history.noFile")}</b>
                    <span className={`hist-tag ${e.output}`}>
                      {e.output === "resolve" ? <IconVideo size={12} /> : <IconFilm size={12} />}
                      {e.output === "resolve" ? "Resolve" : "MP4"}
                    </span>
                    {e.scope ? <span className="hist-tag">{e.scope}</span> : null}
                  </span>
                  {e.prompt ? <span className="hist-said">“{e.prompt}”</span> : null}
                  {/* Lo que hizo, tal cual se lo dijo en el chat: repetirlo con
                      otras palabras aqui seria contarlo dos veces distinto. */}
                  {e.ok && e.did.length ? (
                    <span className="hist-did">{e.did.join(" · ")}</span>
                  ) : null}
                  {e.stopped ? <span className="hist-why">{t("history.stopped")}</span> : null}
                  {!e.ok && !e.stopped ? (
                    <span className="hist-why">{e.error || t("history.failed")}</span>
                  ) : null}
                </span>
                <span className="hist-meta">
                  {e.cuts ? (
                    <span><IconScissors size={12} /> {e.cuts}</span>
                  ) : null}
                  <span>{lasted(e.seconds)}</span>
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
