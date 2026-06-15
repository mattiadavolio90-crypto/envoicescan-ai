export type VariazionePrezzo = {
  prodotto: string;
  categoria: string;
  fornitore: string;
  storico: string;
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
