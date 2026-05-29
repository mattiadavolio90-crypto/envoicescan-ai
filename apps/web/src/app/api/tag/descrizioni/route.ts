import { NextResponse } from "next/server";
import { getToken, workerHeaders, workerUnreachable, unauthorized, WORKER_URL } from "../_worker";

export async function GET() {
  const token = await getToken();
  if (!token) return unauthorized();
  try {
    const res = await fetch(`${WORKER_URL}/api/tag/descrizioni`, {
      headers: workerHeaders(token),
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
