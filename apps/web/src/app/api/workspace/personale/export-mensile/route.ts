import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, WORKER_TIMEOUT_MS, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../_worker";

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();
  const mese = req.nextUrl.searchParams.get("mese") ?? "";
  if (!mese) return NextResponse.json({ error: "Parametro mese mancante" }, { status: 400 });
  try {
    const res = await fetch(
      `${WORKER_URL}/api/workspace/personale/export-mensile?mese=${encodeURIComponent(mese)}`,
      { headers: workerHeaders(token), cache: "no-store", signal: AbortSignal.timeout(WORKER_TIMEOUT_MS) },
    );
    if (!res.ok) {
      const data = await res.json().catch(() => ({ error: "Errore export" }));
      return NextResponse.json(data, { status: res.status });
    }
    const bytes = await res.arrayBuffer();
    const disposition = res.headers.get("content-disposition") ?? `attachment; filename="personale_mensile_${mese.replace("-", "")}.xlsx"`;
    return new NextResponse(bytes, {
      status: 200,
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": disposition,
      },
    });
  } catch {
    return workerUnreachable();
  }
}
