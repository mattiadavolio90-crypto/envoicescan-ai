// Cosa fare del risultato di /api/margini/costo-personale-turni.
//
// Il costo del personale nel MOL vive in margini_mensili (costo_dipendenti +
// costo_personale_extra) e ci arriva SOLO da un inserimento: i turni non lo
// alimentano da soli. Il "Recupera dal tab Personale" e' quell'inserimento
// assistito, quindi decidere quando NON scrivere conta quanto il calcolo:
// un recupero a vuoto che sovrascrive azzera il costo del mese nel MOL.
//
// Le assenze (ferie/malattia a carico datore) restano fuori dal totale: il
// worker le tiene isolate da costo_dipendenti di proposito (vedi
// tests/test_turni_mensili.py::TestMarginiCostoAssenze). Qui le riportiamo
// solo perche' l'utente sappia che esistono e possa aggiungerle a mano.

export type CalcoloTurni = {
  costo_dipendenti: number;
  costo_personale_extra: number;
  costo_assenze_a_carico: number;
  ore_totali: number;
  ore_extra: number;
  n_turni: number;
  n_senza_costo: number;
  n_giorni_assenza: number;
};

export type EsitoRecupero =
  | { azione: "nessun_turno" }
  | { azione: "non_valorizzati"; nSenzaCosto: number }
  | { azione: "compila"; lordo: number; extra: number; nSenzaCosto: number };

/**
 * Decide se il risultato del recupero puo' compilare i campi.
 *
 * "compila" solo se dai turni esce davvero un costo: con tutti i turni privi di
 * costo orario il totale e' 0, e scriverlo cancellerebbe il valore inserito a
 * mano (toStr(0) === ""). In quel caso si lascia il campo com'e'.
 */
export function esitoRecuperoTurni(d: CalcoloTurni | null): EsitoRecupero {
  if (!d || d.n_turni <= 0) return { azione: "nessun_turno" };
  const lordo = d.costo_dipendenti || 0;
  const extra = d.costo_personale_extra || 0;
  const nSenzaCosto = d.n_senza_costo || 0;
  if (lordo <= 0 && extra <= 0) return { azione: "non_valorizzati", nSenzaCosto };
  return { azione: "compila", lordo, extra, nSenzaCosto };
}

/**
 * Il costo delle assenze va mostrato solo se c'e' davvero (importo a carico
 * datore > 0). n_giorni_assenza da solo non basta: un riposo non costa nulla.
 */
export function mostraCostoAssenze(d: CalcoloTurni | null): boolean {
  return !!d && (d.costo_assenze_a_carico || 0) > 0;
}
