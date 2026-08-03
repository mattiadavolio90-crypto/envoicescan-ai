import { NextResponse } from "next/server";
import { WORKER_URL, WORKER_TIMEOUT_MS, getToken, workerHeaders, unauthorized } from "../_worker";

export async function GET() {
  const token = await getToken();
  if (!token) return unauthorized();
  const res = await fetch(`${WORKER_URL}/api/workspace/foodcost/ingredienti`, {
    headers: workerHeaders(token),
    cache: "no-store",
    signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
