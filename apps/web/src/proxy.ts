import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "oneflux_session";

// Rotte pubbliche: non richiedono sessione. Tutto il resto (dashboard,
// analisi-fatture, prezzi, margini, workspace, analisi-e-tag, scadenziario,
// notifiche, impostazioni, admin, style-guide) e' protetto. Prima si usava una
// whitelist di prefissi che era rimasta indietro (/fatture, /ricavi non esistono
// piu') lasciando le rotte nuove scoperte a edge.
const PUBLIC_PATHS = ["/login", "/forgot-password", "/reset-password"];

// Asset SEO/social a route (NON file statici: non hanno estensione nel path, quindi
// il matcher non li esclude e finirebbero rediretti al login dalla regola "rotta
// protetta senza sessione"). Devono restare pubblici: i crawler social/motori non
// hanno cookie di sessione. opengraph-image è generata da Next come route.
const SEO_PATHS = ["/opengraph-image", "/sitemap.xml", "/robots.txt"];

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
  // Il proxy gira a edge ed e' il single-point-of-failure del routing: se lancia
  // un'eccezione imprevista ogni rotta che matcha andrebbe in 500. Avvolgiamo
  // tutto in try/catch e in caso di errore lasciamo proseguire (NextResponse.next):
  // l'auth e' comunque garantita dalla difesa in profondita' in (app)/layout.tsx.
  try {
    const { pathname } = req.nextUrl;
    const hasSession = Boolean(req.cookies.get(SESSION_COOKIE)?.value);

    // Sul dominio app, "/" non mostra mai la landing. Se l'utente ha la sessione
    // -> /dashboard; se non ce l'ha -> direttamente /login (un hop in meno, niente
    // /dashboard intermedio che il layout rimanderebbe comunque al login).
    if (pathname === "/" && isHostApp(req)) {
      const url = req.nextUrl.clone();
      url.pathname = hasSession ? "/dashboard" : "/login";
      return NextResponse.redirect(url);
    }

    // La root "/" e' la landing pubblica (app/page.tsx): la lasciamo passare
    // (sul dominio vetrina; sul dominio app e' gia' stata rediretta sopra).
    const isPublic =
      pathname === "/" ||
      SEO_PATHS.includes(pathname) ||
      PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

    // Rotta protetta senza sessione -> manda al login conservando la destinazione.
    if (!isPublic && !hasSession) {
      const url = req.nextUrl.clone();
      url.pathname = "/login";
      url.searchParams.set("next", pathname);
      return NextResponse.redirect(url);
    }

    return NextResponse.next();
  } catch {
    return NextResponse.next();
  }
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.).*)"],
};
