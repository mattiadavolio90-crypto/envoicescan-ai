import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { type HomeKpi } from "@/lib/home";
import { cn } from "@/lib/utils";

function euro(n: number): string {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n);
}

function Trend({
  delta,
  suffix,
  buonoSeSu,
}: {
  delta: number | null;
  suffix: string;
  buonoSeSu: boolean;
}) {
  if (delta == null) return <span className="text-xs text-muted-foreground/40">—</span>;
  const su = delta > 0;
  const piatto = delta === 0;
  const positivo = piatto ? null : su === buonoSeSu;
  const Icon = piatto ? Minus : su ? ArrowUp : ArrowDown;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-xs font-semibold tabular-nums",
        positivo === null && "text-muted-foreground",
        positivo === true && "text-emerald-600 dark:text-emerald-500",
        positivo === false && "text-rose-600 dark:text-rose-500",
      )}
    >
      <Icon className="size-3" />
      {Math.abs(delta).toLocaleString("it-IT")}
      {suffix}
    </span>
  );
}

function RigaVoce({
  colore,
  label,
  value,
  delta,
  suffix,
  buonoSeSu,
  segno,
}: {
  colore: "emerald" | "amber";
  label: string;
  value: string;
  delta: number | null;
  suffix: string;
  buonoSeSu: boolean;
  segno?: string;
}) {
  const dotCn = colore === "emerald" ? "bg-emerald-400" : "bg-amber-400";
  return (
    <div className="flex items-center gap-3 rounded-xl bg-background/40 px-3.5 py-2.5">
      <span className={cn("mt-0.5 size-2 shrink-0 rounded-full", dotCn)} />
      <span className="flex-1 text-sm text-muted-foreground">
        {segno && <span className="mr-1 text-muted-foreground/50">{segno}</span>}
        {label}
      </span>
      <span className="flex items-baseline gap-2">
        <span className="text-sm font-semibold tabular-nums">{value}</span>
        <span className="w-12 text-right">
          <Trend delta={delta} suffix={suffix} buonoSeSu={buonoSeSu} />
        </span>
      </span>
    </div>
  );
}

export function KpiBlock({ kpi }: { kpi: HomeKpi }) {
  if (!kpi.has_data) return null;
  const molPos = kpi.mol >= 0;

  return (
    <div
      className={cn(
        "relative flex h-full flex-col overflow-hidden rounded-2xl border p-6 sm:p-7",
        molPos
          ? "bg-gradient-to-br from-emerald-500/10 via-emerald-500/[0.03] to-background"
          : "bg-gradient-to-br from-rose-500/10 via-rose-500/[0.03] to-background",
      )}
    >
      <div
        className={cn(
          "pointer-events-none absolute -right-16 -top-16 size-56 rounded-full blur-3xl",
          molPos ? "bg-emerald-400/15" : "bg-rose-400/15",
        )}
      />
      <div
        className={cn(
          "pointer-events-none absolute -bottom-20 left-1/4 size-52 rounded-full blur-3xl",
          molPos ? "bg-emerald-400/8" : "bg-rose-400/8",
        )}
      />

      <div className="mb-4 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">I tuoi conti</h2>
        <span className="text-xs text-muted-foreground/70">{kpi.periodo_label}</span>
      </div>

      {/* MOL — il numero che conta */}
      <div className="flex flex-1 flex-col items-center justify-center gap-1 py-4 text-center">
        <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground/60">
          = MOL (margine)
        </span>
        <div
          className={cn(
            "text-5xl font-black tabular-nums leading-none sm:text-6xl",
            molPos ? "text-emerald-600 dark:text-emerald-500" : "text-rose-600 dark:text-rose-500",
          )}
        >
          {euro(kpi.mol)}
        </div>
        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground/60">
          {kpi.confronto_label && <span>{kpi.confronto_label}</span>}
          <Trend delta={kpi.mol_delta_pct} suffix="%" buonoSeSu />
        </div>
      </div>

      {/* Breakdown */}
      <div className="mt-auto space-y-1.5">
        <RigaVoce
          colore="emerald"
          label="Fatturato"
          value={euro(kpi.fatturato)}
          delta={kpi.fatturato_delta_pct}
          suffix="%"
          buonoSeSu
        />
        <RigaVoce
          colore="amber"
          label="Food cost"
          value={
            kpi.food_cost_pct != null
              ? `${kpi.food_cost_pct.toLocaleString("it-IT")}%`
              : "—"
          }
          delta={kpi.food_cost_delta_pp}
          suffix="pp"
          buonoSeSu={false}
          segno="−"
        />
        <RigaVoce
          colore="amber"
          label="Costo personale"
          value={euro(kpi.costo_personale)}
          delta={kpi.personale_delta_pct}
          suffix="%"
          buonoSeSu={false}
          segno="−"
        />
        <RigaVoce
          colore="amber"
          label="Spese generali"
          value={euro(kpi.spese_generali)}
          delta={kpi.spese_delta_pct}
          suffix="%"
          buonoSeSu={false}
          segno="−"
        />
      </div>
    </div>
  );
}
