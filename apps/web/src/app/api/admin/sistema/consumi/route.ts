import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../_worker";

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { searchParams } = new URL(req.url);
  const mesi = searchParams.get("mesi") || "12";
  try {
    const res = await fetch(`${WORKER_URL}/api/admin/sistema/consumi?mesi=${mesi}`, {
      headers: workerHeaders(token),
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
