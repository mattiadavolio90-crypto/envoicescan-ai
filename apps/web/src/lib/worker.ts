import { cookies } from "next/headers";
import { SESSION_COOKIE } from "./auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

// GET autenticato verso il worker per i Server Component. Centralizza lettura
// cookie, header (incluso X-Worker-Key), check res.ok e gestione errori: prima
// ogni funzione in home.ts/dashboard.ts duplicava lo stesso blocco.
export async function workerGet<T>(path: string, context: string): Promise<T | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(`${WORKER_URL}${path}`, {
      method: "GET",
      headers,
      cache: "no-store",
    });
    if (!res.ok) {
      console.error(`[${context}] worker error:`, res.status, await res.text().catch(() => ""));
      return null;
    }
    return (await res.json()) as T;
  } catch (err) {
    console.error(`[${context}] fetch error:`, err);
    return null;
  }
}
