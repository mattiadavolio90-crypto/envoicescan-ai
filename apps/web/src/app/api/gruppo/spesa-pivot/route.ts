import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY, WORKER_TIMEOUT_MS } from "@/lib/worker-config";

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

// Finestra "Spesa per PV": fetch client-side (si apre da un click sul KPI).
export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const sp = req.nextUrl.searchParams;
  const qs = new URLSearchParams();
  qs.set("dimensione", sp.get("dimensione") === "fornitore" ? "fornitore" : "categoria");
  if (sp.get("data_da")) qs.set("data_da", sp.get("data_da")!);
  if (sp.get("data_a")) qs.set("data_a", sp.get("data_a")!);

  try {
    const res = await fetch(`${WORKER_URL}/api/gruppo/spesa-pivot?${qs}`, {
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
