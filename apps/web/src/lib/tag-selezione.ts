// Logica del riquadro «Modifica tag»: una lista unica a spunte in cui un
// prodotto spuntato e' dentro il tag. Estratta qui perche' un .tsx non e'
// raggiungibile dai test (tests/test_tag_selezione_frontend.py). Serve i tag di
// sede e quelli di catena: i tipi chiedono solo i campi che usa.

/** Una descrizione fra cui scegliere (sede: `DescrizioneDistinta`; catena: `n` letto come occorrenze). */
export type DescrizioneScelta = {
  descrizione: string;
  descrizione_key: string;
  occorrenze: number;
};

/** Un prodotto gia' nel tag. */
export type ProdottoDelTag = {
  descrizione: string;
  descrizione_key: string;
};

/** Tetto di righe renderizzate nel selettore. Non e' un filtro di dominio:
 *  serve solo a non montare 1800 nodi in un dialog. Quando taglia, la UI lo
 *  dice esplicitamente. */
export const MAX_DESC_VISIBILI = 80;

export type FiltroSelettore = "nel_tag" | "tutti";

export type RigaSelettore = {
  descrizione: string;
  descrizione_key: string;
  /** null = prodotto del tag che non compare piu' fra le descrizioni. */
  occorrenze: number | null;
};

export type EsitoSelettore = {
  visibili: RigaSelettore[];
  /** Tutte le righe che passano filtro e ricerca, anche oltre il tetto. */
  corrispondenti: RigaSelettore[];
  totale: number;
  nascoste: number;
  spuntateCorrispondenti: number;
};

export function chiaviDelTag(prodottiTag: ProdottoDelTag[]): Set<string> {
  return new Set(prodottiTag.map((p) => p.descrizione_key));
}

/**
 * Le righe del selettore.
 *
 * - UNIONE: un prodotto del tag la cui chiave non compare fra le descrizioni
 *   (fatture eliminate, descrizione cambiata) resta in lista, in coda e con
 *   `occorrenze: null`. Senza, non lo si potrebbe piu' togliere.
 * - «Nel tag» guarda le chiavi presenti nel tag ALL'APERTURA (`prodottiTag`),
 *   non le spunte correnti: togliere una spunta non fa sparire la riga sotto
 *   il dito.
 * - `ricercaSulServer`: le descrizioni sono gia' il risultato della ricerca
 *   (catena) e non si rifiltrano. Il server confronta TUTTE le varianti di una
 *   descrizione e ne restituisce una sola, che puo' non contenere il testo: un
 *   secondo filtro qui toglierebbe risultati giusti. I prodotti del tag che non
 *   sono fra i risultati si filtrano invece qui, col testo.
 */
export function righeSelettore(
  descrizioni: DescrizioneScelta[],
  prodottiTag: ProdottoDelTag[],
  ricerca: string,
  filtro: FiltroSelettore,
  selezionati: Set<string> = new Set(),
  ricercaSulServer = false,
): EsitoSelettore {
  const iniziali = chiaviDelTag(prodottiTag);
  const viste = new Set<string>();
  const tutte: RigaSelettore[] = [];
  for (const d of descrizioni) {
    if (viste.has(d.descrizione_key)) continue;
    viste.add(d.descrizione_key);
    tutte.push({ descrizione: d.descrizione, descrizione_key: d.descrizione_key, occorrenze: d.occorrenze });
  }
  for (const p of prodottiTag) {
    if (viste.has(p.descrizione_key)) continue;
    viste.add(p.descrizione_key);
    tutte.push({ descrizione: p.descrizione, descrizione_key: p.descrizione_key, occorrenze: null });
  }

  const testo = ricerca.trim().toLowerCase();
  const corrispondenti = tutte.filter(
    (r) =>
      (filtro === "tutti" || iniziali.has(r.descrizione_key)) &&
      (!testo || (ricercaSulServer && r.occorrenze !== null) || r.descrizione.toLowerCase().includes(testo)),
  );
  const visibili = corrispondenti.slice(0, MAX_DESC_VISIBILI);
  return {
    visibili,
    corrispondenti,
    totale: corrispondenti.length,
    nascoste: corrispondenti.length - visibili.length,
    spuntateCorrispondenti: corrispondenti.filter((r) => selezionati.has(r.descrizione_key)).length,
  };
}

export function selezionaTutti(selezionati: Set<string>, chiavi: Iterable<string>): Set<string> {
  const nuovo = new Set(selezionati);
  for (const k of chiavi) nuovo.add(k);
  return nuovo;
}

