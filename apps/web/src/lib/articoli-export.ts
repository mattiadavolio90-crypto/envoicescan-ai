// Costruzione del file Excel del tab "Articoli" di Analisi Fatture.
//
// Come in `@/lib/catena-export`, qui NON entra `xlsx`: le funzioni restituiscono
// le righe, le intestazioni e il nome file; il `.tsx` li passa a
// `XLSX.utils.json_to_sheet`. Il confine e' voluto — cosi' il test misura cosa il
// cliente legge nelle celle senza montare la libreria.
//
// Il file ha DUE fogli. Fino al 21/09/2026 ne aveva uno solo, con una riga per
// articolo (quantita' sommata, prezzo medio, totale speso): il dettaglio delle
// righe fattura che compongono quei totali non era in nessuna cella. Non era un
// troncamento — l'aggregazione avviene nel worker
// (`services/routers/fatture.py`, get_articoli_aggregati) e il client non ha mai
// avuto le righe singole. Il foglio "Dettaglio righe" le porta nel file.

import type { ArticoloAggregato, RigaFattura } from "@/lib/fatture";

export const FOGLIO_ARTICOLI = "Articoli";
export const FOGLIO_DETTAGLIO = "Dettaglio righe";

// Cella vuota. E' la stringa vuota e non un trattino come in `catena-export`:
// li' il file e' un prospetto da leggere, qui e' un export che il cliente
// rielabora in Excel, e un "—" in una colonna numerica la rende testo. E'
// anche cio' che il foglio 1 gia' produceva prima dei due fogli: cambiare
// simbolo avrebbe alterato un file che nessuno ha chiesto di cambiare.
export const CELLA_VUOTA = "";

/**
 * Intestazioni del foglio 1, nell'ordine in cui compaiono nel file.
 *
 * Sono le stesse 11 colonne dell'export a foglio singolo che esisteva prima:
 * chi usava quel file per il riepilogo lo ritrova identico, nello stesso ordine.
 * Passarle a `json_to_sheet` come `header` rende l'ordine esplicito invece di
 * dipendere dall'ordine di inserimento delle chiavi dell'oggetto.
 */
export const headerArticoli: readonly string[] = [
  "Descrizione",
  "Categoria",
  "Fornitore",
  "Altri fornitori",
  "Ultimo acquisto",
  "Quantità",
  "UM",
  "€ medio",
  "Trend prezzo %",
  "Totale speso",
  "N° acquisti",
];

/** Intestazioni del foglio 2, nell'ordine in cui compaiono nel file. */
export const headerDettaglio: readonly string[] = [
  "Data documento",
  "N° documento",
  "Fornitore",
  "Descrizione",
  "Categoria",
  "Quantità",
  "UM",
  "Prezzo unitario",
  "Totale riga",
  "Da classificare",
  "Quota di gruppo",
];

/**
 * Una riga del foglio "Articoli" — il riepilogo aggregato, invariato.
 */
export function rigaExportArticolo(a: ArticoloAggregato): Record<string, string | number> {
  return {
    Descrizione: a.descrizione,
    Categoria: a.categoria ?? CELLA_VUOTA,
    Fornitore: a.fornitore_principale,
    "Altri fornitori": a.altri_fornitori.join("; "),
    "Ultimo acquisto": a.ultimo_acquisto ?? CELLA_VUOTA,
    Quantità: a.quantita_totale,
    UM: a.unita_misura ?? CELLA_VUOTA,
    "€ medio": a.prezzo_unit_medio ?? CELLA_VUOTA,
    "Trend prezzo %": a.prezzo_unit_trend_pct ?? CELLA_VUOTA,
    "Totale speso": a.totale_speso,
    "N° acquisti": a.num_acquisti,
  };
}

/**
 * Una riga del foglio "Dettaglio righe" — la singola riga di fattura.
 *
 * `totale_riga` esce col suo segno: una nota di credito e' un importo negativo e
 * deve restare leggibile come tale. Non si filtra e non si porta in valore
 * assoluto (regola di dominio: i grafici fatture non scartano le note di credito).
 *
 * "Da classificare" traduce `needs_review` in una parola che il cliente legge
 * nella stessa forma in cui la vede a schermo nel filtro omonimo.
 */
