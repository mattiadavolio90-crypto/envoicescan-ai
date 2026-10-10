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

/** `residuo` null: la ricarica e' registrata ma il residuo non si e' potuto
 *  rileggere (dopo un'aggiunta il worker non risponde «riprova»: un secondo clic
 *  ne registrerebbe un'altra). */
export type RicaricheAi = { ricariche: RicaricaAi[]; residuo: number | null; crediti_boost: number };

/** Una risposta del worker si legge cosi' com'e' solo se ha la forma attesa. */
export function leggiRicariche(data: unknown): RicaricheAi | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Partial<RicaricheAi>;
  const residuoOk = typeof d.residuo === "number" || d.residuo === null;
  if (!Array.isArray(d.ricariche) || !residuoOk || typeof d.crediti_boost !== "number") {
    return null;
  }
  return { ricariche: d.ricariche, residuo: d.residuo ?? null, crediti_boost: d.crediti_boost };
}

/** La riga sopra il bottone: quanto resta da spendere. */
export function testoResiduo(r: RicaricheAi): string {
  if (r.residuo === null) return "Ricarica registrata. Il residuo non si legge ora: riapri la pagina più tardi.";
  if (r.ricariche.length === 0) return "Nessuna ricarica AI attivata.";
  return `Ricarica AI da spendere: ${fmtCrediti(r.residuo)} crediti`;
}

// Il giorno di Roma, non dell'UTC: una ricarica fatta all'1 di notte non va
// scritta col giorno prima.
const GIORNO_ROMA = new Intl.DateTimeFormat("it-IT", {
  timeZone: "Europe/Rome", day: "2-digit", month: "2-digit", year: "numeric",
});

/** Una ricarica nell'elenco: «10/10/2026 · 300 crediti · nota». */
export function rigaRicarica(r: RicaricaAi): string {
  const giorno = GIORNO_ROMA.format(new Date(r.created_at));
  const parti = [giorno, `${fmtCrediti(r.crediti)} crediti`];
  if (r.nota) parti.push(r.nota);
  return parti.join(" · ");
}
