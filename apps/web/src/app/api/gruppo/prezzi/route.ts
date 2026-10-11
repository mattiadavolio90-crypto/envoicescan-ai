import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY, WORKER_TIMEOUT_MS } from "@/lib/worker-config";

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

// Scheda «Prezzi» di Analisi catena: fetch client-side al cambio di periodo/soglia.
export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const sp = req.nextUrl.searchParams;
  const qs = new URLSearchParams();
  for (const k of ["data_da", "data_a", "soglia"]) {
    const v = sp.get(k);
    if (v) qs.set(k, v);
  }

  try {
    const res = await fetch(`${WORKER_URL}/api/gruppo/prezzi?${qs}`, {
      method: "GET",
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
