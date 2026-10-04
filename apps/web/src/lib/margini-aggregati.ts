// Logica pura estratta dai componenti di `app/(app)/margini/`.
//
// Perche' un modulo separato: `helpers_ts.py` esegue i moduli TypeScript veri
// dentro pytest con node, ma non sa montare React. Finche' queste funzioni
// stavano dentro un `.tsx` accanto a JSX, hook e recharts erano irraggiungibili
// da un test — e infatti non ne avevano nessuno. Qui sono importabili.
//
// **Copiate byte per byte dai componenti, senza correzioni.** Se una si
// comporta in modo sorprendente (vedi `aggregaRicavi`) e' perche' si comportava
// gia' cosi' in produzione: il test la fotografa, non la sistema.

import type { CopertiMese } from "@/lib/ricavi";
import { MESI_NOMI_SHORT } from "@/app/(app)/margini/periodi";

/* ─── coperti-tab.tsx: colonna Totale/Media ───────────────────────────────── */

// ATTENZIONE, asimmetria voluta (documentata nel verbale del 31/8/2026):
// `aggregaCoperti` somma solo i mesi con `coperti != null`, mentre
// `aggregaRicavi` somma TUTTI i mesi ricevuti. Ma entrambe dividono per lo
// stesso `nMesi`, che il chiamante calcola come "mesi con coperti > 0".
// Su un mese senza coperti ma con ricavi, la media dei ricavi e' quindi
// sovrastimata (numeratore piu' largo del denominatore). Il caso non e' attivo
// su nessuna delle 8 sedi oggi, ma si arma da solo: le righe inserite a mano
// hanno `coperti` NULL. Mattia ha deciso: si fotografa, non si corregge.
export function aggregaCoperti(mesi: CopertiMese[], isMedia: boolean, nMesi: number): number | null {
  const conDati = mesi.filter((m) => m.coperti != null);
  if (conDati.length === 0) return null;
  const tot = conDati.reduce((s, m) => s + (m.coperti ?? 0), 0);
  return isMedia ? tot / Math.max(1, nMesi) : tot;
}

export function aggregaRicavi(mesi: CopertiMese[], isMedia: boolean, nMesi: number): number {
  const tot = mesi.reduce((s, m) => s + m.ricavi_netto, 0);
  return isMedia ? tot / Math.max(1, nMesi) : tot;
}

// I due filtri che il componente applica prima di chiamare le aggrega*: la
// discrepanza fra i due e' l'origine dell'asimmetria, quindi vivono qui accanto.
export function mesiVisibili(mesi: CopertiMese[]): CopertiMese[] {
  return mesi.filter((m) => (m.coperti ?? 0) > 0 || m.ricavi_netto > 0);
}

export function numMesiAttivi(mesi: CopertiMese[]): number {
  return mesi.filter((m) => (m.coperti ?? 0) > 0).length;
}

/* ─── calcolo-tab.tsx: pivot, incidenze, righe derivate ───────────────────── */

export type MesePivot = {
  anno: number;
  mese: number;
  label: string;
  fatturato_iva10: number;
  fatturato_iva22: number;
  altri_ricavi_noiva: number;
  fatturato_netto: number;
  costi_fb_auto: number;
  altri_costi_fb: number;
  costi_fb_totali: number;
  primo_margine: number;
  costi_spese_auto: number;
  altri_costi_spese: number;
  costi_spese_totali: number;
  costo_dipendenti: number;
  costo_personale_extra: number;
  costo_personale_chiamata: number;
  costi_personale: number;
  mol: number;
  quote_riparto_fb: number;
  quote_riparto_spese: number;
};

// Le 2 righe virtuali di ROWS. Restano qui e non nel .tsx perche' `costi_fb_auto`
// e `costi_spese_auto` sommano le quote di riparto: se una `derive` sparisce, la
// quota ripartita non viene piu' mostrata e il costo appare piu' basso del vero
// (e' l'errore gia' visto lato worker nel ciclo 07).
//
// La terza, `totale_costi` («= Spese Generali + Personale»), e' sparita il
// 04/10/2026 con i gruppi apribili: le testate «Spese generali» e «Costo
// personale» dicono gia' i due addendi, e la loro somma era una riga in piu'
// fra il Margine F&B e il MOL.
export const DERIVE: Readonly<Record<string, (m: MesePivot) => number>> = Object.freeze({
  costi_fb_auto: (m: MesePivot) => m.costi_fb_auto + (m.quote_riparto_fb ?? 0),
  costi_spese_auto: (m: MesePivot) => m.costi_spese_auto + (m.quote_riparto_spese ?? 0),
});

