import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../_worker";

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  try {
    const qs = req.nextUrl.searchParams.toString();
    const res = await fetch(`${WORKER_URL}/api/admin/qualita-ai/audit${qs ? `?${qs}` : ""}`, {
      headers: workerHeaders(token),
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
