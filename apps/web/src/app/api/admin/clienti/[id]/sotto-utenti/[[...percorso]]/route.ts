import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../../../_worker";
import { percorsoProxy } from "@/lib/sotto-utenti-admin";

export const runtime = "nodejs";
type Ctx = { params: Promise<{ id: string; percorso?: string[] }> };

// Proxy della scheda «Sotto-utenti». Inoltra solo i percorsi che percorsoProxy
// riconosce: il resto e' un 400, mai una chiamata al worker.
async function inoltra(req: NextRequest, { params }: Ctx, metodo: "GET" | "POST" | "PATCH" | "DELETE") {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id, percorso } = await params;
  const path = percorsoProxy(id, percorso ?? []);
  if (!path) return NextResponse.json({ detail: "Percorso non valido" }, { status: 400 });
  const conCorpo = metodo === "POST" || metodo === "PATCH";
  try {
    const res = await fetch(`${WORKER_URL}${path}`, {
      method: metodo,
      headers: workerHeaders(token, conCorpo),
      body: conCorpo ? await req.text() : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    const data = await res.json().catch(() => ({ detail: "Risposta non valida dal worker" }));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}

export async function GET(req: NextRequest, ctx: Ctx) {
  return inoltra(req, ctx, "GET");
}

export async function POST(req: NextRequest, ctx: Ctx) {
  return inoltra(req, ctx, "POST");
}

export async function PATCH(req: NextRequest, ctx: Ctx) {
  return inoltra(req, ctx, "PATCH");
}

export async function DELETE(req: NextRequest, ctx: Ctx) {
  return inoltra(req, ctx, "DELETE");
}
