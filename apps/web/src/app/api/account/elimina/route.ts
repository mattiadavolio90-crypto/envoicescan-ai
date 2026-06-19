import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../_worker";

export const runtime = "nodejs";

// GDPR Art. 17 — l'utente elimina il proprio account. Dopo la cancellazione lato
// worker, rimuoviamo il cookie di sessione (l'utente non esiste più → logout).
export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  try {
    const body = await req.json();
    const res = await fetch(`${WORKER_URL}/api/account/elimina`, {
      method: "POST",
      headers: workerHeaders(token, true),
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
    });
    const data = await res.json();
    const response = NextResponse.json(data, { status: res.status });
    if (res.ok) {
      const store = await cookies();
      store.delete(SESSION_COOKIE);
    }
    return response;
  } catch {
    return workerUnreachable();
  }
}
