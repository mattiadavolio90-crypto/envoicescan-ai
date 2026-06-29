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
// profondita'): qui evitiamo il round-trip per il caso ovvio (utente senza
// cookie su rotta protetta).
//
// NB: NON facciamo il redirect inverso "rotta pubblica con cookie -> dashboard".
// Il proxy vede solo la PRESENZA del cookie, non la sua validita': un cookie
// scaduto/invalido faceva /login -> /dashboard (proxy) -> /login (layout, token
// ko) -> loop ERR_TOO_MANY_REDIRECTS. Chi e' davvero loggato e apre /login viene
// rediretto dal form lato client; il proxy non deve indovinare la sessione.
// Split per hostname: la landing pubblica (app/page.tsx su "/") deve vivere SOLO
// sul dominio vetrina (oneflux.it / www.oneflux.it e le preview *.vercel.app).
// Sul dominio dell'APP (app.oneflux.it) la "/" NON deve mostrare la landing ma
// portare dentro l'app: cosi' i clienti che aprono app.oneflux.it trovano il
// login/dashboard come sempre, non la pagina di marketing.
function isHostApp(req: NextRequest): boolean {
  const host = (req.headers.get("host") ?? "").toLowerCase();
  return host.startsWith("app.");
}

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const hasSession = Boolean(req.cookies.get(SESSION_COOKIE)?.value);

  // Sul dominio app, "/" -> /dashboard (poi il layout manda a /login se serve).
  // La landing resta invisibile su app.oneflux.it.
  if (pathname === "/" && isHostApp(req)) {
    const url = req.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  // La root "/" e' la landing pubblica (app/page.tsx): la lasciamo passare
  // (sul dominio vetrina; sul dominio app e' gia' stata rediretta sopra).
  const isPublic =
    pathname === "/" ||
    PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

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
