import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

function workerHeaders(token: string, json = false): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (json) h["Content-Type"] = "application/json";
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { searchParams } = new URL(req.url);
  const anno = searchParams.get("anno");
  const mese = searchParams.get("mese");
  if (!anno || !mese) return NextResponse.json({ error: "Missing params" }, { status: 400 });

  try {
    const qs = new URLSearchParams({ anno, mese });
    const res = await fetch(`${WORKER_URL}/api/margini/fatturato-centri-giorni?${qs}`, {
      headers: workerHeaders(token),
      cache: "no-store",
    });
    if (res.status === 404) return NextResponse.json([], { status: 200 });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json([], { status: 200 });
  }
}