export function deselezionaTutti(selezionati: Set<string>, chiavi: Iterable<string>): Set<string> {
  const nuovo = new Set(selezionati);
  for (const k of chiavi) nuovo.delete(k);
  return nuovo;
}

export function inverti(selezionati: Set<string>, chiave: string): Set<string> {
  const nuovo = new Set(selezionati);
  if (nuovo.has(chiave)) nuovo.delete(chiave);
  else nuovo.add(chiave);
  return nuovo;
}

export function differenze(
  iniziali: Set<string>,
  correnti: Set<string>,
): { aggiungi: string[]; togli: string[] } {
  return {
    aggiungi: [...correnti].filter((k) => !iniziali.has(k)),
    togli: [...iniziali].filter((k) => !correnti.has(k)),
  };
}

export type CorpoModificheProdotti = {
  aggiungi: { descrizione: string; descrizione_key: string; fattore_kg: null }[];
  togli: string[];
};

/**
 * Chiave -> descrizione di tutte le righe viste da quando il riquadro e' aperto.
 * Con la ricerca sul server una riga spuntata sparisce dalla lista alla ricerca
 * successiva, ma al Salva serve ancora la sua descrizione.
 */
export function ricordaDescrizioni(
  memoria: Map<string, string>,
  righe: Iterable<{ descrizione: string; descrizione_key: string }>,
): Map<string, string> {
  const nuova = new Map(memoria);
  for (const r of righe) if (!nuova.has(r.descrizione_key)) nuova.set(r.descrizione_key, r.descrizione);
  return nuova;
}

/** Il body di PATCH /api/tag/{id}/prodotti (e /api/gruppo/tag/{id}/prodotti). */
export function corpoModifiche(
  diff: { aggiungi: string[]; togli: string[] },
  righe: Iterable<{ descrizione: string; descrizione_key: string }>,
): CorpoModificheProdotti {
  const perChiave = new Map([...righe].map((r) => [r.descrizione_key, r.descrizione]));
  return {
    aggiungi: diff.aggiungi.map((k) => ({
      descrizione: perChiave.get(k) ?? k,
      descrizione_key: k,
      fattore_kg: null,
    })),
    togli: diff.togli,
  };
}

/** Elementi per lista in una sola PATCH: il worker ne accetta al massimo 2000
 *  (`MAX_ELEMENTI_PER_LISTA` in services/tag_organizza_service.py). «Seleziona
 *  tutti» su una sede con 2.277 descrizioni li supera: si manda a blocchi. */
export const BLOCCO_MODIFICHE = 1000;

/** Spezza il body in PATCH successive, ognuna con al massimo `blocco` elementi
 *  per lista. Un body vuoto produce zero blocchi. */
export function blocchiModifiche(
  corpo: CorpoModificheProdotti,
  blocco: number = BLOCCO_MODIFICHE,
): CorpoModificheProdotti[] {
  const n = Math.ceil(Math.max(corpo.aggiungi.length, corpo.togli.length) / blocco);
  const out: CorpoModificheProdotti[] = [];
  for (let i = 0; i < n; i++) {
    out.push({
      aggiungi: corpo.aggiungi.slice(i * blocco, (i + 1) * blocco),
      togli: corpo.togli.slice(i * blocco, (i + 1) * blocco),
    });
  }
  return out;
}

/** Le due meta' del contatore nel piede, separate perche' le rimozioni hanno
 *  un altro colore. null = quella meta' non c'e'. */
export function partiContatore(aggiungi: number, togli: number): { aggiungi: string | null; togli: string | null } {
  return {
    aggiungi: aggiungi > 0 ? `+${aggiungi} da aggiungere` : null,
    togli: togli > 0 ? `−${togli} da togliere` : null,
  };
}

function prodotti(n: number): string {
  return `${n} prodott${n === 1 ? "o" : "i"}`;
}

/** Il testo del link nell'intestazione del tag. */
export function etichettaProdotti(n: number): string {
  return n === 0 ? "Nessun prodotto" : prodotti(n);
}

/** Il resoconto dopo il salvataggio, con gli accordi giusti. */
export function testoEsito(aggiunte: number, tolte: number): string {
  const parti: string[] = [];
  if (aggiunte > 0) parti.push(`${prodotti(aggiunte)} aggiunt${aggiunte === 1 ? "o" : "i"}`);
  if (tolte > 0) {
    parti.push(aggiunte > 0 ? `${tolte} tolt${tolte === 1 ? "o" : "i"}` : `${prodotti(tolte)} tolt${tolte === 1 ? "o" : "i"}`);
  }
  return parti.join(", ");
}
