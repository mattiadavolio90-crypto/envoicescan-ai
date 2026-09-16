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


/**
 * Il messaggio da mostrare quando non c'e' niente da elencare.
 *
 * Esiste come funzione, e non come ternario dentro il JSX, per una ragione
 * misurata: un presidio che cerca il TESTO nel sorgente passa anche quando la
 * condizione e' stata neutralizzata (`false && ...`, o un ternario che
 * collassa). L'unico modo di provare la scelta e' **eseguirla** — e l'harness
 * dei test esegue `lib/`, non i `.tsx`.
 *
 * `vuoto` e `guasto` sono i due messaggi della pagina; `conFiltri` e' il terzo
 * caso, che riguarda solo l'elenco filtrato e non c'entra col caricamento.
 */
export function messaggioListaVuota(opzioni: {
  caricamentoFallito: boolean;
  righeCaricate: number;
  filtriAttivi?: boolean;
  guasto: string;
  vuoto: string;
  conFiltri?: string;
}): string {
  const { caricamentoFallito, righeCaricate, filtriAttivi, guasto, vuoto, conFiltri } = opzioni;
  // Il guasto vince solo se non e' arrivato NIENTE: dopo un retry riuscito
  // l'errore non deve restare appiccicato a una lista che ora ha dei dati.
  if (caricamentoFallito && righeCaricate === 0) return guasto;
  if (filtriAttivi && conFiltri) return conFiltri;
  return vuoto;
}

/**
 * `true` quando la pagina deve dire "non ci sono riuscito" invece di "non c'e'
 * niente". Gemella booleana di `messaggioListaVuota`, per i casi in cui i due
 * rami non sono due stringhe ma due blocchi di JSX diversi.
 */
export function mostraGuasto(caricamentoFallito: boolean, righeCaricate: number): boolean {
  return caricamentoFallito && righeCaricate === 0;
}


/**
 * Lo stesso principio applicato a un OGGETTO invece che a una lista.
 *
 * I KPI di /margini non sono righe: sono sei totali. `fetchKpiData` ripiega su
 * sei zeri quando il worker non risponde entro 8s, risponde male o manca la
 * sessione — e fino al 16/09/2026 quel ripiego era indistinguibile da un
 * periodo davvero vuoto. L'audit ha visto i riquadri fermi a "0 €" per oltre 30
 * secondi mentre la tabella sotto, che chiama un endpoint diverso lato client,
 * si popolava: non stavano caricando, si erano gia' arresi.
 *
 * `non_disponibile` e' la stessa distinzione di `EsitoLista`, in forma di flag
 * perche' qui il dato non e' un array.
 */
export type StatoKpi = { non_disponibile?: boolean };

/** I riquadri devono mostrare un trattino invece di una cifra. */
export function kpiNonDisponibile(kpi: StatoKpi | null | undefined): boolean {
  return !!kpi?.non_disponibile;
}

/**
 * I segnali commerciali possono essere valutati su questi KPI.
 *
 * `trigger-servizi` dichiara: «un campo assente = "non lo so", quindi il
 * trigger relativo non scatta». Su un ripiego, passare `molNegativo: false`
 * affermerebbe che il MOL e' sano — un giudizio su numeri mai arrivati.
 */
export function kpiValutabiliPerTrigger(kpi: StatoKpi | null | undefined): boolean {
  if (!kpi) return false;
  return !kpi.non_disponibile;
}
