import { NextRequest, NextResponse } from "next/server";
import {
  getToken,
  unauthorized,
  workerHeaders,
  WORKER_URL,
  WORKER_TIMEOUT_MS,
} from "@/lib/worker-config";

// Finestra "Spreco per categoria" (confronto PV): fetch client-side (click sul
// pulsante Categorie). Inoltra ?mese= per restare allineata al selettore periodo.
export async function GET(req: NextRequest) {
  const token = await getToken();
  if (!token) return unauthorized();

  const mese = req.nextUrl.searchParams.get("mese");
  const qs = mese ? `?mese=${encodeURIComponent(mese)}` : "";

  let res: Response;
  try {
    res = await fetch(`${WORKER_URL}/api/gruppo/spreco-categorie${qs}`, {
      method: "GET",
      headers: workerHeaders(token),
      cache: "no-store",
      signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
    });
  } catch (err) {
    // Solo un fallimento di TRASPORTO arriva qui. Il catch nudo di prima diceva
    // sempre "Worker unreachable" con 502: un worker lento (timeout) e uno
    // irraggiungibile davano lo stesso messaggio, e nei log non restava nulla per
    // distinguerli — vedi 16323a4 per lo stesso fix su riparto/riga-categoria.
    const isTimeout = err instanceof Error && err.name === "TimeoutError";
    console.error("[gruppo/spreco-categorie] worker non ha risposto:", err);
    return NextResponse.json(
      { error: isTimeout ? "Worker timeout" : "Worker unreachable", motivo: isTimeout ? "timeout" : "rete" },
      { status: isTimeout ? 504 : 502 },
    );
  }

  // Una risposta non-JSON (traceback, pagina d'errore del proxy Railway) faceva
  // esplodere res.json() dentro il try: un errore applicativo del worker usciva
  // travestito da "Worker unreachable", senza il suo status reale nei log.
  const raw = await res.text();
  try {
    return NextResponse.json(JSON.parse(raw), { status: res.status });
  } catch {
    console.error(
      "[gruppo/spreco-categorie] risposta worker non-JSON",
      res.status,
      raw.slice(0, 500),
    );
    return NextResponse.json(
      { error: `Worker: risposta non valida (HTTP ${res.status})`, motivo: "risposta-non-json" },
      { status: res.status >= 400 ? res.status : 502 },
    );
  }
}
