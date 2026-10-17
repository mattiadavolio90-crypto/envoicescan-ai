import {
  haCatena,
  haHome,
  primaPaginaAbilitata,
  primaTabMobile,
  vedeTabMobile,
  type UtenteVisibilita,
} from "@/lib/sotto-utente";

/**
 * Cosa decidono le guardie di pagina (page-guard.ts), senza Next: page-guard
 * traduce l'esito in notFound/redirect/throw.
 *
 * Una sessione che non e' `ok` non passa mai. Il layout (app) la controlla solo
 * al caricamento completo: sulla navigazione client i layout non si rigirano, e
 * con la sessione revocata o il worker giu' la pagina si rendeva con le tab
 * spente dall'admin di nuovo visibili (pagine = null = nessuna restrizione).
 */

export type SessioneGuardia =
  | { status: "ok"; user: UtenteVisibilita }
  | { status: "invalid" }
  | { status: "unavailable" };

export type EsitoGuardia =
  | { esito: "passa" }
  | { esito: "404" }
  | { esito: "redirect"; a: string }
  // Worker irraggiungibile: la pagina non si rende (la prende error.tsx).
  | { esito: "non_disponibile" };

const PASSA: EsitoGuardia = { esito: "passa" };

function senzaSessione(s: SessioneGuardia): EsitoGuardia | null {
  if (s.status === "invalid") return { esito: "redirect", a: "/login" };
  if (s.status === "unavailable") return { esito: "non_disponibile" };
  return null;
}

/** requirePagina: pagine_abilitate null = nessuna restrizione (admin). */
export function guardiaPagina(s: SessioneGuardia, flag: string): EsitoGuardia {
  if (s.status !== "ok") return senzaSessione(s)!;
  const pagine = s.user.pagine_abilitate;
  if (pagine == null || pagine.includes(flag)) return PASSA;
  return { esito: "404" };
}

/** requireHome: per il titolare la Home e' sempre sua. */
export function guardiaHome(s: SessioneGuardia): EsitoGuardia {
  if (s.status !== "ok") return senzaSessione(s)!;
  if (!s.user.sotto_utente || haHome(s.user)) return PASSA;
  return { esito: "redirect", a: primaPaginaAbilitata(s.user) ?? "/impostazioni" };
}

export function guardiaCatena(s: SessioneGuardia): EsitoGuardia {
  if (s.status !== "ok") return senzaSessione(s)!;
  if (!s.user.sotto_utente || haCatena(s.user)) return PASSA;
  return {
    esito: "redirect",
    a: haHome(s.user) ? "/dashboard" : (primaPaginaAbilitata(s.user) ?? "/impostazioni"),
  };
}

/** Le tab di /m per i sotto-utenti: stessa regola della bottom-nav. */
export function guardiaTabMobile(s: SessioneGuardia, href: string): EsitoGuardia {
  if (s.status !== "ok") return senzaSessione(s)!;
  if (!s.user.sotto_utente || vedeTabMobile(s.user, href)) return PASSA;
  return { esito: "redirect", a: primaTabMobile(s.user) };
}
