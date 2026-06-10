import { cache } from "react";
import { WORKER_URL, WORKER_TIMEOUT_MS, getToken, workerHeaders } from "./worker-config";

export type Notifica = {
  id: string;
  topic_key: string | null;
  source_type: string | null;
  severity: "info" | "warning" | "error" | "success";
  title: string;
  body: string | null;
  action_page: string | null;
  // Dati strutturati del topic (es. count righe/prezzi). Gia' restituito dal
  // worker; opzionale lato tipo perche' non tutte le callsite lo usano.
  payload?: Record<string, unknown> | null;
  dismissed_at: string | null;
  expires_at: string | null;
  created_at: string | null;
};

export type NotificheResponse = {
  notifiche: Notifica[];
  total: number;
  unread: number;
};

// cache(): nello stesso render il layout (badge header) e la dashboard
// (count widget) chiamano entrambi fetchNotifiche() -> un solo round-trip al
// worker, niente doppia lettura. Default (senza dismissed) condiviso.
export const fetchNotifiche = cache(
  async (includeDismissed = false): Promise<NotificheResponse | null> => {
    const token = await getToken();
    if (!token) return null;

    try {
      const url = `${WORKER_URL}/api/notifiche${includeDismissed ? "?include_dismissed=true" : ""}`;
      const res = await fetch(url, {
        headers: workerHeaders(token),
        cache: "no-store",
        signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
      });
      if (!res.ok) return null;
      return (await res.json()) as NotificheResponse;
    } catch {
      return null;
    }
  },
);

// Somma il `count` (payload o titolo "(N)") delle notifiche attive di un topic.
// Usato dai trigger contestuali per leggere segnali GIA' calcolati dal worker
// (es. uncategorized_rows, price_alert) senza query nuove: fetchNotifiche e'
// gia' cache()-ata, quindi nello stesso render non aggiunge round-trip.
// Restituisce 0 se non disponibile (mai throw): un segnale assente = niente
// trigger, che e' il fallback corretto.
export async function contaTopicAttivo(topicKey: string): Promise<number> {
  const res = await fetchNotifiche();
  if (!res) return 0;
  let totale = 0;
  for (const n of res.notifiche) {
    if (n.topic_key !== topicKey) continue;
    const p = n.payload ?? {};
    const raw =
      (p.count as number | undefined) ??
      (p.uncategorized_rows as number | undefined) ??
      parseCountFromTitle(n.title);
    if (typeof raw === "number" && Number.isFinite(raw) && raw > 0) totale += raw;
  }
  return totale;
}

// Estrae il numero tra parentesi da titoli come "Scadenze superate (300)".
// Allineato a _parse_count_from_title del worker (fallback quando il payload
// non porta il conteggio).
function parseCountFromTitle(title: string): number | undefined {
  const m = /\((\d+)\)/.exec(title);
  return m ? Number(m[1]) : undefined;
}
