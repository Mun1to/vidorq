import { useState } from "react";
import { useLang } from "./i18n";
import {
  ACENTOS, ajusta, contraste, fondoDe, guarda, guardado, temaAhora,
} from "./acento";

/* El color de acento, elegible sin poder romper el contraste.
 *
 * Se enseña el numero MEDIDO debajo de cada opcion, y no es adorno: es la regla
 * de la casa ("si tocas un hex, vuelve a medirlo, no lo ajustes mirando") hecha
 * pantalla. El usuario elige el color; el programa le busca la claridad mas
 * cercana que llegue a 4,5 sobre el fondo de este tema, y le dice a cuanto se
 * ha quedado. Asi no hay forma de dejar la ventana ilegible sin verlo.
 */
export default function Aspecto() {
  const { t } = useLang();
  const [elegido, setElegido] = useState(guardado());
  const tema = temaAhora();
  const fondo = fondoDe(tema);

  const pon = (hex: string) => { setElegido(hex); guarda(hex); };

  const corregido = elegido ? ajusta(elegido, fondo) : "";
  const ratio = corregido ? contraste(corregido, fondo) : 0;
  const cambiado = !!elegido && corregido.toLowerCase() !== elegido.toLowerCase();

  return (
    <>
      <p className="hint">{t("asp.sub")}</p>

      <div className="acentos">
        {ACENTOS.map((a) => {
          const bueno = ajusta(a.hex, fondo);
          return (
            <button
              key={a.id}
              className={`acento ${elegido.toLowerCase() === a.hex.toLowerCase() ? "sel" : ""}`}
              onClick={() => pon(a.hex)}
              title={`${a.label} · ${contraste(bueno, fondo).toFixed(2)}:1`}
            >
              <span className="acento-bola" style={{ background: bueno }} />
              <span>{a.label}</span>
              <span className="acento-num">{contraste(bueno, fondo).toFixed(2)}</span>
            </button>
          );
        })}
      </div>

      <div className="row2">
        <label className="grow">
          {t("asp.libre")}
          <input
            type="color"
            value={elegido || "#3d8ee0"}
            onChange={(e) => pon(e.target.value)}
          />
        </label>
        <button className="btn" onClick={() => { setElegido(""); guarda(""); }}>
          {t("asp.reset")}
        </button>
      </div>

      {/* Lo que de verdad importa: a cuanto se ha quedado, y si hubo que
          corregirlo. Un ajuste silencioso seria justo el "ajustar mirando" que
          la regla prohibe, solo que hecho por el programa. */}
      {elegido && (
        <p className="hint">
          {t("asp.mide")} <b>{ratio.toFixed(2)}:1</b>{" "}
          ({tema === "dark" ? t("asp.oscuro") : t("asp.claro")}).{" "}
          {cambiado ? (
            <>
              {t("asp.ajustado")} <code>{elegido}</code> → <code>{corregido}</code>
            </>
          ) : t("asp.tal")}
        </p>
      )}
    </>
  );
}
