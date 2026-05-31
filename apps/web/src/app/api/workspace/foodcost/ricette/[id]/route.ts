import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized } from "../../_worker";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  const res = await fetch(`${WORKER_URL}/api/workspace/foodcost/ricette/${id}`, {
    headers: workerHeaders(token),
    cache: "no-store",
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  const body = await req.json();
  const res = await fetch(`${WORKER_URL}/api/workspace/foodcost/ricette/${id}`, {
    method: "PATCH",
    headers: workerHeaders(token, true),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  const res = await fetch(`${WORKER_URL}/api/workspace/foodcost/ricette/${id}`, {
    method: "DELETE",
    headers: workerHeaders(token),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
