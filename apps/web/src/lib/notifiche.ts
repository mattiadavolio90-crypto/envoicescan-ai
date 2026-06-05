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
