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
  captionAnim?: string;
  hardRules?: string;
}
