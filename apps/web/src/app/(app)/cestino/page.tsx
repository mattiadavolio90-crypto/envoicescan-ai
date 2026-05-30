import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";
import { CestinoClient } from "./cestino-client";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

export type FatturaInCestino = {
  file_origine: string;
  fornitore: string;
  num_righe: number;
  totale: number;
  deleted_at: string;
  data_documento: string;
};

async function fetchCestino(token: string): Promise<FatturaInCestino[]> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  try {
    const res = await fetch(`${WORKER_URL}/api/cestino`, {
      headers: h,
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return (data.cestino as FatturaInCestino[]) ?? [];
  } catch {
    return [];
  }
}

export default async function CestinoPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value ?? "";
  const cestino = await fetchCestino(token);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Cestino Fatture</h1>
      </div>
      <CestinoClient initialCestino={cestino} />
    </div>
  );
}
