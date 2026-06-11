import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

// POST: sposta una fattura GIÀ acquisita verso un'altra sede dello stesso cliente.
// Correzione a posteriori del routing multi-sede (azione dal dettaglio fattura).
export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  try {
    const res = await fetch(`${WORKER_URL}/api/fatture/sposta-sede`, {
      method: "POST",
      headers: workerHeaders(token),
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}
