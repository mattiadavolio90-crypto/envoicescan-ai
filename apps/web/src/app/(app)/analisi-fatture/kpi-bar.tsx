import { ArrowDown, ArrowUp } from "lucide-react";
import type { KpiResponse } from "@/lib/fatture";
import { formatEuro } from "./periodi";

type Props = {
  kpi: KpiResponse | null;
};

function Delta({ pct }: { pct: number | null }) {
  if (pct === null || pct === undefined) {
    return <span className="text-xs text-muted-foreground">vs periodo prec.</span>;
  }
  const up = pct >= 0;
  const Icon = up ? ArrowUp : ArrowDown;
  const cls = up ? "text-emerald-600" : "text-rose-600";
  return (
    <span className={`text-xs font-medium inline-flex items-center gap-0.5 ${cls}`}>
      <Icon className="size-3" />
      {Math.abs(pct).toFixed(0)}% <span className="text-muted-foreground font-normal ml-0.5">vs periodo prec.</span>
    </span>
  );
}

export function KpiBar({ kpi }: Props) {
  if (!kpi) return null;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <KpiCard label="Spesa totale" value={formatEuro(kpi.totale)} delta={kpi.delta_totale_pct} />
      <KpiCard label="Righe" value={kpi.num_righe.toLocaleString("it-IT")} delta={kpi.delta_righe_pct} />
      <KpiCard label="Prodotti diversi" value={kpi.num_prodotti.toLocaleString("it-IT")} delta={kpi.delta_prodotti_pct} />
      <KpiCard label="Media al mese" value={formatEuro(kpi.media_mensile)} delta={kpi.delta_media_pct} />
    </div>
  );
}

function KpiCard({ label, value, delta }: { label: string; value: string; delta: number | null }) {
  return (
    <div className="rounded-lg border border-sky-500/40 bg-card p-3 hover:border-sky-500/70 transition-colors">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-bold tracking-tight mt-1 text-sky-600 dark:text-sky-400">
        {value}
      </p>
      <div className="mt-1">
        <Delta pct={delta} />
      </div>
    </div>
  );
}
