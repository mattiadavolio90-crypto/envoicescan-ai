// Il periodo dell'analisi di un tag: cosa diventa quando si sceglie una delle
// tre voci del controllo «Periodo» (Fase 3 di «Analisi e Tag», 13/10/2026).
// Sta qui e non nel .tsx perche' un componente non e' raggiungibile dai test
// (tests/test_tag_periodo_frontend.py).

export type PeriodoPreset = "anno_corrente" | "mese_specifico" | "personalizzato";

export type PeriodoTag = {
  anno: number;
  mese: number | null;
  preset: PeriodoPreset;
  dataDa?: string;
  dataA?: string;
};

/**
 * Il periodo dopo aver scelto `scelta`, o `null` se e' gia' quello attivo
 * (un secondo clic non ricarica l'analisi).
 *
 * - «Anno in corso»: l'anno di `oggi`, senza mese.
 * - «Mese»: il mese in corso, subito. Prima la voce apriva solo il menu dei mesi
 *   e i numeri restavano quelli dell'anno mentre il controllo diceva «Mese».
 * - «Personalizzato»: tiene anno e mese attuali e le date gia' scritte; finche'
 *   le date non ci sono entrambe, chi chiama ricarica col periodo di prima.
 */
export function periodoScelto(
  scelta: PeriodoPreset,
  attuale: { anno: number; mese: number | null; preset: PeriodoPreset; dataDa: string | null; dataA: string | null },
  oggi: Date,
): PeriodoTag | null {
  if (scelta === attuale.preset) return null;
  if (scelta === "anno_corrente") return { anno: oggi.getFullYear(), mese: null, preset: scelta };
  if (scelta === "mese_specifico") return { anno: oggi.getFullYear(), mese: oggi.getMonth() + 1, preset: scelta };
  return {
    anno: attuale.anno,
    mese: attuale.mese,
    preset: scelta,
    dataDa: attuale.dataDa ?? undefined,
    dataA: attuale.dataA ?? undefined,
  };
}
