import { ArrowDown, ArrowUp } from "lucide-react";
import { formatEuro } from "./periodi";

export type KpiData = {
  fatturato_lordo: number;
  fatturato_netto: number;
  costi_fb: number;
  primo_margine: number;
  spese_generali: number;
  costo_personale: number;
  mol: number;
  food_cost_perc: number;
  primo_margine_perc: number;
  spese_perc: number;
  personale_perc: number;
  mol_perc: number;
  delta_lordo_pct: number | null;
  delta_fb_pct: number | null;
  delta_margine_pct: number | null;
  delta_spese_pct: number | null;
  delta_personale_pct: number | null;
  delta_mol_pct: number | null;
  confronto_label: string;
};

// Per le metriche di costo (F&B, Spese, Personale) spendere meno (↓) è positivo.
// Per ricavi/margini (Lordo, 1° Margine, MOL) crescere (↑) è positivo.
function Delta({ pct, label, costIsGood }: { pct: number | null; label: string; costIsGood: boolean }) {
  if (pct === null || pct === undefined) {
    return <span className="text-[11px] text-muted-foreground">vs {label}</span>;
  }
  const isGood = costIsGood ? pct < 0 : pct >= 0;
  const Icon = pct >= 0 ? ArrowUp : ArrowDown;
  const cls = isGood ? "text-emerald-500" : "text-rose-500";
  return (
    <span className={`text-[11px] font-medium inline-flex items-center gap-0.5 ${cls}`}>
      <Icon className="size-3" />
      {Math.abs(pct).toFixed(0)}%
      <span className="text-muted-foreground font-normal ml-0.5">vs {label}</span>
    </span>
  );
}

type Tone = "sky" | "amber" | "emerald" | "violet" | "pink" | "mol";

const TONE: Record<Tone, { border: string; hover: string; value: string }> = {
  sky:     { border: "border-sky-500/40",     hover: "hover:border-sky-500/70",     value: "text-sky-600 dark:text-sky-400" },
  amber:   { border: "border-amber-500/40",   hover: "hover:border-amber-500/70",   value: "text-amber-600 dark:text-amber-400" },
  emerald: { border: "border-emerald-500/40", hover: "hover:border-emerald-500/70", value: "text-emerald-600 dark:text-emerald-400" },
  violet:  { border: "border-violet-500/40",  hover: "hover:border-violet-500/70",  value: "text-violet-600 dark:text-violet-400" },
  pink:    { border: "border-pink-500/40",    hover: "hover:border-pink-500/70",    value: "text-pink-600 dark:text-pink-400" },
  mol:     { border: "border-border",         hover: "hover:border-foreground/30",  value: "" },
};

export function KpiBar({ kpi }: { kpi: KpiData }) {
  const label = kpi.confronto_label ?? "periodo prec.";

  const molTone: Tone = kpi.mol >= 0 ? "emerald" : "pink";

  const cards: {
    label: string; value: string; sub: string;
    delta: number | null; costIsGood: boolean; tone: Tone; valueOverride?: string;
  }[] = [
    {
      label: "Fatturato Lordo",
      value: formatEuro(kpi.fatturato_lordo),
      sub: `netto ${formatEuro(kpi.fatturato_netto)}`,
      delta: kpi.delta_lordo_pct, costIsGood: false, tone: "sky",
    },
    {
      label: "Costi F&B",
      value: formatEuro(kpi.costi_fb),
      sub: `food cost ${kpi.food_cost_perc.toFixed(1)}%`,
      delta: kpi.delta_fb_pct, costIsGood: true, tone: "amber",
    },
    {
      label: "Margine Lordo",
      value: formatEuro(kpi.primo_margine),
      sub: `incidenza ${kpi.primo_margine_perc.toFixed(1)}%`,
      delta: kpi.delta_margine_pct, costIsGood: false,
      tone: kpi.primo_margine >= 0 ? "emerald" : "pink",
    },
    {
      label: "Spese Generali",
      value: formatEuro(kpi.spese_generali),
      sub: `incidenza ${kpi.spese_perc.toFixed(1)}%`,
      delta: kpi.delta_spese_pct, costIsGood: true, tone: "violet",
    },
    {
      label: "Costo Personale",
      value: formatEuro(kpi.costo_personale),
      sub: `incidenza ${kpi.personale_perc.toFixed(1)}%`,
      delta: kpi.delta_personale_pct, costIsGood: true, tone: "pink",
    },
    {
      label: "MOL",
      value: formatEuro(kpi.mol),
      sub: `incidenza ${kpi.mol_perc.toFixed(1)}%`,
      delta: kpi.delta_mol_pct, costIsGood: false, tone: molTone,
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map((c) => {
        const t = TONE[c.tone];
        return (
          <div
            key={c.label}
            className={`rounded-lg border ${t.border} ${t.hover} bg-card p-3 transition-colors`}
          >
            <p className="text-xs text-muted-foreground">{c.label}</p>
            <p className={`text-lg font-bold tracking-tight mt-1 leading-tight ${t.value}`}>
              {c.value}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{c.sub}</p>
            <div className="mt-1">
              <Delta pct={c.delta} label={label} costIsGood={c.costIsGood} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
