import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../../../_worker";
import { percorsoProxy } from "@/lib/invio-commercialista";

export const runtime = "nodejs";
type Ctx = { params: Promise<{ id: string; percorso?: string[] }> };

// Proxy della scheda «Invio al commercialista». Inoltra solo i percorsi che
// percorsoProxy riconosce: il resto e' un 400, mai una chiamata al worker.
async function inoltra(req: NextRequest, { params }: Ctx, metodo: "GET" | "POST" | "PATCH") {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id, percorso } = await params;
  const path = percorsoProxy(id, percorso ?? [], req.nextUrl.searchParams);
  if (!path) return NextResponse.json({ detail: "Percorso non valido" }, { status: 400 });
  try {
    const res = await fetch(`${WORKER_URL}${path}`, {
      method: metodo,
      headers: workerHeaders(token, metodo !== "GET"),
      body: metodo === "GET" ? undefined : await req.text(),
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
