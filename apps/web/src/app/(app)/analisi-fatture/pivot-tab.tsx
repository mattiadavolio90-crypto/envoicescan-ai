"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import {
  type PivotResponse,
  type TrendResponse,
} from "@/lib/fatture";
import { categoriaIcon, formatEuro, formatEuroCompact } from "./periodi";

type Props = {
  pivot: PivotResponse;
  dimensione: "categoria" | "fornitore";
  filtri: {
    data_da?: string;
    data_a?: string;
    tipo_prodotti?: string;
  };
};

const TIPO_OPTIONS = [
  { key: "tutti", label: "Tutti" },
  { key: "food_beverage", label: "Food & Beverage" },
  { key: "spese_generali", label: "Spese Generali" },
];

export function PivotTab({ pivot, dimensione, filtri }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [selectedForTrend, setSelectedForTrend] = useState<string[]>(
    pivot.rows.slice(0, 3).map((r) => r.dimensione),
  );

  function setParam(updates: Record<string, string | undefined>) {
    const params = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v === undefined || v === "") params.delete(k);
      else params.set(k, v);
    }
    router.push(`${pathname}?${params.toString()}`);
  }

  function exportXls() {
    const periodi = pivot.periodi;
    const labels = pivot.periodi_labels;
    const rows = [
      [dimensione === "categoria" ? "Categoria" : "Fornitore", ...labels, "Totale", "Media", "% sul totale"],
      ...pivot.rows.map((r) => [
        r.dimensione,
        ...periodi.map((p) => (r.periodi[p] ?? 0).toFixed(2)),
        r.totale.toFixed(2),
        r.media.toFixed(2),
        r.incidenza_pct.toFixed(1) + "%",
      ]),
      ["TOTALE", ...periodi.map((p) => (pivot.totali_periodo[p] ?? 0).toFixed(2)), pivot.grand_total.toFixed(2), "", ""],
    ];
    const csv = rows
      .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${dimensione}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const granuLabel =
    pivot.granularita === "mese"
      ? "mese"
      : pivot.granularita === "trimestre"
        ? "trimestre"
        : "anno";

  return (
    <div className="space-y-4">
      {/* Sub-filtri */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          {TIPO_OPTIONS.map((t) => (
            <button
              key={t.key}
              onClick={() => setParam({ tipo: t.key === "tutti" ? undefined : t.key })}
              className={`px-2.5 py-1 text-xs font-medium rounded-md border transition-colors ${
                (filtri.tipo_prodotti ?? "tutti") === t.key
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-background border-input hover:bg-muted"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {pivot.granularita !== "mese" && (
          <span className="text-xs text-muted-foreground">
            Visualizzazione per {granuLabel} ({pivot.periodi.length} periodi)
          </span>
        )}
        <button
          onClick={exportXls}
          className="ml-auto text-xs px-2.5 py-1 rounded-md border border-input bg-background hover:bg-muted font-medium"
        >
          Esporta CSV
        </button>
      </div>

      {pivot.rows.length === 0 ? (
        <div className="text-center py-16 text-sm text-muted-foreground">
          Nessun dato disponibile per il periodo selezionato.
        </div>
      ) : (
        <>
          <PivotTable
            pivot={pivot}
            dimensione={dimensione}
            selectedForTrend={selectedForTrend}
            onToggleSelect={(d) => {
              setSelectedForTrend((prev) =>
                prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].slice(-5),
              );
            }}
          />
          <TrendChart
            dimensione={dimensione}
            valori={selectedForTrend}
            dataDa={filtri.data_da}
            dataA={filtri.data_a}
            tipoProdotti={filtri.tipo_prodotti}
          />
        </>
      )}
    </div>
  );
}

function maxRowValue(periodi: Record<string, number>): number {
  return Math.max(...Object.values(periodi), 1);
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) {
    return <span className="text-muted-foreground text-[10px]">—</span>;
  }
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const w = 64;
  const h = 18;
  const step = w / (values.length - 1);
  const points = values
    .map((v, i) => `${i * step},${h - ((v - min) / range) * h}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="text-primary inline-block">
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        points={points}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PivotTable({
  pivot,
  dimensione,
  selectedForTrend,
  onToggleSelect,
}: {
  pivot: PivotResponse;
  dimensione: "categoria" | "fornitore";
  selectedForTrend: string[];
  onToggleSelect: (dim: string) => void;
}) {
  const labelDim = dimensione === "categoria" ? "Categoria" : "Fornitore";

  return (
    <div className="rounded-lg border overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="bg-muted/50 border-b">
          <tr>
            <th className="text-left px-3 py-2 font-medium text-muted-foreground whitespace-nowrap min-w-44">
              {labelDim}
            </th>
            <th className="text-center px-2 py-2 font-medium text-muted-foreground w-20">Trend</th>
            {pivot.periodi.map((p, idx) => (
              <th
                key={p}
                className="text-right px-2 py-2 font-medium text-muted-foreground whitespace-nowrap min-w-20"
              >
                {pivot.periodi_labels[idx]}
              </th>
            ))}
            <th className="text-right px-3 py-2 font-medium text-muted-foreground whitespace-nowrap min-w-24">
              Totale
            </th>
            <th className="text-right px-3 py-2 font-medium text-muted-foreground whitespace-nowrap min-w-16">
              %
            </th>
          </tr>
        </thead>
        <tbody>
          {pivot.rows.map((row) => {
            const rowMax = maxRowValue(row.periodi);
            const isSelected = selectedForTrend.includes(row.dimensione);
            return (
              <tr
                key={row.dimensione}
                className={`border-b hover:bg-muted/30 cursor-pointer ${
                  isSelected ? "bg-primary/5" : ""
                }`}
                onClick={() => onToggleSelect(row.dimensione)}
                title="Clicca per mostrare/nascondere nel grafico"
              >
                <td className="px-3 py-1.5">
                  <span className="inline-flex items-center gap-1.5">
                    {dimensione === "categoria" && (
                      <span className="text-base leading-none">{categoriaIcon(row.dimensione)}</span>
                    )}
                    <span className="font-medium truncate max-w-44" title={row.dimensione}>
                      {row.dimensione}
                    </span>
                  </span>
                </td>
                <td className="px-2 py-1.5 text-center">
                  <Sparkline values={row.sparkline} />
                </td>
                {pivot.periodi.map((p) => {
                  const v = row.periodi[p] ?? 0;
                  const intensity = v / rowMax;
                  const bg = intensityToBg(intensity);
                  const pct = pivot.totali_periodo[p]
                    ? ((v / pivot.totali_periodo[p]) * 100).toFixed(0)
                    : "0";
                  return (
                    <td
                      key={p}
                      className="text-right px-2 py-1.5 tabular-nums relative whitespace-nowrap"
                      style={{ backgroundColor: bg }}
                      title={`${formatEuro(v)} · ${pct}% del ${p}`}
                    >
                      {v > 0 ? formatEuroCompact(v) : <span className="text-muted-foreground">—</span>}
                    </td>
                  );
                })}
                <td className="px-3 py-1.5 text-right font-semibold tabular-nums whitespace-nowrap">
                  {formatEuro(row.totale)}
                </td>
                <td className="px-3 py-1.5 text-right font-medium tabular-nums text-muted-foreground">
                  {row.incidenza_pct.toFixed(0)}%
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot className="bg-muted border-t-2">
          <tr className="font-semibold">
            <td className="px-3 py-2 text-xs">Totale {pivot.granularita}</td>
            <td></td>
            {pivot.periodi.map((p) => (
              <td key={p} className="text-right px-2 py-2 tabular-nums whitespace-nowrap">
                {formatEuroCompact(pivot.totali_periodo[p] ?? 0)}
              </td>
            ))}
            <td className="text-right px-3 py-2 tabular-nums whitespace-nowrap">
              {formatEuro(pivot.grand_total)}
            </td>
            <td className="text-right px-3 py-2 text-muted-foreground">100%</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

// Mappa intensita 0-1 a un colore di sfondo blu sky tenue
function intensityToBg(intensity: number): string {
  if (intensity <= 0.02) return "transparent";
  const alpha = Math.min(0.35, intensity * 0.4);
  return `rgba(14, 165, 233, ${alpha.toFixed(3)})`;
}

// ─── Grafico trend ─────────────────────────────────────────────────────────

const COLORI_LINEE = ["#0ea5e9", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"];

function TrendChart({
  dimensione,
  valori,
  dataDa,
  dataA,
  tipoProdotti,
}: {
  dimensione: "categoria" | "fornitore";
  valori: string[];
  dataDa?: string;
  dataA?: string;
  tipoProdotti?: string;
}) {
  const [trend, setTrend] = useState<TrendResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (valori.length === 0) {
      setTrend(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const params = new URLSearchParams({
      dimensione,
      valori: valori.join(","),
    });
    if (dataDa) params.set("data_da", dataDa);
    if (dataA) params.set("data_a", dataA);
    if (tipoProdotti) params.set("tipo_prodotti", tipoProdotti);
    fetch(`/api/fatture/trend?${params}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled) setTrend(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dimensione, valori.join("|"), dataDa, dataA, tipoProdotti]);

  if (valori.length === 0) {
    return (
      <div className="rounded-lg border p-6 text-center text-xs text-muted-foreground">
        Seleziona una riga della tabella per visualizzare il trend (max 5 confronti)
      </div>
    );
  }

  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">Andamento nel tempo</h3>
        {loading && <Loader2 className="size-3 animate-spin text-muted-foreground" />}
      </div>
      {trend && trend.serie.length > 0 ? (
        <TrendSvg trend={trend} />
      ) : (
        <p className="text-xs text-muted-foreground text-center py-8">Caricamento...</p>
      )}
      <div className="flex flex-wrap gap-3 mt-3 justify-center">
        {trend?.serie.map((s, i) => (
          <span key={s.valore} className="inline-flex items-center gap-1.5 text-xs">
            <span
              className="inline-block w-3 h-1 rounded-sm"
              style={{ backgroundColor: COLORI_LINEE[i % COLORI_LINEE.length] }}
            />
            <span className="font-medium">{s.valore}</span>
            <span className="text-muted-foreground">· tot {formatEuroCompact(s.totale)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function TrendSvg({ trend }: { trend: TrendResponse }) {
  const W = 720;
  const H = 220;
  const PAD_L = 50;
  const PAD_R = 16;
  const PAD_T = 12;
  const PAD_B = 28;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;

  const allValues = trend.serie.flatMap((s) => s.punti.map((p) => p.valore));
  const yMax = Math.max(...allValues, 1);
  const yMin = 0;
  const periodi = trend.periodi;
  const stepX = periodi.length > 1 ? innerW / (periodi.length - 1) : 0;

  const yTicks = 4;
  const yLabels: number[] = [];
  for (let i = 0; i <= yTicks; i++) {
    yLabels.push((yMax / yTicks) * i);
  }

  function pathFor(values: number[]): string {
    return values
      .map((v, i) => {
        const x = PAD_L + i * stepX;
        const y = PAD_T + innerH - ((v - yMin) / (yMax - yMin || 1)) * innerH;
        return `${i === 0 ? "M" : "L"}${x},${y}`;
      })
      .join(" ");
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: "280px" }}>
      {/* griglia Y */}
      {yLabels.map((v, i) => {
        const y = PAD_T + innerH - (i / yTicks) * innerH;
        return (
          <g key={i}>
            <line
              x1={PAD_L}
              y1={y}
              x2={PAD_L + innerW}
              y2={y}
              stroke="currentColor"
              className="text-border"
              strokeDasharray="2,3"
              strokeWidth="0.5"
            />
            <text x={PAD_L - 6} y={y + 3} textAnchor="end" className="text-[10px] fill-muted-foreground">
              {formatEuroCompact(v)}
            </text>
          </g>
        );
      })}
      {/* assi X labels */}
      {periodi.map((p, i) => {
        // mostra label solo a inizio, fine, e ogni N
        const total = periodi.length;
        const skip = total > 12 ? Math.ceil(total / 8) : 1;
        if (i !== 0 && i !== total - 1 && i % skip !== 0) return null;
        const x = PAD_L + i * stepX;
        return (
          <text
            key={p}
            x={x}
            y={H - 8}
            textAnchor="middle"
            className="text-[10px] fill-muted-foreground"
          >
            {trend.periodi_labels[i]}
          </text>
        );
      })}
      {/* linee */}
      {trend.serie.map((s, idx) => (
        <g key={s.valore}>
          <path
            d={pathFor(s.punti.map((p) => p.valore))}
            fill="none"
            stroke={COLORI_LINEE[idx % COLORI_LINEE.length]}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {s.punti.map((p, i) => {
            const x = PAD_L + i * stepX;
            const y = PAD_T + innerH - ((p.valore - yMin) / (yMax - yMin || 1)) * innerH;
            return (
              <circle
                key={i}
                cx={x}
                cy={y}
                r="2.5"
                fill={COLORI_LINEE[idx % COLORI_LINEE.length]}
              >
                <title>{`${s.valore} · ${p.label}: ${formatEuro(p.valore)}`}</title>
              </circle>
            );
          })}
        </g>
      ))}
    </svg>
  );
}
