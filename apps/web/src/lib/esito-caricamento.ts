// La differenza fra "non ho trovato niente" e "non sono riuscito a chiedere".
//
// I caricamenti server (`workerGet` e le fetch delle pagine) tornano `null` su
// OGNI fallimento: token assente, non-2xx, timeout, rete giu'. Scrivendo
// `data?.righe ?? []` quel `null` diventa una lista vuota, e la pagina dice al
// cliente "Nessun documento trovato" mentre il worker e' semplicemente giu'.
//
// Non e' un caso raro: Railway spegne il worker quando non e' usato, e il
// risveglio sfora gli 8s di timeout — `BlockRetry` esiste esattamente per
// questo. Su /scadenziario il costo e' misurabile: 3.219 fatture non pagate,
// 4,4 M€, 1.891 gia' scadute (misurato il 3/9/2026). Un cliente che apre la
// pagina nel momento sbagliato legge che non ha scadenze.
//
// Qui la scelta e' esplicita: chi carica dichiara se la lista e' VUOTA o
// SCONOSCIUTA, e la pagina puo' mostrare due cose diverse.

export type EsitoLista<T> =
  | { stato: "ok"; righe: T[] }
  | { stato: "non_disponibile"; righe: [] };

/**
 * Interpreta la risposta di un caricamento che puo' essere fallito.
 *
 * `risposta === null` (o `undefined`) significa **fallito**, non vuoto: e' la
 * convenzione di `workerGet` e delle fetch di pagina. Una risposta arrivata ma
 * senza il campo atteso e' invece un vuoto legittimo: il worker ha risposto.
 */
export function esitoLista<T>(
  risposta: { [k: string]: unknown } | null | undefined,
  campo: string,
): EsitoLista<T> {
  if (risposta == null) return { stato: "non_disponibile", righe: [] };
  const valore = risposta[campo];
  if (!Array.isArray(valore)) return { stato: "ok", righe: [] };
  return { stato: "ok", righe: valore as T[] };
}

/** `true` solo quando sappiamo davvero che non c'e' niente. */
export function davveroVuota<T>(esito: EsitoLista<T>): boolean {
  return esito.stato === "ok" && esito.righe.length === 0;
}
