import { NextRequest, NextResponse } from "next/server";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";
import { parametriDisiscrizione } from "@/lib/disiscrizione";

// Disiscrizione dall'email settimanale, SENZA login: la prova e' il token
// firmato dal worker. Due chiamanti:
// - la pagina /disiscrizione, quando la persona preme il bottone;
// - il client di posta, dal List-Unsubscribe "con un clic" (RFC 8058): manda
//   un POST all'indirizzo dell'intestazione, con u e t nella query e il corpo
//   "List-Unsubscribe=One-Click".
// Niente GET che disiscrive: i filtri antispam aprono i link delle email, e un
// GET che agisce disiscriverebbe chiunque riceva l'email.
export async function POST(req: NextRequest) {
  let corpo: unknown = null;
  if ((req.headers.get("content-type") ?? "").includes("application/json")) {
    corpo = await req.json().catch(() => null);
  }
  const p = parametriDisiscrizione(req.nextUrl.searchParams, corpo);
  if (!p) return NextResponse.json({ error: "Link non valido" }, { status: 400 });
  try {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/email/disiscrizione`, {
      method: "POST",
      headers: h,
      body: JSON.stringify(p),
      signal: AbortSignal.timeout(15000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Servizio non raggiungibile" }, { status: 502 });
  }
}
