import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized } from "../_worker";

export async function GET(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const data = req.nextUrl.searchParams.get("data") ?? "";
  const url = `${WORKER_URL}/api/workspace/inventario${data ? `?data=${data}` : ""}`;
  const res = await fetch(url, { headers: workerHeaders(token) });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const body = await req.json();
  const res = await fetch(`${WORKER_URL}/api/workspace/inventario`, {
    method: "POST",
    headers: workerHeaders(token, true),
    body: JSON.stringify(body),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function DELETE(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const data = req.nextUrl.searchParams.get("data") ?? "";
  const res = await fetch(`${WORKER_URL}/api/workspace/inventario?data=${data}`, {
    method: "DELETE",
    headers: workerHeaders(token),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
