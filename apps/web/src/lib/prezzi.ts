export type VariazionePrezzo = {
  prodotto: string;
  categoria: string;
  fornitore: string;
  storico: string;
  /** Valori grezzi della sparkline. `storico` e' solo presentazione (2 decimali). */
  storico_valori?: number[];
  media: number;
  penultimo: number;
  ultimo: number;
  aumento_perc: number;
  data: string;
  n_fattura: string;
  trend: string;
  impatto_stimato: number;
  delta_euro: number;
  preferito: boolean;
};

export type VariazioniResponse = {
  variazioni: VariazionePrezzo[];
  scostamento_medio: number;
  impatto_netto: number;
  fornitori_coinvolti: number;
  soglia: number;
  /**
   * Fatture (documenti distinti) nel periodo, anche quelle che non producono
   * variazioni. Distingue "nessuna variazione" da "nessuna fattura": senza,
   * un anno vuoto mostrava "i prezzi sono stabili nel 2025", cioe' rassicurava
   * su dati inesistenti.
   *
   * Nullable per un motivo preciso: `null`/`undefined` significano "non lo so"
   * (response in cache da prima del deploy del 17/09/2026, o un worker che non
   * popola il campo) e sono ben diversi da `0` ("nessuna fattura"). Trattare
   * l'assenza come 0 direbbe "nessuna fattura" anche a una sede con migliaia di
   * documenti — per questo il default lato worker e' None, non 0.
   */
  fatture_nel_periodo?: number | null;
};

export type ScontoOmaggioItem = {
  tipo: "sconto" | "omaggio";
  descrizione: string;
  categoria: string;
  fornitore: string;
  quantita: number | null;
  valore: number;
  data: string;
  numero_documento: string;
  fattura: string;
};

export type ScontiOmaggiResponse = {
  items: ScontoOmaggioItem[];
  totale_risparmiato: number;
  n_sconti: number;
  n_omaggi: number;
};

export type NotaCreditoItem = {
  documento: string;
  data: string;
  fornitore: string;
  descrizione: string;
  categoria: string;
  quantita: number | null;
  credito: number;
  numero_documento: string;
};

export type NoteCreditoResponse = {
  note: NotaCreditoItem[];
  totale_credito: number;
  n_documenti: number;
};

export type StoricoPrezzoPoint = {
  data: string;
  prezzo_unitario: number;
  fattura?: string;
  numero_documento?: string;
  quantita?: number | null;
  totale_riga?: number | null;
};

export type StoricoPrezzoResponse = {
  prodotto: string;
  fornitore: string;
  punti: StoricoPrezzoPoint[];
  prezzo_medio: number;
};

// ─── Score Fornitori (Osservatorio, tab 4) ──────────────────────────────────
export type ScoreStato =
  | "affidabile"
  | "da_monitorare"
  | "instabile"
  | "provvisorio"
  | "dati_insufficienti";

export type MetricaStato = "stabile" | "da_monitorare" | "instabile" | "non_valutabile";

export type ScoreSottometrica = {
  chiave: "stabilita" | "coerenza" | "impatto" | "documentale";
  label: string;
  punteggio: number;
  stato: MetricaStato;
  spiegazione: string;
  disponibile: boolean;
};

export type ScoreSegnale = {
  tipo: "rincaro" | "sconto_perso" | "oscillazione" | "nota_credito" | "stabilita";
  tono: "attenzione" | "positivo" | "neutro";
  testo: string;
};

export type BozzaTrattativa = {
  attiva: boolean;
  testo: string;
  motivo: string;
};

export type ScoreFornitore = {
  fornitore: string;
  score: number | null;
  stato: ScoreStato;
  affidabilita_dato: "alta" | "media" | "bassa";
  frase_sintesi: string;
  sottometriche: ScoreSottometrica[];
  segnali: ScoreSegnale[];
  bozza: BozzaTrattativa;
  n_fatture: number;
  n_prodotti: number;
  mesi_coperti: number;
  periodo: string;
  spesa_periodo: number;
  impatto_rincari: number;
};

export type ScoreFornitoriResponse = {
  fornitori: ScoreFornitore[];
  periodo: string;
  n_fornitori_valutati: number;
  n_fornitori_insufficienti: number;
};
