export type Track = "adapt" | "repair";
export interface Session {
  id: string;
  track: Track;
  revision: number;
  state: string;
}
export interface Reading {
  value_mm: number | null;
  sigma_mm: number | null;
  status: string;
  sources: string[];
}
export interface Analysis {
  revision: number;
  support: { status: string; reason: string };
  questions: {
    id: string;
    prompt: string;
    options: { id: string; label: string }[];
  }[];
  workspace: {
    image: { id: string } | null;
    message: string | null;
    provider_status: string;
    analysis: {
      object_type: string;
      component: string;
      cross_section_guess: string;
      visible_facts: string[];
      inferences: string[];
      confidence: string;
    } | null;
    confirmation: {
      object_type: string;
      component: string;
      cross_section: string;
      handle_intact: boolean | null;
    } | null;
  };
}
export interface Measurements {
  revision: number;
  dimensionally_complete: boolean;
  missing_dimensions: string[];
  workspace: {
    calibration: { id: string; quality: string } | null;
    measurements: Record<string, Reading>;
    conflicts: Record<string, string[]>;
  };
}
export interface Design {
  id: string;
  session_id: string;
  spec_hash: string;
  spec: {
    track: Track;
    object_type: string;
    variant: string;
    material: string;
    verification_level: string;
    disclaimers: string[];
    parameters: Record<string, string | number>;
  };
  ledger: { solid_material_estimate_g: number };
  files: string[];
  feedback?: { outcome: string; kept_in_use: boolean };
}
export interface Proposal {
  variant: string;
  reason: string;
  parameters: Record<string, string | number>;
  materials: string[];
}
export interface Stats {
  sessions_started: number;
  designs_generated: number;
  adapt_designs: number;
  repair_designs: number;
  reported_fit_trials: number;
  reported_fits: number;
  reported_items_kept_in_use: number;
  solid_material_estimate_g: number;
  limitations: string[];
}
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    "/api" + path,
    body === undefined
      ? {}
      : body instanceof FormData
        ? { method: "POST", body }
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
  );
  const data = await response.json();
  if (!response.ok)
    throw Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
export const pretty = (value: string) => value.replaceAll("_", " ");
export const fileUrl = (id: string, file: string) =>
  `/api/designs/${id}/files/${file}`;
