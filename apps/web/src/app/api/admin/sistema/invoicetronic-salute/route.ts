import { NextResponse } from "next/server";
import { WORKER_URL, WORKER_TIMEOUT_MS, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../_worker";

export const runtime = "nodejs";

export async function GET(req: Request) {
  const token = await getToken();
  if (!token) return unauthorized();
  const url = new URL(req.url);
  const giorni = url.searchParams.get("giorni") ?? "30";
  try {
    const res = await fetch(
      `${WORKER_URL}/api/admin/sistema/invoicetronic-salute?giorni=${encodeURIComponent(giorni)}`,
      {
        headers: workerHeaders(token),
        cache: "no-store",
        signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
      },
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
