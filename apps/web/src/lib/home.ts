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
  // Dati mancanti (label brevi): se non vuota, NON si mostra il verde "tutto a
  // posto" ma una nota neutra. Gateato dal backend con tutto_ok.
  dati_mancanti?: string[];
  azioni: BriefingAzione[];
  generated_at: string | null;
};

export type ConfigTopic = {
  key: string;
  label: string;
  enabled: boolean;
  bloccato: boolean;
  descrizione: string; // micro-spiegazione di cosa fa l'avviso (per i ristoratori)
};

export type AssistantConfig = {
  nome_referente: string;
  topics: ConfigTopic[];
  chat_ai_enabled: boolean;
  chat_limite_giorno: number; // 0 = piano free, chat non disponibile
  chat_domande_oggi: number; // domande gia' consumate oggi (valore iniziale del contatore)
  // Soglia % alert prezzi: da qui si imposta quando scatta l'avviso "Alert prezzi".
  // In pagina Prezzi resta solo come filtro di visualizzazione.
  price_alert_threshold: number;
  // Se true, gli avvisi prezzi si limitano ai prodotti preferiti (stella in pagina
  // Prezzi) + tag. Se non hai preferiti, ricevi solo gli avvisi sui tag.
  alert_prezzi_solo_preferiti: boolean;
  // Giorni di chiusura a settimana (0-6): tolleranza dell'avviso "ricavi automatici
  // assenti". 0 = sempre aperto -> avviso dopo 1 giorno senza ricavi.
  giorni_chiusura_settimanali: number;
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
  // true = il mese ha ricavi ma zero costi (food + spese): MOL e food cost non
  // sono reali. La card lo spiega e nasconde le variazioni "in meglio".
  costi_mancanti?: boolean;
  // Sparkline andamento MOL dei mesi con dati dell'anno corrente (vuoto se <2 punti).
  mol_mensile: { mese: number; mol: number }[];
  mol_mensile_anno: number | null;
};

// Tutte avvolte in cache() come fetchBriefing: nello stesso render piu' punti
// chiedono lo stesso dato (es. layout /m + chat page chiamano entrambi
// fetchConfig) -> un solo round-trip al worker invece di due. La cache vive solo
// per la durata della singola request.
export const fetchConfig = cache(
  async (): Promise<AssistantConfig | null> =>
    workerGet<AssistantConfig>("/api/home/config", "home.config"),
);

export const fetchKpi = cache(
  async (): Promise<HomeKpi | null> => workerGet<HomeKpi>("/api/home/kpi", "home.kpi"),
);

export const fetchSalute = cache(
  async (): Promise<Salute | null> => workerGet<Salute>("/api/home/salute", "home.salute"),
);

// Avvolto in cache() di React: layout e page chiedono entrambi il briefing nello
// stesso render -> una sola chiamata al worker (era duplicata, rallentava la Home).
export const fetchBriefing = cache(
  async (): Promise<Briefing | null> =>
    workerGet<Briefing>("/api/home/briefing", "home.briefing"),
);
