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
  let res: Response;
  try {
    res = await workerFetch("PATCH", "/api/riparto/riga-categoria", token, {
      body: JSON.stringify(body),
    });
  } catch (err) {
    // Solo un fallimento di TRASPORTO arriva qui: il worker non ha risposto affatto.
    // Distinguere il timeout dalla rete evita di dire "irraggiungibile" a un worker
    // che sta solo rispondendo lentamente.
    const isTimeout = err instanceof Error && err.name === "TimeoutError";
    console.error("[riparto/riga-categoria] worker non ha risposto:", err);
    return NextResponse.json(
      { error: isTimeout ? "Worker timeout" : "Worker unreachable", motivo: isTimeout ? "timeout" : "rete" },
      { status: isTimeout ? 504 : 502 },
    );
  }

  // Il worker non ha un exception handler globale: un'eccezione non gestita torna
  // come corpo NON-JSON (traceback, o pagina d'errore del proxy). Facendo res.json()
  // diretto quel SyntaxError finiva nel catch di rete e l'utente leggeva "Worker
  // unreachable" per un errore applicativo — messaggio falso e non diagnosticabile,
  // perche' l'errore vero non veniva ne' mostrato ne' loggato.
  const raw = await res.text();
  try {
    return NextResponse.json(JSON.parse(raw), { status: res.status });
  } catch {
    console.error(
      "[riparto/riga-categoria] risposta worker non-JSON",
      res.status,
      raw.slice(0, 500),
    );
    return NextResponse.json(
      { error: `Worker: risposta non valida (HTTP ${res.status})`, motivo: "risposta-non-json" },
      { status: res.status >= 400 ? res.status : 502 },
    );
  }
}
