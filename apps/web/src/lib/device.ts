// Rilevamento dispositivo per decidere vista mobile (/m) vs app desktop completa.
// Regola: i TABLET (schermi grandi) usano sempre l'app desktop, indipendentemente
// dalla larghezza/orientamento; solo i TELEFONI vanno su /m. Cosi' ruotare un
// tablet o usarlo in Split View non lo butta mai sulla PWA mobile.

const PHONE_MAX_WIDTH = 768;

export function isTabletDevice(): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;

  // iPad esplicito (Safari < iPadOS 13).
  if (/ipad/i.test(ua)) return true;

  // iPadOS 13+ si maschera da Mac: e' un Mac "touch" (i Mac veri non hanno touch).
  const nav = navigator as Navigator & { maxTouchPoints?: number };
  if (/macintosh/i.test(ua) && (nav.maxTouchPoints ?? 0) > 1) return true;

  // Android tablet: UA contiene "Android" ma NON "Mobile" (i telefoni hanno "Mobile").
  if (/android/i.test(ua) && !/mobile/i.test(ua)) return true;

  return false;
}

function isPhoneUserAgent(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  return /iphone|ipod/i.test(ua) || (/android/i.test(ua) && /mobile/i.test(ua));
}

// True solo per i TELEFONI: schermo stretto e/o UA telefono, ma mai per i tablet.
export function isPhoneViewport(): boolean {
  if (typeof window === "undefined") return false;
  if (isTabletDevice()) return false;
  return window.innerWidth < PHONE_MAX_WIDTH || isPhoneUserAgent();
}

export const PREF_DESKTOP = "oneflux_forza_desktop";

// Chi ha chiesto esplicitamente la versione desktop non va piu' rimbalzato su
// /m, nemmeno quando la finestra e' stretta. Senza questa memoria il link
// "Versione desktop" non funzionerebbe affatto: si atterra su /dashboard con la
// finestra ancora sotto soglia e MobileRedirect rispedisce subito indietro.
export function preferisceDesktop(): boolean {
  try {
    return localStorage.getItem(PREF_DESKTOP) === "1";
  } catch {
    // Modalita' privata / storage negato: nessuna preferenza, non bloccare.
    return false;
  }
}

export function impostaPreferenzaDesktop(attiva: boolean): void {
  try {
    if (attiva) localStorage.setItem(PREF_DESKTOP, "1");
    else localStorage.removeItem(PREF_DESKTOP);
  } catch {
    /* storage negato: la scelta vale per la sola navigazione corrente */
  }
}

// Se rimbalzare su /m la pagina `pathname`.
//
// Nasce da una misura del 23/09/2026: `isPhoneViewport()` decide SOLO sulla
// larghezza (il touch non entra mai in gioco fuori da iPad/Android), quindi un
// PC fisso senza touch con la finestra affiancata sotto i 768px veniva spostato
// su /m a meta' lavoro — e da /m non esisteva alcun ritorno. Il redirect resta
// per i telefoni veri, ma solo come SCELTA DELLA PORTA D'INGRESSO: chi e' gia'
// dentro una pagina desktop non viene piu' strappato via da un ridimensionamento.
// La vista mobile e' quella giusta per questo utente, ORA: telefono e nessuna
// richiesta esplicita di desktop. Unico punto di verita' per il login, cosi' la
// preferenza non va ricontrollata a ogni chiamante (e dimenticata in uno).
export function serviVistaMobile(): boolean {
  return isPhoneViewport() && !preferisceDesktop();
}

export function deveRimbalzareSuMobile(opts: {
  isPhone: boolean;
  pathname: string;
  giaDentro: boolean;
  preferisceDesktop: boolean;
}): boolean {
  if (!opts.isPhone) return false;
  if (opts.preferisceDesktop) return false;
  if (opts.giaDentro) return false;
  if (opts.pathname.startsWith("/admin")) return false;
  // Confronto sul SEGMENTO, non sul prefisso: `startsWith("/m")` matcherebbe
  // anche `/margini`.
  if (opts.pathname === "/m" || opts.pathname.startsWith("/m/")) return false;
  return true;
}
