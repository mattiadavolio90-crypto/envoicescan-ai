// Quello che il pannello "Assistente" MANDA al backend — separato dal
// componente per la stessa ragione di catena-costi-gruppo.ts: un payload
// sbagliato si vede solo sui dati veri, e un test sul componente non lo prende.

import { parseDecimaleIt } from "@/lib/format";

export const SOGLIA_MIN = 0;
export const SOGLIA_MAX = 50;
export const SOGLIA_DEFAULT = 5;

export type Topic = { key: string; enabled: boolean; bloccato?: boolean };

// Clamp [0,50] come il backend. Un testo non numerico -> default 5.
//
// Attenzione al `|| 5`: cattura NaN ma anche lo ZERO scritto apposta, che
// diventa 5. E' il comportamento voluto (soglia 0 vorrebbe dire "avvisami per
// qualsiasi variazione", cioe' rumore continuo), non una svista.
export function normalizzaSoglia(testo: string | null | undefined): number {
  return Math.min(SOGLIA_MAX, Math.max(SOGLIA_MIN, parseDecimaleIt(testo) || SOGLIA_DEFAULT));
}

// Un topic bloccato non e' disattivabile: non finisce mai fra i disabilitati,
// nemmeno se arrivasse con enabled=false.
export function topicsDisabilitati(topics: Topic[]): string[] {
  return topics.filter((t) => !t.enabled && !t.bloccato).map((t) => t.key);
}

// Generico: i topic reali portano anche label/descrizione, e una firma su
// Topic[] li scarterebbe silenziosamente dallo stato del componente.
export function toggleTopic<T extends Topic>(topics: T[], key: string, enabled: boolean): T[] {
  return topics.map((t) => (t.key === key && !t.bloccato ? { ...t, enabled } : t));
}

// L'avviso prezzi governa la soglia: spento, il campo non serve.
export function alertPrezziAttivo(topics: Topic[]): boolean {
  return topics.find((t) => t.key === "price_alert")?.enabled ?? true;
}

// I nomi dei campi sono il contratto con POST /api/home/config: non sono
// liberi. `price_alert_threshold`, non "soglia": rinominarlo qui significa
// mandare al backend un campo che ignora, in silenzio e senza errori.
export type PayloadConfig = {
  nome_referente: string | null;
  topics_disabled: string[];
  chat_ai_enabled: boolean;
  price_alert_threshold: number;
  giorni_chiusura_settimanali: number;
};

export function costruisciPayloadConfig(opts: {
  topics: Topic[];
  soglia: string | null | undefined;
  nome: string;
  chatEnabled: boolean;
  giorniChiusura: number;
}): PayloadConfig {
  return {
    nome_referente: opts.nome.trim() || null,
    topics_disabled: topicsDisabilitati(opts.topics),
    chat_ai_enabled: opts.chatEnabled,
    price_alert_threshold: normalizzaSoglia(opts.soglia),
    giorni_chiusura_settimanali: opts.giorniChiusura,
  };
}
