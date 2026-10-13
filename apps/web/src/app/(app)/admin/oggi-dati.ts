import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";
import { leggiOggi, type DatiOggi } from "@/lib/admin-oggi";

// Lettura lato server della lista di Oggi, per le pagine admin che la usano
// (Oggi, lista clienti, scheda cliente). null = il worker non ha risposto.
export async function datiOggi(token: string): Promise<DatiOggi | null> {
  try {
    const h: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/admin/attenzione`, { headers: h, cache: "no-store" });
    if (!res.ok) {
      console.error(`[admin/attenzione] ${res.status}:`, (await res.text().catch(() => "")).slice(0, 300));
      return null;
    }
    return leggiOggi(await res.json());
  } catch (err) {
    console.error("[admin/attenzione] fetch error:", err);
    return null;
  }
}
