"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronUp, RefreshCw, TrendingUp, PieChart as PieChartIcon, BarChart3 } from "lucide-react";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { toast } from "sonner";
import { formatEuro, formatEuroCompact, formatPct } from "./periodi";

type CategoriaDetail = {
  categoria: string;
  costo: number;
  pct_su_centro: number;
};

type CentroDetailItem = {
  centro: string;
  icona: string;
  categorie_def: string[];
  categorie_dettaglio: CategoriaDetail[];
  costo_totale: number;
  fatturato: number;
  margine: number;
  margine_pct: number;
  incidenza_su_fatt: number;
  incidenza_su_fb: number;
  has_fatturato: boolean;
};

type AndamentoMese = {
  anno: number;
  mese: number;
  label: string;
  food: number;
  beverage: number;
  alcolici: number;
  dolci: number;
  shop: number;
};

type Commento = {
  kpi_nome: string;
  percentuale: string;
  commento: string;
  emoji: string;
  colore: string;
};

type AnalisiAvanzataResponse = {
  centri: CentroDetailItem[];
  andamento_mensile: AndamentoMese[];
  commenti: Commento[];
  totale_costi_fb: number;
  fatturato_netto_periodo: number;
  fatturato_per_centro_totale: number;
  primo_margine: number;
  primo_margine_pct: number;
  fatturato_split_attivo: boolean;
  mesi_con_dati: number[];
};

const CENTRO_COLOR: Record<string, string> = {
  FOOD: "#f97316",
  BEVERAGE: "#0ea5e9",
  ALCOLICI: "#a855f7",
  DOLCI: "#ec4899",
  SHOP: "#64748b",
};

type Props = {
  dataDa: string;
  dataA: string;
};

