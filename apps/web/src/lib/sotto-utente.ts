import { sezioneHaTabAttive } from "@/lib/tab-flags";

/**
 * Cosa vede un sotto-utente: Home, Catena e la pagina su cui atterra.
 *
 * Per un titolare Home e Catena non sono pagine configurabili (Home sempre
 * accesa, Catena quando l'account ha 2+ sedi): ogni funzione qui restituisce per
 * lui esattamente cio' che l'app faceva prima. Per un sotto-utente `home` e
 * `catena` arrivano nella lista `pagine_abilitate` solo se accese (il worker
 * accende la Catena solo con tutte le sedi assegnate).
 *
 * Il blocco vero e' sul server: qui si evita solo di mandare qualcuno su una
 * pagina che gli risponderebbe 403.
 */

export type UtenteVisibilita = {
  pagine_abilitate: string[] | null;
  sotto_utente?: boolean;
  num_sedi?: number;
  is_admin?: boolean;
};

// Stesso ordine del menu (app-sidebar.tsx): la prima accesa e' dove si atterra.
export const PAGINE_IN_ORDINE: ReadonlyArray<readonly [string, string]> = [
  ["analisi_fatture", "/analisi-fatture"],
  ["margini", "/margini"],
  ["analisi_e_tag", "/analisi-e-tag"],
  ["prezzi", "/prezzi"],
  ["scadenziario", "/scadenziario"],
  ["agenda", "/agenda"],
  ["workspace", "/workspace"],
];

export function haHome(utente: UtenteVisibilita): boolean {
  if (!utente.sotto_utente) return true;
  return (utente.pagine_abilitate ?? []).includes("home");
}

export function haCatena(utente: UtenteVisibilita): boolean {
  if ((utente.num_sedi ?? 1) < 2) return false;
  if (!utente.sotto_utente) return true;
  return (utente.pagine_abilitate ?? []).includes("catena");
}

/**
 * Dove atterra chi entra, o chi apre una pagina che non ha.
 *
 * `null` = la destinazione di sempre (/dashboard, o /m su telefono): per un
 * titolare non-admin mono-sede, e per un sotto-utente con la Home.
 */
export function primaPaginaAbilitata(utente: UtenteVisibilita, mobile = false): string | null {
  if (utente.is_admin) return "/admin";
  if (haCatena(utente) && !mobile) return "/catena";
  if (haHome(utente)) return null;
  const pagine = utente.pagine_abilitate ?? [];
  for (const [flag, url] of PAGINE_IN_ORDINE) {
    if (pagine.includes(flag) && sezioneHaTabAttive(pagine, flag)) return url;
  }
  return "/impostazioni";
}

// ─── /m: la bottom-nav e le sue pagine ──────────────────────────────────────
// Home e Assistente sono la Home (accesso all'AI); Agenda e Movimenti leggono
// diario, spese e personale, che il worker apre con Agenda oppure Strumenti.
const TAB_MOBILE_HOME = ["/m/briefing", "/m/chat"];
const TAB_MOBILE_AGENDA = ["/m/diario", "/m/turni"];

export function vedeTabMobile(utente: UtenteVisibilita, href: string): boolean {
  if (!utente.sotto_utente) return true;
  if (TAB_MOBILE_HOME.includes(href)) return haHome(utente);
  if (TAB_MOBILE_AGENDA.includes(href)) {
    const pagine = utente.pagine_abilitate ?? [];
    return pagine.includes("agenda") || pagine.includes("workspace");
  }
  return true;
}

export function tabMobileNascoste(utente: UtenteVisibilita): string[] {
  return [...TAB_MOBILE_HOME, ...TAB_MOBILE_AGENDA].filter((h) => !vedeTabMobile(utente, h));
}

/** Dove va un sotto-utente che apre una tab di /m che non ha. */
export function primaTabMobile(utente: UtenteVisibilita): string {
  for (const href of ["/m/briefing", ...TAB_MOBILE_AGENDA]) {
    if (vedeTabMobile(utente, href)) return href;
  }
  return "/m/impostazioni";
}

/**
 * L'identita' della PERSONA nel browser (chiave della conversazione con
 * l'assistente in sessionStorage). Per un sotto-utente `id` e' quello del
 * titolare: senza l'email, sullo stesso dispositivo la conversazione del
 * titolare (cifre e card da confermare) passerebbe al dipendente. Per il
 * titolare resta `id`, cioe' la chiave di sempre.
 */
export function idPersona(utente: { id: string; email?: string; sotto_utente?: boolean }): string {
  return utente.sotto_utente ? `${utente.id}:${utente.email ?? ""}` : utente.id;
}
