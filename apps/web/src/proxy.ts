import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "oneflux_session";

const PROTECTED_PREFIXES = ["/dashboard", "/fatture", "/ricavi", "/margini", "/foodcost", "/impostazioni", "/style-guide"];

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;

  const requiresAuth = PROTECTED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));

  if (!requiresAuth) {
    return NextResponse.next();
  }

  const token = req.cookies.get(SESSION_COOKIE)?.value;

  if (!token) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
