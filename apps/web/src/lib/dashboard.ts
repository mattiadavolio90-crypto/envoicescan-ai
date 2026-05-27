import { cookies } from "next/headers";
import { SESSION_COOKIE } from "./auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

export type DashboardKpi = {
  fatture_uniche: number;
  righe_totali: number;
  spesa_totale: number;
  spesa_mese_corrente: number;
  spesa_mese_precedente: number;
  prima_fattura: string | null;
  ultima_fattura: string | null;
};

export type SpesaMensilePoint = { mese: string; spesa: number };
export type TopItem = { nome: string; spesa: number; righe: number };

export type DashboardStats = {
  kpi: DashboardKpi;
  spesa_mensile: SpesaMensilePoint[];
  top_fornitori: TopItem[];
  top_categorie: TopItem[];
};

export async function fetchDashboardStats(): Promise<DashboardStats | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(`${WORKER_URL}/api/dashboard/stats`, {
      method: "GET",
      headers,
      cache: "no-store",
    });
    if (!res.ok) {
      console.error("[dashboard.stats] worker error:", res.status, await res.text().catch(() => ""));
      return null;
    }
    return (await res.json()) as DashboardStats;
  } catch (err) {
    console.error("[dashboard.stats] fetch error:", err);
    return null;
  }
}
