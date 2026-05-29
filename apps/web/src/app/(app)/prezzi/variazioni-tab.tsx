"use client";

import { useState, useEffect, useCallback } from "react";
import { RefreshCw, Save, ChevronDown, Search, TriangleAlert, CheckCircle2 } from "lucide-react";
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
const MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

function isoDateRange(anno: number, mese: number | null): { data_da: string; data_a: string } {
  if (mese === null) return { data_da: `${anno}-01-01`, data_a: `${anno}-12-31` };
  const lastDay = new Date(anno, mese, 0).getDate();
  const mm = String(mese).padStart(2, "0");
  return { data_da: `${anno}-${mm}-01`, data_a: `${anno}-${mm}-${lastDay}` };
}

function fmtEuro(v: number, withSign = false): string {
  const sign = withSign && v > 0 ? "+" : v < 0 ? "-" : "";
  return `${sign}€ ${new Intl.NumberFormat("it-IT", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(v))}`;
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

type Gravita = "critico" | "alto" | "medio";

function gravita(r: VariazionePrezzo): Gravita {
  const imp = Math.abs(r.impatto_stimato);
  if (imp >= 100) return "critico";
  if (imp >= 30) return "alto";
  return "medio";
}

const GRAVITA_STYLE: Record<Gravita, { dot: string; ring: string; label: string }> = {
  critico: { dot: "bg-rose-500", ring: "border-l-rose-500", label: "Critico" },
  alto: { dot: "bg-orange-500", ring: "border-l-orange-500", label: "Alto" },
  medio: { dot: "bg-amber-400", ring: "border-l-amber-400", label: "Medio" },
};

function parseStorico(s: string): number[] {
  if (!s) return [];
  return s
    .split("→")
    .map((p) => {
      const cleaned = p.replace(/[€\s]/g, "").replace(",", ".");
      return parseFloat(cleaned);
    })
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

type ChartPoint = { data: string; var_pct: number; prezzo: number; label: string };

const TOOLTIP_STYLE = {
  backgroundColor: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: "6px",
  fontSize: 11,
  color: "hsl(var(--foreground))",
};

function PrezzoChart({
  storico,
  media,
  fallbackPrezzi,
}: {
  storico: StoricoPrezzoResponse | null;
  media: number;
  fallbackPrezzi?: number[];
}) {
  const punti = storico?.punti ?? [];
  const mediaUsata = storico?.prezzo_medio ?? media;

  let chartData: ChartPoint[];

  if (punti.length >= 2) {
    chartData = punti.map((p) => ({
      data: fmtData(p.data),
      prezzo: p.prezzo_unitario,
      var_pct: mediaUsata > 0 ? Math.round(((p.prezzo_unitario - mediaUsata) / mediaUsata) * 1000) / 10 : 0,
      label: `€${p.prezzo_unitario.toFixed(2)}`,
    }));
  } else if (fallbackPrezzi && fallbackPrezzi.length >= 2) {
    const fb = fallbackPrezzi;
    const fbMedia = fb.reduce((a, b) => a + b, 0) / fb.length;
    chartData = fb.map((p, i) => ({
      data: `#${i + 1}`,
      prezzo: p,
      var_pct: fbMedia > 0 ? Math.round(((p - fbMedia) / fbMedia) * 1000) / 10 : 0,
      label: `€${p.toFixed(2)}`,
    }));
  } else {
    return (
      <p className="text-sm text-muted-foreground py-6 text-center">
        Dati insufficienti per il grafico
      </p>
    );
  }

  const maxAbs = Math.max(...chartData.map((d) => Math.abs(d.var_pct)), 1);
  const domain: [number, number] = [-Math.ceil(maxAbs * 1.2), Math.ceil(maxAbs * 1.2)];
  const mediaLabel = punti.length >= 2 ? mediaUsata : (fallbackPrezzi ?? []).reduce((a, b) => a + b, 0) / (fallbackPrezzi?.length || 1);

  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">
        Media: <span className="font-semibold text-foreground">€{mediaLabel.toFixed(2)}</span>
        {punti.length < 2 && fallbackPrezzi && fallbackPrezzi.length >= 2 && (
          <span className="ml-2 text-amber-500">(ultimi {fallbackPrezzi.length} acquisti disponibili)</span>
        )}
      </p>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
          <XAxis dataKey="data" tick={{ fontSize: 10, fill: "#94a3b8" }} tickLine={false} axisLine={false} />
          <YAxis
            domain={domain}
            tick={{ fontSize: 10, fill: "#94a3b8" }}
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
            labelStyle={{ fontSize: 11, color: "#94a3b8" }}
            contentStyle={TOOLTIP_STYLE}
          />
          <ReferenceLine
            y={0}
            stroke="#f43f5e"
            strokeDasharray="4 4"
            strokeWidth={1.5}
            label={{
              value: `media €${mediaLabel.toFixed(2)}`,
              position: "insideTopLeft",
              fontSize: 10,
              fill: "#f43f5e",
              dy: -4,
            }}
          />
          <Line type="monotone" dataKey="var_pct" stroke="#60a5fa" strokeWidth={2} dot={{ r: 3, fill: "#60a5fa" }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function AlertCard({
  r,
  expanded,
  storico,
  storicoLoading,
  onToggle,
}: {
  r: VariazionePrezzo;
  expanded: boolean;
  storico: StoricoPrezzoResponse | null;
  storicoLoading: boolean;
  onToggle: () => void;
}) {
  const g = gravita(r);
  const style = GRAVITA_STYLE[g];
  const rialzo = r.aumento_perc > 0;
  const spark = parseStorico(r.storico);

  return (
    <div className={`rounded-lg border border-l-4 ${style.ring} border-border bg-card overflow-hidden`}>
      <button onClick={onToggle} className="w-full text-left px-4 py-3 hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-3 flex-wrap">
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

          <ChevronDown className={`size-4 text-muted-foreground transition-transform shrink-0 ${expanded ? "rotate-180" : ""}`} />
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border px-4 py-3 bg-muted/10">
          {storicoLoading ? (
            <div className="h-20 flex items-center justify-center text-sm text-muted-foreground">Caricamento storico…</div>
          ) : (
            <PrezzoChart
              storico={storico}
              media={r.media}
              fallbackPrezzi={spark.length >= 2 ? spark : undefined}
            />
          )}
        </div>
      )}
    </div>
  );
}

export function VariazioniTab({ initialSoglia }: { initialSoglia: number }) {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [mese, setMese] = useState<number | null>(null); // null = tutto l'anno
  const [soglia, setSoglia] = useState(initialSoglia);
  const [sogliaInput, setSogliaInput] = useState(String(initialSoglia));
  const [savingSoglia, setSavingSoglia] = useState(false);
  const [data, setData] = useState<VariazioniResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");

  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [storico, setStorico] = useState<StoricoPrezzoResponse | null>(null);
  const [storicoLoading, setStoricoLoading] = useState(false);
  const [filtroCategoria, setFiltroCategoria] = useState("");
  const [filtroFornitore, setFiltroFornitore] = useState("");
  const [currentRange, setCurrentRange] = useState<{ data_da: string; data_a: string }>(
    isoDateRange(ANNO_CORRENTE, null),
  );

  const load = useCallback(async (annoArg: number, meseArg: number | null, sogliaArg: number) => {
    setLoading(true);
    setExpandedKey(null);
    setStorico(null);
    setFiltroCategoria("");
    setFiltroFornitore("");
    const range = isoDateRange(annoArg, meseArg);
    setCurrentRange(range);
    try {
      const qs = new URLSearchParams({ ...range, soglia: String(sogliaArg) });
      const res = await fetch(`/api/prezzi/variazioni?${qs}`);
      if (!res.ok) throw new Error();
      setData(await res.json());
    } catch {
      toast.error("Errore nel caricamento variazioni");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(ANNO_CORRENTE, null, initialSoglia);
  }, [load, initialSoglia]);

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
      toast.success(`Soglia salvata: ${val}% — ricarico gli alert`);
      load(anno, mese, val);
    } catch {
      toast.error("Errore nel salvataggio soglia");
    } finally {
      setSavingSoglia(false);
    }
  }

  async function toggleCard(r: VariazionePrezzo) {
    const key = `${r.prodotto}|${r.fornitore}`;
    if (expandedKey === key) {
      setExpandedKey(null);
      return;
    }
    setExpandedKey(key);
    setStorico(null);
    setStoricoLoading(true);
    try {
      const qs = new URLSearchParams({
        prodotto: r.prodotto,
        fornitore: r.fornitore,
        data_da: currentRange.data_da,
        data_a: currentRange.data_a,
      });
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
  const sorted = [...variazioni].sort((a, b) => Math.abs(b.impatto_stimato) - Math.abs(a.impatto_stimato));

  // valori unici per i select categoria/fornitore
  const categorieDisp = Array.from(new Set(sorted.map((r) => r.categoria).filter(Boolean))).sort();
  const fornitoriDisp = Array.from(new Set(sorted.map((r) => r.fornitore).filter(Boolean))).sort();

  const filtered = sorted.filter((r) => {
    const matchSearch =
      !search ||
      r.prodotto.toLowerCase().includes(search.toLowerCase()) ||
      r.fornitore.toLowerCase().includes(search.toLowerCase());
    const matchCat = !filtroCategoria || r.categoria === filtroCategoria;
    const matchForn = !filtroFornitore || r.fornitore === filtroFornitore;
    return matchSearch && matchCat && matchForn;
  });

  // KPI calcolati sul filtered
  const nCritici = filtered.filter((r) => gravita(r) === "critico").length;
  const impattoFiltrato = filtered.reduce((acc, r) => acc + r.impatto_stimato, 0);
  const scostamentoFiltrato =
    filtered.length > 0
      ? filtered.reduce((acc, r) => acc + r.aumento_perc, 0) / filtered.length
      : 0;
  const fornitoriFiltrati = new Set(filtered.map((r) => r.fornitore)).size;

  return (
    <div className="space-y-4">
      {/* Riga controlli */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground">Anno</label>
          <select
            value={anno}
            onChange={(e) => {
              const y = Number(e.target.value);
              setAnno(y);
              load(y, mese, soglia);
            }}
            className="rounded-md border border-border px-2 py-1.5 text-sm bg-background"
          >
            {Array.from({ length: 5 }, (_, i) => ANNO_CORRENTE - i).map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        {/* Filtro mese — pill buttons */}
        <div className="flex items-center gap-1 flex-wrap">
          <button
            onClick={() => { setMese(null); load(anno, null, soglia); }}
            className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
              mese === null
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/40"
            }`}
          >
            Tutto
          </button>
          {MESI.map((label, i) => {
            const m = i + 1;
            return (
              <button
                key={m}
                onClick={() => { setMese(m); load(anno, m, soglia); }}
                className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                  mese === m
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/40"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Riga soglia + aggiorna */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground">Soglia alert</label>
          <input
            type="number"
            min="0"
            max="50"
            step="0.5"
            value={sogliaInput}
            onChange={(e) => setSogliaInput(e.target.value)}
            className="w-16 rounded-md border border-border px-2 py-1.5 text-sm bg-background text-right"
          />
          <span className="text-sm text-muted-foreground">%</span>
          <button
            onClick={saveSoglia}
            disabled={savingSoglia}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md border border-border hover:bg-muted disabled:opacity-50 transition-colors"
          >
            <Save className="size-3" />
            {savingSoglia ? "…" : "Salva"}
          </button>
        </div>

        <button
          onClick={() => load(anno, mese, soglia)}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border border-border hover:bg-muted disabled:opacity-50 transition-colors ml-auto"
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          Aggiorna
        </button>
      </div>

      {/* Filtri di secondo livello — visibili solo quando ci sono dati */}
      {variazioni.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Cerca prodotto…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="rounded-md border border-border pl-9 pr-3 py-1.5 text-sm bg-background w-52"
            />
          </div>
          <select
            value={filtroCategoria}
            onChange={(e) => setFiltroCategoria(e.target.value)}
            className="rounded-md border border-border px-2 py-1.5 text-sm bg-background"
          >
            <option value="">Tutte le categorie</option>
            {categorieDisp.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            value={filtroFornitore}
            onChange={(e) => setFiltroFornitore(e.target.value)}
            className="rounded-md border border-border px-2 py-1.5 text-sm bg-background"
          >
            <option value="">Tutti i fornitori</option>
            {fornitoriDisp.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          {(search || filtroCategoria || filtroFornitore) && (
            <button
              onClick={() => { setSearch(""); setFiltroCategoria(""); setFiltroFornitore(""); }}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Azzera filtri
            </button>
          )}
        </div>
      )}

      {/* Banner riepilogo — riflette sempre i filtri attivi */}
      {data && variazioni.length > 0 && (
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <TriangleAlert className="size-4 text-rose-500" />
            <p className="text-sm font-semibold">
              {filtered.length} variazioni
              {filtered.length !== variazioni.length && (
                <span className="text-muted-foreground font-normal"> (filtrate da {variazioni.length})</span>
              )}
              {nCritici > 0 && <span className="text-rose-600"> · {nCritici} critiche</span>}
            </p>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-muted-foreground">Impatto stimato/mese</p>
              <p className={`text-xl font-bold ${impattoFiltrato > 0 ? "text-rose-600" : impattoFiltrato < 0 ? "text-emerald-600" : ""}`}>
                {impattoFiltrato !== 0 ? fmtEuro(impattoFiltrato, true) : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Scostamento medio</p>
              <p className={`text-xl font-bold ${scostamentoFiltrato > 0 ? "text-rose-600" : scostamentoFiltrato < 0 ? "text-emerald-600" : ""}`}>
                {filtered.length > 0 ? fmtPct(scostamentoFiltrato) : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Fornitori coinvolti</p>
              <p className="text-xl font-bold">{fornitoriFiltrati}</p>
            </div>
          </div>
        </div>
      )}

      {/* Legenda gravità */}
      {variazioni.length > 0 && (
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-rose-500 shrink-0" />Critico &gt;€100/mese</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-orange-500 shrink-0" />Alto &gt;€30/mese</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-amber-400 shrink-0" />Medio &lt;€30/mese</span>
        </div>
      )}

      {/* Stato vuoto positivo */}
      {data && variazioni.length === 0 && (
        <div className="rounded-lg border border-border bg-card py-10 text-center">
          <CheckCircle2 className="size-8 text-emerald-500 mx-auto mb-2" />
          <p className="text-sm font-medium">Nessuna variazione sopra il {soglia}%</p>
          <p className="text-xs text-muted-foreground mt-1">I prezzi dei tuoi fornitori sono stabili nel {anno}.</p>
        </div>
      )}

      {/* Loading iniziale */}
      {!data && loading && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 rounded-lg border border-border bg-card animate-pulse" />
          ))}
        </div>
      )}

      {/* Lista card */}
      {variazioni.length > 0 && (
        <>
          <div className="space-y-2">
            {filtered.map((r) => {
              const key = `${r.prodotto}|${r.fornitore}`;
              return (
                <AlertCard
                  key={key}
                  r={r}
                  expanded={expandedKey === key}
                  storico={expandedKey === key ? storico : null}
                  storicoLoading={expandedKey === key && storicoLoading}
                  onToggle={() => toggleCard(r)}
                />
              );
            })}
          </div>
          {filtered.length === 0 && (
            <p className="text-sm text-muted-foreground py-6 text-center">Nessun risultato per i filtri selezionati</p>
          )}
        </>
      )}
    </div>
  );
}
