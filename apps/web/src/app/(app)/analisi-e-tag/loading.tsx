import { Skeleton } from "@/components/ui/skeleton";

// Skeleton struttura pagina Analisi e Tag: header + filtri + griglia analisi.
export default function Loading() {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <Skeleton className="h-7 w-44" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>

      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-9 w-36 rounded-full" />
        <Skeleton className="h-9 w-28 rounded-full" />
        <Skeleton className="h-9 w-28 rounded-full" />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-44 w-full rounded-2xl" />
        ))}
      </div>
    </div>
  );
}
