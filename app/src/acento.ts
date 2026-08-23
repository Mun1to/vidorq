/* El color de acento, elegible sin romper el contraste.
 *
 * La paleta Grafito deriva todo con `color-mix` a partir de cuatro colores por
 * tema, asi que cambiar el acento es cambiar UNA variable. Lo que no se puede
 * es dejar que el usuario elija un hex cualquiera y ya: el acento lleva texto
 * encima y va sobre el fondo, y aqui esta MEDIDO que un mismo azul da 5,15
 * sobre el fondo oscuro y 3,13 sobre el claro, cuando el minimo de la WCAG 2.1
 * para texto normal es 4,5. Por eso el tema claro y el oscuro no comparten
 * acento.
 *
 * La regla de la casa dice "si tocas un hex, vuelve a medirlo, no lo ajustes
 * mirando". Un selector de color no puede pedirle eso al usuario, asi que lo
 * mide el programa: se coge el TONO que eligio y se le busca la claridad mas
 * cercana que llegue a 4,5 contra el fondo de ese tema. El usuario elige el
 * color; el contraste no se negocia.
 */

const CLAVE = "vidorq-acento";

/* Los fondos de cada tema. Son la RED, no la fuente: lo bueno es leer `--bg` de
   la hoja de estilo, que es donde vive de verdad, y esto solo se usa si esa
   lectura no da nada (fuera del navegador, o antes de que la hoja se aplique).
   No es paranoia: al escribir esto el valor oscuro se copio mal (`#12151a` por
   `#17191c`) y el ajuste salia contra un fondo que no existe. Un numero
   duplicado a mano se desincroniza el primer dia. */
export const FONDO = { light: "#f4f5f7", dark: "#17191c" };

/** El fondo de un tema, leido del CSS. Cae en la constante si no hay DOM. */
export function fondoDe(tema: "light" | "dark"): string {
  try {
    // El `--bg` que hay puesto AHORA solo vale si es el del tema que se pide;
    // para el otro no hay forma de preguntarle a la hoja sin montar un nodo
    // aparte, y montar nodos para leer un color no compensa.
    if (tema === temaAhora()) {
      const v = getComputedStyle(document.documentElement)
        .getPropertyValue("--bg").trim();
      if (/^#[0-9a-f]{3,8}$/i.test(v)) return v;
    }
  } catch {
    /* sin DOM: se usa la constante */
  }
  return FONDO[tema];
}

/* Los que ya vienen medidos. El primero es el de Grafito, que es el de hoy. */
export const ACENTOS: { id: string; hex: string; label: string }[] = [
  { id: "azul", hex: "#3d8ee0", label: "Azul" },
  { id: "verde", hex: "#35b37e", label: "Verde" },
  { id: "ambar", hex: "#d7a13a", label: "Ámbar" },
  { id: "rojo", hex: "#e05c4e", label: "Rojo" },
  { id: "morado", hex: "#9b7bea", label: "Morado" },
  { id: "cian", hex: "#3fb6c4", label: "Cian" },
];

type RGB = [number, number, number];

function aRgb(hex: string): RGB {
  const h = hex.replace("#", "").trim();
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full.slice(0, 6), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function aHex([r, g, b]: RGB): string {
  const c = (x: number) =>
    Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, "0");
  return `#${c(r)}${c(g)}${c(b)}`;
}

/** Luminancia relativa, tal y como la define la WCAG 2.1. */
export function luz(hex: string): number {
  const lin = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const [r, g, b] = aRgb(hex);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** El contraste entre dos colores, de 1 a 21. 4,5 es el minimo para leer. */
export function contraste(a: string, b: string): number {
  const [x, y] = [luz(a), luz(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

/** El mismo color, mas claro o mas oscuro, hasta llegar al contraste pedido.
 *
 * Se mueve por el canal, no por el tono: multiplicar los tres a la vez conserva
 * el color que eligio el usuario y solo cambia cuanta luz tiene. Si ni el negro
 * ni el blanco llegan (no pasa con estos fondos, pero podria con un fondo gris
 * medio), se devuelve el que mas cerca se quede en vez de fallar.
 */
export function ajusta(hex: string, fondo: string, minimo = 4.5): string {
  if (contraste(hex, fondo) >= minimo) return hex;
  const base = aRgb(hex);
  const haciaNegro = luz(fondo) > 0.18;   // fondo claro -> hay que oscurecer
  let mejor = hex;
  let mejorRatio = contraste(hex, fondo);
  // Treinta pasos entre el color y el extremo: suficiente para que el salto no
  // se vea y barato de calcular una sola vez al arrancar.
  for (let i = 1; i <= 30; i++) {
    const k = i / 30;
    const rgb = base.map((c) =>
      haciaNegro ? c * (1 - k) : c + (255 - c) * k) as RGB;
    const cand = aHex(rgb);
    const r = contraste(cand, fondo);
    if (r > mejorRatio) { mejor = cand; mejorRatio = r; }
    if (r >= minimo) return cand;
  }
  return mejor;
}

/** El texto que va ENCIMA del acento: el que mas contraste saque, blanco o casi negro. */
export function sobre(acento: string): string {
  return contraste("#ffffff", acento) >= contraste("#06090c", acento)
    ? "#ffffff" : "#06090c";
}

/** El tema que se esta viendo ahora mismo. */
export function temaAhora(): "light" | "dark" {
  const puesto = document.documentElement.getAttribute("data-theme");
  if (puesto === "light" || puesto === "dark") return puesto;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark" : "light";
}

export function guardado(): string {
  try {
    return localStorage.getItem(CLAVE) || "";
  } catch {
    return "";
  }
}

/** Pinta el acento elegido, ya corregido para el tema que se este viendo.
 *
 * Sin argumento repinta el guardado, que es lo que hay que hacer cuando el
 * sistema cambia de claro a oscuro: el mismo color pedido da otro corregido.
 * Sin nada guardado se quitan las variables y manda la hoja de estilo, o sea
 * el acento de Grafito con sus dos valores ya medidos.
 */
export function aplica(hex?: string): void {
  const pedido = hex !== undefined ? hex : guardado();
  const raiz = document.documentElement;
  if (!pedido) {
    raiz.style.removeProperty("--accent");
    raiz.style.removeProperty("--sobre");
    return;
  }
  const bueno = ajusta(pedido, fondoDe(temaAhora()));
  raiz.style.setProperty("--accent", bueno);
  raiz.style.setProperty("--sobre", sobre(bueno));
}

export function guarda(hex: string): void {
  try {
    if (hex) localStorage.setItem(CLAVE, hex);
    else localStorage.removeItem(CLAVE);
  } catch {
    /* Un navegador con el almacenamiento cerrado no puede recordar el color.
       Se aplica igual para esta sesion en vez de no hacer nada. */
  }
  aplica(hex);
}

/** Deja el acento puesto al arrancar y lo repinta si el sistema cambia de tema. */
export function arranca(): void {
  aplica();
  window.matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => aplica());
}
