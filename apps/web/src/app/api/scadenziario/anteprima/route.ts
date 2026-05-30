import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../_worker";

export async function GET(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { searchParams } = new URL(req.url);
  const fo = searchParams.get("file_origine") ?? "";
  try {
    const res = await fetch(
      `${WORKER_URL}/api/scadenziario/anteprima?file_origine=${encodeURIComponent(fo)}`,
      { headers: workerHeaders(token), cache: "no-store", signal: AbortSignal.timeout(10000) }
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
