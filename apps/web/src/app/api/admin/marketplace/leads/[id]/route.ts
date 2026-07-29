import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { workerFetch } from "@/lib/worker-config";

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const { stato } = body as { stato?: string };
  if (!stato) return NextResponse.json({ error: "stato mancante" }, { status: 400 });

  try {
    const res = await workerFetch("PATCH", `/api/admin/marketplace/leads/${id}`, token, {
      body: JSON.stringify({ stato }),
    });
    if (!res.ok) return NextResponse.json({ error: "Errore worker" }, { status: res.status });
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ error: "Errore di rete" }, { status: 500 });
  }
}
