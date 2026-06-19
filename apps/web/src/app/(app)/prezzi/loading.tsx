import { Skeleton } from "@/components/ui/skeleton";

// Skeleton struttura pagina Prezzi: header + tab + tabella prezzi.
export default function Loading() {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>

      <div className="flex gap-2">
        <Skeleton className="h-9 w-32 rounded-full" />
        <Skeleton className="h-9 w-32 rounded-full" />
        <Skeleton className="h-9 w-28 rounded-full" />
      </div>

      <div className="space-y-2 rounded-2xl border bg-card p-4">
        <Skeleton className="h-9 w-full" />
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    </div>
  );
}
