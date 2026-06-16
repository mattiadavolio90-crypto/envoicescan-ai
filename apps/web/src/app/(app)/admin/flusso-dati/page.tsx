import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import Link from "next/link";
import { getCurrentUser, SESSION_COOKIE } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { ChevronLeft } from "lucide-react";
import { FlussoDatiClient } from "./flusso-dati-client";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

async function fetchData(token: string) {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  const [fatRes, ricRes, mapRes, cliRes] = await Promise.all([
    fetch(`${WORKER_URL}/api/admin/sistema/invoicetronic-salute?giorni=30`, { headers: h, cache: "no-store" }),
    fetch(`${WORKER_URL}/api/admin/sistema/ricavi-salute`, { headers: h, cache: "no-store" }),
    fetch(`${WORKER_URL}/api/admin/ragione-sociale-map`, { headers: h, cache: "no-store" }),
    fetch(`${WORKER_URL}/api/admin/clienti`, { headers: h, cache: "no-store" }),
  ]);
  return {
    fatture: fatRes.ok ? await fatRes.json() : { items: [], counts: {}, orfane: [] },
    ricavi: ricRes.ok ? await ricRes.json() : { items: [], counts: {} },
    mappings: mapRes.ok ? await mapRes.json() : [],
    clienti: cliRes.ok ? await cliRes.json() : [],
  };
}

export default async function FlussoDatiPage() {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) redirect("/dashboard");

  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value ?? "";
  const { fatture, ricavi, mappings, clienti } = await fetchData(token);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/admin" />}>
          <ChevronLeft className="size-4 mr-1" /> Admin
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">Flusso dati</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        Stato di arrivo dei dati per ogni cliente: fatture automatiche (Invoicetronic), ricavi dai gestionali e mapping. Da qui sblocchi le fatture rimaste in attesa senza query manuali.
      </p>
      <FlussoDatiClient
        fattureIniziali={fatture}
        ricaviIniziali={ricavi}
        mappingsIniziali={mappings}
        clienti={clienti}
      />
    </div>
  );
}
