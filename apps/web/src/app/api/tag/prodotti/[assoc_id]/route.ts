import { NextRequest, NextResponse } from "next/server";
import { getToken, workerHeaders, workerUnreachable, unauthorized, WORKER_URL } from "../../_worker";

type Ctx = { params: Promise<{ assoc_id: string }> };

export async function DELETE(_req: NextRequest, ctx: Ctx) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { assoc_id } = await ctx.params;
  try {
    const res = await fetch(`${WORKER_URL}/api/tag/prodotti/${assoc_id}`, {
      method: "DELETE",
      headers: workerHeaders(token),
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
