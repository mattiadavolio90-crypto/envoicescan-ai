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
