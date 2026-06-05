import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, workerHeaders, IMPERSONATE_COOKIE, IMPERSONATE_BACKUP_COOKIE } from "../../_worker";

export const runtime = "nodejs";

export async function POST() {
  const store = await cookies();
  const backupToken = store.get(IMPERSONATE_BACKUP_COOKIE)?.value;
  // Il cookie di sessione corrente contiene ancora il token del cliente impersonato:
  // lo usiamo per chiedere al worker di invalidarlo nel DB (altrimenti resterebbe
  // valido fino alla scadenza e l'admin ne conserverebbe una copia funzionante).
  const targetToken = store.get(SESSION_COOKIE)?.value;

  if (backupToken && targetToken && targetToken !== backupToken) {
    try {
      await fetch(`${WORKER_URL}/api/admin/impersona/exit`, {
        method: "POST",
        headers: workerHeaders(backupToken, true),
        body: JSON.stringify({ target_token: targetToken }),
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
    } catch {
      // Best-effort: anche se l'invalidazione fallisce, ripristiniamo comunque la
      // sessione admin lato cookie. Il token target scadra' per inattivita'.
    }
  }

  if (backupToken) {
    const cookieOpts = { httpOnly: true, path: "/", sameSite: "lax" as const, secure: process.env.NODE_ENV === "production", maxAge: 60 * 60 * 24 * 30 };
    store.set(SESSION_COOKIE, backupToken, cookieOpts);
  }

  store.delete(IMPERSONATE_BACKUP_COOKIE);
  store.delete(IMPERSONATE_COOKIE);

  return NextResponse.json({ ok: true });
}
