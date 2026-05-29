import { NextRequest, NextResponse } from "next/server";
import { getToken, workerHeaders, workerUnreachable, unauthorized, WORKER_URL } from "../../_worker";

type Ctx = { params: Promise<{ tag_id: string }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { tag_id } = await ctx.params;
  const { searchParams } = new URL(req.url);
  const data_da = searchParams.get("data_da");
  const data_a = searchParams.get("data_a");
  if (!data_da || !data_a)
    return NextResponse.json({ error: "Missing params: data_da, data_a" }, { status: 400 });
  try {
    const qs = new URLSearchParams({ data_da, data_a });
    const res = await fetch(`${WORKER_URL}/api/tag/${tag_id}/analisi?${qs}`, {
      headers: workerHeaders(token),
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
