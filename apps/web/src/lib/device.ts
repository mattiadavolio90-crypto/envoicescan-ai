// Rilevamento dispositivo per decidere vista mobile (/m) vs app desktop completa.
// Regola: i TABLET (schermi grandi) usano sempre l'app desktop, indipendentemente
// dalla larghezza/orientamento; i TELEFONI usano SOLO /m (Mattia, 5/10/2026: da
// telefono, iPhone o Android, i clienti hanno solo la versione mobile). Cosi'
// ruotare un tablet o usarlo in Split View non lo butta mai sulla PWA mobile, e un
// telefono non resta mai sulla vista desktop.

const PHONE_MAX_WIDTH = 768;
// Il lato corto dello schermo di un telefono: i piu' grandi stanno sui 440px, il
// tablet piu' piccolo (iPad mini) sui 744.
const LATO_CORTO_TELEFONO = 600;

function isPhoneUserAgent(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  return /iphone|ipod/i.test(ua) || (/android/i.test(ua) && /mobile/i.test(ua));
}

// Il telefono vero, comunque si presenti. Con «Richiedi sito desktop» un iPhone
// manda lo user agent di un Mac (e col touch sembrava un iPad), un Android quello
// di un PC Linux: lo schermo, pero', resta quello di un telefono. Un cliente su
// iPhone e' rimasto cosi' sulla vista desktop, senza la barra in basso (5/10/2026).
export function isPhoneDevice(): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") return false;
  if (isPhoneUserAgent()) return true;
  // Un telefono in «sito desktop» si presenta come Mac o Linux, mai Windows: un
  // 2-in-1 Windows da 10" al 150% ha lo schermo di 853x533 e il touch.
  if (/windows/i.test(navigator.userAgent)) return false;
  const nav = navigator as Navigator & { maxTouchPoints?: number };
  const schermo = window.screen;
  const latoCorto = Math.min(schermo?.width ?? 0, schermo?.height ?? 0);
  return (nav.maxTouchPoints ?? 0) > 0 && latoCorto > 0 && latoCorto < LATO_CORTO_TELEFONO;
}

export function isTabletDevice(): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") return false;
  if (isPhoneDevice()) return false;
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

// True per i telefoni e per le finestre strette di un computer, mai per i tablet.
export function isPhoneViewport(): boolean {
  if (typeof window === "undefined") return false;
  if (isTabletDevice()) return false;
  return window.innerWidth < PHONE_MAX_WIDTH || isPhoneDevice();
}

// Se la decisione per questa pagina e' stata presa davvero, cioe' se va
// memorizzata per non ri-decidere a ogni ridimensionamento.
//
// Esiste per un difetto trovato dalla review del 23/09/2026: `useIsMobile()`
// torna `!!isMobile` e al PRIMO render vale sempre `false` (lo stato parte da
// `undefined`, il valore vero arriva dall'effect). Segnando la decisione come
// presa su quel falso, al secondo render — quello che sa di essere un telefono
// — il rimbalzo trovava `giaDentro` e NON scattava piu': i telefoni veri non
// finivano piu' su /m, cioe' esattamente la regressione che il fix voleva
// evitare. Finche' il rilevamento e' indeterminato non si decide nulla.
export function decisionePresa(isPhone: boolean | undefined | null): boolean {
  return isPhone === true || isPhone === false;
}

// La vista mobile e' quella giusta per questo dispositivo, ORA. Unico punto di
// verita' per il login.
export function serviVistaMobile(): boolean {
  return isPhoneViewport();
}

// Se rimbalzare su /m la pagina `pathname`.
//
// Il telefono vero rimbalza SEMPRE: non c'e' piu' una «Versione desktop» da
// scegliere (la scelta restava memorizzata e da desktop non c'era un tasto per
// tornare indietro). La finestra stretta di un computer rimbalza solo
// all'INGRESSO: misurato il 23/09/2026, chi la affiancava mentre lavorava finiva
// su /m a meta' operazione, senza ritorno.
export function deveRimbalzareSuMobile(opts: {
  isPhone: boolean | undefined;
  telefonoVero: boolean;
  pathname: string;
  giaDentro: boolean;
}): boolean {
  // `undefined` = rilevamento non ancora avvenuto (primo render). NON e'
  // "non e' un telefono": vedi `decisionePresa`.
  if (opts.isPhone !== true) return false;
  if (opts.pathname.startsWith("/admin")) return false;
  // Confronto sul SEGMENTO, non sul prefisso: `startsWith("/m")` matcherebbe
  // anche `/margini`.
  if (opts.pathname === "/m" || opts.pathname.startsWith("/m/")) return false;
  if (opts.telefonoVero) return true;
  return !opts.giaDentro;
}

// L'effetto di MobileRedirect a ogni render: estratto qui perche' nel .tsx
// nessun test lo vedeva. `decisoPer` e' il ref del componente: per lo stesso
// pathname una finestra stretta decide una volta sola; il telefono vero no.
export function rimbalzoAlRender(
  decisoPer: { current: string | null },
  isPhone: boolean | undefined,
  pathname: string,
): boolean {
  // Finche' il rilevamento non e' avvenuto non si decide e non si consuma nulla.
  if (!decisionePresa(isPhone)) return false;
  const giaDentro = decisoPer.current === pathname;
  decisoPer.current = pathname;
  return deveRimbalzareSuMobile({ isPhone, telefonoVero: isPhoneDevice(), pathname, giaDentro });
}
