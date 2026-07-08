"use client";

import { BarChart3, Calculator, Calendar, FlaskConical, Info, Lock, Settings2, Sigma, Users } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { KpiBar, type KpiData } from "@/app/(app)/margini/kpi-bar";
import { formatEuro } from "@/lib/format";
import {
  demoMarginiApr,
  demoMarginiMag,
  demoMarginiTot,
  demoMarginiPeriodo,
  demoMarginiCommenti,
  type DemoMeseMargini,
} from "@/lib/demo-data";

// Ricavi e Margini del Demo Tour: replica 1:1 della pagina reale (tab
// Marginalità) con DUE mesi in colonna (Apr + Mag) + Totale, come la tabella
// trasposta vera. Aprile è visibile apposta: il briefing e lo step del tour
// dicono "tre punti meno di aprile" e qui il confronto si vede coi numeri.

const apr = demoMarginiApr;
const mag = demoMarginiMag;
const tot = demoMarginiTot;
const periodo = demoMarginiPeriodo;

const kpiReale: KpiData = {
  fatturato_lordo: 134640,
  fatturato_netto: tot.fatturato_netto,
  costi_fb: tot.costi_fb_totali,
  primo_margine: tot.primo_margine,
  spese_generali: tot.costi_spese_totali,
  costo_personale: tot.costi_personale,
  mol: tot.mol,
  food_cost_perc: periodo.food_cost_perc,
  primo_margine_perc: periodo.primo_margine_perc,
  spese_perc: periodo.spese_gen_perc,
  personale_perc: periodo.personale_perc,
  mol_perc: periodo.mol_perc,
  delta_lordo_pct: null, delta_fb_pct: null, delta_margine_pct: null,
  delta_spese_pct: null, delta_personale_pct: null, delta_mol_pct: null,
  confronto_label: "periodo prec.",
  spark_mol: [24, 23, 25, 24, 21],
};

const chipBase = "px-3 py-1.5 text-xs font-medium rounded-full border inline-flex items-center gap-1.5";
const chipActive = "bg-primary text-primary-foreground border-primary";
const chipIdle = "bg-background border-input";

const TABS = [
  { key: "calcolo", label: "Marginalità", icon: Calculator },
  { key: "coperti", label: "Coperti", icon: Users },
  { key: "analisi", label: "Analisi Avanzate", icon: FlaskConical },
];

// Righe del conto economico, come ROWS di calcolo-tab.tsx: la chiave punta al
// campo del mese, così Apr/Mag/Totale leggono la stessa definizione di riga.
type NumericKey = Exclude<keyof DemoMeseMargini, "label">;
type Row = {
  label: string;
  key: NumericKey;
  metric?: boolean;
  labelColor?: string;
  valueColor?: string;
  locked?: boolean;
  sep?: boolean;
};
const ROWS: Row[] = [
  { label: "Ricavi IVA 10%", key: "fatturato_iva10", locked: true },
  { label: "Ricavi IVA 22%", key: "fatturato_iva22", locked: true },
  { label: "Altri ricavi (no IVA)", key: "altri_ricavi_noiva", locked: true },
  { label: "= Fatturato Netto", key: "fatturato_netto", metric: true, sep: true, labelColor: "text-sky-500 dark:text-sky-400", valueColor: "text-sky-600 dark:text-sky-400" },
  { label: "Costi F&B (Fatture)", key: "costi_fb_auto", locked: true },
  { label: "Altri Costi F&B", key: "altri_costi_fb" },
  { label: "= Costi F&B Totali", key: "costi_fb_totali", metric: true, labelColor: "text-orange-500 dark:text-orange-400", valueColor: "text-orange-600 dark:text-orange-400" },
  { label: "= 1° Margine", key: "primo_margine", metric: true, labelColor: "text-emerald-500 dark:text-emerald-400", valueColor: "text-emerald-600 dark:text-emerald-400" },
  { label: "Spese Gen. (Fatture)", key: "costi_spese_auto", locked: true, sep: true },
  { label: "Altre Spese Generali", key: "altri_costi_spese" },
  { label: "Costo Personale Lordo", key: "costo_dipendenti", labelColor: "text-pink-600 dark:text-pink-400", valueColor: "text-pink-600 dark:text-pink-400" },
  { label: "Costo Personale Extra", key: "costo_personale_extra", labelColor: "text-pink-600 dark:text-pink-400", valueColor: "text-pink-600 dark:text-pink-400" },
  { label: "= Costi gestione totali", key: "totale_costi", metric: true, sep: true, labelColor: "text-violet-500 dark:text-violet-400", valueColor: "text-violet-600 dark:text-violet-400" },
];

