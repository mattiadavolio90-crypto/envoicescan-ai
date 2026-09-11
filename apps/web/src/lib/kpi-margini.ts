// I nomi dei KPI di /api/margini/analisi viaggiano come stringhe DISPLAY su
// entrambi i lati: la response non ha una chiave stabile. Il match fra il gauge
// e il suo commento e' quindi un confronto di etichette, e ha gia' sbagliato
// due volte — il gauge "Costi Gestione" cercava se stesso mentre il worker
// manda "Spese Generali", e restava senza emoji ne' commento.
//
// Col retail il rischio raddoppia: il worker rinomina il KPI merce in «Costo
// Merce» (_nome_kpi_per_settore, services/routers/margini.py), e un frontend
// che cercasse il letterale "Food Cost" perderebbe colore E diagnosi senza
// dare errore. Questa logica sta in `lib/` perche' e' l'unico posto che i test
// riescono a ESEGUIRE: un .tsx non e' raggiungibile da tests/helpers_ts.py.

import { costoMerceLabel, type Settore } from "@/lib/categorie-spesa";

export type CommentoKpi = {
  kpi_nome: string;
  percentuale: string;
  commento: string;
  emoji: string;
  colore: string;
};

/** I nomi KPI viaggiano come stringhe display su entrambi i lati (nessuna chiave
 *  stabile nella response): il confronto ignora spazi, gradi e maiuscole. */
export function normalizzaKpi(nome: string): string {
  return nome.toLowerCase().replace(/[°\s]/g, "");
}

/** Il commento che il worker ha emesso per questo KPI, o undefined. */
export function commentoPerKpi(
  commenti: CommentoKpi[],
  kpiNome: string,
): CommentoKpi | undefined {
  return commenti.find((c) => normalizzaKpi(c.kpi_nome) === normalizzaKpi(kpiNome));
}

/** Il nome con cui il worker manda il KPI merce per questo settore: deve
 *  combaciare con `_nome_kpi_per_settore` del backend, o il gauge non trova il
 *  suo commento. */
export function nomeKpiMerce(settore?: Settore | null): string {
  return costoMerceLabel(settore);
}