export type RowLike = { key: string; derive?: (m: MesePivot) => number };

export function rowVal(row: RowLike, m: MesePivot): number {
  if (row.derive) return row.derive(m);
  return (m[row.key as keyof MesePivot] as number) ?? 0;
}

/* ─── calcolo-tab.tsx: gruppi apribili della tabella (04/10/2026) ─────────── */

// Richiesta di Mattia (SCREEN 15): la tabella mostra le TESTATE — Incasso,
// Spese F&B, Spese generali, Costo personale — e il dettaglio compare solo
// aprendo il gruppo. Margine F&B e MOL restano sempre visibili: sono i due
// risultati che la tabella esiste per dire.
//
// L'ordine delle righe, il gruppo e la testata vivono QUI e non in ROWS del
// .tsx: il .tsx aggiunge solo l'aspetto (etichetta, colore, tipo di cella).
// Cosi' un test puo' eseguire la struttura vera — prima i blocchi si
// riconoscevano da indici scritti a mano (`SEP_BEFORE = {4, 8, 12}`), che una
// riga aggiunta spostava senza che niente lo segnalasse.

export type GruppoMargini = "incasso" | "fb" | "spese" | "personale";

export type ChiaveRigaMargini =
  | "fatturato_netto" | "fatturato_iva10" | "fatturato_iva22" | "altri_ricavi_noiva"
  | "costi_fb_totali" | "costi_fb_auto" | "altri_costi_fb"
  | "primo_margine"
  | "costi_spese_totali" | "costi_spese_auto" | "altri_costi_spese"
  | "costi_personale" | "costo_dipendenti" | "costo_personale_extra" | "costo_personale_chiamata"
  | "mol";

export type RigaMargini = {
  key: ChiaveRigaMargini;
  /** `null` = sempre visibile (Margine F&B, MOL). */
  gruppo: GruppoMargini | null;
  /** La riga che riassume il gruppo e lo apre/chiude. Una per gruppo, in testa. */
  testata?: boolean;
  derive?: (m: MesePivot) => number;
};

export const RIGHE_MARGINI: readonly RigaMargini[] = Object.freeze([
  { key: "fatturato_netto",          gruppo: "incasso", testata: true },
  { key: "fatturato_iva10",          gruppo: "incasso" },
  { key: "fatturato_iva22",          gruppo: "incasso" },
  { key: "altri_ricavi_noiva",       gruppo: "incasso" },
  { key: "costi_fb_totali",          gruppo: "fb", testata: true },
  { key: "costi_fb_auto",            gruppo: "fb", derive: DERIVE.costi_fb_auto },
  { key: "altri_costi_fb",           gruppo: "fb" },
  { key: "primo_margine",            gruppo: null },
  { key: "costi_spese_totali",       gruppo: "spese", testata: true },
  { key: "costi_spese_auto",         gruppo: "spese", derive: DERIVE.costi_spese_auto },
  { key: "altri_costi_spese",        gruppo: "spese" },
  { key: "costi_personale",          gruppo: "personale", testata: true },
  { key: "costo_dipendenti",         gruppo: "personale" },
  { key: "costo_personale_extra",    gruppo: "personale" },
  { key: "costo_personale_chiamata", gruppo: "personale" },
  { key: "mol",                      gruppo: null },
] as RigaMargini[]);

type RigaStruttura = { key: string; gruppo: GruppoMargini | null; testata?: boolean };

/** Tutti chiusi: la tabella si apre corta, a ogni visita (niente memoria). */
export function gruppiEspansiIniziali(): GruppoMargini[] {
  return [];
}

/** Apre il gruppo se e' chiuso, lo chiude se e' aperto. Non tocca gli altri. */
export function alternaGruppo(
  espansi: readonly GruppoMargini[],
  gruppo: GruppoMargini,
): GruppoMargini[] {
  return espansi.includes(gruppo)
    ? espansi.filter((g) => g !== gruppo)
    : [...espansi, gruppo];
}

