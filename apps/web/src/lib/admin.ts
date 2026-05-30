export type Sede = {
  id: string;
  nome_ristorante: string;
  partita_iva: string | null;
  ragione_sociale: string | null;
  attivo: boolean;
};

export type TrialInfo = {
  active: boolean;
  expires_at?: string;
  days_remaining?: number;
};

export type Cliente = {
  id: string;
  email: string;
  nome_ristorante: string;
  ragione_sociale: string | null;
  partita_iva: string | null;
  attivo: boolean;
  piano: "base" | "plus" | "pro";
  limite_fatture_mese: number;
  n_fatture: number;
  created_at: string | null;
  last_seen_at: string | null;
  trial: TrialInfo | null;
  pagine_abilitate: Record<string, boolean>;
  n_sedi: number;
  sedi: Sede[];
};

export type ClienteDettaglio = Cliente & {
  price_alert_threshold: number | null;
};

export const PIANO_LABEL: Record<string, string> = {
  base: "Base",
  plus: "Plus",
  pro: "Pro",
};

export const PIANO_COLOR: Record<string, string> = {
  base: "bg-slate-100 text-slate-700",
  plus: "bg-sky-100 text-sky-700",
  pro: "bg-violet-100 text-violet-700",
};

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
