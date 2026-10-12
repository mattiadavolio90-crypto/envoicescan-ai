// Le tre viste delle variazioni di prezzo, uguali nell'Osservatorio del PV e
// nella scheda «Prezzi» di catena: Tutti, Preferiti, Da controllare.
//
// «Da controllare» raccoglie i prezzi saltati di 10 volte o piu' fra due
// acquisti (`da_controllare` dal worker): una bottiglia contro una cassa, il kg
// contro il cartone. Non sono rincari, e misurato l'11/10/2026 sette righe cosi'
// spostavano di 1.400 EUR l'impatto/mese di una catena. Restano consultabili,
// ma fuori da «Tutti» e dai totali.

export type VistaPrezzi = "tutti" | "preferiti" | "da_controllare";

export const SPIEGAZIONE_DA_CONTROLLARE =
  "Prezzi saltati di 10 volte o più fra due acquisti: di solito è cambiata la confezione o l'unità di misura (bottiglia o cassa, kg o cartone). Non sono rincari veri e non entrano nei totali.";

export function inVista(
  r: { da_controllare?: boolean },
  vista: VistaPrezzi,
  preferito: boolean,
): boolean {
  if (vista === "da_controllare") return r.da_controllare === true;
  if (r.da_controllare) return false;
  return vista === "tutti" || preferito;
}

export function contaDaControllare(righe: readonly { da_controllare?: boolean }[]): number {
  return righe.filter((r) => r.da_controllare === true).length;
}

// Suffissi che il worker aggiunge al nome a video (« ⚠️ >6m»).
const SUFFISSI_UI = [" ⚠️ >6M", " ⚠ >6M"];

/**
 * La coppia con cui si salva e si riconosce la stella. Usa le chiavi intere
 * quando il worker le manda: il nome a video e' troncato (prodotto a 60,
 * fornitore a 30), e fino all'11/10/2026 la stella salvata col nome troncato
 * non si riaccendeva piu' — 10 preferiti su 19.
 */
export function coppiaPreferito(r: {
  prodotto: string;
  fornitore: string;
  desc_key?: string;
  forn_key?: string;
}): { prodotto: string; fornitore: string } {
  if (r.desc_key) return { prodotto: r.desc_key, fornitore: r.forn_key ?? "" };
  let d = r.prodotto.trim().toUpperCase();
  for (const s of SUFFISSI_UI) {
    if (d.endsWith(s)) {
      d = d.slice(0, -s.length).trim();
      break;
    }
  }
  return { prodotto: d, fornitore: r.fornitore.trim().toUpperCase() };
}

export function chiavePreferito(r: Parameters<typeof coppiaPreferito>[0]): string {
  const c = coppiaPreferito(r);
  return `${c.prodotto}|${c.fornitore}`;
}
