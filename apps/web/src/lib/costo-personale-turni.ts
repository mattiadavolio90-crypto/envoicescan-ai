// Cosa fare del risultato di /api/margini/costo-personale-turni.
//
// Il costo del personale nel MOL vive in margini_mensili in TRE voci che si
// sommano: costo_dipendenti («Lordo»), costo_personale_extra («Ore extra») e
// costo_personale_chiamata («Chiamata»). Ci arriva SOLO da un inserimento: i
// turni non lo alimentano da soli. Il "Recupera dal tab Personale" e' quell'
// inserimento assistito, quindi decidere quando NON scrivere conta quanto il
// calcolo: un recupero a vuoto che sovrascrive azzera il costo del mese nel MOL.
//
// Le assenze (ferie/malattia a carico datore) restano fuori dal totale: il
// worker le tiene isolate da costo_dipendenti di proposito (vedi
// tests/test_turni_mensili.py::TestMarginiCostoAssenze). Qui le riportiamo
// solo perche' l'utente sappia che esistono e possa aggiungerle a mano.
//
// costo_personale_chiamata e n_con_stipendio sono arrivati dopo: una risposta
// che non li porta (worker non ancora aggiornato) vale 0, non un guasto.

export type CalcoloTurni = {
  costo_dipendenti: number;
  costo_personale_extra: number;
  costo_personale_chiamata?: number;
  costo_assenze_a_carico: number;
  ore_totali: number;
  ore_extra: number;
  n_turni: number;
  n_senza_costo: number;
  n_con_stipendio?: number;
  n_giorni_assenza: number;
};

export type EsitoRecupero =
  | { azione: "nessun_turno" }
  | { azione: "non_valorizzati"; nSenzaCosto: number }
  | { azione: "compila"; lordo: number; extra: number; chiamata: number; nSenzaCosto: number };

function numero(v: number | null | undefined): number {
  return typeof v === "number" && Number.isFinite(v) ? v : 0;
}

/**
 * Decide se il risultato del recupero puo' compilare i campi.
 *
 * "compila" solo se dai turni esce davvero un costo, in almeno una delle tre
 * voci: con tutti i turni privi di costo il totale e' 0, e scriverlo
 * cancellerebbe il valore inserito a mano (toStr(0) === ""). In quel caso si
 * lasciano i campi come sono.
 */
export function esitoRecuperoTurni(d: CalcoloTurni | null): EsitoRecupero {
  if (!d || d.n_turni <= 0) return { azione: "nessun_turno" };
  const lordo = numero(d.costo_dipendenti);
  const extra = numero(d.costo_personale_extra);
  const chiamata = numero(d.costo_personale_chiamata);
  const nSenzaCosto = numero(d.n_senza_costo);
  if (lordo <= 0 && extra <= 0 && chiamata <= 0) return { azione: "non_valorizzati", nSenzaCosto };
  return { azione: "compila", lordo, extra, chiamata, nSenzaCosto };
}

/**
 * Il costo delle assenze va mostrato solo se c'e' davvero (importo a carico
 * datore > 0). n_giorni_assenza da solo non basta: un riposo non costa nulla.
 */
export function mostraCostoAssenze(d: CalcoloTurni | null): boolean {
  return !!d && (d.costo_assenze_a_carico || 0) > 0;
}

/**
 * Riga di sintesi del recupero sotto il bottone, o null se non ci sono turni.
 * Il conteggio dei dipendenti coperti dallo stipendio del mese compare solo se
 * > 0: spiega perche' i loro turni non risultano "senza costo orario".
 */
export function sintesiRecuperoTurni(d: CalcoloTurni | null): string | null {
  if (!d || d.n_turni <= 0) return null;
  const parti = [
    `${d.n_turni} turni · ${Math.round(numero(d.ore_totali))}h di cui ${Math.round(numero(d.ore_extra))}h extra`,
  ];
  const conStipendio = numero(d.n_con_stipendio);
  if (conStipendio > 0) {
    parti.push(`${conStipendio} ${conStipendio === 1 ? "dipendente" : "dipendenti"} con lo stipendio del mese`);
  }
  const senzaCosto = numero(d.n_senza_costo);
  if (senzaCosto > 0) parti.push(`${senzaCosto} senza costo orario`);
  return parti.join(" · ");
}

/** Le tre voci del personale: nessuna puo' essere negativa. */
export function vociPersonaleValide(lordo: number, extra: number, chiamata: number): boolean {
  return lordo >= 0 && extra >= 0 && chiamata >= 0;
}

/** «Totale personale» del modulo: la somma delle tre voci, come nel MOL. */
export function totalePersonale(lordo: number, extra: number, chiamata: number): number {
  return lordo + extra + chiamata;
}

/** Le celle di margini_mensili che il modulo scrive, una POST /cella ciascuna. */
export function celleDaSalvare(lordo: number, extra: number, chiamata: number): Array<[string, number]> {
  return [
    ["costo_dipendenti", lordo],
    ["costo_personale_extra", extra],
    ["costo_personale_chiamata", chiamata],
  ];
}
