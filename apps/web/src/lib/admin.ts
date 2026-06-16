export type Sede = {
  id: string;
  nome_ristorante: string;
  partita_iva: string | null;
  ragione_sociale: string | null;
  indirizzo: string | null;
  cap: string | null;
  comune: string | null;
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
  // Etichetta gruppo/catena opzionale (clienti multi-sede). Quando presente la UI
  // la mostra al posto del nome della prima sede.
  nome_gruppo: string | null;
  ragione_sociale: string | null;
  partita_iva: string | null;
  attivo: boolean;
  piano: "free" | "base" | "plus" | "pro";
  piano_inizio_at: string | null;
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
  chat_ai_enabled: boolean;
};

export const PIANO_LABEL: Record<string, string> = {
  free: "FREE",
  base: "50",
  plus: "100",
  pro: "100+",
};

export const PIANO_COLOR: Record<string, string> = {
  free: "bg-slate-100 text-slate-600",
  base: "bg-sky-100 text-sky-700",
  plus: "bg-emerald-100 text-emerald-700",
  pro: "bg-violet-100 text-violet-700",
};

export const PIANO_OPTIONS: { value: string; label: string }[] = [
  { value: "free", label: "FREE" },
  { value: "base", label: "50 fatture/mese" },
  { value: "plus", label: "100 fatture/mese" },
  { value: "pro", label: "100+ fatture/mese" },
];

// Categorie valide (allineate a config/constants.py TUTTE_LE_CATEGORIE + speciale diciture).
// "Da Clasificare" è VIETATA da constraint DB — non includerla mai.
export const CATEGORIE_TUTTE: string[] = [
  "📝 NOTE E DICITURE",
  "CARNE", "PESCE", "LATTICINI", "SALUMI", "UOVA", "SCATOLAME E CONSERVE",
  "OLIO E CONDIMENTI", "PASTA E CEREALI", "VERDURE", "FRUTTA", "SALSE E CREME",
  "ACQUA", "BEVANDE", "CAFFE E THE", "BIRRE", "VINI",
  "VARIE BAR", "DISTILLATI", "AMARI/LIQUORI", "PASTICCERIA",
  "PRODOTTI DA FORNO", "SPEZIE E AROMI", "GELATI E DESSERT", "SHOP", "SUSHI VARIE",
  "SERVIZI E CONSULENZE", "UTENZE E LOCALI", "MANUTENZIONE E ATTREZZATURE", "MATERIALE DI CONSUMO",
];

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
