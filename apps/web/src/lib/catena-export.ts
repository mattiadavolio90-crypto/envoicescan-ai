// Costruzione dei file Excel delle due finestre di catena ("Margini e coperti",
// "Spesa per punto vendita"). Esiste perche' era l'ultima logica di `catena/`
// che nessun test poteva raggiungere: viveva dentro `exportXls()`, una funzione
// async dentro un componente React, dopo un `await import("xlsx")`.
//
// Qui NON entra `xlsx`: le funzioni restituiscono le righe e i nomi file, il
// `.tsx` li passa a `XLSX.utils.json_to_sheet`. Il confine e' voluto — cosi' il
// test misura cosa il cliente legge nelle celle senza montare la libreria.
//
// Il gemello di queste righe e' `righeExportPv`/`righeExportFornitori` in
// `@/lib/catena-tag`: stessa natura (intestazioni di colonna che finiscono in
// un file scaricato), file diverso solo perche' i tipi di partenza divergono.

import type { MarginiCopertiPV, SpesaPivot } from "@/lib/gruppo";
// `slugPeriodo` vive in `catena-tag` per ragioni storiche (e' nato li' con
// l'export dei tag) ma e' una utility di slug generica, oggi usata da tre
// chiamanti in tre file diversi. Si importa invece di ri-dichiararla: una
// quarta copia della stessa regex sarebbe il modo tipico di farle divergere.
import { slugPeriodo } from "@/lib/catena-tag";

/**
 * Colonna dell'export margini: il sottoinsieme di `Col` che serve a costruire
 * il file. `fmt` e `tooltip` restano nel `.tsx` — sono funzioni di rendering e
 * testo di UI, non hanno posto in un modulo che produce dati.
 */
export type ColonnaExport = { key: keyof MarginiCopertiPV; label: string };

export const CELLA_DATI_INCOMPLETI = "dati incompleti";
export const CELLA_VUOTA = "—";

/**
 * Una riga PV dell'export margini.
 *
 * Ordine dei parametri: prima la riga, poi le colonne — l'inverso di
 * `calcolaExtremes(righe, cols)` no, e' lo stesso: righe/dati prima, config dopo.
 *
 * Un PV con `dati_incompleti` non esce con i suoi numeri: esce con la scritta
 * `"dati incompleti"` in OGNI colonna. E' voluto — pubblicare il fatturato di
 * una sede che non ha ancora i costi caricati farebbe leggere come definitivo
 * un dato che l'UI dichiara parziale.
 */
export function rigaExportMargini(
  r: MarginiCopertiPV,
  cols: readonly ColonnaExport[],
): Record<string, string | number> {
  const row: Record<string, string | number> = { "Punto vendita": r.nome };
  cols.forEach((c) => {
    const v = r[c.key] as number | null;
    row[c.label] = r.dati_incompleti ? CELLA_DATI_INCOMPLETI : v == null ? CELLA_VUOTA : v;
  });
  return row;
}

/**
 * La riga "gruppo" con la qualificazione `(parziale)` sul margine.
 *
 * Il suffisso si applica SOLO se la cella contiene davvero un numero: su una
 * cella gia' `"dati incompleti"` o `"—"` si leggerebbe `"— (parziale)"`, che
 * non aggiunge nulla e sembra un errore di formattazione. La nota in coda al
 * foglio resta comunque (vedi `notaIncompleti`), quindi l'informazione non si
 * perde: cambia solo dove la si legge.
 */
export function rigaExportGruppo(
  gruppo: MarginiCopertiPV,
  cols: readonly ColonnaExport[],
  nIncompleti: number,
  chiaveMargine: keyof MarginiCopertiPV = "margine_perc",
): Record<string, string | number> {
  const row = rigaExportMargini(gruppo, cols);
  if (nIncompleti > 0) {
    const mp = cols.find((c) => c.key === chiaveMargine);
    if (mp && typeof row[mp.label] === "number") {
      row[mp.label] = `${row[mp.label]} (parziale)`;
    }
  }
  return row;
}

/**
 * La nota in coda al foglio. `null` quando non c'e' niente da qualificare:
 * il chiamante salta `sheet_add_aoa`.
 */
export function notaIncompleti(nIncompleti: number): string | null {
  // `!(n > 0)` e NON `n <= 0`: sono diversi per NaN, e l'originale nel .tsx era
  // `if (data.n_incompleti > 0) {…}`. Con `<= 0` un NaN produrrebbe la nota
  // "NaN sedi non hanno…" invece di nessuna nota. Oggi irraggiungibile
  // (`n_incompleti` nasce da len()/sum() nel worker), ma un'estrazione che
  // cambia semantica su un input di bordo resta un'estrazione infedele.
  if (!(nIncompleti > 0)) return null;
  return `Margine di gruppo parziale: ${nIncompleti} ${
    nIncompleti === 1 ? "sede non ha" : "sedi non hanno"
  } ancora i costi caricati.`;
}

/**
 * Nome file dell'export margini. `oggiIso` e' iniettabile perche' la data e'
 * il fallback quando `periodo_label` e' vuoto: un test che dipendesse da
 * `new Date()` misurerebbe il giorno in cui gira, non la funzione.
 */
