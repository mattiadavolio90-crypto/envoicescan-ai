import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../../_worker";

export const runtime = "nodejs";
type Ctx = { params: Promise<{ id: string }> };

// Boost AI (fase J): ricariche dei crediti dell'assistente del cliente.
async function inoltra(req: NextRequest, { params }: Ctx, metodo: "GET" | "POST") {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  const conCorpo = metodo === "POST";
  try {
    const res = await fetch(`${WORKER_URL}/api/admin/clienti/${encodeURIComponent(id)}/ricariche-ai`, {
      method: metodo,
      headers: workerHeaders(token, conCorpo),
      body: conCorpo ? await req.text() : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
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
