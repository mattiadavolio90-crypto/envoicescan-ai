import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY, WORKER_TIMEOUT_MS } from "@/lib/worker-config";

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });

  const url = new URL(req.url);
  const qs = url.searchParams.toString();

  try {
    const res = await fetch(`${WORKER_URL}/api/fatture/righe-articolo${qs ? `?${qs}` : ""}`, {
      headers: workerHeaders(token),
      cache: "no-store",
      signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Errore di rete" }, { status: 500 });
  }
}
