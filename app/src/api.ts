export const ENGINE = "http://127.0.0.1:9877";

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${ENGINE}${path}`);
  return r.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${ENGINE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

export interface Workspaces { active: string; list: string[] }

// Un estilo de caption tal y como lo sirve el motor en /captions/presets.
export interface CaptionStyle { id: string; label: string; note: string }

// Un destino de exportacion. `sugiere` es la forma que la ventana pone en el
// selector de arriba al elegirlo, no una imposicion: el usuario la puede
// cambiar despues y el destino sigue valiendo. `alto` en 0 quiere decir "el
// tamaño del original", que es el caso del master.
export interface ExportPreset {
  id: string; label: string; hint: string; sugiere: string; alto: number;
}

export interface BrandProfile {
  brandName?: string;
  about?: string;
  vibes?: string[];
  color1?: string;
  color2?: string;
  references?: string[];
  antiReference?: string;
  pace?: number;
  captionPreset?: string;
  // El nombre que el usuario le puso al copiarlo de un video suyo.
  captionPresetName?: string;
  captionAnim?: string;
  hardRules?: string;
}
