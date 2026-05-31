import { NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized } from "../_worker";

export async function GET() {
  const token = await getToken();
  if (!token) return unauthorized();
  const res = await fetch(`${WORKER_URL}/api/workspace/foodcost/ingredienti`, {
    headers: workerHeaders(token),
    cache: "no-store",
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
