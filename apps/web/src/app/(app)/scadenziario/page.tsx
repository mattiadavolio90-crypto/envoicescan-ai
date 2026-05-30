import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";
import { ScadenziarioClient } from "./scadenziario-client";
import type { Documento } from "@/lib/scadenziario";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

async function fetchDocumenti(token: string): Promise<Documento[]> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  try {
    const res = await fetch(`${WORKER_URL}/api/scadenziario`, {
      headers: h,
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return (data.documenti as Documento[]) ?? [];
  } catch {
    return [];
  }
}

async function triggerNotifica(token: string): Promise<void> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  try {
    await fetch(`${WORKER_URL}/api/scadenziario/notifica`, {
      method: "POST",
      headers: h,
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    // best-effort
  }
}

export default async function ScadenziarioPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value ?? "";

  const [documenti] = await Promise.all([
    fetchDocumenti(token),
    token ? triggerNotifica(token) : Promise.resolve(),
  ]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Scadenziario</h1>
      </div>
      <ScadenziarioClient initialDocumenti={documenti} />
    </div>
  );
}
