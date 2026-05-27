export type VariazionePrezzo = {
  prodotto: string;
  categoria: string;
  fornitore: string;
  storico: string;
  media: number;
  ultimo: number;
  aumento_perc: number;
  data: string;
  n_fattura: string;
  trend: string;
  impatto_stimato: number;
  delta_euro: number;
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
};

export type NoteCreditoResponse = {
  note: NotaCreditoItem[];
  totale_credito: number;
  n_documenti: number;
};

export type StoricoPrezzoPoint = {
  data: string;
  prezzo_unitario: number;
};

export type StoricoPrezzoResponse = {
  prodotto: string;
  fornitore: string;
  punti: StoricoPrezzoPoint[];
  prezzo_medio: number;
};
