import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { getCurrentUser, SESSION_COOKIE } from "@/lib/auth";
import { ClientiClient } from "./clienti-client";
import type { Cliente } from "@/lib/admin";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";
import { datiOggi } from "../oggi-dati";
import { vistaDaUrl } from "@/lib/admin-mappa";

async function fetchClienti(token: string): Promise<Cliente[]> {
  try {
    const h: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/admin/clienti`, { headers: h, cache: "no-store" });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function AdminClientiPage({ searchParams }: { searchParams: Promise<{ vista?: string | string[] }> }) {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) redirect("/dashboard");

  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value ?? "";
  const [clienti, oggi] = await Promise.all([fetchClienti(token), datiOggi(token)]);
  const problemi = oggi?.problemi_per_cliente ?? {};
  const { vista } = await searchParams;

  return (
    <ClientiClient
      clientiIniziali={clienti.map((c) => ({ ...c, n_problemi: problemi[c.id] ?? 0 }))}
      voci={oggi ? oggi.voci : null}
      vistaIniziale={vistaDaUrl(Array.isArray(vista) ? vista[0] : vista)}
    />
  );
}
