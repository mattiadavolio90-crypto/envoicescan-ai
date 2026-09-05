// Come si ripartiscono le ore di un turno fra ordinarie e straordinario.
//
// Modello in vigore dal 05/09/2026: le ore extra sono un SOTTOINSIEME delle
// ore del turno, non un addendo. Un 09-17 con 2 extra sono 8 ore totali di cui
// 2 di straordinario, non 10. Prima erano additive: se tocchi questo file, i
// punti da allineare sono il worker (_ore_turno), margini.py, workspace.py,
// personale_export_service.py, il tab desktop e /m — cercali, non fidarti
// di questa lista.
//
// Il clamp non e' difensivo per abitudine: senza, un ore_extra maggiore delle
// ore lavorate fa uscire l'ordinario negativo e gonfia il monte ore totale
// (8 ore con 10 extra diventavano 10 ore e il 25% di costo in piu').

export type RipartizioneOre = {
  /** Ore ordinarie: totale meno lo straordinario, mai negative. */
  ordinarie: number;
  /** Straordinario effettivo, mai superiore alle ore del turno. */
  extra: number;
};

/**
 * Divide le ore di un turno fra ordinarie e straordinario.
 *
 * `ordinarie + extra` e' sempre pari a `oreTotali` (a meno di negativi in
 * ingresso, che valgono zero): e' la proprieta' che rende il totale mostrato
 * uguale alle ore davvero lavorate.
 */
export function ripartisciOre(oreTotali: number, oreExtra: number | null | undefined): RipartizioneOre {
  const tot = Math.max(0, oreTotali || 0);
  const extra = Math.min(Math.max(0, oreExtra || 0), tot);
  return { ordinarie: Math.round((tot - extra) * 100) / 100, extra };
}

/** Il minimo che serve per aggregare: il resto della riga turno non conta qui. */
export type TurnoAggregabile = {
  dipendente_id: string;
  tipo_giorno?: string | null;
  mensile?: boolean | null;
  ore_extra?: number | null;
  costo_orario?: number | null;
  costo_orario_extra?: number | null;
  lordo_mensile?: number | null;
  importo_extra?: number | null;
};

export type TotaliPersona = {
  oreStd: Record<string, number>;
  oreExt: Record<string, number>;
  costoStd: Record<string, number>;
  costoExt: Record<string, number>;
  costoTot: Record<string, number>;
};

/**
 * Somma ore e costo per persona, dividendo ordinarie e straordinario.
 *
 * Vive qui e non nel .tsx perche' e' il punto che si e' rotto: la libreria era
 * corretta ma il chiamante leggeva `ore_extra` grezzo, e un test sulla sola
 * `ripartisciOre` restava verde. In `lib/` il TypeScript vero e' eseguibile
 * dai test (tests/helpers_ts.py), quindi il presidio copre il consumatore.
 *
 * `oreDi` arriva dal chiamante perche' il calcolo dagli orari sta nel .tsx
 * insieme al parsing dei campi form; qui serve solo il totale gia' risolto.
 */
export function aggregaPerPersona(
  turni: TurnoAggregabile[],
  nomeDi: (t: TurnoAggregabile) => string,
  oreDi: (t: TurnoAggregabile) => number,
): TotaliPersona {
  const oreStd: Record<string, number> = {};
  const oreExt: Record<string, number> = {};
  const costoStd: Record<string, number> = {};
  const costoExt: Record<string, number> = {};
  const costoTot: Record<string, number> = {};
  for (const t of turni) {
    // riposo/ferie/malattia: fuori da ore e costo lavorato
    if ((t.tipo_giorno ?? "turno") !== "turno") continue;
    const n = nomeDi(t);
    const { ordinarie, extra } = ripartisciOre(oreDi(t), t.ore_extra);
    oreStd[n] = (oreStd[n] ?? 0) + ordinarie;
    oreExt[n] = (oreExt[n] ?? 0) + extra;
    if (t.mensile) {
      // Riga mensile: costo dal lordo reale della busta paga, non da tariffa.
      const lordo = t.lordo_mensile ?? 0;
      const impExt = t.importo_extra ?? 0;
      costoStd[n] = (costoStd[n] ?? 0) + Math.max(0, lordo - impExt);
      costoExt[n] = (costoExt[n] ?? 0) + impExt;
      costoTot[n] = (costoTot[n] ?? 0) + lordo;
      continue;
    }
    const coStd = t.costo_orario ?? null;
    if (coStd == null) continue;   // turno senza tariffa: non inventiamo un costo
    const coExt = t.costo_orario_extra ?? coStd;
    costoStd[n] = (costoStd[n] ?? 0) + ordinarie * coStd;
    costoExt[n] = (costoExt[n] ?? 0) + extra * coExt;
    costoTot[n] = (costoTot[n] ?? 0) + ordinarie * coStd + extra * coExt;
  }
  return { oreStd, oreExt, costoStd, costoExt, costoTot };
}

/**
 * Costo di un turno giornaliero: ordinarie x tariffa + extra x tariffa extra.
 *
 * Estratta perche' la stessa formula viveva in tre punti (tab desktop, /m,
 * riepilogo mensile) e uno di essi e' rimasto indietro per giorni. Ritorna 0
 * senza tariffa: un turno senza costo_orario non vale zero euro "per default",
 * semplicemente non lo sappiamo, e inventarlo falserebbe il MOL.
 */
export function costoTurnoGiornaliero(
  oreTotali: number,
  oreExtra: number | null | undefined,
  costoOrario: number | null | undefined,
  costoOrarioExtra?: number | null,
): number {
  if (costoOrario == null) return 0;
  const { ordinarie, extra } = ripartisciOre(oreTotali, oreExtra);
  const tariffaExtra = costoOrarioExtra ?? costoOrario;
  return ordinarie * costoOrario + extra * tariffaExtra;
}
