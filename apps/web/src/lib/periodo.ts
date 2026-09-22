// Intervalli di date per i filtri di periodo — FONTE UNICA.
//
// Il 22/09/2026 la stessa funzione esisteva in CINQUE copie: `isoDateRange` in
// prezzi/nc-tab, prezzi/sconti-tab, prezzi/score-tab, prezzi/variazioni-tab e
// `isoRange` in analisi-e-tag (stessa matematica, chiavi diverse: `{da, a}`
// invece di `{data_da, data_a}` — la divergenza che impediva di accorgersene
// cercando un nome solo).
//
// Due difetti che le copie avevano e qui non ci sono:
//  - il giorno finale non era zero-paddato (`2026-02-9` invece di `2026-02-09`).
//    Non capita mai, perche' nessun mese finisce prima del 28, ma era una
//    trappola che aspettava un caso limite;
//  - «tutto l'anno» finiva al 31 DICEMBRE, cioe' nel futuro: a schermo si
//    leggeva «01/01/26 → 31/12/26» mentre Margini e Analisi Fatture dicevano
//    «→ oggi». Sui dati non cambiava nulla (misurato a DB il 22/09: zero righe
//    con data futura in tutto il parco), ma l'etichetta mentiva.

/** Primo e ultimo giorno di un mese, in ISO. Zero-padding su entrambi. */
export function intervalloMese(anno: number, mese: number): { data_da: string; data_a: string } {
  const ultimo = new Date(anno, mese, 0).getDate();
  const mm = String(mese).padStart(2, "0");
  return {
    data_da: `${anno}-${mm}-01`,
    data_a: `${anno}-${mm}-${String(ultimo).padStart(2, "0")}`,
  };
}

/**
 * Intervallo di un anno, o di un suo mese quando `mese` e' valorizzato.
 *
 * L'anno IN CORSO si ferma a oggi, non al 31 dicembre: «anno in corso» che
 * comprende novembre e dicembre non e' un periodo, e' una promessa. Gli anni
 * passati restano interi.
 */
export function intervalloPeriodo(
  anno: number,
  mese: number | null,
  oggi: Date = new Date(),
): { data_da: string; data_a: string } {
  if (mese !== null) return intervalloMese(anno, mese);
  const data_da = `${anno}-01-01`;
  if (anno < oggi.getFullYear()) return { data_da, data_a: `${anno}-12-31` };
  if (anno > oggi.getFullYear()) return { data_da, data_a: `${anno}-12-31` };
  const m = String(oggi.getMonth() + 1).padStart(2, "0");
  const g = String(oggi.getDate()).padStart(2, "0");
  return { data_da, data_a: `${oggi.getFullYear()}-${m}-${g}` };
}
