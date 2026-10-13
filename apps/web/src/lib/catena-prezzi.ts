// Scheda «Prezzi» di Analisi catena (/api/gruppo/prezzi): tipi e logica pura.
//
// Due liste diverse, da non confondere:
// - VARIAZIONI: il prezzo di un prodotto che cambia DENTRO un punto vendita,
//   calcolato dal worker con la stessa funzione dell'Osservatorio del PV;
// - DIVARI: lo stesso prodotto dallo stesso fornitore pagato diverso FRA i
//   punti vendita (ultimo prezzo di ciascuno).
// Mescolare le due cose e' l'errore che la scheda esiste per evitare: il PV
// che paga 15,80 e quello che paga 17,58 non sono un rincaro dell'11%.

import { parseDecimaleIt } from "@/lib/format";
import { chiavePreferito, inVista, type VistaPrezzi } from "@/lib/prezzi-viste";

// Il worker riporta la soglia in [0, 100]: a video deve succedere lo stesso.
export const SOGLIA_CATENA_MAX = 100;

export function testoSoglia(soglia: number | null | undefined): string {
  return soglia == null ? "" : String(soglia).replace(".", ",");
}

/** La casella «Mostra da … % in su» quando l'utente conferma (Invio o clic fuori).
 *  `attuale` e' la soglia che la scheda sta gia' mostrando: quella degli avvisi
 *  finche' l'utente non ne scrive una. `nuova` e' null quando non c'e' niente da
 *  ricaricare: testo non numerico o negativo (si ripristina `attuale`) o uguale
 *  ad `attuale` — al primo clic fuori dalla casella la scheda ricaricava sempre. */
export function sogliaDaApplicare(
  testo: string,
  attuale: number | null,
  massimo: number = SOGLIA_CATENA_MAX,
): { testo: string; nuova: number | null } {
  const val = parseDecimaleIt(testo);
  if (Number.isNaN(val) || val < 0) return { testo: testoSoglia(attuale), nuova: null };
  const limitata = Math.min(massimo, val);
  return { testo: testoSoglia(limitata), nuova: limitata === attuale ? null : limitata };
}

export type VariazionePrezzoCatena = {
  ristorante_id: string;
  nome_pv: string;
  prodotto: string;
  categoria: string;
  fornitore: string;
  storico_valori: number[];
  media: number;
  penultimo: number;
  ultimo: number;
  aumento_perc: number;
  data: string;
  trend: string;
  impatto_stimato: number;
  delta_euro: number;
  n_pv_stesso_verso: number;
  n_pv_confrontabili: number;
  /** La stella e' quella del PV della riga (la stessa del suo Osservatorio). */
  preferito?: boolean;
  desc_key?: string;
  forn_key?: string;
  da_controllare?: boolean;
};

export type PrezzoPV = {
  ristorante_id: string;
  nome_pv: string;
  ultimo: number;
  data: string;
  scarto_perc: number;
  extra_stimato: number;
};

export type DivarioPrezzo = {
  prodotto: string;
  categoria: string;
  fornitore: string;
  prezzo_min: number;
  prezzo_max: number;
  divario_perc: number;
  extra_stimato: number;
  per_pv: PrezzoPV[];
  /** Prezzi a 10 volte o piu' l'uno dall'altro: confezioni diverse, non un divario. */
  da_controllare?: boolean;
  /** Chiave del prodotto: due divari possono avere lo stesso nome a video. */
  desc_key?: string;
  forn_key?: string;
  /** Stellato in almeno uno dei PV del confronto. */
  preferito?: boolean;
};

export type GruppoPrezzi = {
  variazioni: VariazionePrezzoCatena[];
  divari: DivarioPrezzo[];
  soglia: number;
  periodo_label: string;
  acquisti_nel_periodo: number;
  divario_finestra_giorni: number;
};