function pct(raw: number, netto: number): string | null {
  if (!netto || raw === 0) return null;
  return `${((raw / netto) * 100).toFixed(0)}%`;
}

export function DemoMargini() {
  return (
    <div className="space-y-5">
      <PageHeader icon="bar-chart" title="Ricavi e Margini" hint="La salute economica del tuo locale" />

      {/* Filtri periodo (chip inerti): personalizzato Apr→Mag, coerente con le
          due colonne della tabella sotto. */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className={`${chipBase} ${chipIdle}`}>Anno in corso</span>
        <span className={`${chipBase} ${chipIdle}`}><Calendar className="size-3" />Seleziona mese</span>
        <span className={`${chipBase} ${chipActive}`}><Settings2 className="size-3" />Personalizzato</span>
        <span className="ml-2 text-xs font-medium text-sky-500 dark:text-sky-400">{periodo.range_label}</span>
      </div>

      <KpiBar kpi={kpiReale} />

      <div className="pb-4" />

      {/* Tabs (inerti) */}
      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <span
              key={t.key}
              className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
                t.key === "calcolo" ? "border-primary text-foreground" : "border-transparent text-muted-foreground"
              }`}
            >
              <Icon className="size-3.5" />
              {t.label}
            </span>
          );
        })}
      </div>

      <div className="space-y-4">
        {/* Toolbar */}
        <div className="flex items-center gap-2">
          <Info className="size-3 text-muted-foreground" />
          <p className="text-xs text-muted-foreground">
            Modifica le righe in bianco; le altre sono calcolate o ereditate dalle fatture.
          </p>
          <div className="ml-auto inline-flex items-center rounded-md border border-input p-0.5 text-xs font-semibold">
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-primary text-primary-foreground">
              <Sigma className="size-3" />Totale
            </span>
          </div>
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-primary text-primary-foreground">
            Carica ricavi
          </span>
        </div>

        {/* Legenda colori */}
        <div className="flex flex-wrap gap-1.5">
          {[
            { label: "Ricavi", cls: "text-sky-700 dark:text-sky-300 border-sky-500/40" },
            { label: "Costi F&B", cls: "text-orange-700 dark:text-orange-300 border-orange-500/40" },
            { label: "Costi Gestione", cls: "text-purple-700 dark:text-purple-300 border-purple-500/40" },
            { label: "Personale", cls: "text-pink-700 dark:text-pink-300 border-pink-500/40" },
            { label: "Totali & Margini", cls: "text-emerald-700 dark:text-emerald-300 border-emerald-500/40" },
          ].map((c) => (
            <span key={c.label} className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${c.cls}`}>
              {c.label}
            </span>
          ))}
        </div>

        {/* Tabella conto economico trasposta: Apr | Mag (corrente) | Totale */}
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full table-auto text-[15px] border-collapse">
              <thead className="bg-muted/40">
                <tr className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="text-left px-3 py-2.5 font-semibold border-r border-border">Voce</th>
                  <th className="text-right px-3 py-2.5 font-semibold border-r border-border">{apr.label}</th>
                  <th className="text-right px-3 py-2.5 font-semibold text-sky-500 dark:text-sky-400 border-l border-r border-sky-500/50">
                    <span className="mr-1 inline-block size-1.5 rounded-full bg-sky-400 align-middle" />
                    {mag.label}
                  </th>
                  <th className="text-right px-3 py-2.5 font-bold border-l-2 border-sky-500/50 bg-sky-500/8 text-sky-600 dark:text-sky-400">
                    Totale
                  </th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map((r) => (
                  <RigaVoce key={r.key} r={r} />
                ))}
                {/* Riga MOL — ancora del tour (data-attr sul <tr>) */}
                <tr data-demo-anchor="mol" className="border-t-[3px] border-t-border font-semibold bg-emerald-500/[0.06]">
                  <td className="px-3 py-2.5 border-r border-border whitespace-nowrap font-bold text-green-600 dark:text-green-300">
                    = 2° Margine (MOL)
                  </td>
                  <CellaMol mese={apr} corrente={false} />
                  <CellaMol mese={mag} corrente />
                  <td className="text-right px-3 py-2.5 tabular-nums border-l-2 border-sky-500/50 bg-sky-500/8 align-middle">
                    <div className="font-bold text-emerald-600 dark:text-emerald-400">{formatEuro(tot.mol)}</div>
                    <div className="text-[11px] tabular-nums opacity-70 text-emerald-600 dark:text-emerald-400">
                      {pct(tot.mol, tot.fatturato_netto)}
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Analisi visiva: cascata P&L + gauge (sul totale del periodo) */}
        <div className="rounded-lg border border-border bg-card p-4 space-y-5">
          <h3 className="text-base font-semibold flex items-center gap-1.5">
            <BarChart3 className="size-4 text-primary" />
            Analisi visiva
          </h3>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 items-stretch">
            <CascataPL />
            <div className="flex flex-col divide-y divide-border">
              <GaugeRow label="Food Cost" value={periodo.food_cost_perc} track="#f97316" c={demoMarginiCommenti.food_cost} tone="amber" />
              <GaugeRow label="1° Margine" value={periodo.primo_margine_perc} track="#10b981" c={demoMarginiCommenti.primo_margine} tone="green" />
              <GaugeRow label="Costi Gestione" value={periodo.spese_gen_perc} track="#8b5cf6" c={demoMarginiCommenti.costi_gestione} tone="green" />
              <GaugeRow label="MOL" value={periodo.mol_perc} track="#22c55e" c={demoMarginiCommenti.mol} tone="amber" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function CellaValore({
  value,
  netto,
  metric,
  valueColor,
  locked,
  corrente,
}: {
  value: number;
  netto: number;
  metric?: boolean;
  valueColor?: string;
  locked?: boolean;
  corrente: boolean;
}) {
  const p = pct(value, netto);
  const borderCls = corrente ? "border-l border-r border-sky-500/50" : "border-r border-border";
  return (
    <td className={`text-right px-3 py-2 align-middle ${borderCls}`}>
      <div className={`inline-flex items-center justify-end gap-1 tabular-nums ${metric ? "font-bold" : ""} ${valueColor ?? ""}`}>
        {formatEuro(value)}
        {locked && <Lock className="size-3 opacity-30" />}
      </div>
      {p && <div className={`text-[11px] tabular-nums opacity-70 ${valueColor ?? ""}`}>{p}</div>}
    </td>
  );
}

