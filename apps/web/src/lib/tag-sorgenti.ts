// Da dove leggono e dove scrivono la lista dei tag e il riquadro «Modifica
// tag»: i tag della sede (`/api/tag`) o quelli di catena (`/api/gruppo/tag`).
// Le rotte hanno la stessa forma sotto le due basi; cambia la ricerca dei
// prodotti, che in catena va sul server. Estratta qui perche' un .tsx non e'
// raggiungibile dai test (tests/test_tag_sorgenti_frontend.py).

import { MIN_LETTERE_RICERCA } from "@/lib/tag-candidati";
import type { DescrizioneScelta } from "@/lib/tag-selezione";

export type SorgenteTag = {
  base: "/api/tag" | "/api/gruppo/tag";
  /**
   * La lista iniziale dei prodotti e' parziale (catena: i primi 500 per spesa
   * su tutti i punti vendita) e da `MIN_LETTERE_RICERCA` lettere si cerca sul
   * server, fra tutti. Senza, la lista e' completa e si filtra nel browser.
   */
  ricercaRemota: boolean;
};

export const sorgenteSede: SorgenteTag = { base: "/api/tag", ricercaRemota: false };
export const sorgenteCatena: SorgenteTag = { base: "/api/gruppo/tag", ricercaRemota: true };

/** Vero se il testo va cercato sul server invece che filtrato nella lista. */
export function ricercaSulServer(sorgente: SorgenteTag, ricerca: string): boolean {
  return sorgente.ricercaRemota && ricerca.trim().length >= MIN_LETTERE_RICERCA;
}

/** La lista iniziale, all'apertura del riquadro. */
export function urlDescrizioni(sorgente: SorgenteTag): string {
  return `${sorgente.base}/descrizioni`;
}

/** La ricerca sul server per questo testo, o null se il testo si filtra nel browser. */
export function urlRicerca(sorgente: SorgenteTag, ricerca: string): string | null {
  if (!ricercaSulServer(sorgente, ricerca)) return null;
  return `${sorgente.base}/descrizioni?q=${encodeURIComponent(ricerca.trim())}`;
}

/**
 * Le descrizioni di una risposta, nella forma del selettore. La sede manda
 * `occorrenze`, la catena `n` (righe di fattura su tutti i punti vendita).
 * Una riga senza chiave o senza testo si scarta: non si potrebbe ne' spuntare
 * ne' salvare.
 */
export function descrizioniDaRisposta(dato: unknown): DescrizioneScelta[] {
  const righe = (dato as { descrizioni?: unknown } | null)?.descrizioni;
  if (!Array.isArray(righe)) return [];
  const out: DescrizioneScelta[] = [];
  for (const r of righe) {
    if (!r || typeof r !== "object") continue;
    const { descrizione, descrizione_key, occorrenze, n } = r as Record<string, unknown>;
    if (typeof descrizione !== "string" || !descrizione.trim()) continue;
    if (typeof descrizione_key !== "string" || !descrizione_key) continue;
    const conteggio = typeof occorrenze === "number" ? occorrenze : typeof n === "number" ? n : 0;
    out.push({ descrizione, descrizione_key, occorrenze: conteggio });
  }
  return out;
}
