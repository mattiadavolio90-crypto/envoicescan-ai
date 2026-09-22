// Costruzione del CSV della vista Spese (Workspace).
//
// Come in `@/lib/articoli-export`, qui non entra ne' React ne' il DOM: le
// funzioni restituiscono le righe e il testo del file, il `.tsx` si limita a
// creare il Blob e a farlo scaricare. Il confine e' voluto — cosi' il test
// misura cosa il cliente legge nelle celle.
//
// Il modulo nasce il 22/09/2026 da un difetto: `esportaCSV` controllava
// `risposta.voci` (l'elenco completo del mese) ma scriveva `voci` (lo stesso
// elenco dopo i filtri Tipo e Categoria). Con un filtro che non seleziona
// nulla, la guardia passava e il file usciva senza righe ma con i totali del
// mese intero sotto: un `TOTALE F&B 1.234,50` che non corrisponde a niente di
// cio' che il cliente ha davanti. Finche' la logica e' rimasta dentro il
// componente React nessun test poteva vederlo.

/** Le colonne del file, nell'ordine in cui compaiono. */
export const headerSpese: readonly string[] = [
  "Data",
  "Tipo",
  "Categoria",
  "Descrizione",
  "Importo",
  "Note",
];

/** Etichette delle due righe di totale in coda al file. */
export const ETICHETTA_TOTALE_FB = "TOTALE F&B";
export const ETICHETTA_TOTALE_GENERALI = "TOTALE GENERALI";

/**
 * Importo nel formato che Excel italiano legge come numero: separatore
 * decimale virgola, due decimali al massimo, segno conservato.
 *
 * Il segno resta perche' una spesa puo' essere uno storno: portarla in valore
 * assoluto la farebbe sommare invece che sottrarre.
 */
export function importoCsv(v: number): string {
  return String(Math.round(v * 100) / 100).replace(".", ",");
}

/**
 * Una cella nel formato CSV: sempre fra virgolette, con le virgolette interne
 * raddoppiate (RFC 4180). Le virgolette sempre presenti sono cio' che permette
 * a un nome fornitore contenente `;` di non spezzare la riga.
 */
export function cellaCsv(c: unknown): string {
  return `"${String(c ?? "").replace(/"/g, '""')}"`;
}

export type VoceSpesaExport = {
  data_spesa: string;
  tipo: string;
  categoria?: string | null;
  descrizione: string;
  importo: number;
  note?: string | null;
};

/**
 * Le righe del file a partire dalle voci **visibili a schermo**.
 *
 * `fmtData` e `labelTipo` arrivano come argomenti e non sono importate qui: il
 * formato data della vista Spese e' `GG/MM` senza anno, diverso da quello di
 * `@/lib/inventario`, e l'etichetta del tipo dipende dal settore della sede.
 * Passarle da fuori evita di riscrivere il file che i clienti gia' scaricano.
 */
export function righeExportSpese(
  voci: readonly VoceSpesaExport[],
  fmtData: (iso: string) => string,
  labelTipo: (tipo: string) => string,
): string[][] {
  return voci.map((s) => [
    fmtData(s.data_spesa),
    labelTipo(s.tipo),
    s.categoria ?? "",
    s.descrizione,
    importoCsv(s.importo),
    s.note ?? "",
  ]);
}

/**
 * Le due righe di totale, precedute da una riga separatrice vuota.
 *
 * I totali descrivono **le voci passate**, non il mese intero: sono ricalcolati
 * qui invece di essere letti dalla risposta del server. E' il cuore del fix —
 * con un filtro attivo, la somma in fondo al file deve essere la somma delle
 * righe che il file contiene, altrimenti il cliente legge un totale che non
 * torna con nulla.
 *
 * La riga separatrice ha tante celle vuote quante sono le colonne: una riga
 * davvero vuota Excel la interpreta come una riga a una sola colonna.
 */
export function righeTotaliSpese(
  voci: readonly VoceSpesaExport[],
  tipoFb: string,
  tipoGenerale: string,
): string[][] {
  // Due confronti positivi (`=== fb`, `=== generale`) e non uno negativo: e'
  // quello che fa il server (`workspace.py`, ws_spese_list). Con `!== fb` una
  // voce di un tipo sconosciuto finirebbe nei generali invece che fuori da
  // entrambi i totali, e il file direbbe una cosa diversa dall'API.
  const somma = (tipo: string) =>
    voci.filter((v) => v.tipo === tipo).reduce((acc, v) => acc + (v.importo ?? 0), 0);
  const vuota = headerSpese.map(() => "");
  const totale = (etichetta: string, valore: number) => {
    const r = headerSpese.map(() => "");
    r[0] = etichetta;
    r[4] = importoCsv(valore);
    return r;
  };
  return [
    vuota,
    totale(ETICHETTA_TOTALE_FB, somma(tipoFb)),
    totale(ETICHETTA_TOTALE_GENERALI, somma(tipoGenerale)),
  ];
}

/**
 * Il testo completo del file CSV.
 *
 * Separatore `;` e non `,`: e' quello che Excel in locale italiano usa come
 * separatore di colonna. Terminatore `\r\n` per la stessa ragione.
 */
export function csvSpese(
  voci: readonly VoceSpesaExport[],
  fmtData: (iso: string) => string,
  labelTipo: (tipo: string) => string,
  tipoFb: string,
  tipoGenerale: string,
): string {
  const righe = [
    [...headerSpese],
    ...righeExportSpese(voci, fmtData, labelTipo),
    ...righeTotaliSpese(voci, tipoFb, tipoGenerale),
  ];
  return righe.map((r) => r.map(cellaCsv).join(";")).join("\r\n");
}

/**
 * Nome del file scaricato. Invariato rispetto a prima: chi ha cartelle o
 * automatismi che lo cercano per nome non se ne accorge.
 */
export function nomeFileSpese(da: string, a: string): string {
  return `spese_${da}_${a}.csv`;
}

/**
 * Se l'export ha senso. Guarda le voci **visibili**, non quelle caricate: e' la
 * riga che il difetto del 22/09/2026 aveva sbagliato, ed e' esportata perche'
 * un test possa rimuoverla e vedere il rosso.
 */
export function puoEsportareSpese(voci: readonly VoceSpesaExport[]): boolean {
  return voci.length > 0;
}
