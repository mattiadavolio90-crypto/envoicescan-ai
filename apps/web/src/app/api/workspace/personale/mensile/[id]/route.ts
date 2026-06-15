import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized } from "../../../_worker";

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  const body = await req.json();
  const res = await fetch(`${WORKER_URL}/api/workspace/personale/mensile/${id}`, {
    method: "PATCH",
    headers: workerHeaders(token, true),
    body: JSON.stringify(body),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
