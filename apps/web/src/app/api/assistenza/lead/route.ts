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
  const { servizio_key, servizio_label, messaggio } = body as {
    servizio_key?: string;
    servizio_label?: string;
    messaggio?: string;
  };
  if (!servizio_key || !servizio_label) {
    return NextResponse.json({ error: "Servizio mancante" }, { status: 400 });
  }

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(`${WORKER_URL}/api/assistenza/lead`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        servizio_key,
        servizio_label,
        messaggio: messaggio ?? "",
      }),
    });
    if (!res.ok) return NextResponse.json({ error: "Errore worker" }, { status: res.status });
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ error: "Errore di rete" }, { status: 500 });
  }
}
