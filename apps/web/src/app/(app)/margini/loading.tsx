import { Skeleton } from "@/components/ui/skeleton";

// Skeleton fedele alla struttura della pagina Margini: header + barra KPI a 6
// celle + tab + area contenuto. Scatta al click (Server Component async) cosi'
// la pagina "appare" subito invece dello spinner generico.
export default function Loading() {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-72" />
      </div>

      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-8 w-28 rounded-full" />
        <Skeleton className="h-8 w-32 rounded-full" />
        <Skeleton className="h-8 w-28 rounded-full" />
        <Skeleton className="h-8 w-36 rounded-full" />
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="space-y-2 rounded-xl border bg-card p-4">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-3 w-16" />
          </div>
        ))}
      </div>

      <div className="flex gap-2 pt-2">
        <Skeleton className="h-9 w-28 rounded-full" />
        <Skeleton className="h-9 w-28 rounded-full" />
        <Skeleton className="h-9 w-28 rounded-full" />
      </div>

      <Skeleton className="h-72 w-full rounded-2xl" />
    </div>
  );
}
