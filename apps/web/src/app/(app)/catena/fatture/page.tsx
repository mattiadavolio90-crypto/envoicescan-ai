import { Suspense } from "react";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE } from "@/lib/auth";
import { requirePagina } from "@/lib/page-guard";
import { fetchGruppoOverview } from "@/lib/gruppo";
import { PageHeader } from "@/components/ui/page-header";
import { ScadenziarioClient } from "../../scadenziario/scadenziario-client";
import type { Documento, SedeCatena } from "@/lib/scadenziario";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

type GruppoScadenziarioResponse = {
  nome_gruppo: string;
  sedi: SedeCatena[];
  documenti: Documento[];
};

async function fetchGruppoFatture(token: string): Promise<GruppoScadenziarioResponse | null> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  try {
    const res = await fetch(`${WORKER_URL}/api/gruppo/scadenziario`, {
      headers: h,
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return null;
    return (await res.json()) as GruppoScadenziarioResponse;
  } catch {
    return null;
  }
}

function FattureSkeleton() {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl border bg-muted/40" />
        ))}
      </div>
      <div className="h-96 animate-pulse rounded-lg border bg-muted/40" />
    </div>
  );
}

async function FattureBlock() {
  const overview = await fetchGruppoOverview();
  // Account mono-sede: niente vista di gruppo da mostrare, torna alla Home del PV
  // (stesso comportamento di /catena — vedi catena/page.tsx:44-46).
  if (overview === null || overview.num_pv < 2) {
    redirect("/dashboard");
  }

  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value ?? "";
  const data = await fetchGruppoFatture(token);

  return (
    <ScadenziarioClient
      initialDocumenti={data?.documenti ?? []}
      modalitaCatena
      sedi={data?.sedi ?? []}
    />
  );
}

export default async function CatenaFatturePage() {
  await requirePagina("scadenziario");

  return (
    <div className="space-y-5">
      <PageHeader
        icon="calendar"
        title="Gestione Fatture — Gruppo"
        hint="Scadenze e pagamenti di tutti i punti vendita"
      />
      <Suspense fallback={<FattureSkeleton />}>
        <FattureBlock />
      </Suspense>
    </div>
  );
}
