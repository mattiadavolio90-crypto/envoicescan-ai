import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../../../_worker";

export const runtime = "nodejs";
type Ctx = { params: Promise<{ id: string; sid: string }> };

export async function DELETE(_req: NextRequest, { params }: Ctx) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id, sid } = await params;
  try {
    const res = await fetch(`${WORKER_URL}/api/admin/clienti/${id}/sedi/${sid}`, {
      method: "DELETE",
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
