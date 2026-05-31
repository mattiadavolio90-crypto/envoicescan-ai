import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized } from "../_worker";

export async function GET(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const da = req.nextUrl.searchParams.get("da") ?? "";
  const a = req.nextUrl.searchParams.get("a") ?? "";
  const params = new URLSearchParams();
  if (da) params.set("da", da);
  if (a) params.set("a", a);
  const qs = params.toString();
  const res = await fetch(`${WORKER_URL}/api/workspace/personale${qs ? `?${qs}` : ""}`, {
    headers: workerHeaders(token),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const body = await req.json();
  const res = await fetch(`${WORKER_URL}/api/workspace/personale`, {
    method: "POST",
    headers: workerHeaders(token, true),
    body: JSON.stringify(body),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
