import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, WORKER_TIMEOUT_MS, getToken, workerHeaders, unauthorized, workerFetch, workerUnreachable } from "../_worker";

export async function GET(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const data = req.nextUrl.searchParams.get("data") ?? "";
  const url = `${WORKER_URL}/api/workspace/inventario${data ? `?data=${data}` : ""}`;
  const res = await fetch(url, { headers: workerHeaders(token), signal: AbortSignal.timeout(WORKER_TIMEOUT_MS) });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const body = await req.json();
  try {
    const res = await workerFetch("POST", "/api/workspace/inventario", token, {
      body: JSON.stringify(body),
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}

export async function DELETE(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const data = req.nextUrl.searchParams.get("data") ?? "";
  try {
    const res = await workerFetch("DELETE", `/api/workspace/inventario?data=${data}`, token, { json: false });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
