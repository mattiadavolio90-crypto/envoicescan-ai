import { cache } from "react";
import { workerGet } from "./worker";

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
  chat_ai_enabled: boolean;
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
  return workerGet<AssistantConfig>("/api/home/config", "home.config");
}

export async function fetchKpi(): Promise<HomeKpi | null> {
  return workerGet<HomeKpi>("/api/home/kpi", "home.kpi");
}

export async function fetchSalute(): Promise<Salute | null> {
  return workerGet<Salute>("/api/home/salute", "home.salute");
}

// Avvolto in cache() di React: layout e page chiedono entrambi il briefing nello
// stesso render -> una sola chiamata al worker (era duplicata, rallentava la Home).
export const fetchBriefing = cache(
  async (): Promise<Briefing | null> =>
    workerGet<Briefing>("/api/home/briefing", "home.briefing"),
);
