// Scheda «Prezzi» di Analisi catena (/api/gruppo/prezzi): tipi e logica pura.
//
// Due liste diverse, da non confondere:
// - VARIAZIONI: il prezzo di un prodotto che cambia DENTRO un punto vendita,
//   calcolato dal worker con la stessa funzione dell'Osservatorio del PV;
// - DIVARI: lo stesso prodotto dallo stesso fornitore pagato diverso FRA i
//   punti vendita (ultimo prezzo di ciascuno).
// Mescolare le due cose e' l'errore che la scheda esiste per evitare: il PV
// che paga 15,80 e quello che paga 17,58 non sono un rincaro dell'11%.

import { chiavePreferito, inVista, type VistaPrezzi } from "@/lib/prezzi-viste";

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
  /** Assente = «Tutti». Sui divari «Preferiti» vale «Tutti»: un divario e' di piu' PV. */
  vista?: VistaPrezzi;
};

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
      corrisponde(f.ricerca, d.prodotto, d.fornitore) &&
      inVista(d, f.vista === "da_controllare" ? "da_controllare" : "tutti", false),
  );
}

/**
 * Se il rincaro e' del fornitore o della sede. `null` quando il prodotto lo
 * compra un solo PV: non c'e' niente con cui confrontarlo, e «1 su 1» direbbe
 * «listino» su un caso che non lo prova.
 */
export function etichettaDiffusione(v: Pick<VariazionePrezzoCatena, "n_pv_stesso_verso" | "n_pv_confrontabili">): string | null {
  if (v.n_pv_confrontabili < 2) return null;
  if (v.n_pv_stesso_verso >= 2) return `In ${v.n_pv_stesso_verso} PV su ${v.n_pv_confrontabili}`;
  return `Solo questo PV su ${v.n_pv_confrontabili}`;
}

export type TotaliPrezzi = {
  aumenti: number;
  cali: number;
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
    impattoNetto: Math.round(variazioni.reduce((s, v) => s + v.impatto_stimato, 0) * 100) / 100,
    divari: divari.length,
    extraDivari: Math.round(extra * 100) / 100,
  };
}
