import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "oneflux_session";

// Rotte pubbliche: non richiedono sessione. Tutto il resto (dashboard,
// analisi-fatture, prezzi, margini, workspace, analisi-e-tag, scadenziario,
// notifiche, impostazioni, admin, style-guide) e' protetto. Prima si usava una
// whitelist di prefissi che era rimasta indietro (/fatture, /ricavi non esistono
// piu') lasciando le rotte nuove scoperte a edge.
const PUBLIC_PATHS = ["/login", "/forgot-password", "/reset-password"];

// Gira a edge e decide i redirect SOLO sulla presenza del cookie, senza chiamare
// il worker. La validazione vera del token resta in (app)/layout.tsx (difesa in
// profondita'): qui evitiamo il round-trip per i casi ovvi (utente senza cookie
// su rotta protetta, utente loggato su /login), causa principale della lentezza
// a ogni cambio pagina.
export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const hasSession = Boolean(req.cookies.get(SESSION_COOKIE)?.value);

  // La root "/" e' la landing pubblica (app/page.tsx): la lasciamo passare.
  const isPublic =
    pathname === "/" ||
    PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  // Rotta pubblica con sessione attiva -> manda in dashboard.
  if (isPublic && hasSession) {
    return NextResponse.redirect(new URL("/dashboard", req.url));
  }

  // Rotta protetta senza sessione -> manda al login conservando la destinazione.
  if (!isPublic && !hasSession) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.).*)"],
};
