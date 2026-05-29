import { NextRequest, NextResponse } from "next/server";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  try {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/auth/reset-confirm`, {
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
