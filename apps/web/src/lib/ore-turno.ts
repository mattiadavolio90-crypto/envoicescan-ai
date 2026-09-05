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