function RigaVoce({ r }: { r: Row }) {
  const totVal = tot[r.key];
  const pTot = pct(totVal, tot.fatturato_netto);
  return (
    <tr className={`${r.sep ? "border-t-[3px] border-t-border" : "border-t border-border"} ${r.metric ? "font-semibold bg-muted/[0.04]" : ""}`}>
      <td className={`px-3 py-2 border-r border-border whitespace-nowrap ${r.metric ? `font-bold ${r.labelColor ?? ""}` : r.labelColor ?? ""}`}>
        {r.label}
      </td>
      <CellaValore value={apr[r.key]} netto={apr.fatturato_netto} metric={r.metric} valueColor={r.valueColor} locked={r.locked} corrente={false} />
      <CellaValore value={mag[r.key]} netto={mag.fatturato_netto} metric={r.metric} valueColor={r.valueColor} locked={r.locked} corrente />
      <td className="text-right px-3 py-2 tabular-nums border-l-2 border-sky-500/50 bg-sky-500/8 align-middle">
        <div className={`tabular-nums ${r.metric ? "font-bold" : ""} ${r.valueColor ?? ""}`}>{formatEuro(totVal)}</div>
        {pTot && <div className={`text-[11px] tabular-nums opacity-70 ${r.valueColor ?? ""}`}>{pTot}</div>}
      </td>
    </tr>
  );
}

function CellaMol({ mese, corrente }: { mese: DemoMeseMargini; corrente: boolean }) {
  const p = pct(mese.mol, mese.fatturato_netto);
  const borderCls = corrente ? "border-l border-r border-sky-500/50" : "border-r border-border";
  return (
    <td className={`text-right px-3 py-2.5 align-middle ${borderCls}`}>
      <div className="inline-flex items-center justify-end gap-1 tabular-nums font-bold text-emerald-600 dark:text-emerald-400">
        {formatEuro(mese.mol)}
      </div>
      {p && <div className="text-[11px] tabular-nums opacity-70 text-emerald-600 dark:text-emerald-400">{p}</div>}
    </td>
  );
}

