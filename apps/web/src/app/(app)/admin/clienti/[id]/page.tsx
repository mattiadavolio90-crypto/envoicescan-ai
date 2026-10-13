import { redirect, notFound } from "next/navigation";
import { cookies } from "next/headers";
import { getCurrentUser, SESSION_COOKIE } from "@/lib/auth";
import { ClienteDettaglioClient } from "./cliente-dettaglio-client";
import type { ClienteDettaglio } from "@/lib/admin";
import { tabDaUrl } from "@/lib/admin-clienti";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

async function fetchCliente(token: string, id: string): Promise<ClienteDettaglio | null> {
  try {
    const h: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/admin/clienti/${id}`, { headers: h, cache: "no-store" });
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

type Ctx = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string | string[] }>;
};

export default async function ClienteDettaglioPage({ params, searchParams }: Ctx) {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) redirect("/dashboard");

  const { id } = await params;
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value ?? "";
  const cliente = await fetchCliente(token, id);
  if (!cliente) notFound();

  const { tab } = await searchParams;
  return <ClienteDettaglioClient cliente={cliente} tabIniziale={tabDaUrl(Array.isArray(tab) ? tab[0] : tab)} />;
}
