import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  try {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/auth/reset-request`, {
      method: "POST",
      headers: h,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Servizio non raggiungibile" }, { status: 502 });
  }
}
