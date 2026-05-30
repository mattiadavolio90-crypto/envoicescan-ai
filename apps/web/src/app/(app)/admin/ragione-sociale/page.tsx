import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import Link from "next/link";
import { getCurrentUser, SESSION_COOKIE } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { ChevronLeft } from "lucide-react";
import { RagioneSocialeClient } from "./ragione-sociale-client";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

async function fetchData(token: string) {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  const [mapRes, clientiRes] = await Promise.all([
    fetch(`${WORKER_URL}/api/admin/ragione-sociale-map`, { headers: h, cache: "no-store" }),
    fetch(`${WORKER_URL}/api/admin/clienti`, { headers: h, cache: "no-store" }),
  ]);
  return {
    mappings: mapRes.ok ? await mapRes.json() : [],
    clienti: clientiRes.ok ? await clientiRes.json() : [],
  };
}

export default async function RagioneSocialePage() {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) redirect("/dashboard");

  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value ?? "";
  const { mappings, clienti } = await fetchData(token);

  const sediFlat = clienti.flatMap((c: { id: string; email: string; sedi: { id: string; nome_ristorante: string; partita_iva: string | null }[] }) =>
    (c.sedi || []).map((s: { id: string; nome_ristorante: string; partita_iva: string | null }) => ({
      id: s.id,
      label: `${s.nome_ristorante} (${c.email})`,
    }))
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/admin"><ChevronLeft className="size-4 mr-1" /> Admin</Link>
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">Mapping Ragione Sociale</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        Collega le ragioni sociali che appaiono sulle email dei gestionali (es. Passbi) al ristorante corretto in ONEFLUX.
      </p>
      <RagioneSocialeClient mappingsIniziali={mappings} sedi={sediFlat} />
    </div>
  );
}
