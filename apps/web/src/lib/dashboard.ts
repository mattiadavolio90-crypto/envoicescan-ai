import { workerGet } from "./worker";

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
  return workerGet<DashboardStats>("/api/dashboard/stats", "dashboard.stats");
}
