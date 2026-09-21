import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY, WORKER_TIMEOUT_MS } from "@/lib/worker-config";

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

// L'elenco delle descrizioni visibili a schermo puo' essere lungo (centinaia di
// articoli), quindi la richiesta al worker va in POST con le descrizioni nel
// body: una querystring con quell'elenco supererebbe i limiti di lunghezza URL
// di proxy e server. I filtri di periodo restano in querystring.
export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Richiesta non valida" }, { status: 400 });
  }

  const url = new URL(req.url);
  const qs = url.searchParams.toString();

  try {
    const res = await fetch(`${WORKER_URL}/api/fatture/righe-export${qs ? `?${qs}` : ""}`, {
      method: "POST",
      headers: { ...workerHeaders(token), "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Errore di rete" }, { status: 500 });
  }
}
