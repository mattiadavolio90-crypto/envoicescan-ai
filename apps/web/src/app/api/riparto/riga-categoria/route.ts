import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { workerFetch } from "@/lib/worker-config";

// PATCH: corregge la categoria di una riga appartenente a un costo di gruppo.
// Le righe di una fattura di struttura vivono sulla sede tecnica, non sul punto
// vendita: categoria-batch non le troverebbe (filtra per ristorante_id del PV).
export async function PATCH(req: NextRequest) {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const body = await req.json();
  try {
    const res = await workerFetch("PATCH", "/api/riparto/riga-categoria", token, {
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}