function CascataPL() {
  const steps = [
    { label: "Fatturato Netto", value: tot.fatturato_netto, result: true, rgb: "14,165,233" },
    { label: "− Costi F&B", value: tot.costi_fb_totali, result: false, rgb: "249,115,22" },
    { label: "= 1° Margine", value: tot.primo_margine, result: true, rgb: "16,185,129" },
    { label: "− Costi Gestione", value: tot.costi_spese_totali + tot.costi_personale, result: false, rgb: "168,85,247" },
    { label: "= MOL", value: tot.mol, result: true, rgb: "16,185,129" },
  ];
  const refMax = Math.max(1, ...steps.map((s) => Math.abs(s.value)));
  return (
    <div className="flex flex-col gap-6 justify-around">
      {steps.map((s) => {
        const w = Math.min(100, (Math.abs(s.value) / refMax) * 100);
        return (
          <div key={s.label} className="flex items-center gap-3">
            <span className={`w-36 sm:w-40 shrink-0 text-base ${s.result ? "font-bold" : "text-muted-foreground"}`}>
              {s.label}
            </span>
            <div className={`flex-1 h-9 rounded overflow-hidden ${s.result ? "bg-muted/40" : "bg-muted/20"}`}>
              <div
                className="h-full rounded"
                style={{
                  width: `${w}%`,
                  backgroundColor: `rgb(${s.rgb})`,
                  opacity: s.result ? 0.95 : 0.65,
                  boxShadow: s.result ? `0 0 14px rgba(${s.rgb},0.5)` : undefined,
                }}
              />
            </div>
            <span
              className={`w-28 sm:w-32 shrink-0 text-right text-base tabular-nums ${s.result ? "font-bold" : "text-muted-foreground"}`}
              style={s.result ? { color: `rgb(${s.rgb})` } : undefined}
            >
              {formatEuro(s.value)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function GaugeRow({
  label,
  value,
  track,
  c,
  tone,
}: {
  label: string;
  value: number;
  track: string;
  c: { emoji: string; testo: string };
  tone: "green" | "amber" | "rose";
}) {
  const valueColor = tone === "green" ? "#10b981" : tone === "amber" ? "#f59e0b" : "#f43f5e";
  return (
    <div className="flex items-center gap-6 py-5">
      <Gauge value={value} track={track} valueColor={valueColor} />
      <div className="flex flex-col gap-1.5 min-w-0">
        <span className="text-base font-bold leading-tight">{c.emoji} {label}</span>
        <span className="text-sm text-muted-foreground leading-snug">{c.testo}</span>
      </div>
    </div>
  );
}

function Gauge({ value, track, valueColor }: { value: number; track: string; valueColor: string }) {
  const f = Math.max(0, Math.min(1, value / 100));
  const r = 36;
  const startDeg = 225;
  const sweepDeg = 270;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const sx = 50 + r * Math.cos(toRad(startDeg));
  const sy = 50 + r * Math.sin(toRad(startDeg));
  const endDeg = startDeg + sweepDeg;
  const ex = 50 + r * Math.cos(toRad(endDeg));
  const ey = 50 + r * Math.sin(toRad(endDeg));
  const largeArc = sweepDeg > 180 ? 1 : 0;
  const ARC = `M ${sx.toFixed(2)} ${sy.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${ex.toFixed(2)} ${ey.toFixed(2)}`;
  return (
    <svg viewBox="0 0 100 100" className="w-20 h-20 shrink-0">
      <path d={ARC} fill="none" stroke="currentColor" className="text-muted-foreground/15" strokeWidth="10" strokeLinecap="round" pathLength={100} />
      <path
        d={ARC}
        fill="none"
        stroke={track}
        strokeWidth="10"
        strokeLinecap="round"
        pathLength={100}
        strokeDasharray={`${f * 100} 100`}
        style={{ filter: f > 0.05 ? `drop-shadow(0 0 4px ${track}90)` : undefined }}
      />
      <text x="50" y="53" textAnchor="middle" dominantBaseline="middle" fontSize="18" fontWeight="bold" fill={valueColor}>
        {value}%
      </text>
    </svg>
  );
}
