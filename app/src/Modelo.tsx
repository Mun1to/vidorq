import { useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "./api";
import { useLang } from "./i18n";

/* Quien piensa y cuanto, pegado a donde se escribe.
 *
 * Esto ya se podia cambiar antes, pero estaba en Ajustes, o sea a tres clics y
 * una pantalla modal de distancia del sitio donde se decide. Un modelo es una
 * eleccion que se cambia A MITAD de una conversacion ("esta la hago con el
 * grande"), asi que vivir donde se escribe no es una comodidad, es el sitio
 * correcto.
 *
 * Se pide sus propios datos en vez de recibirlos por props. Es a proposito: la
 * barra no la usa solo el chat, y encadenarla al estado de App.tsx la ataria a
 * una pantalla concreta. La pantalla de Ajustes sigue existiendo entera; esto
 * es un atajo a las dos cosas que se cambian a menudo, no su sustituto.
 *
 * El punto de color es de VoCript, donde ya esta resuelto: verde listo, ambar
 * le falta la clave, rojo no se puede usar. Un boton apagado y mudo no dice si
 * le falta algo a el o al ordenador.
 */

interface Prov {
  id: string;
  label: string;
  needsKey: boolean;
  installed: boolean;
  why?: string;
}

interface Esf {
  id: string;
  label: string;
  note: string;
}

interface Datos {
  list: Prov[];
  provider: string;
  model: string;
  hasKey: string[];
  esfuerzo: string;
  esfuerzos: Esf[];
}

type Estado = "listo" | "sin-clave" | "roto";

function estadoDe(d: Datos | null): Estado {
  if (!d) return "roto";
  const p = (d.list || []).find((x) => x.id === d.provider);
  if (!p) return "roto";
  if (p.needsKey && !(d.hasKey || []).includes(p.id)) return "sin-clave";
  return p.installed ? "listo" : "roto";
}

export default function Modelo({ onSetup }: { onSetup: () => void }) {
  const { t, lang } = useLang();
  const [d, setD] = useState<Datos | null>(null);
  const [open, setOpen] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const caja = useRef<HTMLDivElement>(null);

  const carga = () =>
    apiGet<Datos>(`/providers?lang=${lang}`).then(setD).catch(() => setD(null));

  useEffect(() => { carga(); }, [lang]);

  // Al abrir se pregunta por los modelos del proveedor elegido, y no antes:
  // esa llamada sale a la red del proveedor y no vale la pena hacerla cada vez
  // que se pinta el chat.
  useEffect(() => {
    if (!open || !d) return;
    apiGet<{ models: string[] }>(`/models?provider=${encodeURIComponent(d.provider)}`)
      .then((r) => setModels(r.models || []))
      .catch(() => setModels([]));
  }, [open, d?.provider]);

  // Cerrar al pulsar fuera. Sin esto el desplegable se queda abierto encima de
  // lo que el usuario intenta leer, que es peor que no tenerlo.
  useEffect(() => {
    if (!open) return;
    const fuera = (e: MouseEvent) => {
      if (caja.current && !caja.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  /* Optimista: la barra cambia ya y el motor se entera despues. Si falla, la
     recarga devuelve la verdad, que es mejor que un desplegable que se queda
     pensando medio segundo cada vez que se toca. */
  const guarda = (aqui: Partial<Datos>, alla: Record<string, string>) => {
    setD((v) => (v ? { ...v, ...aqui } : v));
    apiPost("/config", alla).then(carga).catch(carga);
  };

  /* Cambiar de proveedor BORRA el modelo, y no es un extra: un
     `claude-sonnet-5` no existe en Ollama, asi que arrastrarlo al proveedor
     siguiente deja la barra diciendo un nombre que ese proveedor no reconoce y
     la edicion falla en la primera llamada. Vacio significa "sin preferencia" y
     el motor usa el que trae por defecto. */
  const ponProveedor = (pid: string) => {
    setModels([]);
    guarda({ provider: pid, model: "" }, { aiProvider: pid, aiModel: "" });
  };

  if (!d) return null;

  /* Un motor mas viejo que la ventana no manda `esfuerzos`, y eso no es
     hipotetico: el motor es un proceso que lleva horas vivo y no se entera de
     que se ha tocado su codigo. Sin esta red, `d.esfuerzos.map` revienta y la
     pantalla de chat entera se queda en blanco por un mando de tres botones.
     Con ella, la barra sale sin el esfuerzo y todo lo demas funciona. */
  const esfuerzos = Array.isArray(d.esfuerzos) ? d.esfuerzos : [];
  const lista = Array.isArray(d.list) ? d.list : [];
  const conClave = Array.isArray(d.hasKey) ? d.hasKey : [];

  const estado = estadoDe(d);
  const prov = lista.find((x) => x.id === d.provider);
  const nombre = d.model || prov?.label || d.provider;

  return (
    <div className="modelo" ref={caja}>
      <button
        className={`modelo-btn ${open ? "abierto" : ""}`}
        onClick={() => setOpen(!open)}
        title={estado === "sin-clave" ? t("modelo.sinClave")
             : estado === "roto" ? (prov?.why || t("modelo.roto"))
             : `${prov?.label || d.provider} · ${nombre}`}
      >
        <span className={`punto ${estado}`} />
        <span className="modelo-quien">{prov?.label || d.provider}</span>
        <span className="modelo-cual">{nombre}</span>
        <span className="modelo-flecha" aria-hidden="true" />
      </button>

      {/* El esfuerzo va FUERA del desplegable, a la vista y de un toque: es lo
          que mas se cambia y esconderlo detras de un clic lo mataria. */}
      <div className="esfuerzo" role="group" aria-label={t("modelo.esfuerzo")}>
        {esfuerzos.map((e) => (
          <button
            key={e.id}
            className={e.id === d.esfuerzo ? "sel" : ""}
            title={e.note}
            aria-pressed={e.id === d.esfuerzo}
            onClick={() => guarda({ esfuerzo: e.id }, { aiEsfuerzo: e.id })}
          >{e.label}</button>
        ))}
      </div>

      {open && (
        <div className="modelo-menu">
          <p className="modelo-tit">{t("modelo.quien")}</p>
          {lista.map((p) => {
            const falta = p.needsKey && !conClave.includes(p.id);
            return (
              <button
                key={p.id}
                className={`modelo-fila ${p.id === d.provider ? "sel" : ""}`}
                disabled={!p.installed && !falta}
                onClick={() => ponProveedor(p.id)}
              >
                <span className={`punto ${!p.installed ? "roto"
                                  : falta ? "sin-clave" : "listo"}`} />
                <span className="modelo-nom">{p.label}</span>
                {/* Un proveedor que no se puede usar dice POR QUE aqui mismo,
                    en vez de dejar al usuario adivinando por que esta gris. */}
                {falta && <span className="modelo-nota">{t("modelo.falta")}</span>}
                {!p.installed && p.why && (
                  <span className="modelo-nota">{p.why}</span>
                )}
              </button>
            );
          })}

          {models.length > 0 && (
            <>
              <p className="modelo-tit">{t("modelo.cual")}</p>
              <div className="modelo-modelos">
                {models.map((m) => (
                  <button
                    key={m}
                    className={`chip ${m === d.model ? "sel" : ""}`}
                    onClick={() => guarda({ model: m }, { aiModel: m })}
                  >{m}</button>
                ))}
              </div>
            </>
          )}

          <button className="btn" onClick={() => { setOpen(false); onSetup(); }}>
            {t("modelo.mas")}
          </button>
        </div>
      )}
    </div>
  );
}
