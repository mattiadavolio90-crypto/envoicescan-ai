import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized } from "../../_worker";

export async function GET(_req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const res = await fetch(`${WORKER_URL}/api/workspace/inventario/articoli`, {
    headers: workerHeaders(token),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
