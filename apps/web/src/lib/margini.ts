import { WORKER_URL, getToken, workerHeaders } from "./worker-config";

// Variante con query params (la workerGet centrale e' senza params): riusa
// comunque WORKER_URL/getToken/workerHeaders dal modulo unico.
async function workerGet<T>(
  path: string,
  params: Record<string, string | number | undefined> = {},
): Promise<T | null> {
  const token = await getToken();
  if (!token) return null;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) qs.set(k, String(v));
  }
  const url = `${WORKER_URL}${path}${qs.toString() ? `?${qs}` : ""}`;
  try {
    const res = await fetch(url, { headers: workerHeaders(token), cache: "no-store" });
    if (!res.ok) {
      console.error(`[margini] worker error:`, res.status);
      return null;
    }
    return (await res.json()) as T;
  } catch (err) {
    console.error(`[margini] fetch error:`, err);
    return null;
  }
}

export type MarginiMese = {
  mese: number;
  fatturato_iva10: number;
  fatturato_iva22: number;
  altri_ricavi_noiva: number;
  altri_costi_fb: number;
  altri_costi_spese: number;
  costo_dipendenti: number;
  costo_personale_extra: number;
  costi_fb_auto: number;
  costi_spese_auto: number;
};

export type MarginiAnnoResponse = {
  anno: number;
  mesi: MarginiMese[];
};

export type FatturatoCentri = {
  anno: number;
  mese: number;
  fatturato_food: number;
  fatturato_beverage: number;
  fatturato_alcolici: number;
  fatturato_dolci: number;
};

export type CentroCosto = {
  centro: string;
  categorie: string[];
  costo_totale: number;
  fatturato: number;
  margine: number;
  incidenza_su_fatt: number;
  incidenza_su_fb: number;
};

export type AnalisiCentriResponse = {
  centri: CentroCosto[];
  totale_costi_fb: number;
  fatturato_netto_periodo: number;
  primo_margine: number;
  primo_margine_pct: number;
  mesi_con_dati: number[];
};

export async function fetchMarginiAnno(anno: number): Promise<MarginiAnnoResponse | null> {
  return workerGet<MarginiAnnoResponse>("/api/margini", { anno });
}

export async function fetchFatturatoCentriMese(
  anno: number,
  mese: number,
): Promise<FatturatoCentri | null> {
  return workerGet<FatturatoCentri>("/api/margini/fatturato-centri", { anno, mese });
}

export async function fetchAnalisiCentri(
  data_da: string,
  data_a: string,
): Promise<AnalisiCentriResponse | null> {
  return workerGet<AnalisiCentriResponse>("/api/margini/analisi-centri", { data_da, data_a });
}
