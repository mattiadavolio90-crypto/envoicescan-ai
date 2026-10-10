// Boost AI (fase J, 10/10/2026): la scheda «Ricarica AI» dell'admin. Logica
// pura qui, perche' l'unica rete sul frontend esegue lib/ e non i .tsx.

import { fmtCrediti } from "@/lib/home-chat";

export type RicaricaAi = {
  id: string;
  crediti: number;
  nota: string | null;
  creata_da: string | null;
  created_at: string;
};

export type RicaricheAi = { ricariche: RicaricaAi[]; residuo: number; crediti_boost: number };

/** Una risposta del worker si legge cosi' com'e' solo se ha la forma attesa. */
export function leggiRicariche(data: unknown): RicaricheAi | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Partial<RicaricheAi>;
  if (!Array.isArray(d.ricariche) || typeof d.residuo !== "number" || typeof d.crediti_boost !== "number") {
    return null;
  }
  return { ricariche: d.ricariche, residuo: d.residuo, crediti_boost: d.crediti_boost };
}

/** La riga sopra il bottone: quanto resta da spendere. */
export function testoResiduo(r: RicaricheAi): string {
  if (r.ricariche.length === 0) return "Nessuna ricarica AI attivata.";
  return `Ricarica AI da spendere: ${fmtCrediti(r.residuo)} crediti`;
}

/** Una ricarica nell'elenco: «10/10/2026 · 300 crediti · nota». */
export function rigaRicarica(r: RicaricaAi): string {
  const giorno = r.created_at.slice(0, 10).split("-").reverse().join("/");
  const parti = [giorno, `${fmtCrediti(r.crediti)} crediti`];
  if (r.nota) parti.push(r.nota);
  return parti.join(" · ");
}
