// Ordinamento della tabella pivot di Analisi Fatture (tab Categorie e Fornitori).
//
// Vive qui e non dentro `pivot-tab.tsx` per una ragione precisa: fino al
// 22/09/2026 l'ordinamento era uno `useState` interno al componente
// `PivotTable`, mentre il bottone "Esporta Excel" sta nel componente padre e
// leggeva `pivot.rows` non ordinato. Il cliente ordinava per una colonna,
// esportava, e trovava nel file un ordine diverso da quello a schermo.
//
// Con la funzione qui e lo stato sollevato al padre, schermo ed export
// chiamano la stessa riga di codice — e un test puo' vederla.

export type SortState = { key: string | null; dir: "asc" | "desc" | null };

/** Lo stato iniziale: spesa totale decrescente, la voce piu' pesante in cima. */
export const SORT_PIVOT_INIZIALE: SortState = { key: "totale", dir: "desc" };

export type RigaPivotOrdinabile = {
  dimensione: string;
  totale: number;
  incidenza_pct: number;
  periodi: Record<string, number>;
};

/**
 * Il ciclo di un'intestazione cliccata: asc → desc → nessun ordine → asc.
 *
 * Il terzo stato esiste per poter tornare all'ordine con cui il server ha
 * mandato le righe, che non e' riproducibile con nessuna delle due direzioni.
 */
export function prossimoSort(prev: SortState, k: string): SortState {
  if (prev.key !== k) return { key: k, dir: "asc" };
  if (prev.dir === "asc") return { key: k, dir: "desc" };
  if (prev.dir === "desc") return { key: null, dir: null };
  return { key: k, dir: "asc" };
}

/**
 * Le righe nell'ordine scelto dall'utente.
 *
 * Senza ordinamento attivo restituisce l'array originale **senza copiarlo**:
 * e' cio' che permette a `useMemo` di non ricalcolare a valle.
 *
 * `key` puo' essere `dimensione`, `totale`, `incidenza_pct` o la chiave di un
 * periodo (una colonna mese/trimestre/anno). Un periodo assente da una riga
 * vale 0: quella categoria in quel mese non ha speso nulla, e lasciarla
 * `undefined` la manderebbe in fondo o in cima a seconda del motore.
 */
export function ordinaRighePivot<T extends RigaPivotOrdinabile>(
  rows: readonly T[],
  sort: SortState,
): readonly T[] {
  if (!sort.key || !sort.dir) return rows;
  const key = sort.key;
  return [...rows].sort((a, b) => {
    let va: number | string;
    let vb: number | string;
    if (key === "dimensione") {
      va = a.dimensione;
      vb = b.dimensione;
    } else if (key === "totale") {
      va = a.totale;
      vb = b.totale;
    } else if (key === "incidenza_pct") {
      va = a.incidenza_pct;
      vb = b.incidenza_pct;
    } else {
      va = a.periodi[key] ?? 0;
      vb = b.periodi[key] ?? 0;
    }
    let cmp: number;
    if (typeof va === "string" && typeof vb === "string") {
      // `sensitivity: "base"` perche' i nomi fornitore arrivano con
      // maiuscole incoerenti dalle fatture: senza, "Acme" e "ACME" finiscono
      // lontanissimi nell'elenco.
      cmp = va.localeCompare(vb, "it", { sensitivity: "base" });
    } else {
      cmp = (va as number) - (vb as number);
    }
    return sort.dir === "asc" ? cmp : -cmp;
  });
}
