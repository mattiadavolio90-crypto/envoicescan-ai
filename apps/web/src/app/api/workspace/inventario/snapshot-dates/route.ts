import { NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized } from "../../_worker";

export async function GET() {
  const token = await getToken();
  if (!token) return unauthorized();
  const res = await fetch(`${WORKER_URL}/api/workspace/inventario/snapshot-dates`, {
    headers: workerHeaders(token),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
