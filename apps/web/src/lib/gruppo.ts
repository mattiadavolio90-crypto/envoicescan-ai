import { cache } from "react";
import { workerGet } from "./worker";

// Modalità catena — vista gruppo multi-sede, sola lettura. Fase 1: overview.

export type GruppoKpi = {
  fatturato: number;
  margine_medio_perc: number;
  spesa_fornitori: number;
  mol: number;
  food_cost_pct: number | null;
  costo_personale: number;
  spese_generali: number;
  // Cascata dati: "nessuno" (niente numeri, completa i PV) | "food" (food cost/1°
  // margine si', MOL no) | "completo" (MOL affidabile).
  livello_dati: "nessuno" | "food" | "completo";
  pv_da_completare: number;
};

export type MolMensile = {
  mese: number;
  mol: number;
};

export type SalutePV = {
  ristorante_id: string;
  nome: string;
  indice: number;
  colore: "verde" | "giallo" | "rosso";
};

export type RankingPV = {
  ristorante_id: string;
  nome: string;
  margine_perc: number | null; // null = dati incompleti (nessun ricavo)
  fatturato: number;
  colore: "verde" | "giallo" | "rosso" | "grigio";
  dati_incompleti: boolean;
};

export type GruppoBriefing = {
  saluto: string;
  narrativa: string;
  severity_max: "info" | "warning" | "error";
  // Fatture di gruppo da collocare (a nome società, non attribuite a un locale).
  // Fuori dalla narrativa: desktop ha la coda sotto (azionabile), mobile rimanda al PC.
  n_fatture_da_collocare?: number;
};

export type GruppoOverview = {
  nome_gruppo: string;
  num_pv: number;
  periodo_label: string;
  briefing: GruppoBriefing;
  kpi: GruppoKpi;
  mol_mensile: MolMensile[];
  mol_mensile_anno: number;
  salute_indice: number;
  salute_colore: "verde" | "giallo" | "rosso";
  salute_pv: SalutePV[];
  ranking: RankingPV[];
};

export const fetchGruppoOverview = cache(
  async (): Promise<GruppoOverview | null> =>
    workerGet<GruppoOverview>("/api/gruppo/overview", "gruppo.overview"),
);

export type GruppoChatConfig = {
  enabled: boolean;
  limite_giorno: number;
  domande_oggi: number;
};

export const fetchGruppoChatConfig = cache(
  async (): Promise<GruppoChatConfig | null> =>
    workerGet<GruppoChatConfig>("/api/gruppo/chat-config", "gruppo.chatConfig"),
);

// ─── Finestra "Spesa per PV" ──────────────────────────────────────────────

export type SpesaPivotRow = {
  dim_val: string;
  emoji?: string | null; // icona categoria (null per fornitore)
  per_pv: Record<string, number>; // ristorante_id -> spesa
  totale: number;
  incidenza_pct: number;
};

export type SpesaPivot = {
  nome_gruppo: string;
  periodo_label: string;
  dimensione: "categoria" | "fornitore";
  pv: { id: string; nome: string }[];
  rows: SpesaPivotRow[];
  totali_pv: Record<string, number>;
  grand_total: number;
};

// ─── Finestra "Margini e Coperti per PV" ──────────────────────────────────

export type MarginiCopertiPV = {
  ristorante_id: string;
  nome: string;
  margine_perc: number | null;
  fatturato: number;
  coperti: number;
  scontrino_medio: number | null;
  mp_per_coperto: number | null; // BASSO = meglio
  dati_incompleti: boolean;
};

export type MarginiCoperti = {
  nome_gruppo: string;
  periodo_label: string;
  righe: MarginiCopertiPV[];
  gruppo: MarginiCopertiPV;
  n_incompleti: number;
};

// ─── Finestra "Spreco per categoria" (€MP/coperto, confronto PV) ───────────

export type SprecoCategoriaCella = {
  ristorante_id: string;
  valore: number | null;
};

export type SprecoCategoriaRiga = {
  categoria: string;
  per_pv: SprecoCategoriaCella[]; // stesso ordine di pv
  media_gruppo: number | null;
};

export type SprecoCategoriePV = {
  ristorante_id: string;
  nome: string;
  dati_incompleti: boolean;
};

export type SprecoCategorie = {
  nome_gruppo: string;
  periodo_label: string;
  pv: SprecoCategoriePV[];
  righe: SprecoCategoriaRiga[];
};

// ─── Segnali "Da vedere nella catena" ─────────────────────────────────────

export type Segnale = {
  tipo: "dati_mancanti" | "margine_calo" | "prezzi_sopra" | "ricavi_mancanti";
  severity: "warning" | "error";
  ristorante_id: string;
  pv_nome: string;
  testo: string;
  cta_page: string; // pagina PV dove approfondire (deep link "Vedi PV →")
};

export type SegnaliGruppo = {
  nome_gruppo: string;
  generated_at: string | null;
  segnali: Segnale[];
};

// ─── Tag di catena (Analisi e Tag, solo multi-sede) ───────────────────────

export type GruppoTag = {
  id: number;
  nome: string;
  emoji: string | null;
  colore: string | null;
  n_prodotti?: number;
};

export type GruppoTagDescrizione = {
  descrizione: string;
  descrizione_key: string;
  n: number;
  spesa: number;
};

export type GruppoTagProdotto = {
  id: number;
  descrizione: string;
  descrizione_key: string;
  fattore_kg: number | null;
};

export type TagAnalisiPV = {
  ristorante_id: string;
  nome: string;
  spesa: number;
  quantita: number;
  n_righe: number;
  n_fornitori: number;
  incidenza_pct: number;
  prezzo_medio: number | null;
};

export type TagFornitore = {
  nome: string;
  spesa: number;
  incidenza_pct: number;
  n_righe: number;
};

export type TagTrendPunto = {
  anno: number;
  mese: number;
  spesa: number;
};

export type GruppoTagAnalisi = {
  tag_id: number;
  nome: string;
  emoji?: string | null;
  periodo_label: string;
  spesa_totale: number;
  quantita_totale: number;
  prezzo_medio: number | null;
  n_fornitori: number;
  per_pv: TagAnalisiPV[];
  fornitori: TagFornitore[];
  trend: TagTrendPunto[];
};
