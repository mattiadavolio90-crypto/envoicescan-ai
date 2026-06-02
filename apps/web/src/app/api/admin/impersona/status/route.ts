import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { getCurrentUser } from "@/lib/auth";
import { IMPERSONATE_COOKIE } from "../../_worker";

export const runtime = "nodejs";

/**
 * Stato impersonazione per il banner admin. Il cookie oneflux_impersonate è
 * HttpOnly e non contiene PII: l'email impersonata è derivata qui dalla
 * sessione corrente (token dell'utente impersonato), lato server.
 */
export async function GET() {
  const store = await cookies();
  const active = store.get(IMPERSONATE_COOKIE)?.value === "1";
  if (!active) {
    return NextResponse.json({ active: false, email: null });
  }
  const user = await getCurrentUser();
  return NextResponse.json({ active: true, email: user?.email ?? null });
}
