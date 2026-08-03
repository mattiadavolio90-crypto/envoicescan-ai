import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, WORKER_TIMEOUT_MS, getToken, workerHeaders, unauthorized, workerFetch, workerUnreachable } from "../_worker";

export async function GET() {
  const token = await getToken();
  if (!token) return unauthorized();
  const res = await fetch(`${WORKER_URL}/api/workspace/foodcost/ricette`, {
    headers: workerHeaders(token),
    cache: "no-store",
    signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const body = await req.json();
  try {
    const res = await workerFetch("POST", "/api/workspace/foodcost/ricette", token, {
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
