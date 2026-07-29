import { NextRequest, NextResponse } from "next/server";
import { getToken, unauthorized, workerFetch, workerUnreachable } from "../../_worker";

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  const body = await req.json();
  try {
    const res = await workerFetch("PATCH", `/api/workspace/foodcost/ingredienti-manuali/${id}`, token, {
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
    const res = await workerFetch("DELETE", `/api/workspace/foodcost/ingredienti-manuali/${id}`, token, {
      json: false,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
