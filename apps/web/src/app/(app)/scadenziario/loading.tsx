import { Skeleton } from "@/components/ui/skeleton";

// Skeleton struttura pagina Gestione Fatture / Scadenziario: header + filtri +
// lista fatture.
export default function Loading() {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <Skeleton className="h-7 w-52" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>

      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-9 w-28 rounded-full" />
        <Skeleton className="h-9 w-28 rounded-full" />
        <Skeleton className="h-9 w-36 rounded-full" />
      </div>

      <div className="space-y-2 rounded-2xl border bg-card p-4">
        {Array.from({ length: 9 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    </div>
  );
}
