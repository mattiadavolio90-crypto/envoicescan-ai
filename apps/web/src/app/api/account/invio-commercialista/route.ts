import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { workerFetch } from "@/lib/worker-config";

// Invio delle fatture al commercialista, attivato dal titolare dalle Impostazioni.
// Lo stato lo legge la pagina lato server; qui si attiva (o si modifica).
const PERCORSO = "/api/account/invio-commercialista";

async function token() {
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE)?.value;
}

async function risposta(res: Response) {
  const data = await res.json().catch(() => ({ detail: "Risposta non valida dal worker" }));
  return NextResponse.json(data, { status: res.status });
}

export async function POST(req: NextRequest) {
  const t = await token();
  if (!t) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  try {
    return risposta(await workerFetch("POST", PERCORSO, t, { body: await req.text(), timeoutMs: 30000 }));
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}
