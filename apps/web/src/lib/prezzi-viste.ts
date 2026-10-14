// Le tre viste delle variazioni di prezzo, uguali nell'Osservatorio del PV e
// nella scheda «Prezzi» di catena: Tutti, Preferiti, Da controllare.
//
// «Da controllare» raccoglie i prezzi saltati di 10 volte o piu' fra due
// acquisti (`da_controllare` dal worker): una bottiglia contro una cassa, il kg
// contro il cartone. Non sono rincari, e misurato l'11/10/2026 sette righe cosi'
// spostavano di 1.400 EUR l'impatto/mese di una catena. Restano consultabili,
// ma fuori da «Tutti» e dai totali.

export type VistaPrezzi = "tutti" | "preferiti" | "da_controllare";

// Suffissi che il worker aggiunge al nome a video (« ⚠️ >6m»).
const SUFFISSI_UI = [" ⚠️ >6M", " ⚠ >6M"];

// Le parole a video (Mattia, 13/10/2026: «saltati» e «cambio» non si capivano).
export const ETICHETTA_DA_CONTROLLARE = "Confezione diversa?";

export const SPIEGAZIONE_DA_CONTROLLARE =
  "Il prezzo è diventato 10 volte più alto o più basso da un acquisto all'altro, per esempio da 0,40 € a 14 €. Quasi sempre il fornitore ha fatturato una volta il pezzo e una volta la cassa, o una volta il kg e una volta il cartone. Non è un aumento vero, quindi resta fuori dai totali.";

// Il worker aggiunge « ⚠️ >6m» al nome quando fra gli ultimi due acquisti sono
// passati piu' di sei mesi. A video «>6m» non si capiva: il nome resta pulito e
// la nota si scrive per esteso.
export const NOTA_OLTRE_SEI_MESI = "Fra gli ultimi due acquisti sono passati più di 6 mesi";

export function nomeProdotto(prodotto: string): { nome: string; oltreSeiMesi: boolean } {
  const testo = prodotto.trimEnd();
  for (const s of SUFFISSI_UI) {
    if (testo.toUpperCase().endsWith(s)) return { nome: testo.slice(0, -s.length).trimEnd(), oltreSeiMesi: true };
  }
  return { nome: prodotto, oltreSeiMesi: false };
}

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
