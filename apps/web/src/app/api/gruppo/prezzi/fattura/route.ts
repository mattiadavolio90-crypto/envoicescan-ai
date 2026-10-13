import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY, WORKER_TIMEOUT_MS } from "@/lib/worker-config";

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

// Anteprima di una fattura dalla lista acquisti della scheda «Prezzi» di catena:
// la fattura e' di UNA sede del gruppo, che il worker verifica (404 se non e' del gruppo).
export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const sp = req.nextUrl.searchParams;
  const ristoranteId = sp.get("ristorante_id");
  const fileOrigine = sp.get("file_origine");
  if (!ristoranteId || !fileOrigine) {
    return NextResponse.json({ error: "Missing param: ristorante_id, file_origine" }, { status: 400 });
  }
  const qs = new URLSearchParams({ ristorante_id: ristoranteId, file_origine: fileOrigine });

  try {
    const res = await fetch(`${WORKER_URL}/api/gruppo/prezzi/fattura?${qs}`, {
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
