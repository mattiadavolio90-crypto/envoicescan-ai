import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../_worker";

// Il body porta la sede da svuotare (catena); senza, il worker svuota la sede attiva.
export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const body = await req.json().catch(() => ({}));
  try {
    const res = await fetch(`${WORKER_URL}/api/cestino/svuota`, {
      method: "POST",
      headers: workerHeaders(token, true),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
