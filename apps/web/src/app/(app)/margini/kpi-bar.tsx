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

type Tone = "sky" | "orange" | "emerald" | "rose" | "violet" | "pink";

const TONE: Record<Tone, { border: string; hover: string; value: string }> = {
  sky:     { border: "border-sky-500/40",     hover: "hover:border-sky-500/70",     value: "text-sky-600 dark:text-sky-400" },
  orange:  { border: "border-orange-500/40",  hover: "hover:border-orange-500/70",  value: "text-orange-600 dark:text-orange-400" },
  emerald: { border: "border-emerald-500/40", hover: "hover:border-emerald-500/70", value: "text-emerald-600 dark:text-emerald-400" },
  rose:    { border: "border-rose-500/40",    hover: "hover:border-rose-500/70",    value: "text-rose-600 dark:text-rose-400" },
  violet:  { border: "border-violet-500/40",  hover: "hover:border-violet-500/70",  value: "text-violet-600 dark:text-violet-400" },
  pink:    { border: "border-pink-500/40",    hover: "hover:border-pink-500/70",    value: "text-pink-600 dark:text-pink-400" },
};

type CardDef = {
  label: string;
  value: string;
  sub?: string; // solo Fatturato Lordo ha il sub
  tone: Tone;
};

export function KpiBar({ kpi }: { kpi: KpiData }) {
  const molTone: Tone = kpi.mol >= 0 ? "emerald" : "rose";

  const cards: CardDef[] = [
    { label: "Fatturato Lordo",  value: formatEuro(kpi.fatturato_lordo), sub: `netto ${formatEuro(kpi.fatturato_netto)}`, tone: "sky" },
    { label: "Costi F&B",        value: formatEuro(kpi.costi_fb),         tone: "orange" },
    { label: "Margine Lordo",    value: formatEuro(kpi.primo_margine),    tone: kpi.primo_margine >= 0 ? "emerald" : "rose" },
    { label: "Spese Generali",   value: formatEuro(kpi.spese_generali),   tone: "violet" },
    { label: "Costo Personale",  value: formatEuro(kpi.costo_personale),  tone: "pink" },
    { label: "MOL",              value: formatEuro(kpi.mol),              tone: molTone },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map((c) => {
        const t = TONE[c.tone];
        return (
          <div
            key={c.label}
            className={`rounded-lg border ${t.border} ${t.hover} bg-card p-4 transition-colors`}
          >
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
              {c.label}
            </p>
            <p className={`text-2xl font-bold tracking-tight mt-1.5 leading-tight ${t.value}`}>
              {c.value}
            </p>
            {c.sub && <p className="text-[11px] text-muted-foreground mt-1">{c.sub}</p>}
          </div>
        );
      })}
    </div>
  );
}
