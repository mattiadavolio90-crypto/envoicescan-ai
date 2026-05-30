import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../_worker";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Ctx) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  try {
    const res = await fetch(`${WORKER_URL}/api/admin/clienti/${id}`, {
      headers: workerHeaders(token),
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}

export async function PATCH(req: NextRequest, { params }: Ctx) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  try {
    const body = await req.json();
    const res = await fetch(`${WORKER_URL}/api/admin/clienti/${id}`, {
      method: "PATCH",
      headers: workerHeaders(token, true),
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}

export async function DELETE(req: NextRequest, { params }: Ctx) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  const { searchParams } = new URL(req.url);
  const eliminaMemoria = searchParams.get("elimina_memoria") === "true";
  try {
    const res = await fetch(
      `${WORKER_URL}/api/admin/clienti/${id}?elimina_memoria=${eliminaMemoria}`,
      {
        method: "DELETE",
        headers: workerHeaders(token),
        cache: "no-store",
        signal: AbortSignal.timeout(30000),
      }
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
