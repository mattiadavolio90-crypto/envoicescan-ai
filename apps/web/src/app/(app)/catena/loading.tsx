import { Skeleton } from "@/components/ui/skeleton";

// Skeleton struttura plancia Catena: header gruppo + KPI gruppo + ranking sedi.
export default function Loading() {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <Skeleton className="h-7 w-52" />
        <Skeleton className="h-4 w-64" />
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="space-y-2 rounded-xl border bg-card p-4">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-7 w-28" />
          </div>
        ))}
      </div>

      <div className="space-y-3 rounded-2xl border bg-card p-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full rounded-xl" />
        ))}
      </div>
    </div>
  );
}
