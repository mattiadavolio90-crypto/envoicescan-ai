import { Suspense } from "react";
import { cookies } from "next/headers";
import { getCurrentUser } from "@/lib/auth";
import { fetchBriefing, fetchSalute, fetchKpi } from "@/lib/home";
import { fetchGruppoOverview } from "@/lib/gruppo";
import { SaluteCard } from "@/app/(app)/dashboard/salute-card";
import { KpiBlock } from "@/app/(app)/dashboard/kpi-block";
import { MobileBriefing } from "./mobile-briefing";
import { MobileCatena } from "./mobile-catena";

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
  // hideLinks: nessuna CTA "Vai alla pagina" che porti fuori dalla PWA.
  return <SaluteCard salute={salute} hideLinks />;
}

function CardSkeleton() {
  return (
    <div className="h-56 animate-pulse rounded-2xl border bg-muted/40" />
  );
}

async function CatenaBlock() {
  const overview = await fetchGruppoOverview();
  // Se l'overview non c'è (worker lento) o l'account non è multi-sede, lascia
  // proseguire la Home del PV qui sotto (il chiamante gestisce il fallback).
  if (!overview || overview.num_pv < 2) return null;
  return <MobileCatena overview={overview} />;
}

export default async function MobileBriefingPage() {
  // Cliente catena (≥2 sedi) in modalità "chain" (cookie oneflux_view): la Home
  // mobile è la vista di GRUPPO (briefing + segnali + ranking). Scendendo in un PV
  // il cookie passa a "pv" e qui torna la Home del singolo locale.
  const [user, cookieStore] = await Promise.all([getCurrentUser(), cookies()]);
  const inChain = (user?.num_sedi ?? 1) >= 2 && cookieStore.get("oneflux_view")?.value !== "pv";
  if (inChain) {
    const blocco = await CatenaBlock();
    if (blocco) return <div className="space-y-5">{blocco}</div>;
  }

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
