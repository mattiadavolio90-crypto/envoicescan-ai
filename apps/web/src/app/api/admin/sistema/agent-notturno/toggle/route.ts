import { NextRequest, NextResponse } from "next/server";
import { getToken, unauthorized, workerUnreachable, workerFetch } from "../../../_worker";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  try {
    const body = await req.json().catch(() => ({}));
    const res = await workerFetch("POST", "/api/admin/sistema/agent-notturno/toggle", token, {
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
