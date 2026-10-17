import {
  haCatena,
  haHome,
  primaPaginaAbilitata,
  primaTabMobile,
  vedeTabMobile,
  type UtenteVisibilita,
} from "@/lib/sotto-utente";
import { sezioneHaTabAttive } from "@/lib/tab-flags";

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

// Primo segmento del percorso -> pagina. Lo stesso di `_PAGINA_DI_PERCORSO`
// (services/permessi_rotte.py), che decide quali notifiche vede un sotto-utente.
export const PAGINA_DI_PERCORSO: Readonly<Record<string, string>> = {
  "analisi-fatture": "analisi_fatture",
  margini: "margini",
  "analisi-e-tag": "analisi_e_tag",
  prezzi: "prezzi",
  scadenziario: "scadenziario",
  agenda: "agenda",
  workspace: "workspace",
  catena: "catena",
  dashboard: "home",
};

/**
 * Il link solo se la pagina d'arrivo si apre: stesse guardie della pagina, e una
 * pagina con tutte le tab spente fa 404 (requirePaginaConTab). null = il testo
 * resta, senza link. Le pagine senza guardia (impostazioni, notifiche) passano.
 */
export function hrefSeConsentito(href: string | null | undefined, utente: UtenteVisibilita): string | null {
  if (!href) return null;
  const segmento = href.split(/[?#]/, 1)[0].replace(/^\/+/, "").split("/", 1)[0];
  const pagina = PAGINA_DI_PERCORSO[segmento];
  if (!pagina) return href;
  const s: SessioneGuardia = { status: "ok", user: utente };
  const esito =
    pagina === "home" ? guardiaHome(s) : pagina === "catena" ? guardiaCatena(s) : guardiaPagina(s, pagina);
  if (esito.esito !== "passa") return null;
  return sezioneHaTabAttive(utente.pagine_abilitate, pagina) ? href : null;
}
