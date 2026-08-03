import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, WORKER_TIMEOUT_MS, getToken, workerHeaders, unauthorized, workerFetch, workerUnreachable } from "../../_worker";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  const res = await fetch(`${WORKER_URL}/api/workspace/foodcost/ricette/${id}`, {
    headers: workerHeaders(token),
    cache: "no-store",
    signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  const body = await req.json();
  try {
    const res = await workerFetch("PATCH", `/api/workspace/foodcost/ricette/${id}`, token, {
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  try {
    const res = await workerFetch("DELETE", `/api/workspace/foodcost/ricette/${id}`, token, { json: false });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
