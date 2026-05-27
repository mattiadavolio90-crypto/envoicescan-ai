import { cookies } from "next/headers";
import { SESSION_COOKIE } from "./auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

export type TipoProdotti = "food_beverage" | "spese_generali" | "tutti";

export type RigaFattura = {
  id: number;
  file_origine: string;
  numero_riga: number;
  data_documento: string | null;
  fornitore: string;
  descrizione: string;
  quantita: number | null;
  unita_misura: string | null;
  prezzo_unitario: number | null;
  totale_riga: number | null;
  categoria: string | null;
  needs_review: boolean | null;
  tipo_documento: string | null;
  data_competenza: string | null;
  piva_cedente: string | null;
  created_at: string | null;
};

export type ArticoloAggregato = {
  descrizione: string;
  categoria: string | null;
  fornitore_principale: string;
  altri_fornitori: string[];
  ultimo_acquisto: string | null;
  quantita_totale: number;
  unita_misura: string | null;
  prezzo_unit_medio: number | null;
  prezzo_unit_trend_pct: number | null;
  totale_speso: number;
  num_acquisti: number;
  righe_ids: number[];
  needs_review: boolean;
  is_nuovo: boolean;
};

export type ArticoliResponse = {
  articoli: ArticoloAggregato[];
  total: number;
};

export type KpiResponse = {
  totale: number;
  num_righe: number;
  num_prodotti: number;
  media_mensile: number;
  delta_totale_pct: number | null;
  delta_righe_pct: number | null;
  delta_prodotti_pct: number | null;
  delta_media_pct: number | null;
};

export type MeseDisponibile = {
  year: number;
  month: number;
  label: string;
  count: number;
};

export type PivotRowData = {
  dimensione: string;
  periodi: Record<string, number>;
  totale: number;
  media: number;
  incidenza_pct: number;
  sparkline: number[];
};

export type PivotResponse = {
  rows: PivotRowData[];
  periodi: string[];
  periodi_labels: string[];
  granularita: "mese" | "trimestre" | "anno";
  totali_periodo: Record<string, number>;
  grand_total: number;
};

export type TrendPunto = {
  periodo: string;
  label: string;
  valore: number;
};

export type TrendSerie = {
  valore: string;
  punti: TrendPunto[];
  media: number;
  totale: number;
};

export type TrendResponse = {
  serie: TrendSerie[];
  periodi: string[];
  periodi_labels: string[];
};

export type FattureFilters = {
  data_da?: string;
  data_a?: string;
  tipo_prodotti?: TipoProdotti;
  fornitore?: string;
  categoria?: string;
  needs_review?: boolean;
  search?: string;
  page?: number;
  page_size?: number;
};

async function getToken(): Promise<string | null> {
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE)?.value ?? null;
}

function buildParams(obj: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null || v === "") continue;
    p.set(k, String(v));
  }
  return p.toString();
}

async function workerGet<T>(path: string, params: Record<string, any> = {}): Promise<T | null> {
  const token = await getToken();
  if (!token) return null;
  const qs = buildParams(params);
  const url = `${WORKER_URL}${path}${qs ? `?${qs}` : ""}`;
  try {
    const res = await fetch(url, { headers: workerHeaders(token), cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function fetchKpi(
  data_da?: string,
  data_a?: string,
  tipo_prodotti?: TipoProdotti,
): Promise<KpiResponse | null> {
  return workerGet<KpiResponse>("/api/fatture/kpi", { data_da, data_a, tipo_prodotti });
}

export async function fetchMesiDisponibili(): Promise<MeseDisponibile[]> {
  const data = await workerGet<{ mesi: MeseDisponibile[] }>("/api/fatture/mesi-disponibili");
  return data?.mesi ?? [];
}

export async function fetchArticoliAggregati(filters: {
  data_da?: string;
  data_a?: string;
  tipo_prodotti?: TipoProdotti;
  categoria?: string;
  search?: string;
  solo_nuovi?: boolean;
  solo_da_verificare?: boolean;
}): Promise<ArticoliResponse | null> {
  return workerGet<ArticoliResponse>("/api/fatture/articoli-aggregati", filters);
}

export async function fetchRigheArticolo(
  descrizione: string,
  data_da?: string,
  data_a?: string,
): Promise<RigaFattura[]> {
  const data = await workerGet<RigaFattura[]>("/api/fatture/righe-articolo", {
    descrizione,
    data_da,
    data_a,
  });
  return data ?? [];
}

export async function fetchPivot(
  dimensione: "categoria" | "fornitore",
  filters: { data_da?: string; data_a?: string; tipo_prodotti?: TipoProdotti } = {},
): Promise<PivotResponse | null> {
  return workerGet<PivotResponse>("/api/fatture/pivot", { dimensione, ...filters });
}

export async function fetchTrend(
  dimensione: "categoria" | "fornitore",
  valori: string[],
  filters: { data_da?: string; data_a?: string; tipo_prodotti?: TipoProdotti } = {},
): Promise<TrendResponse | null> {
  return workerGet<TrendResponse>("/api/fatture/trend", {
    dimensione,
    valori: valori.join(","),
    ...filters,
  });
}

export async function fetchCategorie(): Promise<{ categorie: string[]; usate: string[] }> {
  const data = await workerGet<{ categorie: string[]; usate: string[] }>("/api/fatture/categorie");
  return data ?? { categorie: [], usate: [] };
}

export async function fetchFatture(filters: FattureFilters = {}): Promise<{
  righe: RigaFattura[];
  total: number;
  page: number;
  page_size: number;
} | null> {
  return workerGet("/api/fatture", { ...filters, page: filters.page ?? 1, page_size: filters.page_size ?? 50 });
}