export function AnalisiTab({ dataDa, dataA }: Props) {
  const [data, setData] = useState<AnalisiAvanzataResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [chartMode, setChartMode] = useState<"euro" | "perc">("euro");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/margini/analisi-avanzata?${new URLSearchParams({ data_da: dataDa, data_a: dataA })}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error();
      const d: AnalisiAvanzataResponse = await res.json();
      setData(d);
    } catch {
      toast.error("Errore nel caricamento analisi");
    } finally {
      setLoading(false);
    }
  }, [dataDa, dataA]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
        Caricamento analisi…
      </div>
    );
  }

  if (!data || (data.totale_costi_fb === 0 && data.fatturato_netto_periodo === 0)) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center space-y-2">
        <p className="text-sm font-medium">Nessun dato analizzabile nel periodo</p>
        <p className="text-xs text-muted-foreground">
          Carica fatture e inserisci ricavi per popolare l'analisi per centri.
        </p>
      </div>
    );
  }

  const centriConCosto = data.centri.filter((c) => c.costo_totale > 0);

  return (
    <div className="space-y-5">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md border border-border hover:bg-muted disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`size-3 ${loading ? "animate-spin" : ""}`} />
          Aggiorna
        </button>
        {!data.fatturato_split_attivo && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            ⚠️ Nessuna ripartizione fatturato per centro: imposta i valori nel tab Ricavi
          </p>
        )}
      </div>

      {/* KPI cards di periodo */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <KpiMini
          label="Fatturato Periodo"
          value={formatEuroCompact(data.fatturato_netto_periodo)}
          tone="primary"
        />
        <KpiMini
          label="Costi F&B"
          value={formatEuroCompact(data.totale_costi_fb)}
          tone="default"
        />
        <KpiMini
          label="1° Margine"
          value={formatEuroCompact(data.primo_margine)}
          tone={data.primo_margine >= 0 ? "positive" : "negative"}
        />
        <KpiMini
          label="1° Margine %"
          value={formatPct(data.primo_margine_pct)}
          tone={data.primo_margine_pct >= 62 ? "positive" : data.primo_margine_pct >= 55 ? "default" : "negative"}
        />
      </div>

      {/* Grid: DonutChart Centri + LineChart Andamento */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* DonutChart Costi per Centro */}
        <div className="lg:col-span-2 rounded-lg border border-border bg-card p-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
            <PieChartIcon className="size-4 text-primary" />
            Distribuzione Costi per Centro
          </h3>
          <CentriDonutChart centri={centriConCosto} />
        </div>

        {/* LineChart Andamento */}
        <div className="lg:col-span-3 rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold flex items-center gap-1.5">
              <TrendingUp className="size-4 text-primary" />
              Andamento mensile per Centro
            </h3>
            <div className="flex rounded-md border border-input overflow-hidden text-xs">
              <button
                onClick={() => setChartMode("euro")}
                className={`px-2 py-0.5 ${chartMode === "euro" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
              >€</button>
              <button
                onClick={() => setChartMode("perc")}
                disabled={!data.fatturato_split_attivo}
                className={`px-2 py-0.5 border-l border-input disabled:opacity-50 ${chartMode === "perc" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
              >%</button>
            </div>
          </div>
          <AndamentoLineChart
            andamento={data.andamento_mensile}
            centri={centriConCosto}
            mode={chartMode}
          />
        </div>
      </div>

      {/* Cards Performance per Centro */}
      {centriConCosto.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold flex items-center gap-1.5">
            <BarChart3 className="size-4 text-primary" />
            Performance per Centro
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {centriConCosto
              .filter((c) => c.has_fatturato)
              .map((c) => (
                <CentroPerformanceCard key={c.centro} centro={c} andamento={data.andamento_mensile} />
              ))}
          </div>
        </div>
      )}

      {/* Tabella espandibile per Centri */}
      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="text-sm font-semibold">Dettaglio Centri / Categorie</h3>
        </div>
        <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[560px]">
          <thead className="bg-muted/40">
            <tr className="text-[10px] uppercase tracking-wider text-muted-foreground">
              <th className="text-left px-3 py-2 font-medium w-1/3">Centro / Categoria</th>
              <th className="text-right px-3 py-2 font-medium">Fatturato</th>
              <th className="text-right px-3 py-2 font-medium">Costo F&B</th>
              <th className="text-right px-3 py-2 font-medium">% su Fatt.</th>
              <th className="text-right px-3 py-2 font-medium">Margine</th>
              <th className="text-right px-3 py-2 font-medium">% su F&B Tot</th>
            </tr>
          </thead>
          <tbody>
            {centriConCosto.map((c) => (
              <CentroRow key={c.centro} centro={c} />
            ))}
            {/* Riga totale */}
            <tr className="bg-emerald-500/10 font-bold text-emerald-700 dark:text-emerald-300 border-t-2 border-emerald-500/40">
              <td className="px-3 py-2">TOTALE (1° Margine)</td>
              <td className="text-right px-3 py-2 tabular-nums">{formatEuro(data.fatturato_netto_periodo)}</td>
              <td className="text-right px-3 py-2 tabular-nums">{formatEuro(data.totale_costi_fb)}</td>
              <td className="text-right px-3 py-2 tabular-nums">
                {data.fatturato_netto_periodo > 0
                  ? formatPct((data.totale_costi_fb / data.fatturato_netto_periodo) * 100)
                  : "—"}
              </td>
              <td className={`text-right px-3 py-2 tabular-nums ${data.primo_margine >= 0 ? "text-emerald-700 dark:text-emerald-300" : "text-rose-700 dark:text-rose-400"}`}>
                {formatEuro(data.primo_margine)}
              </td>
              <td className="text-right px-3 py-2 tabular-nums">100%</td>
            </tr>
          </tbody>
        </table>
        </div>
      </div>

      {/* Commenti automatici */}
      {data.commenti.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">💬 Analisi automatica per centro</h3>
          <div className="space-y-1.5">
            {data.commenti.map((c, i) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-md border border-border bg-card p-3"
                style={{ borderLeftWidth: 4, borderLeftColor: c.colore }}
              >
                <span className="text-base font-bold shrink-0" style={{ color: c.colore }}>
                  {c.emoji} {c.percentuale}
                </span>
                <div className="text-sm">
                  <strong>{c.kpi_nome}</strong>
                  <span className="text-muted-foreground"> · {c.commento}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================ */
function KpiMini({
  label, value, tone,
}: {
  label: string;
  value: string;
  tone: "primary" | "positive" | "negative" | "default";
}) {
  const cls =
    tone === "primary" ? "border-primary/30 bg-primary/5 text-primary"
    : tone === "positive" ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
    : tone === "negative" ? "border-rose-500/30 bg-rose-500/5 text-rose-700 dark:text-rose-400"
    : "border-border bg-card";
  return (
    <div className={`rounded-lg border p-3 ${cls}`}>
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <p className="text-lg font-bold mt-0.5 leading-tight">{value}</p>
    </div>
  );
}

/* ============================================================ */
function CentriDonutChart({ centri }: { centri: CentroDetailItem[] }) {
  const data = centri.map((c) => ({
    name: c.centro,
    value: c.costo_totale,
    fill: CENTRO_COLOR[c.centro] ?? "#94a3b8",
  }));
  if (data.length === 0) return <p className="text-sm text-muted-foreground py-8 text-center">Nessun costo nel periodo</p>;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie data={data} cx="50%" cy="50%" innerRadius={55} outerRadius={85} dataKey="value" stroke="hsl(var(--card))" strokeWidth={2}>
          {data.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
        </Pie>
        <Tooltip formatter={(v: unknown) => formatEuro(typeof v === "number" ? v : 0)}
                 contentStyle={{ fontSize: 11, borderRadius: 6 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" />
      </PieChart>
    </ResponsiveContainer>
  );
}

/* ============================================================ */
function AndamentoLineChart({
  andamento,
  centri,
  mode,
}: {
  andamento: AndamentoMese[];
  centri: CentroDetailItem[];
  mode: "euro" | "perc";
}) {
  const centriAttivi = centri
    .filter((c) => c.costo_totale > 0)
    .map((c) => c.centro);

  const data = andamento.map((m) => {
    const out: Record<string, number | string> = { label: m.label };
    for (const centro of centriAttivi) {
      const key = centro.toLowerCase() as keyof AndamentoMese;
      const v = (m[key] as number) ?? 0;
      if (mode === "perc") {
        const total = m.food + m.beverage + m.alcolici + m.dolci + m.shop;
        out[centro] = total > 0 ? (v / total) * 100 : 0;
      } else {
        out[centro] = v;
      }
    }
    return out;
  });

  if (data.length === 0 || centriAttivi.length === 0) {
    return <p className="text-sm text-muted-foreground py-8 text-center">Dati insufficienti</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} />
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
               tickLine={false} axisLine={false} />
        <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
               tickLine={false} axisLine={false}
               tickFormatter={(v: number) => mode === "perc" ? `${v.toFixed(0)}%` : formatEuroCompact(v)} />
        <Tooltip
          formatter={(value: unknown) => {
            const v = typeof value === "number" ? value : 0;
            return mode === "perc" ? `${v.toFixed(1)}%` : formatEuro(v);
          }}
          contentStyle={{ fontSize: 11, borderRadius: 6 }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" />
        {centriAttivi.map((centro) => (
          <Line
            key={centro}
            type="monotone"
            dataKey={centro}
            stroke={CENTRO_COLOR[centro] ?? "#94a3b8"}
            strokeWidth={2}
            dot={{ r: 3 }}
            name={centro}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

/* ============================================================ */
function CentroPerformanceCard({
  centro,
  andamento,
}: {
  centro: CentroDetailItem;
  andamento: AndamentoMese[];
}) {
  const fc = centro.incidenza_su_fatt;
  const tone =
    fc <= 28 ? { color: "text-emerald-600 dark:text-emerald-400", emoji: "🟢", border: "border-emerald-500/40" }
    : fc <= 33 ? { color: "text-yellow-600 dark:text-yellow-400", emoji: "🟡", border: "border-yellow-500/40" }
    : fc <= 38 ? { color: "text-orange-600 dark:text-orange-400", emoji: "🟠", border: "border-orange-500/40" }
    : { color: "text-rose-600 dark:text-rose-400", emoji: "🔴", border: "border-rose-500/40" };

  const key = centro.centro.toLowerCase() as keyof AndamentoMese;
  const sparklinePts = andamento.map((m) => (m[key] as number) ?? 0);
  const maxV = Math.max(...sparklinePts, 1);

  return (
    <div className={`rounded-lg border ${tone.border} bg-card p-3`}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-semibold flex items-center gap-1">
          <span className="text-base">{centro.icona}</span>
          {centro.centro}
        </span>
        <span className="text-base">{tone.emoji}</span>
      </div>
      <p className={`text-2xl font-bold tabular-nums ${tone.color}`}>{fc.toFixed(1)}%</p>
      <p className="text-[10px] text-muted-foreground">incidenza costi su fatturato</p>
      {/* Sparkline */}
      <div className="mt-2 flex items-end gap-0.5 h-8">
        {sparklinePts.map((v, i) => (
          <div
            key={i}
            className="flex-1 rounded-sm"
            style={{
              height: `${Math.max(2, (v / maxV) * 100)}%`,
              backgroundColor: CENTRO_COLOR[centro.centro] ?? "#94a3b8",
              opacity: 0.7,
            }}
            title={`${andamento[i]?.label}: ${formatEuro(v)}`}
          />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-1 mt-2 text-[10px]">
        <div>
          <p className="text-muted-foreground">Costo</p>
          <p className="font-semibold">{formatEuroCompact(centro.costo_totale)}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Margine</p>
          <p className={`font-semibold ${centro.margine >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
            {formatEuroCompact(centro.margine)}
          </p>
        </div>
      </div>
    </div>
  );
}

/* ============================================================ */
function CentroRow({ centro }: { centro: CentroDetailItem }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <tr
        className="border-t border-border hover:bg-muted/20 transition-colors cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="px-3 py-2 font-semibold whitespace-nowrap">
          <span className="inline-flex items-center gap-1.5">
            {expanded ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
            <span className="text-base">{centro.icona}</span>
            <span style={{ color: CENTRO_COLOR[centro.centro] }}>{centro.centro}</span>
          </span>
        </td>
        <td className="text-right px-3 py-2 tabular-nums">
          {centro.has_fatturato ? formatEuro(centro.fatturato) : "—"}
        </td>
        <td className="text-right px-3 py-2 tabular-nums font-medium">{formatEuro(centro.costo_totale)}</td>
        <td className="text-right px-3 py-2">
          <PercBar value={centro.incidenza_su_fatt} color={CENTRO_COLOR[centro.centro] ?? "#94a3b8"} />
        </td>
        <td className="text-right px-3 py-2 tabular-nums">
          {centro.has_fatturato ? (
            <span className={centro.margine >= 0 ? "text-emerald-600 dark:text-emerald-400 font-semibold" : "text-rose-600 dark:text-rose-400 font-semibold"}>
              {formatEuro(centro.margine)} ({centro.margine_pct.toFixed(1)}%)
            </span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </td>
        <td className="text-right px-3 py-2 tabular-nums">
          <PercBar value={centro.incidenza_su_fb} color="#f97316" />
        </td>
      </tr>
      {expanded && centro.categorie_dettaglio.length > 0 && (
        <tr className="bg-muted/10">
          <td colSpan={6} className="px-3 py-2">
            <table className="w-full text-xs">
              <tbody>
                {centro.categorie_dettaglio.map((cat) => (
                  <tr key={cat.categoria} className="border-b border-border/50 last:border-b-0">
                    <td className="py-1 pl-7 text-muted-foreground">{cat.categoria}</td>
                    <td className="text-right tabular-nums py-1">{formatEuro(cat.costo)}</td>
                    <td className="text-right py-1 w-32">
                      <PercBar value={cat.pct_su_centro} color={CENTRO_COLOR[centro.centro] ?? "#94a3b8"} small />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}

function PercBar({ value, color, small = false }: { value: number; color: string; small?: boolean }) {
  const width = Math.min(100, Math.max(0, value));
  return (
    <div className="inline-flex items-center gap-1.5">
      <div className={`bg-muted rounded-full overflow-hidden ${small ? "h-1.5 w-16" : "h-2 w-20"}`}>
        <div
          className="h-full rounded-full"
          style={{ width: `${width}%`, backgroundColor: color }}
        />
      </div>
      <span className="tabular-nums text-xs font-medium">{value.toFixed(1)}%</span>
    </div>
  );
}
