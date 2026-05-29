import { NextRequest, NextResponse } from "next/server";
import { getToken, workerHeaders, workerUnreachable, unauthorized, WORKER_URL } from "./_worker";

export async function GET() {
  const token = await getToken();
  if (!token) return unauthorized();
  try {
    const res = await fetch(`${WORKER_URL}/api/tag`, {
      headers: workerHeaders(token),
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const body = await req.json();
  try {
    const res = await fetch(`${WORKER_URL}/api/tag`, {
      method: "POST",
      headers: workerHeaders(token, true),
      body: JSON.stringify(body),
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
