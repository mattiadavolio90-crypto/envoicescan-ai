import { Suspense } from "react";
import { redirect } from "next/navigation";
import { requirePagina } from "@/lib/page-guard";
import { fetchGruppoOverview } from "@/lib/gruppo";
import { PageHeader } from "@/components/ui/page-header";
import { ScadenziarioClient } from "../../scadenziario/scadenziario-client";
import { BlockRetry } from "../../dashboard/block-retry";
import type { Documento, SedeCatena } from "@/lib/scadenziario";
import { workerGet } from "@/lib/worker";

type GruppoScadenziarioResponse = {
  nome_gruppo: string;
  sedi: SedeCatena[];
  documenti: Documento[];
};

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
  // Worker giù/lento (null) → BlockRetry ripinga e fa refresh da solo appena
  // risponde. Mandare a /dashboard anche in questo caso sbatteva fuori dalla
  // pagina chi ha davvero un gruppo, per un guasto temporaneo.
  if (overview === null) {
    return (
      <BlockRetry endpoint="/api/account/sedi">
        <FattureSkeleton />
      </BlockRetry>
    );
  }
  // Account mono-sede: niente vista di gruppo da mostrare, torna alla Home del PV
  // (stesso comportamento di /catena — vedi catena/page.tsx).
  if (overview.num_pv < 2) {
    redirect("/dashboard");
  }

  const data = await workerGet<GruppoScadenziarioResponse>(
    "/api/gruppo/scadenziario",
    "catena/fatture",
  );

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
