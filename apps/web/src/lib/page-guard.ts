import { notFound, redirect } from "next/navigation";
import { getCurrentSession } from "@/lib/auth";
import { risolviTab, tabAttive, type SezioneConTab, type TabDef } from "@/lib/tab-flags";

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

/**
 * Come `requirePagina`, ma risolve anche QUALE tab mostrare.
 *
 * Le tab si spengono dal pannello admin, e nascondere il bottone non basta:
 * `?tab=` e `?layer=` sono deep-linkabili, quindi un link salvato aggirerebbe
 * lo switcher. Qui la richiesta viene riscritta su una tab consentita.
 *
 * Ritorna la tab da rendere e l'elenco delle tab consentite (per lo switcher:
 * il bottone di una tab spenta non deve comparire). L'elenco lo calcola il
 * guard, che ha gia' la sessione: farlo rileggere a ognuna delle 5 pagine
 * sarebbe cinque occasioni di sbagliarlo.
 *
 * Tre esiti:
 *  - tab richiesta valida e accesa  -> la restituisce (nessun redirect);
 *  - tab spenta o param ignoto      -> redirect alla prima tab attiva;
 *  - nessuna tab attiva             -> notFound().
 *
 * Sull'ultimo caso: una sezione senza tab non ha nulla da mostrare e
 * renderizzerebbe header e filtri sopra un corpo vuoto, che sembra un guasto.
 * 404 e' gia' l'esito di una sezione spenta, quindi non rivela configurazione.
 * Il complemento sta in app-sidebar.tsx, che nasconde la voce: senza, resterebbe
 * un link di menu che porta a una pagina inesistente.
 *
 * `redirect()` lancia (NEXT_REDIRECT): va chiamata prima di qualunque fetch, o
 * si pagano richieste che nessuno leggera'.
 */
export async function requirePaginaConTab(
  flag: string,
  sezione: SezioneConTab,
  richiesta: string | null | undefined,
  path: string,
  nomeParam: string = "tab",
  altriParam?: Record<string, string | undefined>,
): Promise<{ tab: string; disponibili: TabDef[] }> {
  await requirePagina(flag);
  const session = await getCurrentSession();
  const pagine = session.status === "ok" ? session.user.pagine_abilitate : null;

  const risolta = risolviTab(pagine, sezione, richiesta);
  if (risolta == null) notFound();
  const disponibili = tabAttive(pagine, sezione);
  if (risolta === richiesta) return { tab: risolta, disponibili };

  // `risolviTab` e' idempotente: la tab su cui si redirige risolve a se stessa,
  // quindi la pagina di arrivo non redirige di nuovo (niente ciclo).
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(altriParam ?? {})) {
    if (v != null && v !== "") params.set(k, v);
  }
  params.set(nomeParam, risolta);
  redirect(`${path}?${params.toString()}`);
}
