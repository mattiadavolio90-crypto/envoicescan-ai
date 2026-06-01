import { cache } from "react";
import { cookies } from "next/headers";
import { SESSION_COOKIE } from "./auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

export type BriefingAzione = {
  id: string;
  topic_key: string;
  severity: "info" | "warning" | "error" | "success";
  testo: string;
  cta_label: string;
  cta_page: string;
};

export type Briefing = {
  saluto: string;
  data: string;
  narrativa: string;
  severity_max: "info" | "warning" | "error" | "success";
  tutto_ok: boolean;
  azioni: BriefingAzione[];
  generated_at: string | null;
};

export type ConfigTopic = {
  key: string;
  label: string;
  enabled: boolean;
  bloccato: boolean;
};

export type AssistantConfig = {
  nome_referente: string;
  topics: ConfigTopic[];
};

export type SaluteVoce = {
  key: string;
  label: string;
  ok: boolean;
  dettaglio: string;
  cta_page: string | null;
};

export type Salute = {
  indice: number;
  colore: "verde" | "giallo" | "rosso";
  mese_label: string;
  voci: SaluteVoce[];
};

export type HomeKpi = {
  periodo_label: string;
  is_mese_in_corso: boolean;
  fatturato: number;
  food_cost_pct: number | null;
  costo_personale: number;
  spese_generali: number;
  mol: number;
  has_data: boolean;
  confronto_label: string | null;
  fatturato_delta_pct: number | null;
  food_cost_delta_pp: number | null;
  personale_delta_pct: number | null;
  spese_delta_pct: number | null;
  mol_delta_pct: number | null;
};

export async function fetchConfig(): Promise<AssistantConfig | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(`${WORKER_URL}/api/home/config`, {
      method: "GET",
      headers,
      cache: "no-store",
    });
    if (!res.ok) {
      console.error("[home.config] worker error:", res.status, await res.text().catch(() => ""));
      return null;
    }
    return (await res.json()) as AssistantConfig;
  } catch (err) {
    console.error("[home.config] fetch error:", err);
    return null;
  }
}

export async function fetchKpi(): Promise<HomeKpi | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(`${WORKER_URL}/api/home/kpi`, {
      method: "GET",
      headers,
      cache: "no-store",
    });
    if (!res.ok) {
      console.error("[home.kpi] worker error:", res.status, await res.text().catch(() => ""));
      return null;
    }
    return (await res.json()) as HomeKpi;
  } catch (err) {
    console.error("[home.kpi] fetch error:", err);
    return null;
  }
}

export async function fetchSalute(): Promise<Salute | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(`${WORKER_URL}/api/home/salute`, {
      method: "GET",
      headers,
      cache: "no-store",
    });
    if (!res.ok) {
      console.error("[home.salute] worker error:", res.status, await res.text().catch(() => ""));
      return null;
    }
    return (await res.json()) as Salute;
  } catch (err) {
    console.error("[home.salute] fetch error:", err);
    return null;
  }
}

// Avvolto in cache() di React: layout e page chiedono entrambi il briefing nello
// stesso render -> una sola chiamata al worker (era duplicata, rallentava la Home).
export const fetchBriefing = cache(async (): Promise<Briefing | null> => {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(`${WORKER_URL}/api/home/briefing`, {
      method: "GET",
      headers,
      cache: "no-store",
    });
    if (!res.ok) {
      console.error("[home.briefing] worker error:", res.status, await res.text().catch(() => ""));
      return null;
    }
    return (await res.json()) as Briefing;
  } catch (err) {
    console.error("[home.briefing] fetch error:", err);
    return null;
  }
});
