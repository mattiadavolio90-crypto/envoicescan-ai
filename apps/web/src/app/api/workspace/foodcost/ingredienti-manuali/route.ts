import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized } from "../_worker";

export async function GET() {
  const token = await getToken();
  if (!token) return unauthorized();
  const res = await fetch(`${WORKER_URL}/api/workspace/foodcost/ingredienti-manuali`, {
    headers: workerHeaders(token),
    cache: "no-store",
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const body = await req.json();
  const res = await fetch(`${WORKER_URL}/api/workspace/foodcost/ingredienti-manuali`, {
    method: "POST",
    headers: workerHeaders(token, true),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
