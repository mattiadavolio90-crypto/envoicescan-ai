import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable } from "../../../_worker";

export const runtime = "nodejs";
type Ctx = { params: Promise<{ id: string }> };

// Invio di prova dell'email settimanale (fase 7c): il worker compone l'email di
// questo cliente e la spedisce all'admin che chiama, con [PROVA] nell'oggetto.
// Il cliente non riceve niente.
export async function POST(_req: NextRequest, { params }: Ctx) {
  const token = await getToken();
  if (!token) return unauthorized();
  const { id } = await params;
  try {
    const res = await fetch(
      `${WORKER_URL}/api/admin/email-settimanale/prova?user_id=${encodeURIComponent(id)}`,
      {
        method: "POST",
        headers: workerHeaders(token),
        cache: "no-store",
        signal: AbortSignal.timeout(30000),
      },
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return workerUnreachable();
  }
}
