import { NextRequest, NextResponse } from "next/server";
import { getToken, workerUnreachable, unauthorized, workerFetch } from "../../../_worker";

type Ctx = { params: Promise<{ sid: string }> };

export async function POST(_req: NextRequest, ctx: Ctx) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { sid } = await ctx.params;
  try {
    const res = await workerFetch("POST", `/api/tag/suggestions/${sid}/dismiss`, token, { body: "{}" });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
