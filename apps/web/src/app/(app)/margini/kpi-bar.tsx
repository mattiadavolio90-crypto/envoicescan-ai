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
  spark_lordo?: number[];
  spark_fb?: number[];
  spark_margine?: number[];
  spark_spese?: number[];
  spark_personale?: number[];
  spark_mol?: number[];
};

function Sparkline({ values, color }: { values: number[]; color: string }) {
  if (!values || values.length < 2) return null;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const w = 100;
  const h = 24;
  const step = w / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(h - ((v - min) / range) * (h - 2) - 1).toFixed(1)}`)
    .join(" ");
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="block w-full">
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        opacity={0.85}
      />
    </svg>
  );
}

type Tone = "sky" | "orange" | "emerald" | "rose" | "violet" | "pink";

const TONE: Record<Tone, { border: string; hover: string; value: string }> = {
  sky:     { border: "border-sky-500/40",     hover: "hover:border-sky-500/70",     value: "text-sky-600 dark:text-sky-400" },
  orange:  { border: "border-orange-500/40",  hover: "hover:border-orange-500/70",  value: "text-orange-600 dark:text-orange-400" },
  emerald: { border: "border-emerald-500/40", hover: "hover:border-emerald-500/70", value: "text-emerald-600 dark:text-emerald-400" },
  rose:    { border: "border-rose-500/40",    hover: "hover:border-rose-500/70",    value: "text-rose-600 dark:text-rose-400" },
  violet:  { border: "border-violet-500/40",  hover: "hover:border-violet-500/70",  value: "text-violet-600 dark:text-violet-400" },
  pink:    { border: "border-pink-500/40",    hover: "hover:border-pink-500/70",    value: "text-pink-600 dark:text-pink-400" },
};

// Colori hex allineati al TONE per i tratti SVG sparkline
const TONE_COLOR: Record<Tone, string> = {
  sky:     "#0ea5e9",
  orange:  "#f97316",
  emerald: "#10b981",
  rose:    "#f43f5e",
  violet:  "#8b5cf6",
  pink:    "#ec4899",
};

type CardDef = {
  label: string;
  value: string;
  sub?: string;
  tone: Tone;
  spark?: number[];
};

export function KpiBar({ kpi }: { kpi: KpiData }) {
  const molTone: Tone = kpi.mol >= 0 ? "emerald" : "rose";

  const cards: CardDef[] = [
    { label: "Fatturato Netto",  value: formatEuro(kpi.fatturato_netto), sub: `lordo ${formatEuro(kpi.fatturato_lordo)}`, tone: "sky",    spark: kpi.spark_lordo },
    { label: "Costi F&B",        value: formatEuro(kpi.costi_fb),                                                          tone: "orange", spark: kpi.spark_fb },
    { label: "Margine Lordo",    value: formatEuro(kpi.primo_margine),                                                     tone: kpi.primo_margine >= 0 ? "emerald" : "rose", spark: kpi.spark_margine },
    { label: "Costi Gestione",   value: formatEuro(kpi.spese_generali),                                                    tone: "violet", spark: kpi.spark_spese },
    { label: "Costo Personale",  value: formatEuro(kpi.costo_personale),                                                   tone: "pink",   spark: kpi.spark_personale },
    { label: "MOL",              value: formatEuro(kpi.mol),                                                                tone: molTone,  spark: kpi.spark_mol },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map((c) => {
        const t = TONE[c.tone];
        return (
          <div
            key={c.label}
            className={`rounded-lg border ${t.border} ${t.hover} bg-card px-4 pt-3 pb-2 transition-colors flex flex-col gap-1`}
          >
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium leading-none">
              {c.label}
            </p>
            <p className={`text-2xl font-bold tracking-tight leading-tight ${t.value} truncate`}>
              {c.value}
            </p>
            {c.sub && (
              <p className="text-[11px] text-muted-foreground leading-none">{c.sub}</p>
            )}
            {c.spark && c.spark.length >= 2 && (
              <div className="mt-1">
                <Sparkline values={c.spark} color={TONE_COLOR[c.tone]} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
