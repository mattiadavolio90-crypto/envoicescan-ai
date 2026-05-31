import { redirect, notFound } from "next/navigation";
import { cookies } from "next/headers";
import Link from "next/link";
import { getCurrentUser, SESSION_COOKIE } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { ChevronLeft } from "lucide-react";
import { ClienteDettaglioClient } from "./cliente-dettaglio-client";
import type { ClienteDettaglio } from "@/lib/admin";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

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

type Ctx = { params: Promise<{ id: string }> };

export default async function ClienteDettaglioPage({ params }: Ctx) {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) redirect("/dashboard");

  const { id } = await params;
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value ?? "";
  const cliente = await fetchCliente(token, id);
  if (!cliente) notFound();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/admin/clienti" />}>
          <ChevronLeft className="size-4 mr-1" /> Clienti
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">{cliente.nome_ristorante || cliente.email}</h1>
      </div>
      <ClienteDettaglioClient cliente={cliente} />
    </div>
  );
}
