// Tipi per la pagina Analisi e Tag — allineati all'output di tag_analytics_service.py

export type CustomTag = {
  id: number;
  nome: string;
  emoji: string | null;
  colore: string | null;
  created_at: string;
};

export type TagProdotto = {
  id: number;
  tag_id: number;
  descrizione: string;
  descrizione_key: string;
  fattore_kg: number | null;
  created_at: string;
};

export type DescrizioneDistinta = {
  descrizione: string;
  descrizione_key: string;
  occorrenze: number;
  num_fornitori: number;
  fornitori: string[];
  ultima_data: string | null;
  unita_misura: string[];
};

// Analytics

export type TagKpi = {
  spesa_totale: number;
  quantita_norm_totale: number;
  prezzo_medio_ponderato: number | null;
  num_fornitori: number;
  num_fatture: number;
  quantita_label: string;
  prezzo_label: string;
};

export type TagTrendPunto = {
  data: string;
  prezzo: number;
  var_perc: number;
};

export type TagTrend = {
  punti: TagTrendPunto[];
  prezzo_medio_periodo: number;
};

export type TagFornitore = {
  fornitore: string;
  spesa_totale: number;
  quantita_totale: number;
  num_acquisti: number;
  prezzo_medio: number | null;
  delta_pct: number;
  incidenza_spesa: number;
};

export type TagFornitoriAggregati = {
  num_fornitori: number;
  concentrazione_top: number;
  gap_pct: number;
  prezzo_medio_tag: number | null;
  best_fornitore: string;
  best_delta_pct: number;
  worst_fornitore: string;
  worst_delta_pct: number;
  quantita_label: string;
};

export type TagAnalisiResponse = {
  vuoto: boolean;
  kpi: TagKpi | null;
  trend: TagTrend;
  fornitori: {
    fornitori: TagFornitore[];
    aggregati: TagFornitoriAggregati | null;
  };
};

// Suggerimenti

export type SuggestionItem = {
  descrizione: string;
  descrizione_key: string;
  occorrenze: number;
  fornitori_count: number;
  last_seen_date: string | null;
  selected_by_default: boolean;
};

export type TagSuggestion = {
  id: number;
  suggestion_type: "new_tag" | "extend_tag";
  status: "pending";
  suggested_tag_name: string | null;
  target_tag_id: number | null;
  cluster_key: string;
  confidence_score: number;
  matched_products_count: number;
  matched_rows_count: number;
  tag_name?: string;
  items: SuggestionItem[];
};
