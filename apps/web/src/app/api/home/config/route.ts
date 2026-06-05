import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

async function authHeaders() {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;
  return headers;
}

export async function GET() {
  const headers = await authHeaders();
  if (!headers) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });
  try {
    const res = await fetch(`${WORKER_URL}/api/home/config`, { method: "GET", headers, cache: "no-store" });
    if (!res.ok) return NextResponse.json({ error: "Errore worker" }, { status: res.status });
    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json({ error: "Errore di rete" }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  const headers = await authHeaders();
  if (!headers) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  try {
    const res = await fetch(`${WORKER_URL}/api/home/config`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!res.ok) return NextResponse.json({ error: "Errore worker" }, { status: res.status });
    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json({ error: "Errore di rete" }, { status: 500 });
  }
}
