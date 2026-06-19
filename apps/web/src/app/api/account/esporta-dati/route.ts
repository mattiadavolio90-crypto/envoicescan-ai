import { NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../_worker";

export const runtime = "nodejs";

// GDPR Art. 20 — export dati personali dell'utente. Risponde come file JSON
// scaricabile (Content-Disposition: attachment).
export async function GET() {
  const token = await getToken();
  if (!token) return unauthorized();
  try {
    const res = await fetch(`${WORKER_URL}/api/account/esporta-dati`, {
      method: "GET",
      headers: workerHeaders(token, true),
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({ error: "Errore export" }));
      return NextResponse.json(data, { status: res.status });
    }
    const data = await res.json();
    const oggi = new Date().toISOString().slice(0, 10);
    return new NextResponse(JSON.stringify(data, null, 2), {
      status: 200,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Disposition": `attachment; filename="oneflux-dati-${oggi}.json"`,
      },
    });
  } catch {
    return workerUnreachable();
  }
}
