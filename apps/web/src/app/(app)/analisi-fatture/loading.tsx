import { Loader2 } from "lucide-react";

export default function Loading() {
  return (
    <div className="space-y-5">
      <div className="h-8 w-48 rounded bg-muted animate-pulse" />
      <div className="flex gap-2">
        <div className="h-7 w-28 rounded-full bg-muted animate-pulse" />
        <div className="h-7 w-32 rounded-full bg-muted animate-pulse" />
        <div className="h-7 w-32 rounded-full bg-muted animate-pulse" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="rounded-lg border bg-card p-3 space-y-2">
            <div className="h-3 w-20 rounded bg-muted animate-pulse" />
            <div className="h-6 w-24 rounded bg-muted animate-pulse" />
            <div className="h-3 w-28 rounded bg-muted animate-pulse" />
          </div>
        ))}
      </div>
      <div className="flex items-center justify-center py-12">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">Caricamento dati...</span>
      </div>
    </div>
  );
}
