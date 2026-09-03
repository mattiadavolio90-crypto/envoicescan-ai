// Come si MOSTRA il netto di un mese quando la lettura puo' essere fallita.
//
// `fetchNettoMese` (in `(app)/margini/periodi.ts`) distingue apposta due casi
// che sembrano lo stesso numero:
//
//   netto: 0     -> mese davvero senza ricavi ("zero vero")
//   netto: null  -> la lettura e' fallita ("non lo so")
//
// La distinzione costa: sul desktop il valore e' la base delle percentuali che
// l'utente salva a DB, e degradare l'errore a 0 faceva valere 0 EUR ogni
// percentuale digitata. Sul mobile il valore si mostra soltanto, ma mostrarlo
// come "0,00 €" e' una bugia della stessa famiglia: dice al ristoratore che il
// mese ha incassato zero mentre il dato non e' stato letto.
//
// Questa funzione vive qui, e non nel .tsx, perche' `esegui_ts` non entra nei
// componenti React (tests/helpers_ts.py): la regola che decide cosa legge il
// cliente dev'essere provabile.

export type NettoDaMostrare = {
  /** Gia' formattato per la UI: l'importo, oppure "—" se il dato non c'e'. */
  testo: string;
  /** false = non lo sappiamo. La UI non deve dire ne' "0 €" ne' "N giorni". */
  disponibile: boolean;
};

const PLACEHOLDER = "—";

/**
 * Decide cosa scrivere nel KPI "Incasso netto del mese".
 *
 * `netto` arriva da `fetchNettoMese`: `null` significa lettura fallita, non zero.
 * `NaN` viene trattato come indisponibile: e' il risultato di uno scorporo su
 * campi assenti, e "NaN €" a schermo e' peggio di "—".
 */
export function nettoDaMostrare(
  netto: number | null | undefined,
  formatta: (v: number) => string,
): NettoDaMostrare {
  if (netto == null || !Number.isFinite(netto)) {
    return { testo: PLACEHOLDER, disponibile: false };
  }
  return { testo: formatta(netto), disponibile: true };
}

/**
 * La riga sotto il KPI. Tre stati, non due: il terzo esiste perche' senza dato
 * non si puo' dire ne' "0 giorni inseriti" (falso: forse ce ne sono) ne'
 * "totale mensile" (non lo sappiamo).
 */
export function dettaglioNettoMese(
  disponibile: boolean,
  mensile: boolean,
  giorni: number,
): string {
  if (!disponibile) return "Dato non disponibile";
  if (mensile) return "Totale mensile inserito da desktop";
  return `${giorni} ${giorni === 1 ? "giorno inserito" : "giorni inseriti"}`;
}
