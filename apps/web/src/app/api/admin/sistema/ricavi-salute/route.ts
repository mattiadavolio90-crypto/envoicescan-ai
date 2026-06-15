import { NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../_worker";

export const runtime = "nodejs";

export async function GET(req: Request) {
  const token = await getToken();
  if (!token) return unauthorized();
  const url = new URL(req.url);
  const silenzio = url.searchParams.get("silenzio_giorni") ?? "2";
  try {
    const res = await fetch(
      `${WORKER_URL}/api/admin/sistema/ricavi-salute?silenzio_giorni=${encodeURIComponent(silenzio)}`,
      {
        headers: workerHeaders(token),
        cache: "no-store",
      },
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
