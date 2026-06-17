import { cache } from "react";
import { workerGet } from "./worker";

// Modalità catena — vista gruppo multi-sede, sola lettura. Fase 1: overview.

export type GruppoKpi = {
  fatturato: number;
  margine_medio_perc: number;
  spesa_fornitori: number;
};

export type RankingPV = {
  ristorante_id: string;
  nome: string;
  margine_perc: number | null; // null = dati incompleti (nessun ricavo)
  fatturato: number;
  colore: "verde" | "giallo" | "rosso" | "grigio";
  dati_incompleti: boolean;
};

export type GruppoOverview = {
  nome_gruppo: string;
  num_pv: number;
  periodo_label: string;
  kpi: GruppoKpi;
  salute_indice: number;
  salute_colore: "verde" | "giallo" | "rosso";
  ranking: RankingPV[];
};

export const fetchGruppoOverview = cache(
  async (): Promise<GruppoOverview | null> =>
    workerGet<GruppoOverview>("/api/gruppo/overview", "gruppo.overview"),
);