/** Le righe da disegnare: testate e sempre-visibili, piu' il dettaglio dei gruppi aperti. */
export function righeVisibili<R extends RigaStruttura>(
  righe: readonly R[],
  espansi: readonly GruppoMargini[],
): R[] {
  return righe.filter(
    (r) => r.gruppo === null || r.testata === true || espansi.includes(r.gruppo),
  );
}

/**
 * Aria sopra la riga: si apre un blocco nuovo quando cambia il gruppo rispetto
 * alla riga VISIBILE precedente, e sopra ogni sempre-visibile. Mai fra righe
 * dello stesso gruppo, mai sopra la prima riga della tabella.
 */
export function separatoreSopra(
  riga: RigaStruttura,
  precedente: RigaStruttura | null | undefined,
): boolean {
  if (!precedente) return false;
  return riga.gruppo === null || riga.gruppo !== precedente.gruppo;
}

/** Il piede della tabella: il MOL, riconosciuto per chiave e non per posizione. */
export function rigaPiede(riga: { key: string }): boolean {
  return riga.key === "mol";
}

/**
 * Le celle mese che aprono il modulo del personale: le tre voci modificabili
 * (Lordo, Ore extra, Chiamata) E la testata «Costo personale», anche a gruppo
 * chiuso — il briefing manda su /margini quando il personale del mese manca, e
 * l'inserimento deve restare a un clic. Le altre testate sono totali calcolati:
 * aprono e chiudono il gruppo e basta.
 */
export function apreCostoPersonale(riga: RigaStruttura & { type?: string }): boolean {
  if (riga.gruppo !== "personale") return false;
  return riga.testata === true || riga.type === "input-editable";
}

// Divide tutti i campi numerici della pivot per il numero di mesi attivi.
// Divisore unico di periodo: ogni riga scende dello stesso fattore, quindi
// la colonna resta coerente (media MOL = media Ricavi − media Costi) e le
// percentuali di incidenza (riga/fatturato) restano invariate.
export function pivotMedia(p: MesePivot, nMesi: number): MesePivot {
  const n = Math.max(1, nMesi);
  const out = { ...p };
  for (const k of Object.keys(out) as (keyof MesePivot)[]) {
    if (typeof out[k] === "number") {
      (out[k] as number) = (out[k] as number) / n;
    }
  }
  return out;
}

export function pctIncidenza(raw: number, netto: number): string | null {
  if (!netto || netto === 0 || raw === 0) return null;
  return `${((raw / netto) * 100).toFixed(0)}%`;
}

// Un mese con ricavi e NESSUNA FATTURA DELLA MERCE: il suo margine non e' un
// risultato, e' un buco nei dati. Stessa definizione di `_mesi_senza_costi`
// (services/routers/margini.py): le due devono restare uguali, divergendo la
// tabella colorerebbe di verde proprio i mesi per cui «Analisi visiva» dice di
// non avere un giudizio.
//
// La condizione guarda i SOLI costi F&B, non piu' «F&B E spese entrambi a zero»
// (decisione di Mattia, 23/09/2026). Con l'AND bastava un costo qualsiasi a
// dichiarare completo un mese senza una sola bolla di merce: misurato lo stesso
// giorno, CASATI Set 2026 aveva 101 EUR di utenze su 5.696 EUR di ricavi e
// mostrava «MOL 5.595 EUR, 98%» in verde; SUSHILAND gennaio, 114 EUR di utenze
// su 444.000 EUR di ricavi, MOL verde all'86% su tutte e tre le sedi. In un
// ristorante un mese senza merce non e' giudicabile, quale che sia la bolletta
// della luce: il food cost e' 0% e il MOL e' gonfiato di tutto il costo merce.
//
// "costi_fb_totali" include gia' le quote di riparto F&B dei costi di gruppo
// (catena): una sede che riceve solo quote ripartite resta un mese CON costi.
//
// Serve solo per DECIDERE IL COLORE. Il numero non si tocca (decisione di
// Mattia): il MOL di un mese senza costi resta quello che e', smette solo di
// essere dichiarato buono.
export function meseSenzaCosti(m: MesePivot): boolean {
  if ((m.fatturato_netto ?? 0) <= 0) return false;
  return (m.costi_fb_totali ?? 0) <= 0;
}

/* ─── analisi-tab.tsx + carica-ricavi-dialog.tsx: elenco mesi del periodo ─── */

