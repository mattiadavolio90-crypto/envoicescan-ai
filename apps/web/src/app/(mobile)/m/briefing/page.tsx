import { Suspense } from "react";
import { fetchBriefing, fetchSalute, fetchKpi } from "@/lib/home";
import { SaluteCard } from "@/app/(app)/dashboard/salute-card";
import { KpiBlock } from "@/app/(app)/dashboard/kpi-block";
import { MobileBriefing } from "./mobile-briefing";

// Briefing: e' il primo blocco, lo mostriamo appena pronto.
async function BriefingBlock() {
  const briefing = await fetchBriefing();
  if (!briefing) {
    return (
      <div className="py-10 text-center text-sm text-muted-foreground">
        Impossibile caricare il briefing. Riprova più tardi.
      </div>
    );
  }
  return <MobileBriefing briefing={briefing} />;
}

// Conti (MOL): caricato in streaming, non blocca il briefing.
async function ContiBlock() {
  const kpi = await fetchKpi();
  if (!kpi) return null;
  return <KpiBlock kpi={kpi} />;
}

// Salute della gestione: anch'essa in streaming.
async function SaluteBlock() {
  const salute = await fetchSalute();
  if (!salute) return null;
  return <SaluteCard salute={salute} />;
}

function CardSkeleton() {
  return (
    <div className="h-56 animate-pulse rounded-2xl border bg-muted/40" />
  );
}

export default function MobileBriefingPage() {
  // Streaming: ogni blocco ha il suo Suspense -> il briefing appare per primo,
  // conti e salute arrivano dopo con skeleton, senza bloccarsi a vicenda.
  return (
    <div className="space-y-5">
      <Suspense fallback={<div className="h-40 animate-pulse rounded-2xl border bg-muted/40" />}>
        <BriefingBlock />
      </Suspense>
      <Suspense fallback={<CardSkeleton />}>
        <ContiBlock />
      </Suspense>
      <Suspense fallback={<CardSkeleton />}>
        <SaluteBlock />
      </Suspense>
    </div>
  );
}
