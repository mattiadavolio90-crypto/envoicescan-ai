import { notFound } from "next/navigation";
import { getCurrentSession } from "@/lib/auth";

/**
 * Guard di permesso pagina lato route (server component).
 *
 * Finora `pagine_abilitate` filtrava SOLO le voci di sidebar: una pagina con
 * flag spento restava raggiungibile digitando l'URL. Questo helper chiude il
 * buco in modo trasversale — stessa semantica della sidebar:
 *   - pagine_abilitate == null  -> nessuna restrizione (admin): passa sempre
 *   - flag presente nella lista  -> passa
 *   - altrimenti                 -> notFound() (404, non rivela la pagina)
 *
 * Le pagine SENZA flag (Home, ecc.) non chiamano questo guard. Sessione
 * assente/scaduta o worker giù sono già gestiti dal layout (app)/layout.tsx,
 * che gira prima: qui assumiamo una sessione valida e, per sicurezza, in caso
 * contrario lasciamo decidere al layout senza bloccare (fail-open sul guard,
 * il layout fa fail-closed sull'auth).
 */
export async function requirePagina(flag: string): Promise<void> {
  const session = await getCurrentSession();
  if (session.status !== "ok") return; // l'auth la gestisce il layout
  const pagine = session.user.pagine_abilitate;
  if (pagine == null) return; // admin / nessuna restrizione
  if (!pagine.includes(flag)) notFound();
}
