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

// GET: regola di ripartizione memorizzata per un fornitore ("fai sempre così").
// Sola lettura — pre-compila il dialog di riparto; il cliente conferma sempre.
export async function GET(req: NextRequest) {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const fornitore = req.nextUrl.searchParams.get("fornitore") ?? "";
  try {
    const res = await fetch(
      `${WORKER_URL}/api/riparto/regola-fornitore?fornitore=${encodeURIComponent(fornitore)}`,
      { headers: workerHeaders(token), cache: "no-store" },
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}
