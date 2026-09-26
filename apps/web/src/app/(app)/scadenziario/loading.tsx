import { Skeleton } from "@/components/ui/skeleton";

// Skeleton della pagina Gestione Fatture: ricerca + KPI + filtri + lista.
//
// Le forme seguono quelle vere, altrimenti al caricamento la pagina "salta":
// il contenitore lista e' `rounded-lg` come in scadenziario-client.tsx (era
// `rounded-2xl`, e gli angoli cambiavano sotto gli occhi), e i chip di filtro
// sono alti quanto quelli reali (~h-7, non h-9: lo scheletro prometteva
// controlli piu' grandi di quelli che arrivavano).
export default function Loading() {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <Skeleton className="h-7 w-52" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>

      <Skeleton className="h-10 w-full rounded-md" />

      {/* I filtri stanno SOPRA i KPI, come nella pagina vera: promettere le
          tessere dove poi arrivano i chip e' la stessa cosa che questo file
          serve a evitare. */}
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-7 w-28 rounded-full" />
        <Skeleton className="h-7 w-28 rounded-full" />
        <Skeleton className="h-7 w-36 rounded-full" />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[88px] w-full rounded-xl" />
        ))}
      </div>

      <div className="space-y-2 rounded-lg border bg-card p-4">
        {Array.from({ length: 9 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    </div>
  );
}
