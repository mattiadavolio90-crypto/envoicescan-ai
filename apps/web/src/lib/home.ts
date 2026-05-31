import { cookies } from "next/headers";
import { SESSION_COOKIE } from "./auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

export type BriefingAzione = {
  id: string;
  topic_key: string;
  severity: "info" | "warning" | "error" | "success";
  testo: string;
  cta_label: string;
  cta_page: string;
};

export type Briefing = {
  saluto: string;
  data: string;
  narrativa: string;
  severity_max: "info" | "warning" | "error" | "success";
  tutto_ok: boolean;
  azioni: BriefingAzione[];
  generated_at: string | null;
};

export async function fetchBriefing(): Promise<Briefing | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(`${WORKER_URL}/api/home/briefing`, {
      method: "GET",
      headers,
      cache: "no-store",
    });
    if (!res.ok) {
      console.error("[home.briefing] worker error:", res.status, await res.text().catch(() => ""));
      return null;
    }
    return (await res.json()) as Briefing;
  } catch (err) {
    console.error("[home.briefing] fetch error:", err);
    return null;
  }
}
