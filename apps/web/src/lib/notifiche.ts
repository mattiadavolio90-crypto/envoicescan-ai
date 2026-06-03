import { cache } from "react";
import { cookies } from "next/headers";
import { SESSION_COOKIE } from "./auth";
import { WORKER_TIMEOUT_MS } from "./worker";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

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

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

// cache(): nello stesso render il layout (badge header) e la dashboard
// (count widget) chiamano entrambi fetchNotifiche() -> un solo round-trip al
// worker, niente doppia lettura. Default (senza dismissed) condiviso.
export const fetchNotifiche = cache(
  async (includeDismissed = false): Promise<NotificheResponse | null> => {
    const cookieStore = await cookies();
    const token = cookieStore.get(SESSION_COOKIE)?.value;
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
