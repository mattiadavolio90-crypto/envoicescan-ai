import { NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../_worker";
import { WORKER_TIMEOUT_MS } from "@/lib/worker-config";

export const runtime = "nodejs";

export async function GET() {
  const token = await getToken();
  if (!token) return unauthorized();
  try {
    const res = await fetch(`${WORKER_URL}/api/account/ricavi-noiva`, {
      method: "GET",
      headers: workerHeaders(token),
      cache: "no-store",
      signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
