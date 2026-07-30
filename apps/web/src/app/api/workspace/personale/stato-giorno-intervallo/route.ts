import { NextRequest, NextResponse } from "next/server";
import { getToken, unauthorized, workerFetch, workerUnreachable } from "../../_worker";

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const body = await req.json();
  try {
    const res = await workerFetch("POST", "/api/workspace/personale/stato-giorno-intervallo", token, {
      body: JSON.stringify(body),
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