export type FiltriPrezzi = {
  /** id del punto vendita, "" = tutti */
  pv: string;
  ricerca: string;
  /** Assente = «Tutti». Sui divari «Preferiti» = stellato in almeno un PV del confronto. */
  vista?: VistaPrezzi;
  /** "" o assente = tutte / tutti, come nell'Osservatorio del PV. */
  categoria?: string;
  fornitore?: string;
};

/** La chiave di un divario: il nome a video non basta (stesso nome, provenienze
 *  diverse) e con chiavi doppie la lista teneva a schermo schede vecchie. */
export function chiaveDivario(d: Pick<DivarioPrezzo, "prodotto" | "fornitore" | "desc_key" | "forn_key">): string {
  return d.desc_key ? `${d.desc_key}|${d.forn_key ?? ""}` : `${d.prodotto}|${d.fornitore}`;
}

function filtroValore(atteso: string | undefined, valore: string): boolean {
  return !atteso || valore === atteso;
}

/** Categorie e fornitori delle righe, per le due tendine dei filtri. */
export function valoriFiltro(righe: readonly { categoria: string; fornitore: string }[]): {
  categorie: string[];
  fornitori: string[];
} {
  const ordina = (xs: string[]) => Array.from(new Set(xs.filter(Boolean))).sort((a, b) => a.localeCompare(b, "it"));
  return { categorie: ordina(righe.map((r) => r.categoria)), fornitori: ordina(righe.map((r) => r.fornitore)) };
}

/** La stella di una riga: PV + coppia intera. Due PV con lo stesso prodotto
 *  hanno due stelle distinte, come nei loro Osservatori. */
export function chiaveStellaCatena(v: Pick<VariazionePrezzoCatena, "ristorante_id" | "prodotto" | "fornitore" | "desc_key" | "forn_key">): string {
  return `${v.ristorante_id}|${chiavePreferito(v)}`;
}

/** Le stelle accese nei dati del worker, per lo stato ottimistico della scheda. */
export function stelleIniziali(variazioni: readonly VariazionePrezzoCatena[]): Set<string> {
  return new Set(variazioni.filter((v) => v.preferito).map(chiaveStellaCatena));
}

export type PvPrezzi = { id: string; nome: string };

/** I PV che compaiono nei dati, per il filtro: in ordine di nome. */
export function pvDeiPrezzi(data: GruppoPrezzi | null): PvPrezzi[] {
  if (!data) return [];
  const nomi = new Map<string, string>();
  for (const v of data.variazioni) nomi.set(v.ristorante_id, v.nome_pv);
  for (const d of data.divari) for (const p of d.per_pv) nomi.set(p.ristorante_id, p.nome_pv);
  return [...nomi.entries()]
    .map(([id, nome]) => ({ id, nome }))
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));
}

function corrisponde(ricerca: string, ...campi: string[]): boolean {
  const q = ricerca.trim().toLowerCase();
  return !q || campi.some((c) => c.toLowerCase().includes(q));
}

/** Filtrate e ordinate come l'Osservatorio del PV: dall'impatto in euro piu' alto,
 *  aumenti e cali insieme (un calo grosso e' una notizia quanto un rincaro). */
export function filtraVariazioni(
  variazioni: VariazionePrezzoCatena[],
  f: FiltriPrezzi,
  stelle?: ReadonlySet<string>,
): VariazionePrezzoCatena[] {
  const vista = f.vista ?? "tutti";
  return variazioni
    .filter(
      (v) =>
        (!f.pv || v.ristorante_id === f.pv) &&
        filtroValore(f.categoria, v.categoria) &&
        filtroValore(f.fornitore, v.fornitore) &&
        corrisponde(f.ricerca, v.prodotto, v.fornitore) &&
        inVista(v, vista, stelle ? stelle.has(chiaveStellaCatena(v)) : v.preferito === true),
    )
    .sort((a, b) => Math.abs(b.impatto_stimato) - Math.abs(a.impatto_stimato));
}

