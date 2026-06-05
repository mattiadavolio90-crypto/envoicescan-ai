import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, WORKER_URL, WORKER_SECRET_KEY, WORKER_TIMEOUT_MS } from "./auth";

// Helper centralizzati per le chiamate al worker. URL/secret/timeout vivono in
// auth.ts (modulo base) e sono ri-esportati qui per comodita' degli importatori.
// Prima questo blocco era duplicato in ~56 file (URL hardcoded + getToken/
// workerHeaders riscritti in ogni _worker.ts e in piu' route).
export { WORKER_URL, WORKER_SECRET_KEY, WORKER_TIMEOUT_MS };

/** Legge il session token dal cookie HTTP-only. */
export async function getToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}

/** Header per il worker: Bearer + X-Worker-Key (+ Content-Type se json). */
export function workerHeaders(token: string, json = false): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (json) h["Content-Type"] = "application/json";
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

// ─── Risposte standard per i route handler ────────────────────────────────────
export function unauthorized() {
  return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
}

export function forbidden() {
  return NextResponse.json({ error: "Accesso riservato agli amministratori" }, { status: 403 });
}

export function workerUnreachable() {
  return NextResponse.json({ error: "Worker non raggiungibile" }, { status: 502 });
}

export function workerError(status: number, msg: string) {
  return NextResponse.json({ error: msg }, { status });
}

/**
 * GET autenticato verso il worker per i Server Component.
 * Centralizza lettura cookie, header (incluso X-Worker-Key), check res.ok,
 * timeout e gestione errori. Ritorna null su mancato auth / errore / timeout.
 */
export async function workerGet<T>(path: string, context: string): Promise<T | null> {
  const token = await getToken();
  if (!token) return null;

  try {
    const res = await fetch(`${WORKER_URL}${path}`, {
      method: "GET",
      headers: workerHeaders(token, true),
      cache: "no-store",
      signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
    });
    if (!res.ok) {
      console.error(`[${context}] worker error:`, res.status);
      return null;
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof Error && err.name === "TimeoutError") {
      console.warn(`[${context}] worker timeout (${WORKER_TIMEOUT_MS}ms) — cold start?`);
    } else {
      console.error(`[${context}] fetch error:`, err);
    }
    return null;
  }
}
