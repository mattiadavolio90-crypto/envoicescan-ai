import { Suspense } from "react";
import { redirect } from "next/navigation";
import { fetchGruppoOverview } from "@/lib/gruppo";
import { SintesiCatena } from "./sintesi-catena";

// Modalità catena (Fase 1) — UNA pagina: la Sintesi (plancia di sola lettura).
// La catena è un layer superiore di analisi/visualizzazione sopra i PV;
// l'inserimento vive solo nel punto vendita.

function SintesiSkeleton() {
  return (
    <div className="space-y-8">
      <div className="h-10 w-72 animate-pulse rounded-xl bg-muted/40" />
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="h-28 animate-pulse rounded-2xl border bg-muted/40" />
        <div className="h-28 animate-pulse rounded-2xl border bg-muted/40" />
        <div className="h-28 animate-pulse rounded-2xl border bg-muted/40" />
      </div>
      <div className="h-64 animate-pulse rounded-2xl border bg-muted/40" />
    </div>
  );
}

async function SintesiBlock() {
  const overview = await fetchGruppoOverview();
  // Account mono-sede (o worker che risponde 400): non c'è un gruppo da mostrare,
  // si torna alla Home del PV. Worker giù (null) → mostra lo skeleton/retry.
  if (overview === null) {
    return (
      <div className="rounded-2xl border bg-muted/30 p-8 text-center text-sm text-muted-foreground">
        Sto preparando la vista della catena… ricarica tra qualche secondo.
      </div>
    );
  }
  if (overview.num_pv < 2) {
    redirect("/dashboard");
  }
  return <SintesiCatena overview={overview} />;
}

export default async function CatenaPage() {
  return (
    <Suspense fallback={<SintesiSkeleton />}>
      <SintesiBlock />
    </Suspense>
  );
}