// Era duplicata identica nei due file (verificato con `diff`: nessuna riga di
// scarto). Unificata qui: due copie divergono prima o poi, e questa decide
// quali mesi l'utente puo' compilare.
export function buildMesiList(dataDa: string, dataA: string) {
  const mesi: { anno: number; mese: number; label: string }[] = [];
  const y0 = parseInt(dataDa.slice(0, 4), 10), m0 = parseInt(dataDa.slice(5, 7), 10);
  const y1 = parseInt(dataA.slice(0, 4), 10), m1 = parseInt(dataA.slice(5, 7), 10);
  for (let y = y0; y <= y1; y++) {
    const mFrom = y === y0 ? m0 : 1;
    const mTo = y === y1 ? m1 : 12;
    for (let m = mFrom; m <= mTo; m++) {
      mesi.push({ anno: y, mese: m, label: `${MESI_NOMI_SHORT[m - 1]} ${y}` });
    }
  }
  return mesi;
}

// Dove posizionare lo scroller orizzontale della tabella per far vedere il mese
// corrente all'apertura.
//
// Sta qui e non dentro l'useEffect perche' un test possa ESEGUIRLA: il conto ha
// un pezzo che si sbaglia in silenzio — la colonna Totale e' `sticky right`,
// quindi senza sottrarre la sua larghezza il mese corrente finisce NASCOSTO
// sotto di essa invece che accanto, e a schermo sembra che lo scroll non abbia
// funzionato.
//
// Torna 0 quando la tabella ci sta tutta (niente scroll) o quando il target e'
// negativo: `scrollLeft` negativo non esiste, verrebbe silenziosamente portato
// a 0 dal browser, ma dichiararlo qui rende la regola verificabile.
export function scrollPerMeseCorrente(opts: {
  offsetCella: number;
  larghezzaCella: number;
  larghezzaTotale: number;
  larghezzaVisibile: number;
  margine?: number;
}): number {
  const { offsetCella, larghezzaCella, larghezzaTotale, larghezzaVisibile } = opts;
  const margine = opts.margine ?? 24;
  const target =
    offsetCella + larghezzaCella + larghezzaTotale + margine - larghezzaVisibile;
  return Math.max(0, target);
}

// La larghezza della colonna TOTALE, che e' `sticky right` e coprirebbe il mese
// corrente se lo scroll si fermasse al suo bordo destro. Sta qui e non nel .tsx
// perche' passandola come letterale al call site nessun presidio la vedeva:
// metterla a 0 rimetteva il mese corrente sotto la colonna sticky con tutti i
// test verdi (mutante M14 della review del 23/09).
export const LARGHEZZA_COLONNA_TOTALE = 160;

/**
 * Lo scroll orizzontale da applicare al contenitore della tabella per mostrare
 * il mese corrente, letto direttamente dai due nodi DOM.
 *
 * Wrapper attorno a `scrollPerMeseCorrente` che esiste per una ragione sola: il
 * conto stava dentro un `useEffect` e leggeva `larghezzaTotale: 160` scritto a
 * mano nel call site. La funzione era provata, il chiamante no.
 */
export function scrollDaNodi(
  scroller: { clientWidth: number },
  cella: { offsetLeft: number; offsetWidth: number },
): number {
  return scrollPerMeseCorrente({
    offsetCella: cella.offsetLeft,
    larghezzaCella: cella.offsetWidth,
    larghezzaTotale: LARGHEZZA_COLONNA_TOTALE,
    larghezzaVisibile: scroller.clientWidth,
  });
}

/**
 * Il colore di una barra "result" della cascata P&L (Margine F&B, MOL).
 *
 * Il verde/rosso dice «bene»/«male»: sui mesi senza costi caricati non lo sa, e
 * il MOL esce verde pieno perche' i costi mancano, non perche' vada bene. E' lo
 * stesso difetto gia' chiuso nella tabella il 23/09 — ma la cascata era il
 * QUARTO punto che colora per segno, e non era stato contato: la barra verde
 * restava a pochi centimetri dai gauge che dicono «Nessun giudizio: N mesi su M
 * non ha costi registrati». Trovato dalla terza review, stessa giornata.
 */
export function coloreBarraRisultato(
  valore: number,
  incompleto: boolean,
): string {
  if (incompleto) return "var(--muted-foreground)";
  return valore >= 0 ? "var(--positivo)" : "var(--negativo)";
}
