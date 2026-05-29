import { NextRequest, NextResponse } from "next/server";
import { getToken, workerHeaders, workerUnreachable, unauthorized, WORKER_URL } from "../_worker";

type Ctx = { params: Promise<{ tag_id: string }> };

export async function PUT(req: NextRequest, ctx: Ctx) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { tag_id } = await ctx.params;
  const body = await req.json();
  try {
    const res = await fetch(`${WORKER_URL}/api/tag/${tag_id}`, {
      method: "PUT",
      headers: workerHeaders(token, true),
      body: JSON.stringify(body),
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}

export async function DELETE(_req: NextRequest, ctx: Ctx) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { tag_id } = await ctx.params;
  try {
    const res = await fetch(`${WORKER_URL}/api/tag/${tag_id}`, {
      method: "DELETE",
      headers: workerHeaders(token),
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
