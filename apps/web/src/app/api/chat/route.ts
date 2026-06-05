import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

// Il worker da' all'OpenAI un timeout di 30s e risponde 504 se sfora; qui teniamo
// un margine sopra (35s) per coprire anche un cold-start della connessione a
// Railway. Senza, la chiamata restava appesa a tempo indeterminato e la chat
// mostrava "Sto cercando..." per sempre. Il client gia' gestisce il 504.
const CHAT_TIMEOUT_MS = 35_000;

export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });

  const body = await req.json().catch(() => ({}));

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(`${WORKER_URL}/api/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(CHAT_TIMEOUT_MS),
    });
    if (!res.ok) {
      // Estrae il messaggio leggibile (es. detail del 429 rate limit). Il 422 di
      // Pydantic ha 'detail' come array: in quel caso teniamo un testo generico.
      let messaggio = "Errore worker";
      try {
        const j = await res.json();
        if (typeof j.detail === "string") messaggio = j.detail;
        else if (typeof j.error === "string") messaggio = j.error;
      } catch {
        /* body non JSON */
      }
      return NextResponse.json({ error: messaggio }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (err) {
    // Timeout della connessione al worker -> 504, gestito dal client come "ha
    // impiegato troppo tempo". Gli altri errori restano un 500 di rete.
    if (err instanceof Error && err.name === "TimeoutError") {
      return NextResponse.json(
        { error: "L'assistente ha impiegato troppo tempo. Riprova." },
        { status: 504 },
      );
    }
    return NextResponse.json({ error: "Errore di rete" }, { status: 500 });
  }
}
