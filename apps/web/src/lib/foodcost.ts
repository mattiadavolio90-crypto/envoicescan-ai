// Tipi e fetch helpers per il tab Foodcost del Workspace.

export type ColoreFC = "verde" | "ambra" | "rosso" | "grigio";

export interface ArticoloFattura {
  tipo: "articolo";
  nome: string;
  prezzo_unitario: number;
  um: string;
  grammatura_confezione: number | null;
  grammatura_um: string | null;
  grammatura_str: string | null;
}

export interface IngredienteManuale {
  tipo: "manuale";
  id: string;
  nome: string;
  prezzo_unitario: number;
  um: string;
}

export interface Semilavorato {
  tipo: "semilavorato";
  id: string;
  nome: string;
  foodcost_ricetta: number;
}

export type Ingrediente = ArticoloFattura | IngredienteManuale | Semilavorato;

export interface RigaRicetta {
  nome: string;
  tipo: "articolo" | "manuale" | "semilavorato";
  quantita: number;
  um: string;
  um_db?: string;
  prezzo_unitario?: number;
  grammatura_confezione?: number | null;
  grammatura_um?: string | null;
  prezzo_override?: number | null;
  foodcost_ricetta?: number | null;
  costo?: number; // calcolato, non salvato
}

export interface Ricetta {
  id: string;
  nome: string;
  categoria: string;
  foodcost_totale: number;
  prezzo_vendita_ivainc: number | null;
  prezzo_netto: number | null;
  margine: number | null;
  incidenza_pct: number | null;
  colore_fc: ColoreFC;
  ordine_visualizzazione: number;
}

export interface RicettaDettaglio extends Ricetta {
  righe: RigaRicetta[];
}

export interface KpiFoodcost {
  totale: number;
  costo_medio: number;
  margine_medio: number | null;
  incidenza_media: number | null;
}

export interface CategoriaStats {
  categoria: string;
  n_ricette: number;
  fc_totale: number;
  fc_medio: number;
  margine_medio: number | null;
  incidenza_media: number | null;
}

export interface RicetteResponse {
  ricette: Ricetta[];
  kpi: KpiFoodcost;
  categorie: CategoriaStats[];
}

export interface IngredientiResponse {
  articoli: ArticoloFattura[];
  manuali: IngredienteManuale[];
  semilavorati: Semilavorato[];
}

export const CATEGORIE_RICETTE = [
  "ANTIPASTI", "BRACE", "CARNE", "CONTORNI", "CRUDI", "DOLCI",
  "FOCACCE", "FRITTI", "GRIGLIA", "INSALATE", "PANINI", "PESCE",
  "PIADINE", "PINZE", "PIZZE", "POKE", "PRIMI", "RISOTTI",
  "SALTATI", "SECONDI", "SEMILAVORATI", "SUSHI", "TEMPURA",
  "VAPORE", "VERDURE",
] as const;

export const UM_OPTIONS = ["G", "KG", "ML", "CL", "LT", "PZ"] as const;

export const FC_COLORE_CLASS: Record<ColoreFC, string> = {
  verde: "text-emerald-600 dark:text-emerald-400",
  ambra: "text-amber-600 dark:text-amber-400",
  rosso: "text-destructive",
  grigio: "text-muted-foreground",
};

export const FC_BADGE_CLASS: Record<ColoreFC, string> = {
  verde: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800",
  ambra: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400 border-amber-200 dark:border-amber-800",
  rosso: "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-400 border-red-200 dark:border-red-800",
  grigio: "bg-muted text-muted-foreground border-border",
};

export function fmtEuro(v: number | null | undefined): string {
  if (v == null) return "—";
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);
}

export function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v.toFixed(1)}%`;
}

// Stesse soglie del backend (foodcost_service.py): ≤30 verde, ≤40 ambra, >40 rosso
export function coloreFC(incidenza: number | null | undefined): ColoreFC {
  if (incidenza == null) return "grigio";
  if (incidenza <= 30) return "verde";
  if (incidenza <= 40) return "ambra";
  return "rosso";
}
