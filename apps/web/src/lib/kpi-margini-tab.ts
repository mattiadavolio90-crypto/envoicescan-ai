// Quali tessere KPI mostrare in Ricavi e Margini, in base al tab aperto.
//
// Fino al 23/09/2026 le sei tessere restavano IDENTICHE passando da Marginalita'
// a Coperti ad Analisi Avanzate: `KpiBar` e' reso in `margini/page.tsx` sopra il
// TabsSwitcher e non sapeva quale tab fosse attivo. In Coperti si leggeva lo
// scontrino medio con sopra «MOL 2.678.419 €», che con quel tab non c'entra.
//
// Non si eliminano (decisione presa con Mattia il 21/09, dopo obiezione portata
// e accolta): in Analisi Avanzate NON esiste una tabella con quei totali, in
// Coperti «Giorno piu' pieno» non e' riportato altrove, e la sparkline da' il
// trend che la colonna TOTALE non da'. Si riducono e si legano al tab.
//
// Su Marginalita' restano tre: Fatturato, MOL e Margine Lordo. Le altre tre
// (Costi F&B, Spese Generali, Costo Personale) sono gia' nella colonna TOTALE
// della tabella sotto, riga per riga — erano il secondo dei tre posti in cui la
// pagina scriveva lo stesso numero.

export type TabMargini = "calcolo" | "coperti" | "analisi";

// Le chiavi sono quelle delle card in `margini/kpi-bar.tsx`: cambiare una label
// li' senza cambiarla qui fa sparire la tessera invece di rinominarla. Sono
// asserite da tests/test_kpi_margini_tab_frontend.py, che confronta le due liste.
export const KPI_TUTTE = [
  "Fatturato Netto",
  "Costi F&B",
  "Margine Lordo",
  "Spese Generali",
  "Costo Personale",
  "MOL",
] as const;

const PER_TAB: Record<TabMargini, readonly string[]> = {
  // I tre numeri che rispondono a «come sta andando»: quanto entra, quanto
  // resta dopo la materia prima, quanto resta alla fine.
  calcolo: ["Fatturato Netto", "Margine Lordo", "MOL"],
  // Coperti ha le sue quattro card dentro il tab (coperti totali, media/giorno,
  // scontrino medio, giorno piu' pieno): qui basta il fatturato che le lega.
  coperti: ["Fatturato Netto"],
  // Analisi Avanzate ragiona sui costi per centro: il fatturato e' la base delle
  // incidenze, i costi F&B il totale che i centri si spartiscono.
  analisi: ["Fatturato Netto", "Costi F&B", "Margine Lordo"],
};

/**
 * Le etichette da mostrare per un tab. Senza `tab` (o su un valore che non
 * conosciamo) torna tutte e sei: un tab nuovo deve degradare mostrando di piu',
 * non una barra vuota. Lo usa anche la demo, che non ha un tab attivo vero.
 */
export function kpiPerTab(tab?: string | null): readonly string[] {
  if (!tab) return KPI_TUTTE;
  const scelte = PER_TAB[tab as TabMargini];
  return scelte ?? KPI_TUTTE;
}

// Le tessere da rendere, gia' scelte. Sta qui e non nel componente perche' un
// test puo' ESEGUIRLA: con la `.filter()` dentro il .tsx, disattivarla lasciava
// verdi tutti i test (mutante N2 del 23/09, sopravvissuto) — provavo la lista
// giusta senza provare che qualcuno la usasse. E' lo stesso errore dei blocchi
// B e C di questa fase, la terza volta.
//
// `carte` arriva dal componente (i valori dipendono dai KPI e dal tono del MOL):
// qui si decide solo QUALI passano e in che ordine.
export function selezionaKpi<T extends { label: string }>(
  carte: readonly T[],
  tab?: string | null,
): T[] {
  const visibili = kpiPerTab(tab);
  // Ordine di `carte`, non della lista per-tab: le tessere non si riordinano
  // passando da un tab all'altro, spariscono e basta.
  return carte.filter((c) => visibili.includes(c.label));
}

// Le colonne della griglia, per numero di tessere.
//
// Classi INTERE, mai interpolate: Tailwind legge i sorgenti come testo e una
// classe costruita a runtime (`lg:grid-cols-` + n) non finisce nel CSS — la
// griglia collasserebbe a una colonna senza nessun errore.
// Include la BASE (`grid-cols-*`, sotto i 768px), non solo `md:`/`lg:`.
//
// Prima la base era scritta fissa nel componente come `grid-cols-2`: con sei
// tessere andava sempre bene, ma da quando seguono il tab il caso n=1 (Coperti)
// rendeva una card a meta' larghezza con meta' riga vuota accanto. Il numero di
// tessere lo decide il tab, quindi la griglia deve seguirlo a ogni larghezza.
const COLONNE: Record<number, string> = {
  1: "grid-cols-1 md:grid-cols-1 lg:grid-cols-1",
  2: "grid-cols-2 md:grid-cols-2 lg:grid-cols-2",
  3: "grid-cols-1 md:grid-cols-3 lg:grid-cols-3",
  4: "grid-cols-2 md:grid-cols-2 lg:grid-cols-4",
  5: "grid-cols-2 md:grid-cols-3 lg:grid-cols-5",
  6: "grid-cols-2 md:grid-cols-3 lg:grid-cols-6",
};

export function colonneGriglia(n: number): string {
  return COLONNE[n] ?? "grid-cols-2 md:grid-cols-3 lg:grid-cols-6";
}
