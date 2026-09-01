// Punti di una mini-linea `<polyline>` su una serie di numeri.
//
// Non e' la stessa curva di calcolaSparkline (che disegna un path M/L con la
// % YTD e vive su una serie di MOL mensili): questa e' la famiglia piu'
// semplice usata in margini, prezzi, analisi-fatture e demo, dove l'input e'
// un `number[]` e non c'e' nessuna percentuale.
//
// Le quattro copie che questa funzione sostituisce NON erano identiche, e le
// differenze non sono cosmetiche:
//
//   - geometria diversa (100x24, 96x32, 64x18);
//   - due normalizzazioni diverse dell'asse y — `ancoraZero` include lo zero
//     e l'uno nell'intervallo (`Math.max(...v, 1)` / `Math.min(...v, 0)`),
//     l'altra auto-scala sui soli valori presenti. A parita' di dati disegnano
//     linee DIVERSE: non si potevano collassare in un comportamento unico
//     senza cambiare grafici oggi corretti. Da qui i parametri.
//   - `decimali`: pivot-tab non arrotondava le coordinate, le altre a 1.
//
// L'unico comportamento reso uniforme e' il filtro dei valori non finiti, che
// aveva UNA sola delle quattro (margini/kpi-bar): senza, un NaN o un Infinity
// nella serie propaga in min/max e produce `points="NaN,NaN"`, cioe' un grafico
// rotto in silenzio. Le altre tre filtravano isNaN a monte o niente affatto —
// e isNaN non ferma Infinity.

export type OpzioniSparkline = {
  w: number;
  h: number;
  // true: l'asse comprende sempre 0 e 1 (una serie tutta positiva parte da
  // zero, non dal suo minimo). false: la scala si adatta ai valori presenti.
  ancoraZero?: boolean;
  // Margine verticale in px sottratto all'altezza utile (kpi-bar usa 2).
  padY?: number;
  // Cifre decimali delle coordinate; null = nessun arrotondamento.
  decimali?: number | null;
};

// Meno di due punti non e' una linea: chi chiama decide cosa mostrare al posto
// (un trattino, un box vuoto, niente). Torna null, non una stringa vuota, per
// non disegnare una polyline degenere.
export function puntiSparkline(valori: number[], opts: OpzioniSparkline): string | null {
  const { w, h, ancoraZero = false, padY = 0, decimali = 1 } = opts;
  const vals = (valori ?? []).filter((v) => Number.isFinite(v));
  if (vals.length < 2) return null;

  const max = ancoraZero ? Math.max(...vals, 1) : Math.max(...vals);
  const min = ancoraZero ? Math.min(...vals, 0) : Math.min(...vals);
  const range = max - min || 1;
  const step = w / (vals.length - 1);
  const utile = h - padY * 2;

  return vals
    .map((v, i) => {
      const x = i * step;
      const y = h - ((v - min) / range) * utile - padY;
      return decimali == null ? `${x},${y}` : `${x.toFixed(decimali)},${y.toFixed(decimali)}`;
    })
    .join(" ");
}
