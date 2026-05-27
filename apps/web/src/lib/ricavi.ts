export type RicavoGiornaliero = {
  id?: string;
  data: string;
  fatturato_iva10: number;
  fatturato_iva22: number;
  altri_ricavi_noiva: number;
  source: "manuale" | "xls" | "email";
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

export type RicaviImportXlsResponse = {
  parsed_rows: number;
  inserted: number;
  updated: number;
  skipped: number;
  errors: string[];
  preview: RicavoGiornaliero[];
};
