import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

// Fase 4 (23/07): l'anteprima ora e' PERSISTENTE lato worker — parsa l'XML una
// sola volta e salva le righe; le aperture successive leggono dal DB e tornano
// istantanee. Il parsing a caldo (e quindi questo timeout) scatta solo al PRIMO
// accesso di ogni fattura. Storicamente, sotto contesa sull'unica istanza Railway
// un colpo di lentezza superava i 15s fissi e l'abort Vercel scattava PRIMA della
// risposta worker → il frontend mostrava "documento non leggibile" (fuorviante: il
// documento e' sano, era solo lento). Timeout generoso per assorbire quel primo
// parse; dalla seconda apertura in poi la contesa non c'e' piu'.
const ANTEPRIMA_TIMEOUT_MS = 30000;

// La function serverless deve poter vivere piu' del timeout della fetch verso il
// worker (30s), altrimenti Vercel la ucciderebbe prima e il timeout non servirebbe.
export const maxDuration = 35;

// GET: anteprima righe di una fattura ancora in coda 'da_assegnare' (parsing a caldo,
// nessuna scrittura, categoria stimata da dizionario/regole).
export async function GET(req: NextRequest) {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const queueId = req.nextUrl.searchParams.get("queue_id") ?? "";
  try {
    const res = await fetch(
      `${WORKER_URL}/api/riparto/anteprima-coda?queue_id=${encodeURIComponent(queueId)}`,
      { headers: workerHeaders(token), cache: "no-store", signal: AbortSignal.timeout(ANTEPRIMA_TIMEOUT_MS) },
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    // Distinguere il timeout (worker lento/occupato, il documento e' probabilmente
    // sano) da un errore di rete: il frontend mostra un messaggio onesto e diverso
    // da "documento non leggibile", cosi' l'utente sa che puo' riprovare.
    const isTimeout = err instanceof Error && err.name === "TimeoutError";
    return NextResponse.json(
      { error: isTimeout ? "Worker timeout" : "Worker unreachable", motivo: isTimeout ? "timeout" : "rete" },
      { status: isTimeout ? 504 : 502 },
    );
  }
}
