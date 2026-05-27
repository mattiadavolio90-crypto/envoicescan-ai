import { cookies } from "next/headers";
import { SESSION_COOKIE } from "./auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

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
};

export type FattureListResponse = {
  righe: RigaFattura[];
  total: number;
  page: number;
  page_size: number;
};

export type PivotRow = {
  dimensione: string;
  mesi: Record<string, number>;
  totale: number;
};

export type PivotResponse = {
  rows: PivotRow[];
  mesi_disponibili: string[];
};

export type FattureFilters = {
  data_da?: string;
  data_a?: string;
  fornitore?: string;
  categoria?: string;
  needs_review?: boolean;
  page?: number;
  page_size?: number;
};

async function getToken(): Promise<string | null> {
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE)?.value ?? null;
}

export async function fetchFatture(filters: FattureFilters = {}): Promise<FattureListResponse | null> {
  const token = await getToken();
  if (!token) return null;

  const params = new URLSearchParams();
  if (filters.data_da) params.set("data_da", filters.data_da);
  if (filters.data_a) params.set("data_a", filters.data_a);
  if (filters.fornitore) params.set("fornitore", filters.fornitore);
  if (filters.categoria) params.set("categoria", filters.categoria);
  if (filters.needs_review !== undefined) params.set("needs_review", String(filters.needs_review));
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.page_size ?? 50));

  try {
    const res = await fetch(`${WORKER_URL}/api/fatture?${params}`, {
      headers: workerHeaders(token),
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as FattureListResponse;
  } catch {
    return null;
  }
}

export async function fetchPivot(
  dimensione: "categoria" | "fornitore",
  data_da?: string,
  data_a?: string,
): Promise<PivotResponse | null> {
  const token = await getToken();
  if (!token) return null;

  const params = new URLSearchParams({ dimensione });
  if (data_da) params.set("data_da", data_da);
  if (data_a) params.set("data_a", data_a);

  try {
    const res = await fetch(`${WORKER_URL}/api/fatture/pivot?${params}`, {
      headers: workerHeaders(token),
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as PivotResponse;
  } catch {
    return null;
  }
}

export async function fetchCategorie(): Promise<string[]> {
  const token = await getToken();
  if (!token) return [];
  try {
    const res = await fetch(`${WORKER_URL}/api/fatture/categorie`, {
      headers: workerHeaders(token),
      cache: "no-store",
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.categorie ?? [];
  } catch {
    return [];
  }
}
