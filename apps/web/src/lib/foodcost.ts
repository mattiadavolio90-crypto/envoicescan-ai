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
  alert_prezzo?: boolean;
  ingredienti_aumentati?: string[];
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
  verde: "text-positivo",
  ambra: "text-incerto",
  rosso: "text-negativo",
  grigio: "text-muted-foreground",
};

export const FC_BADGE_CLASS: Record<ColoreFC, string> = {
  verde: "bg-positivo/10 text-positivo border-positivo/30",
  ambra: "bg-incerto/10 text-incerto border-incerto/30",
  rosso: "bg-negativo/10 text-negativo border-negativo/30",
  grigio: "bg-muted text-muted-foreground border-border",
};

// Copia locale, non un import: `tests/helpers_ts.py` esegue QUESTO modulo con
// node, che non risolve un import relativo senza estensione (provato il
// 22/09/2026: 11 test rossi con ERR_MODULE_NOT_FOUND). Stesso motivo per cui
// `lib/catena-confronti.ts` tiene la sua `intervalloMese`. L'output e'
// byte-identico a `formatEuro(v, 2)` — verificato su 19 valori, limiti di
// arrotondamento inclusi — ed e' il test di equivalenza a tenerle allineate.
export function fmtEuro(v: number | null | undefined): string {
  if (v == null) return "—";
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v);
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

/** Messaggio d'errore di una risposta del worker, per il toast.

Il backend rifiuta il salvataggio di una ricetta con una riga non calcolabile
(422) e nel `detail` dice QUALE ingrediente: buttarlo via lascia l'utente con
un "Errore salvataggio" che non gli fa sistemare niente.

Difensiva su tre casi reali: la risposta puo' non essere JSON (502/504 di
Railway, HTML di errore), e FastAPI usa `detail` sia come stringa sia come
array di oggetti per gli errori di validazione Pydantic — passare quest'ultimo
a un toast stamperebbe "[object Object]". */
export function messaggioErroreRisposta(corpo: unknown, fallback: string): string {
  if (typeof corpo !== "object" || corpo === null) return fallback;
  const detail = (corpo as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (typeof d === "object" && d !== null ? (d as { msg?: unknown }).msg : d))
      .filter((m): m is string => typeof m === "string" && m.trim().length > 0);
    if (msgs.length) return msgs.join("; ");
  }
  return fallback;
}
