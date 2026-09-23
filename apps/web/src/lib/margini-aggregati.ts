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
  costi_personale: number;
  mol: number;
  quote_riparto_fb: number;
  quote_riparto_spese: number;
};

// Le 3 righe virtuali di ROWS. Restano qui e non nel .tsx perche' `costi_fb_auto`
// e `costi_spese_auto` sommano le quote di riparto: se una `derive` sparisce, la
// quota ripartita non viene piu' mostrata e il costo appare piu' basso del vero
// (e' l'errore gia' visto lato worker nel ciclo 07).
export const DERIVE: Readonly<Record<string, (m: MesePivot) => number>> = Object.freeze({
  costi_fb_auto: (m: MesePivot) => m.costi_fb_auto + (m.quote_riparto_fb ?? 0),
  costi_spese_auto: (m: MesePivot) => m.costi_spese_auto + (m.quote_riparto_spese ?? 0),
  totale_costi: (m: MesePivot) => m.costi_spese_totali + m.costi_personale,
});

export type RowLike = { key: string; derive?: (m: MesePivot) => number };

export function rowVal(row: RowLike, m: MesePivot): number {
  if (row.derive) return row.derive(m);
  return (m[row.key as keyof MesePivot] as number) ?? 0;
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

// Un mese con ricavi e NESSUN costo automatico: il suo margine non e' un
// risultato, e' un buco nei dati. Stessa definizione di `_mesi_senza_costi`
// (services/routers/margini.py): F&B totali <= 0 E spese totali <= 0, dove
// "spese totali" include gia' le quote di riparto dei costi di gruppo — un mese
// con 114 EUR di sola quota conta come "con costi". Le due definizioni devono
// restare uguali: divergendo, la tabella colorerebbe di verde proprio i mesi per
// cui «Analisi visiva» dice di non avere un giudizio.
//
// Serve solo per DECIDERE IL COLORE. Il numero non si tocca (decisione di
// Mattia): il MOL di un mese senza costi resta quello che e', smette solo di
// essere dichiarato buono.
export function meseSenzaCosti(m: MesePivot): boolean {
  if ((m.fatturato_netto ?? 0) <= 0) return false;
  return (m.costi_fb_totali ?? 0) <= 0 && (m.costi_spese_totali ?? 0) <= 0;
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
