import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });

  const body = await req.json().catch(() => ({}));

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(`${WORKER_URL}/api/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      // Estrae il messaggio leggibile (es. detail del 429 rate limit).
      let messaggio = "Errore worker";
      try {
        const j = await res.json();
        messaggio = j.detail || j.error || messaggio;
      } catch {
        /* body non JSON */
      }
      return NextResponse.json({ error: messaggio }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json({ error: "Errore di rete" }, { status: 500 });
  }
}