/** Con un PV scelto restano i divari in cui quel PV c'e', dal piu' caro al meno caro. */
export function filtraDivari(divari: DivarioPrezzo[], f: FiltriPrezzi): DivarioPrezzo[] {
  return divari.filter(
    (d) =>
      (!f.pv || d.per_pv.some((p) => p.ristorante_id === f.pv)) &&
      filtroValore(f.categoria, d.categoria) &&
      filtroValore(f.fornitore, d.fornitore) &&
      corrisponde(f.ricerca, d.prodotto, d.fornitore) &&
      inVista(d, f.vista ?? "tutti", d.preferito === true),
  );
}

/**
 * Se il rincaro e' del fornitore o della sede. `null` quando il prodotto lo
 * compra un solo PV: non c'e' niente con cui confrontarlo, e «1 su 1» direbbe
 * «listino» su un caso che non lo prova.
 */
type Diffusione = Pick<VariazionePrezzoCatena, "n_pv_stesso_verso" | "n_pv_confrontabili" | "aumento_perc">;

export function etichettaDiffusione(v: Diffusione): string | null {
  if (v.n_pv_confrontabili < 2) return null;
  const verbo = v.aumento_perc < 0 ? "Calato" : "Aumentato";
  if (v.n_pv_stesso_verso >= 2) return `${verbo} in ${v.n_pv_stesso_verso} PV su ${v.n_pv_confrontabili}`;
  const altri = v.n_pv_confrontabili - 1;
  return `Solo qui: ${altri === 1 ? "l'altro PV no" : `gli altri ${altri} PV no`}`;
}

/** La frase al passaggio del mouse sull'etichetta. */
export function spiegazioneDiffusione(v: Diffusione): string | null {
  if (v.n_pv_confrontabili < 2) return null;
  const verso = v.aumento_perc < 0 ? "calato" : "aumentato";
  if (v.n_pv_stesso_verso >= 2) {
    return `Il prezzo è ${verso} in ${v.n_pv_stesso_verso} dei ${v.n_pv_confrontabili} punti vendita che comprano questo prodotto: probabilmente è il fornitore che ha cambiato il listino.`;
  }
  const altri = v.n_pv_confrontabili - 1;
  return `Il prezzo è ${verso} solo in questo punto vendita: ${altri === 1 ? "l'altro che compra" : `gli altri ${altri} che comprano`} questo prodotto non hanno avuto lo stesso cambiamento.`;
}

export type TotaliPrezzi = {
  aumenti: number;
  cali: number;
  /** Media delle variazioni %, come «Variazione media» nell'Osservatorio del PV. */
  variazioneMedia: number;
  impattoNetto: number;
  divari: number;
  extraDivari: number;
};

/**
 * KPI della scheda sulle righe FILTRATE. Con un PV scelto l'extra dei divari e'
 * quello di quel PV soltanto: il totale del divario comprende le altre sedi, e
 * sommarlo sotto il nome di una sola le attribuirebbe costi non suoi.
 */
export function totaliPrezzi(variazioni: VariazionePrezzoCatena[], divari: DivarioPrezzo[], pv: string): TotaliPrezzi {
  const extra = divari.reduce(
    (s, d) => s + (pv ? d.per_pv.filter((p) => p.ristorante_id === pv).reduce((t, p) => t + p.extra_stimato, 0) : d.extra_stimato),
    0,
  );
  return {
    aumenti: variazioni.filter((v) => v.aumento_perc > 0).length,
    cali: variazioni.filter((v) => v.aumento_perc < 0).length,
    variazioneMedia: variazioni.length ? variazioni.reduce((t, v) => t + v.aumento_perc, 0) / variazioni.length : 0,
    impattoNetto: Math.round(variazioni.reduce((s, v) => s + v.impatto_stimato, 0) * 100) / 100,
    divari: divari.length,
    extraDivari: Math.round(extra * 100) / 100,
  };
}
