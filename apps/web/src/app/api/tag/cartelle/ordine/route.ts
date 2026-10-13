import { NextRequest, NextResponse } from "next/server";
import { getToken, workerUnreachable, unauthorized, workerFetch } from "../../_worker";

export async function PUT(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const body = await req.json();
  try {
    const res = await workerFetch("PUT", "/api/tag/cartelle/ordine", token, { body: JSON.stringify(body) });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
