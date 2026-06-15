import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../../_worker";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  try {
    const body = await req.json().catch(() => ({}));
    const res = await fetch(`${WORKER_URL}/api/admin/qualita-ai/coda/suggerisci-ai`, {
      method: "POST",
      headers: workerHeaders(token, true),
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(120000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
