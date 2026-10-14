import { NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../_worker";

export const runtime = "nodejs";

export async function GET() {
  const token = await getToken();
  if (!token) return unauthorized();
  try {
    const res = await fetch(`${WORKER_URL}/api/admin/categorie/da-sistemare`, {
      headers: workerHeaders(token),
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
    });
    const data = await res.json().catch(() => ({ detail: "Risposta non valida dal worker" }));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
