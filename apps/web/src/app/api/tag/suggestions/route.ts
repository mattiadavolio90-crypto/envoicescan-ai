import { NextRequest, NextResponse } from "next/server";
import { getToken, workerHeaders, workerUnreachable, unauthorized, WORKER_URL } from "../_worker";

export async function GET(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const refresh = new URL(req.url).searchParams.get("refresh") === "true";
  try {
    const qs = refresh ? "?refresh=true" : "";
    const res = await fetch(`${WORKER_URL}/api/tag/suggestions${qs}`, {
      headers: workerHeaders(token),
      cache: "no-store",
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
