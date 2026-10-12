import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY, WORKER_TIMEOUT_MS } from "@/lib/worker-config";

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

// Stella della scheda «Prezzi» di catena: e' il preferito del PV della riga.
// La sede la verifica il worker (404 se non e' del gruppo).
export async function POST(req: NextRequest) {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  try {
    const body = await req.text();
    const res = await fetch(`${WORKER_URL}/api/gruppo/prezzi/preferiti`, {
      method: "POST",
      headers: { ...workerHeaders(token), "Content-Type": "application/json" },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}

export async function DELETE(req: NextRequest) {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const sp = req.nextUrl.searchParams;
  const ristoranteId = sp.get("ristorante_id");
  const prodotto = sp.get("prodotto");
  if (!ristoranteId || !prodotto) {
    return NextResponse.json({ error: "Missing param: ristorante_id, prodotto" }, { status: 400 });
  }
  const qs = new URLSearchParams({ ristorante_id: ristoranteId, prodotto, fornitore: sp.get("fornitore") ?? "" });
  try {
    const res = await fetch(`${WORKER_URL}/api/gruppo/prezzi/preferiti?${qs}`, {
      method: "DELETE",
      headers: workerHeaders(token),
      cache: "no-store",
      signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}