export function nomeFileMargini(periodoLabel: string | null | undefined, oggiIso: string): string {
  return `margini_coperti_${slugPeriodo(periodoLabel) || oggiIso}.xlsx`;
}

/** L'intestazione dell'export margini: la colonna fissa piu' quelle configurate. */
export function headerMargini(cols: readonly ColonnaExport[]): string[] {
  return ["Punto vendita", ...cols.map((c) => c.label)];
}

// ─── Spesa per punto vendita (pivot) ───────────────────────────────────────

/** L'etichetta della prima colonna della pivot: dipende dalla dimensione scelta. */
export function etichettaDimensione(dimensione: SpesaPivot["dimensione"]): string {
  return dimensione === "fornitore" ? "Fornitore" : "Categoria";
}

export function headerPivot(dimLabel: string, pv: readonly { nome: string }[]): string[] {
  return [dimLabel, ...pv.map((p) => p.nome), "Totale", "%"];
}

/**
 * Arrotondamento a 2 decimali, regola commerciale italiana.
 *
 * CORRETTO l'1/9/2026 (prima era fotografato come anomalia). La forma vecchia
 * `Math.round(n * 100) / 100` sbagliava per la rappresentazione binaria del
 * prodotto, in modo **non simmetrico rispetto al segno**:
 *   `1.005 -> 1` (invece di 1.01), perche' `1.005*100` vale `100.49999...`
 *   `-2.675 -> -2.67` (invece di -2.68), perche' su `-267.5` esatto
 *   `Math.round` va verso +infinito
 *
 * Il fix usa la notazione esponenziale (`Number(a + "e+2")`) per spostare il
 * punto decimale senza moltiplicazione, quindi senza errore binario, e
 * arrotonda sempre il valore assoluto riapplicando il segno alla fine: cosi'
 * `2.675` e `-2.675` danno `2.68` e `-2.68`, non due regole diverse.
 *
 * `Number.isFinite` protegge NaN e Infinity, che con la concatenazione di
 * stringhe darebbero `NaN` da `"Infinitye+2"`.
 *
 * Nota: l'ultimo passaggio potrebbe essere `centesimi / 100` — verificato
 * equivalente su 57.000 centesimi interi, 0 divergenze. Dopo `Math.round` il
 * valore e' intero, e dividere un intero per 100 non introduce l'errore che
 * nasce invece moltiplicando un decimale. Si tiene la forma esponenziale per
 * simmetria con la riga sopra, non perche' l'altra sbagli.
 */
export function arrotonda2(n: number): number {
  if (!Number.isFinite(n)) return n;
  const segno = n < 0 ? -1 : 1;
  const assoluto = Math.abs(n);
  const centesimi = Math.round(Number(`${assoluto}e+2`));
  return segno * Number(`${centesimi}e-2`);
}

/**
 * Una riga della pivot. Le celle dei PV assenti da `per_pv` valgono 0, non
 * `"—"`: in una pivot di spesa una sede senza quella categoria ha speso zero,
 * e uno zero si somma mentre un trattino no.
 */
export function rigaExportPivot(
  r: SpesaPivot["rows"][number],
  pv: readonly { id: string; nome: string }[],
  dimLabel: string,
): Record<string, string | number> {
  const row: Record<string, string | number> = { [dimLabel]: r.dim_val };
  pv.forEach((p) => {
    row[p.nome] = arrotonda2(r.per_pv[p.id] ?? 0);
  });
  row["Totale"] = arrotonda2(r.totale);
  row["%"] = `${r.incidenza_pct.toFixed(1)}%`;
  return row;
}

/**
 * La riga TOTALE della pivot.
 *
 * ANOMALIA FOTOGRAFATA: la percentuale e' la costante `"100%"`, non la somma
 * delle incidenze. Se il backend tronca o esclude righe, le colonne possono
 * sommare a 99,8% mentre il totale dichiara 100%. E' una scelta di leggibilita'
 * (un totale che dice 99,8% sembra un bug del file), ma va saputa: il numero
 * non e' misurato.
 */
export function rigaTotalePivot(
  totaliPv: Record<string, number>,
  grandTotal: number,
  pv: readonly { id: string; nome: string }[],
  dimLabel: string,
): Record<string, string | number> {
  const row: Record<string, string | number> = { [dimLabel]: "TOTALE" };
  pv.forEach((p) => {
    row[p.nome] = arrotonda2(totaliPv[p.id] ?? 0);
  });
  row["Totale"] = arrotonda2(grandTotal);
  row["%"] = "100%";
  return row;
}

/**
 * Nome del foglio Excel. Il taglio a 31 caratteri non e' estetico: e' il limite
 * duro del formato xlsx, oltre il quale la libreria solleva.
 */
export const MAX_NOME_FOGLIO = 31;

export function nomeFoglioPivot(dimLabel: string): string {
  return dimLabel.slice(0, MAX_NOME_FOGLIO);
}

export function nomeFilePivot(
  dimensione: SpesaPivot["dimensione"],
  periodoLabel: string | null | undefined,
  oggiIso: string,
): string {
  return `spesa_per_pv_${dimensione}_${slugPeriodo(periodoLabel) || oggiIso}.xlsx`;
}
