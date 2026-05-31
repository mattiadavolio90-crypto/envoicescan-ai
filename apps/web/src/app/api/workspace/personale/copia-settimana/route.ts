import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized } from "../../_worker";

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const body = await req.json();
  const res = await fetch(`${WORKER_URL}/api/workspace/personale/copia-settimana`, {
    method: "POST",
    headers: workerHeaders(token, true),
    body: JSON.stringify(body),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
