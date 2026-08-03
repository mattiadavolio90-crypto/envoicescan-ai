import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, WORKER_TIMEOUT_MS, getToken, workerHeaders, unauthorized, workerFetch, workerUnreachable } from "../_worker";

export async function GET(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const da = req.nextUrl.searchParams.get("da") ?? "";
  const a = req.nextUrl.searchParams.get("a") ?? "";
  const mensile = req.nextUrl.searchParams.get("mensile");
  const params = new URLSearchParams();
  if (da) params.set("da", da);
  if (a) params.set("a", a);
  if (mensile !== null) params.set("mensile", mensile);
  const qs = params.toString();
  const res = await fetch(`${WORKER_URL}/api/workspace/personale${qs ? `?${qs}` : ""}`, {
    headers: workerHeaders(token),
    signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const body = await req.json();
  try {
    const res = await workerFetch("POST", "/api/workspace/personale", token, {
      body: JSON.stringify(body),
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
