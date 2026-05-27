"use client";

import { useState } from "react";
import { RefreshCw, Save, TrendingUp, TrendingDown } from "lucide-react";
import { toast } from "sonner";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { VariazioniResponse, VariazionePrezzo, StoricoPrezzoResponse } from "@/lib/prezzi";

const ANNO_CORRENTE = new Date().getFullYear();

function isoDateRange(anno: number): { data_da: string; data_a: string } {
  return { data_da: `${anno}-01-01`, data_a: `${anno}-12-31` };
}

function fmtEuro(v: number): string {
  if (v === 0) return "—";
  const sign = v < 0 ? "-" : "";
  return `${sign}€ ${new Intl.NumberFormat("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
    Math.abs(v),
  )}`;
}

function fmtPct(v: number): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

function fmtData(s: string): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

function pctColor(v: number): string {
  if (v > 0) return "text-rose-600";
  if (v < 0) return "text-emerald-600";
  return "text-muted-foreground";
}

type ChartPoint = { data: string; var_pct: number; prezzo: number; label: string };

function PrezzoChart({
  storico,
  media,
}: {
  storico: StoricoPrezzoResponse;
  media: number;
}) {
  if (storico.punti.length < 2) {
    return (
      <p className="text-sm text-muted-foreground py-6 text-center">
        Dati insufficienti per disegnare il grafico (servono almeno 2 acquisti)
      </p>
    );
  }

  const chartData: ChartPoint[] = storico.punti.map((p) => ({
    data: fmtData(p.data),
    prezzo: p.prezzo_unitario,
    var_pct: media > 0 ? Math.round(((p.prezzo_unitario - media) / media) * 1000) / 10 : 0,
    label: `€${p.prezzo_unitario.toFixed(2)}`,
  }));

  const maxAbs = Math.max(...chartData.map((d) => Math.abs(d.var_pct)), 1);
  const domain: [number, number] = [-Math.ceil(maxAbs * 1.2), Math.ceil(maxAbs * 1.2)];

  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">
        Media storica: <span className="font-semibold text-foreground">€{media.toFixed(2)}</span> — variazione %
        rispetto alla media
      </p>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
          <XAxis
            dataKey="data"
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            domain={domain}
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v}%`}
          />
          <Tooltip
            formatter={(value, _name, props) => {
              const v = typeof value === "number" ? value : 0;
              const payload = props.payload as ChartPoint | undefined;
              return [`${v > 0 ? "+" : ""}${v.toFixed(1)}% (${payload?.label ?? ""})`, "Variazione"];
            }}
            labelStyle={{ fontSize: 11 }}
            contentStyle={{ fontSize: 11 }}
          />
          <ReferenceLine y={0} stroke="hsl(var(--destructive))" strokeDasharray="4 4" strokeWidth={1.5} />
          <Line
            type="monotone"
            dataKey="var_pct"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={{ r: 3, fill: "hsl(var(--primary))" }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function VariazioniTab({ initialSoglia }: { initialSoglia: number }) {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [soglia, setSoglia] = useState(initialSoglia);
  const [sogliaInput, setSogliaInput] = useState(String(initialSoglia));
  const [savingSoglia, setSavingSoglia] = useState(false);
  const [data, setData] = useState<VariazioniResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedRow, setSelectedRow] = useState<VariazionePrezzo | null>(null);
  const [storico, setStorico] = useState<StoricoPrezzoResponse | null>(null);
  const [storicoLoading, setStoricoLoading] = useState(false);
  const [search, setSearch] = useState("");

  async function saveSoglia() {
    const val = parseFloat(sogliaInput.replace(",", ".")) || 5;
    setSavingSoglia(true);
    try {
      const res = await fetch("/api/prezzi/soglia-alert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ soglia: val }),
      });
      if (!res.ok) throw new Error();
      setSoglia(val);
      toast.success(`Soglia alert salvata: ${val}%`);
    } catch {
      toast.error("Errore nel salvataggio soglia");
    } finally {
      setSavingSoglia(false);
    }
  }

  async function load() {
    setLoading(true);
    setSelectedRow(null);
    setStorico(null);
    try {
      const { data_da, data_a } = isoDateRange(anno);
      const qs = new URLSearchParams({ data_da, data_a, soglia: String(soglia) });
      const res = await fetch(`/api/prezzi/variazioni?${qs}`);
      if (!res.ok) throw new Error();
      setData(await res.json());
    } catch {
      toast.error("Errore nel caricamento variazioni");
    } finally {
      setLoading(false);
    }
  }

  async function loadStorico(row: VariazionePrezzo) {
    setSelectedRow(row);
    setStoricoLoading(true);
    setStorico(null);
    try {
      const qs = new URLSearchParams({ prodotto: row.prodotto, fornitore: row.fornitore });
      const res = await fetch(`/api/prezzi/storico-prodotto?${qs}`);
      if (!res.ok) throw new Error();
      setStorico(await res.json());
    } catch {
      toast.error("Errore nel caricamento storico");
    } finally {
      setStoricoLoading(false);
    }
  }

  const variazioni = data?.variazioni ?? [];
  const filtered = search
    ? variazioni.filter(
        (r) =>
          r.prodotto.toLowerCase().includes(search.toLowerCase()) ||
          r.fornitore.toLowerCase().includes(search.toLowerCase()),
      )
    : variazioni;

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground">Anno</label>
          <select
            value={anno}
            onChange={(e) => setAnno(Number(e.target.value))}
            className="rounded border border-border px-2 py-1 text-sm bg-background"
          >
            {Array.from({ length: 5 }, (_, i) => ANNO_CORRENTE - i).map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground">Soglia %</label>
          <input
            type="number"
            min="0"
            max="50"
            step="0.5"
            value={sogliaInput}
            onChange={(e) => setSogliaInput(e.target.value)}
            className="w-20 rounded border border-border px-2 py-1 text-sm bg-background text-right"
          />
          <button
            onClick={saveSoglia}
            disabled={savingSoglia}
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md border border-border hover:bg-muted disabled:opacity-50 transition-colors"
          >
            <Save className="size-3" />
            {savingSoglia ? "…" : "Salva"}
          </button>
        </div>

        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          Carica Variazioni
        </button>
      </div>

      <p className="text-xs text-muted-foreground">
        Mostra le variazioni di prezzo (rispetto all'acquisto precedente) con scostamento assoluto ≥{" "}
        <span className="font-medium text-foreground">{soglia}%</span>. Clicca una riga per vedere lo storico prezzi.
      </p>

      {/* KPI */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            {
              label: "Alert attivi",
              value: String(variazioni.length),
              color: variazioni.length > 0 ? "text-rose-600" : "",
            },
            {
              label: "Scostamento medio",
              value: fmtPct(data.scostamento_medio),
              color: pctColor(data.scostamento_medio),
            },
            {
              label: "Impatto stimato",
              value: fmtEuro(data.impatto_netto),
              color: data.impatto_netto > 0 ? "text-rose-600" : data.impatto_netto < 0 ? "text-emerald-600" : "",
            },
            { label: "Fornitori coinvolti", value: String(data.fornitori_coinvolti), color: "" },
          ].map((k) => (
            <div key={k.label} className="rounded-md border border-border p-3 bg-card">
              <p className="text-xs text-muted-foreground">{k.label}</p>
              <p className={`text-base font-bold mt-0.5 ${k.color}`}>{k.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Alert table */}
      {data && variazioni.length === 0 && (
        <p className="text-sm text-muted-foreground py-8 text-center">
          ✅ Nessuna variazione rilevata sopra la soglia {soglia}%
        </p>
      )}

      {variazioni.length > 0 && (
        <>
          <input
            type="text"
            placeholder="Cerca prodotto o fornitore…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full max-w-sm rounded-md border border-border px-3 py-1.5 text-sm bg-background"
          />

          <div className="overflow-x-auto rounded-md border border-border">
            <table className="min-w-max text-xs border-collapse">
              <thead>
                <tr className="bg-muted/60">
                  {[
                    "Prodotto", "Cat.", "Fornitore", "Storico (ultimi 5)",
                    "Media", "Ultimo", "Var. %", "Imp. €/mese", "Data", "Trend",
                  ].map((h) => (
                    <th key={h} className="text-left px-3 py-2 font-semibold border-r last:border-r-0 border-border whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => {
                  const isSelected = selectedRow?.prodotto === r.prodotto && selectedRow?.fornitore === r.fornitore;
                  return (
                    <tr
                      key={i}
                      onClick={() => loadStorico(r)}
                      className={`border-t border-border cursor-pointer transition-colors ${
                        isSelected
                          ? "bg-sky-50 dark:bg-sky-950/20"
                          : "hover:bg-muted/20"
                      }`}
                    >
                      <td className="px-3 py-2 border-r border-border font-medium whitespace-nowrap max-w-[180px] truncate">
                        {r.prodotto}
                      </td>
                      <td className="px-3 py-2 border-r border-border text-muted-foreground max-w-[100px] truncate">
                        {r.categoria}
                      </td>
                      <td className="px-3 py-2 border-r border-border whitespace-nowrap">{r.fornitore}</td>
                      <td className="px-3 py-2 border-r border-border text-muted-foreground font-mono text-[10px] whitespace-nowrap">
                        {r.storico}
                      </td>
                      <td className="px-3 py-2 border-r border-border text-right">€{r.media.toFixed(2)}</td>
                      <td className="px-3 py-2 border-r border-border text-right font-semibold">
                        €{r.ultimo.toFixed(2)}
                      </td>
                      <td className={`px-3 py-2 border-r border-border text-right font-semibold ${pctColor(r.aumento_perc)}`}>
                        {fmtPct(r.aumento_perc)}
                      </td>
                      <td
                        className={`px-3 py-2 border-r border-border text-right ${
                          r.impatto_stimato > 0 ? "text-rose-600" : r.impatto_stimato < 0 ? "text-emerald-600" : ""
                        }`}
                      >
                        {fmtEuro(r.impatto_stimato)}
                      </td>
                      <td className="px-3 py-2 border-r border-border whitespace-nowrap">{fmtData(r.data)}</td>
                      <td className="px-3 py-2 text-center">{r.trend}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Storico grafico */}
      {selectedRow && (
        <div className="rounded-md border border-border p-4 space-y-2">
          <div className="flex items-center gap-2">
            <TrendingUp className="size-4 text-primary" />
            <h3 className="text-sm font-semibold">
              Storico prezzi — {selectedRow.prodotto}{" "}
              <span className="font-normal text-muted-foreground">({selectedRow.fornitore})</span>
            </h3>
          </div>
          {storicoLoading ? (
            <div className="h-24 flex items-center justify-center text-sm text-muted-foreground">
              Caricamento…
            </div>
          ) : storico && storico.punti.length > 0 ? (
            <PrezzoChart storico={storico} media={storico.prezzo_medio} />
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Nessun dato storico disponibile per questo prodotto
            </p>
          )}
        </div>
      )}
    </div>
  );
}
