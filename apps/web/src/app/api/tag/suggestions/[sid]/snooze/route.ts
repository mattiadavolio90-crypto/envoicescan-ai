import { NextRequest, NextResponse } from "next/server";
import { getToken, workerHeaders, workerUnreachable, unauthorized, WORKER_URL } from "../../../_worker";

type Ctx = { params: Promise<{ sid: string }> };

export async function POST(req: NextRequest, ctx: Ctx) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { sid } = await ctx.params;
  const body = await req.json().catch(() => ({ days: 30 }));
  try {
    const res = await fetch(`${WORKER_URL}/api/tag/suggestions/${sid}/snooze`, {
      method: "POST",
      headers: workerHeaders(token, true),
      body: JSON.stringify(body),
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
