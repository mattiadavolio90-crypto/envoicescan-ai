export type RicavoGiornaliero = {
  id?: string;
  data: string;
  fatturato_iva10: number;
  fatturato_iva22: number;
  altri_ricavi_noiva: number;
  coperti?: number | null;
  source: "manuale" | "xls" | "email";
};

/* ─── Coperti ─────────────────────────────────────────────────────────────── */
export type CopertiMese = {
  anno: number;
  mese: number;
  label: string;
  coperti: number | null;
  ricavi_netto: number;
  ricavi_lordo: number;
  scontrino_medio_netto: number | null;
  scontrino_medio_lordo: number | null;
  costo_fb: number;
  costo_fb_per_coperto: number | null;
};

export type CopertiGiorno = {
  data: string;
  coperti: number;
  ricavi_netto: number;
  ricavi_lordo: number;
};

export type CopertiKpi = {
  coperti_totali: number | null;
  coperti_medi_giorno: number | null;
  scontrino_medio_netto: number | null;
  scontrino_medio_lordo: number | null;
  giorno_top: CopertiGiorno | null;
  giorno_min: CopertiGiorno | null;
  media_per_dow: (number | null)[]; // lun..dom
  delta_coperti_pct: number | null;
  confronto_label: string;
  costo_fb_per_coperto: number | null;
  costo_fb_per_coperto_delta_pct: number | null;
  efficienza_commento: string | null;
};

export type CopertiAnalisiResponse = {
  mesi: CopertiMese[];
  totale_coperti: number | null;
  totale_ricavi_netto: number;
  totale_ricavi_lordo: number;
  giorni: CopertiGiorno[];
  ha_dati_giornalieri: boolean;
  kpi: CopertiKpi;
};

/* ─── Costo materia prima/coperto per categoria (dialog) ──────────────────── */
export type CategoriaCopertoMese = {
  anno: number;
  mese: number;
  label: string;
  valore: number | null;
};

export type CategoriaCopertoRiga = {
  categoria: string;
  per_mese: CategoriaCopertoMese[];
  media: number | null;
};

export type CopertiCategorieResponse = {
  mesi_label: string[];
  righe: CategoriaCopertoRiga[];
};

export type RicaviGiornalieriResponse = {
  items: RicavoGiornaliero[];
  totale_iva10: number;
  totale_iva22: number;
  totale_altri: number;
  totale_netto: number;
  giorni_con_dati: number;
};

export type RicaviBatchUpsertResponse = {
  inserted: number;
  updated: number;
  skipped: number;
  errors: string[];
};

export type RicaviImportSedeDettaglio = {
  ristorante_id: string;
  nome: string | null;
  giorni: number;
  coperti_giorni: number;
};

export type RicaviImportXlsResponse = {
  parsed_rows: number;
  inserted: number;
  updated: number;
  skipped: number;
  coperti_giorni: number;
  errors: string[];
  preview: RicavoGiornaliero[];
  dettaglio_sedi: RicaviImportSedeDettaglio[];
};
