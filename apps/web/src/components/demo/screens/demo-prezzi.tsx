"use client";

import { ChevronDown, Search, TriangleAlert, Star } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import type { VariazionePrezzo } from "@/lib/prezzi";
import { demoPrezziKpi, demoVariazioni } from "@/lib/demo-data";
import { DemoAnchor } from "../demo-anchor";

// Osservatorio (Prezzi) del Demo Tour: replica STATICA del tab Variazioni.
// I KPI di sintesi + la lista di AlertCard (dal vero variazioni-tab.tsx), senza
// filtri/fetch/espansione. Lo spotlight punta la card del salmone (+16%).

function fmtPct(v: number): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}
function fmtEuro(v: number, withSign = false): string {
  const sign = withSign && v > 0 ? "+" : v < 0 ? "-" : "";
  return `${sign}€ ${new Intl.NumberFormat("it-IT", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(v))}`;
}
function fmtData(s: string): string {
  const d = new Date(s);
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

type Gravita = "critico" | "alto" | "medio";
function gravita(r: VariazionePrezzo): Gravita {
  const imp = Math.abs(r.impatto_stimato);
  if (imp >= 100) return "critico";
  if (imp >= 30) return "alto";
  return "medio";
}
const GRAVITA_STYLE: Record<Gravita, { dot: string; ring: string }> = {
  critico: { dot: "bg-rose-500", ring: "border-l-rose-500" },
  alto: { dot: "bg-orange-500", ring: "border-l-orange-500" },
  medio: { dot: "bg-amber-400", ring: "border-l-amber-400" },
};

function parseStorico(s: string): number[] {
  return s
    .split("→")
    .map((p) => parseFloat(p.replace(/[€\s]/g, "").replace(",", ".")))
    .filter((n) => !isNaN(n));
}

function Sparkline({ values, rialzo }: { values: number[]; rialzo: boolean }) {
  if (values.length < 2) return <div className="h-8 w-24" />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const w = 96;
  const h = 32;
  const step = w / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(h - ((v - min) / range) * h).toFixed(1)}`)
    .join(" ");
  const stroke = rialzo ? "rgb(244 63 94)" : "rgb(16 185 129)";
  return (
    <svg width={w} height={h} className="overflow-visible shrink-0">
      <polyline points={points} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      {values.map((v, i) => (
        <circle
          key={i}
          cx={(i * step).toFixed(1)}
          cy={(h - ((v - min) / range) * h).toFixed(1)}
          r={i === values.length - 1 ? 2.5 : 1.5}
          fill={i === values.length - 1 ? stroke : "rgb(148 163 184)"}
        />
      ))}
    </svg>
  );
}

function AlertCard({ r }: { r: VariazionePrezzo }) {
  const style = GRAVITA_STYLE[gravita(r)];
  const rialzo = r.aumento_perc > 0;
  const spark = parseStorico(r.storico);
  return (
    <div className={`rounded-lg border border-l-4 ${style.ring} border-border bg-card overflow-hidden`}>
      <div className="w-full text-left px-4 py-3">
        <div className="flex items-center gap-3 flex-wrap">
          <Star className={`size-4 shrink-0 ${r.preferito ? "fill-amber-400 text-amber-400" : "text-muted-foreground/50"}`} />
          <span className={`size-2.5 rounded-full ${style.dot} shrink-0`} aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-sm truncate">{r.prodotto}</p>
            <p className="text-xs text-muted-foreground truncate">
              {r.fornitore} · {r.categoria} · {fmtData(r.data)}
            </p>
          </div>
          <div className="text-right shrink-0">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Media periodo</p>
            <p className="text-xs tabular-nums text-muted-foreground">€{r.media.toFixed(2)}</p>
          </div>
          <div className="text-right shrink-0">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Penultimo</p>
            <p className="text-xs tabular-nums text-muted-foreground">€{r.penultimo.toFixed(2)}</p>
          </div>
          <div className="text-right shrink-0">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Ultimo</p>
            <p className="text-xs font-bold tabular-nums text-foreground">€{r.ultimo.toFixed(2)}</p>
            <p className={`text-lg font-bold leading-tight ${rialzo ? "text-rose-600" : "text-emerald-600"}`}>
              {fmtPct(r.aumento_perc)}
            </p>
          </div>
          <Sparkline values={spark} rialzo={rialzo} />
          <div className="text-right shrink-0 w-28">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Impatto/mese</p>
            <p className={`text-sm font-semibold ${r.impatto_stimato > 0 ? "text-rose-600" : r.impatto_stimato < 0 ? "text-emerald-600" : "text-muted-foreground"}`}>
              {r.impatto_stimato !== 0 ? fmtEuro(r.impatto_stimato, true) : "—"}
            </p>
          </div>
          <ChevronDown className="size-4 text-muted-foreground shrink-0" />
        </div>
      </div>
    </div>
  );
}

type KpiTone = "sky" | "emerald" | "rose";
const KPI_TONE: Record<KpiTone, { border: string; value: string }> = {
  sky: { border: "border-sky-500/40", value: "text-sky-600 dark:text-sky-400" },
  emerald: { border: "border-emerald-500/40", value: "text-emerald-600 dark:text-emerald-400" },
  rose: { border: "border-rose-500/40", value: "text-rose-600 dark:text-rose-400" },
};
function KpiCard({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: KpiTone }) {
  const t = KPI_TONE[tone];
  return (
    <div className={`rounded-xl border ${t.border} bg-card px-4 py-3 flex flex-col gap-1`}>
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium leading-none">{label}</span>
      <span className={`text-2xl font-bold tracking-tight leading-tight ${t.value}`}>{value}</span>
      <span className="text-[11px] text-muted-foreground leading-tight truncate">{sub}</span>
    </div>
  );
}

export function DemoPrezzi() {
  const k = demoPrezziKpi;
  return (
    <div className="space-y-4">
      <PageHeader
        icon="search"
        title="Osservatorio"
        hint="Variazioni e anomalie sui tuoi fornitori"
        subtitle="Come cambiano i prezzi d'acquisto nel tempo, con l'impatto reale in euro al mese."
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Rincari medi" value={fmtPct(k.rincaro_medio)} sub={`${k.n_rincari} prodotti in aumento`} tone="rose" />
        <KpiCard label="Risparmi medi" value={fmtPct(k.risparmio_medio)} sub={`${k.n_risparmi} prodotto in calo`} tone="emerald" />
        <KpiCard label="Scostamento medio" value={fmtPct(k.scostamento_medio)} sub="su 4 variazioni" tone="rose" />
        <KpiCard label="Impatto stimato/mese" value={fmtEuro(k.impatto_stimato, true)} sub="effetto sui costi mensili" tone="rose" />
      </div>

      {/* Filtri di secondo livello (veste inerte, come il tab reale): il toggle
          Tutti/Preferiti spiega la ⭐ sulle card — nella vista "Tutti" i prodotti
          seguiti e non seguiti convivono, con la stellina a distinguerli. */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="inline-flex rounded-full border border-border p-0.5 bg-background">
          <span className="px-3 py-1 text-xs font-medium rounded-full bg-primary text-primary-foreground">
            Tutti
          </span>
          <span className="inline-flex items-center gap-1 px-3 py-1 text-xs font-medium rounded-full text-muted-foreground">
            <Star className="size-3 fill-amber-400 text-amber-400" />
            Preferiti (1)
          </span>
        </div>
        <div className="relative">
          <Search className="size-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
          <div className="rounded-md border border-border pl-9 pr-3 py-1.5 text-sm bg-background w-52 text-muted-foreground">
            Cerca prodotto…
          </div>
        </div>
        <span className="rounded-md border border-border px-2 py-1.5 text-sm bg-background text-muted-foreground">
          Tutte le categorie
        </span>
        <span className="rounded-md border border-border px-2 py-1.5 text-sm bg-background text-muted-foreground">
          Tutti i fornitori
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <TriangleAlert className="size-4 text-rose-500 shrink-0" />
        <p className="text-sm font-semibold">
          {demoVariazioni.length} variazioni <span className="text-rose-600">· 1 critica</span>
        </p>
        <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-rose-500 shrink-0" />Critico</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-orange-500 shrink-0" />Alto</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-amber-400 shrink-0" />Medio</span>
        </div>
      </div>

      <div className="space-y-2">
        {demoVariazioni.map((r) => {
          const isSalmone = r.prodotto.startsWith("Salmone");
          const card = <AlertCard r={r} />;
          return isSalmone ? (
            <DemoAnchor key={r.prodotto} id="variazione-salmone" inert={false}>
              {card}
            </DemoAnchor>
          ) : (
            <div key={r.prodotto}>{card}</div>
          );
        })}
      </div>
    </div>
  );
}