export function rigaExportDettaglio(r: RigaFattura): Record<string, string | number> {
  return {
    "Data documento": r.data_documento ?? CELLA_VUOTA,
    "N° documento": r.numero_documento ?? CELLA_VUOTA,
    Fornitore: r.fornitore,
    Descrizione: r.descrizione,
    Categoria: r.categoria ?? CELLA_VUOTA,
    Quantità: r.quantita ?? CELLA_VUOTA,
    UM: r.unita_misura ?? CELLA_VUOTA,
    "Prezzo unitario": r.prezzo_unitario ?? CELLA_VUOTA,
    "Totale riga": r.totale_riga ?? CELLA_VUOTA,
    "Da classificare": r.needs_review ? "Sì" : "No",
    "Quota di gruppo": r.ripartita_su_gruppo ? "Sì" : "No",
  };
}

/**
 * I parametri con cui l'export chiede le righe di dettaglio al worker.
 *
 * Vive qui e non dentro `exportXls` perche' e' la gamba che nessun test vedeva:
 * il 21/09/2026 il foglio 2 usciva senza il filtro "Nuovi caricati" e mostrava
 * tutto lo storico degli articoli mentre il foglio 1 mostrava l'ultimo carico
 * (misurato su una sede vera: 4.833 righe e 512.669 EUR contro 1.545 e 170.596).
 * Il difetto e' stato corretto nel worker e nel client, ma finche' la
 * costruzione della querystring e' rimasta dentro il componente React,
 * toglierne una riga non faceva fallire nulla.
 *
 * Le regole in una riga ciascuna:
 * - `tipo_prodotti` si manda solo se non e' "tutti", come fa l'espansione riga:
 *   altrimenti il totale del foglio 1 (filtrato) non e' la somma del foglio 2.
 * - `solo_nuovi` e' l'unico dei sei filtri che il worker deve conoscere: gli
 *   altri cinque vivono nel browser e viaggiano come elenco di descrizioni.
 */
export function paramsExportRighe(f: {
  data_da?: string;
  data_a?: string;
  tipo_prodotti?: string;
  soloNuovi?: boolean;
}): string {
  const params = new URLSearchParams();
  if (f.data_da) params.set("data_da", f.data_da);
  if (f.data_a) params.set("data_a", f.data_a);
  if (f.tipo_prodotti && f.tipo_prodotti !== "tutti") {
    params.set("tipo_prodotti", f.tipo_prodotti);
  }
  if (f.soloNuovi) params.set("solo_nuovi", "true");
  return params.toString();
}

/**
 * Il corpo della richiesta con cui l'export chiede le righe di dettaglio.
 *
 * E' l'elenco degli articoli che l'utente ha DAVVERO a schermo. I filtri Cerca,
 * Fornitore, Categoria, Solo verifica e Solo ripartite vivono solo nel browser:
 * il worker non li conosce, quindi senza questo elenco il foglio 2 conterrebbe
 * righe di articoli appena esclusi dalla vista.
 *
 * Sta qui e non dentro `exportXls` per la stessa ragione di `paramsExportRighe`:
 * dentro il componente nessun test lo raggiungeva, e svuotarlo passava 498 test
 * verdi (misurato il 21/09/2026).
 *
 * Una lista vuota resta vuota e non diventa `undefined`: significa "a schermo
 * non c'e' nulla", che e' diverso da "nessun filtro". Il worker distingue i due
 * casi, e appiattirli qui gli farebbe esportare l'intero periodo proprio quando
 * l'utente ha filtrato via tutto.
 */
export function bodyExportRighe(
  articoli: readonly { descrizione: string }[],
): { descrizioni: string[] } {
  return { descrizioni: articoli.map((a) => a.descrizione) };
}

/**
 * Nome del file scaricato. Invariato rispetto all'export a foglio singolo: chi
 * ha automatismi o cartelle che lo cercano per nome non se ne accorge.
 *
 * `data` e' un argomento e non `new Date()` letto dentro: una funzione che legge
 * l'orologio non e' verificabile due volte con lo stesso esito.
 */
export function nomeFileArticoli(data: Date): string {
  return `articoli_${data.toISOString().slice(0, 10)}.xlsx`;
}
