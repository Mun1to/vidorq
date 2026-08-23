import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { LangProvider } from "./i18n";
import { arranca } from "./acento";

// El acento se pone ANTES de pintar nada. Si se pusiera dentro de un efecto de
// React, la primera pasada saldria con el acento de la hoja y el usuario veria
// el color cambiar delante, que es el parpadeo que se nota mas.
arranca();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <LangProvider>
      <App />
    </LangProvider>
  </React.StrictMode>,
);
