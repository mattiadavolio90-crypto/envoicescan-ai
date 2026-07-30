import { NextRequest, NextResponse } from "next/server";
import { getToken, unauthorized, workerFetch, workerUnreachable } from "../../../_worker";

export async function PATCH(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  try {
    const res = await workerFetch("PATCH", `/api/workspace/dipendenti/${id}/disattiva`, token, { json: false });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
