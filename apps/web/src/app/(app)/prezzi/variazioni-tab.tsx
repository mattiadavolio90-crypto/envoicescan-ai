"use client";

import { useState, useEffect, useCallback } from "react";
import { RefreshCw, ChevronDown, Search, TriangleAlert, CheckCircle2, Calendar, Settings2, Star } from "lucide-react";
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
import type { VariazioniResponse, VariazionePrezzo, StoricoPrezzoResponse, StoricoPrezzoPoint } from "@/lib/prezzi";
import { Input } from "@/components/ui/input";
import { AnteprimaFatturaDialog } from "./anteprima-fattura-dialog";

const ANNO_CORRENTE = new Date().getFullYear();
const MESI_LUNGHI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];

type ModoPeriodo = "anno" | "mese" | "custom";

function isoDateRange(anno: number, mese: number | null): { data_da: string; data_a: string } {
  if (mese === null) return { data_da: `${anno}-01-01`, data_a: `${anno}-12-31` };
  const lastDay = new Date(anno, mese, 0).getDate();
  const mm = String(mese).padStart(2, "0");
  return { data_da: `${anno}-${mm}-01`, data_a: `${anno}-${mm}-${lastDay}` };
}

function fmtRangeIt(da: string, a: string): string {
  const f = (iso: string) => {
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y.slice(2)}`;
  };
  return `${f(da)} → ${f(a)}`;
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

// Chiave preferito: gemella di _pulisci_desc_key/_pulisci_forn_key del worker.
// Rimuove i suffissi UI (" ⚠️ >6m"), UPPER+TRIM. Serve per aggiornare in modo
// ottimistico il Set locale dei preferiti coerentemente col campo `preferito`
// che arriva dal server.
const SUFFISSI_UI = [" ⚠️ >6M", " ⚠ >6M"];
function prefKey(prodotto: string, fornitore: string): string {
  let d = prodotto.trim().toUpperCase();
  for (const s of SUFFISSI_UI) {
    if (d.endsWith(s)) {
      d = d.slice(0, -s.length).trim();
      break;
    }
  }
  return `${d}|${fornitore.trim().toUpperCase()}`;
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
  backgroundColor: "var(--card)",
  border: "1px solid var(--border)",
  borderRadius: "6px",
  fontSize: 11,
  color: "var(--foreground)",
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
          <XAxis dataKey="data" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
          <YAxis
            domain={domain}
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
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
            labelStyle={{ fontSize: 11, color: "var(--muted-foreground)" }}
            itemStyle={{ color: "var(--foreground)" }}
            contentStyle={TOOLTIP_STYLE}
          />
          <ReferenceLine
            y={0}
            stroke="#f43f5e"
            strokeDasharray="4 4"
            strokeWidth={1.5}
            label={{
              value: "Media",
              position: "insideTopRight",
              fontSize: 10,
              fill: "#f43f5e",
              dy: -4,
            }}
          />
          <Line type="monotone" dataKey="var_pct" stroke="#60a5fa" strokeWidth={2} dot={{ r: 3, fill: "#60a5fa" }} activeDot={{ r: 5, fill: "#60a5fa", stroke: "var(--card)", strokeWidth: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// Lista degli acquisti (= punti storico, dal più recente) sotto il grafico.
// Ogni riga è una riga di fattura cliccabile per aprire l'anteprima. Niente
// fetch extra: sono gli stessi dati del grafico, arricchiti col file_origine.
function ListaAcquisti({
  punti,
  media,
  onApriFattura,
}: {
  punti: StoricoPrezzoPoint[];
  media: number;
  onApriFattura: (p: StoricoPrezzoPoint) => void;
}) {
  const conFattura = punti.filter((p) => p.fattura);
  if (conFattura.length === 0) return null;

  // Dal più recente: i punti arrivano ordinati per data crescente dal worker.
  const ordinati = [...conFattura].reverse();

  return (
    <div className="mt-4">
      <p className="text-xs font-medium text-muted-foreground mb-2">
        Acquisti nel periodo ({ordinati.length}) — clicca per aprire la fattura
      </p>
      <div className="rounded-lg border border-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/40">
              <tr>
                <th className="text-left px-3 py-2 text-muted-foreground font-medium">Data</th>
                <th className="text-left px-3 py-2 text-muted-foreground font-medium">Fattura</th>
                <th className="text-right px-3 py-2 text-muted-foreground font-medium">Qtà</th>
                <th className="text-right px-3 py-2 text-muted-foreground font-medium">Prezzo unit.</th>
                <th className="text-right px-3 py-2 text-muted-foreground font-medium">Totale</th>
                <th className="text-right px-3 py-2 text-muted-foreground font-medium">vs media</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {ordinati.map((p, i) => {
                const delta = media > 0 ? ((p.prezzo_unitario - media) / media) * 100 : 0;
                return (
                  <tr
                    key={`${p.fattura}-${i}`}
                    onClick={() => onApriFattura(p)}
                    className="cursor-pointer hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-3 py-2 tabular-nums">{fmtData(p.data)}</td>
                    <td className="px-3 py-2 max-w-[160px]">
                      <span className="text-primary truncate inline-block max-w-full align-bottom">
                        {p.numero_documento || "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{p.quantita ?? "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium">€{p.prezzo_unitario.toFixed(4)}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                      {p.totale_riga != null ? fmtEuro(p.totale_riga) : "—"}
                    </td>
                    <td className={`px-3 py-2 text-right tabular-nums ${delta > 0.05 ? "text-rose-600" : delta < -0.05 ? "text-emerald-600" : "text-muted-foreground"}`}>
                      {Math.abs(delta) < 0.05 ? "—" : fmtPct(delta)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function AlertCard({
  r,
  expanded,
  preferito,
  storico,
  storicoLoading,
  onToggle,
  onToggleStar,
  onApriFattura,
}: {
  r: VariazionePrezzo;
  expanded: boolean;
  preferito: boolean;
  storico: StoricoPrezzoResponse | null;
  storicoLoading: boolean;
  onToggle: () => void;
  onToggleStar: () => void;
  onApriFattura: (p: StoricoPrezzoPoint) => void;
}) {
  const g = gravita(r);
  const style = GRAVITA_STYLE[g];
  const rialzo = r.aumento_perc > 0;
  const spark = parseStorico(r.storico);

  return (
    <div className={`rounded-lg border border-l-4 ${style.ring} border-border bg-card overflow-hidden`}>
      <button onClick={onToggle} className="w-full text-left px-4 py-3 hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-3 flex-wrap">
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => { e.stopPropagation(); onToggleStar(); }}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); onToggleStar(); } }}
            aria-label={preferito ? "Rimuovi dai preferiti" : "Aggiungi ai preferiti"}
            aria-pressed={preferito}
            className="shrink-0 -m-1 p-1 rounded hover:bg-muted transition-colors cursor-pointer"
          >
            <Star className={`size-4 transition-colors ${preferito ? "fill-amber-400 text-amber-400" : "text-muted-foreground/50 hover:text-amber-400"}`} />
          </span>
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
            <>
              <PrezzoChart
                storico={storico}
                media={r.media}
                fallbackPrezzi={spark.length >= 2 ? spark : undefined}
              />
              {storico && (
                <ListaAcquisti
                  punti={storico.punti}
                  media={storico.prezzo_medio || r.media}
                  onApriFattura={onApriFattura}
                />
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

type KpiTone = "sky" | "emerald" | "rose";

const KPI_TONE: Record<KpiTone, { border: string; hover: string; value: string }> = {
  sky:     { border: "border-sky-500/40",     hover: "hover:border-sky-500/70",     value: "text-sky-600 dark:text-sky-400" },
  emerald: { border: "border-emerald-500/40", hover: "hover:border-emerald-500/70", value: "text-emerald-600 dark:text-emerald-400" },
  rose:    { border: "border-rose-500/40",    hover: "hover:border-rose-500/70",    value: "text-rose-600 dark:text-rose-400" },
};

function KpiCard({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone: KpiTone }) {
  const t = KPI_TONE[tone];
  return (
    <div className={`rounded-xl border ${t.border} ${t.hover} bg-card px-4 py-3 flex flex-col gap-1 transition-colors`}>
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium leading-none">{label}</span>
      <span className={`text-2xl font-bold tracking-tight leading-tight ${t.value}`}>{value}</span>
      {sub && <span className="text-[11px] text-muted-foreground leading-tight truncate">{sub}</span>}
    </div>
  );
}

export function VariazioniTab({ initialSoglia }: { initialSoglia: number }) {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [mese, setMese] = useState<number | null>(null); // null = tutto l'anno
  const [modo, setModo] = useState<ModoPeriodo>("anno");
  const [customDa, setCustomDa] = useState("");
  const [customA, setCustomA] = useState("");
  const [soglia, setSoglia] = useState(initialSoglia);
  const [sogliaInput, setSogliaInput] = useState(String(initialSoglia));
  const [data, setData] = useState<VariazioniResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");

  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [storico, setStorico] = useState<StoricoPrezzoResponse | null>(null);
  const [storicoLoading, setStoricoLoading] = useState(false);
  const [filtroCategoria, setFiltroCategoria] = useState("");
  const [filtroFornitore, setFiltroFornitore] = useState("");
  const [preferiti, setPreferiti] = useState<Set<string>>(new Set());
  const [soloPreferiti, setSoloPreferiti] = useState(false);
  const [currentRange, setCurrentRange] = useState<{ data_da: string; data_a: string }>(
    isoDateRange(ANNO_CORRENTE, null),
  );
  // Anteprima fattura aperta da una riga della lista acquisti.
  const [anteprima, setAnteprima] = useState<{ punto: StoricoPrezzoPoint; prodotto: string } | null>(null);

  // Carica per range esplicito: cosi' lo stesso fetch serve anno, mese e custom.
  const loadRange = useCallback(async (range: { data_da: string; data_a: string }, sogliaArg: number) => {
    if (!range.data_da || !range.data_a) return;
    setLoading(true);
    setExpandedKey(null);
    setStorico(null);
    setFiltroCategoria("");
    setFiltroFornitore("");
    setCurrentRange(range);
    try {
      const qs = new URLSearchParams({ ...range, soglia: String(sogliaArg) });
      const res = await fetch(`/api/prezzi/variazioni?${qs}`);
      if (!res.ok) throw new Error();
      const json: VariazioniResponse = await res.json();
      setData(json);
      // Set preferiti iniziale dal campo `preferito` della response: cosi' la
      // stella riflette lo stato salvato e gli aggiornamenti ottimistici partono
      // da una base corretta.
      setPreferiti(
        new Set(
          (json.variazioni ?? [])
            .filter((v) => v.preferito)
            .map((v) => prefKey(v.prodotto, v.fornitore)),
        ),
      );
    } catch {
      toast.error("Errore nel caricamento variazioni");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRange(isoDateRange(ANNO_CORRENTE, null), initialSoglia);
  }, [loadRange, initialSoglia]);

  // Applica un preset di periodo aggiornando stato + ricaricando.
  function applyAnno(y: number) {
    setAnno(y);
    setModo("anno");
    setMese(null);
    loadRange(isoDateRange(y, null), soglia);
  }
  function applyMese(m: number) {
    setMese(m);
    setModo("mese");
    loadRange(isoDateRange(anno, m), soglia);
  }
  function applyCustom(da: string, a: string) {
    setCustomDa(da);
    setCustomA(a);
    if (da && a) loadRange({ data_da: da, data_a: a }, soglia);
  }

  // Range attivo in base al modo (per ricaricare dopo il salvataggio soglia).
  function rangeAttivo(): { data_da: string; data_a: string } {
    if (modo === "custom" && customDa && customA) return { data_da: customDa, data_a: customA };
    if (modo === "mese") return isoDateRange(anno, mese);
    return isoDateRange(anno, null);
  }

  // Filtro di SOLA VISUALIZZAZIONE: muove la soglia per vedere cosa supererebbe
  // in questa pagina, senza salvare nulla. La soglia che fa scattare gli AVVISI si
  // imposta nel configuratore assistente (Home) ed e' quella di partenza qui.
  function applicaFiltroSoglia() {
    const val = parseFloat(sogliaInput.replace(",", ".")) || 5;
    setSoglia(val);
    loadRange(rangeAttivo(), val);
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

  // Stella ottimistica: aggiorna subito il Set locale, poi persiste. Su errore
  // fa rollback e mostra un toast — la stella non resta in uno stato falso.
  async function toggleStar(r: VariazionePrezzo) {
    const key = prefKey(r.prodotto, r.fornitore);
    const eraPreferito = preferiti.has(key);
    setPreferiti((prev) => {
      const next = new Set(prev);
      if (eraPreferito) next.delete(key);
      else next.add(key);
      return next;
    });
    try {
      let res: Response;
      if (eraPreferito) {
        const qs = new URLSearchParams({ prodotto: r.prodotto, fornitore: r.fornitore });
        res = await fetch(`/api/prezzi/preferiti?${qs}`, { method: "DELETE" });
      } else {
        res = await fetch("/api/prezzi/preferiti", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prodotto: r.prodotto, fornitore: r.fornitore }),
        });
      }
      if (!res.ok) throw new Error();
    } catch {
      setPreferiti((prev) => {
        const next = new Set(prev);
        if (eraPreferito) next.add(key);
        else next.delete(key);
        return next;
      });
      toast.error("Non sono riuscito ad aggiornare i preferiti");
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
    const matchPref = !soloPreferiti || preferiti.has(prefKey(r.prodotto, r.fornitore));
    return matchSearch && matchCat && matchForn && matchPref;
  });

  const nPreferiti = preferiti.size;

  // KPI calcolati sul filtered
  const nCritici = filtered.filter((r) => gravita(r) === "critico").length;
  const impattoFiltrato = filtered.reduce((acc, r) => acc + r.impatto_stimato, 0);
  const scostamentoFiltrato =
    filtered.length > 0
      ? filtered.reduce((acc, r) => acc + r.aumento_perc, 0) / filtered.length
      : 0;

  // KPI di sintesi mostrati in cima al tab (specifici di "Variazioni Prezzo")
  const rincari = filtered.filter((r) => r.aumento_perc > 0);
  const risparmi = filtered.filter((r) => r.aumento_perc < 0);
  const rincaroMedio = rincari.length > 0 ? rincari.reduce((a, r) => a + r.aumento_perc, 0) / rincari.length : 0;
  const risparmioMedio = risparmi.length > 0 ? risparmi.reduce((a, r) => a + r.aumento_perc, 0) / risparmi.length : 0;

  const chipBase =
    "px-3 py-1.5 text-xs font-medium rounded-full border transition-colors inline-flex items-center gap-1.5 disabled:opacity-60";
  const chipActive = "bg-primary text-primary-foreground border-primary";
  const chipIdle = "bg-background border-input hover:bg-muted";

  return (
    <div className="space-y-4">
      {/* ── Filtro periodo (stile Analisi Fatture) ── */}
      <div className="space-y-2">
        <div className={`flex flex-wrap items-center gap-1.5 ${loading ? "opacity-70" : ""}`}>
          <select
            value={anno}
            disabled={loading}
            onChange={(e) => applyAnno(Number(e.target.value))}
            className="h-8 rounded-full border border-input bg-background px-3 text-xs font-medium"
          >
            {Array.from({ length: 5 }, (_, i) => ANNO_CORRENTE - i).map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
          <button
            disabled={loading}
            onClick={() => applyAnno(anno)}
            className={`${chipBase} ${modo === "anno" ? chipActive : chipIdle}`}
          >
            Anno in corso
          </button>
          <button
            disabled={loading}
            onClick={() => { setModo("mese"); if (mese !== null) loadRange(isoDateRange(anno, mese), soglia); }}
            className={`${chipBase} ${modo === "mese" ? chipActive : chipIdle}`}
          >
            <Calendar className="size-3" />
            Seleziona mese
          </button>
          <button
            disabled={loading}
            onClick={() => setModo("custom")}
            className={`${chipBase} ${modo === "custom" ? chipActive : chipIdle}`}
          >
            <Settings2 className="size-3" />
            Personalizzato
          </button>
          {currentRange.data_da && currentRange.data_a && (
            <span className="ml-2 text-xs font-medium text-sky-500 dark:text-sky-400">
              {fmtRangeIt(currentRange.data_da, currentRange.data_a)}
            </span>
          )}
          <button
            onClick={() => loadRange(rangeAttivo(), soglia)}
            disabled={loading}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
          >
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
            Aggiorna
          </button>
        </div>

        {modo === "mese" && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Mese:</span>
            <select
              value={mese ?? ""}
              onChange={(e) => applyMese(Number(e.target.value))}
              className="h-7 rounded-md border border-input bg-background px-2 text-xs"
            >
              <option value="" disabled>Seleziona un mese</option>
              {MESI_LUNGHI.map((label, i) => (
                <option key={i + 1} value={i + 1}>{label} {anno}</option>
              ))}
            </select>
          </div>
        )}

        {modo === "custom" && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Dal</span>
            <Input
              type="date"
              value={customDa}
              onChange={(e) => applyCustom(e.target.value, customA)}
              className="h-7 w-36 text-xs"
            />
            <span className="text-xs text-muted-foreground">al</span>
            <Input
              type="date"
              value={customA}
              onChange={(e) => applyCustom(customDa, e.target.value)}
              className="h-7 w-36 text-xs"
            />
          </div>
        )}
      </div>

      {/* ── Soglia di visualizzazione (NON imposta gli avvisi) ── */}
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm text-muted-foreground">Mostra variazioni da</label>
        <input
          type="number"
          min="0"
          max="50"
          step="0.5"
          value={sogliaInput}
          onChange={(e) => setSogliaInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") applicaFiltroSoglia(); }}
          className="w-16 rounded-md border border-border px-2 py-1.5 text-sm bg-background text-right"
        />
        <span className="text-sm text-muted-foreground">% in su</span>
        <button
          onClick={applicaFiltroSoglia}
          disabled={loading}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md border border-border hover:bg-muted disabled:opacity-50 transition-colors"
        >
          <Search className="size-3" />
          Applica
        </button>
        <span className="text-xs text-muted-foreground basis-full sm:basis-auto">
          Filtro solo per questa pagina. La soglia degli avvisi si imposta nell&apos;assistente, in Home.
        </span>
      </div>

      {/* ── KPI di sintesi (specifici del tab Variazioni) ── */}
      {data && variazioni.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <KpiCard
            label="Rincari medi"
            value={rincari.length > 0 ? fmtPct(rincaroMedio) : "—"}
            sub={`${rincari.length} prodott${rincari.length === 1 ? "o" : "i"} in aumento`}
            tone="rose"
          />
          <KpiCard
            label="Risparmi medi"
            value={risparmi.length > 0 ? fmtPct(risparmioMedio) : "—"}
            sub={`${risparmi.length} prodott${risparmi.length === 1 ? "o" : "i"} in calo`}
            tone="emerald"
          />
          <KpiCard
            label="Scostamento medio"
            value={filtered.length > 0 ? fmtPct(scostamentoFiltrato) : "—"}
            sub={`su ${filtered.length} variazion${filtered.length === 1 ? "e" : "i"}`}
            tone={scostamentoFiltrato < 0 ? "emerald" : "rose"}
          />
          <KpiCard
            label="Impatto stimato/mese"
            value={impattoFiltrato !== 0 ? fmtEuro(impattoFiltrato, true) : "—"}
            sub="effetto sui costi mensili"
            tone={impattoFiltrato < 0 ? "emerald" : "rose"}
          />
        </div>
      )}

      {/* Filtri di secondo livello — visibili solo quando ci sono dati */}
      {variazioni.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          <div className="inline-flex rounded-full border border-border p-0.5 bg-background">
            <button
              onClick={() => setSoloPreferiti(false)}
              className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${!soloPreferiti ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
            >
              Tutti
            </button>
            <button
              onClick={() => setSoloPreferiti(true)}
              className={`inline-flex items-center gap-1 px-3 py-1 text-xs font-medium rounded-full transition-colors ${soloPreferiti ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
            >
              <Star className={`size-3 ${soloPreferiti ? "fill-current" : "fill-amber-400 text-amber-400"}`} />
              Preferiti{nPreferiti > 0 ? ` (${nPreferiti})` : ""}
            </button>
          </div>
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

      {/* N. variazioni + legenda gravità — appena sopra la lista */}
      {data && variazioni.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <TriangleAlert className="size-4 text-rose-500 shrink-0" />
          <p className="text-sm font-semibold">
            {filtered.length} variazioni
            {filtered.length !== variazioni.length && (
              <span className="text-muted-foreground font-normal"> (filtrate da {variazioni.length})</span>
            )}
            {nCritici > 0 && <span className="text-rose-600"> · {nCritici} critiche</span>}
          </p>
          <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-rose-500 shrink-0" />Critico</span>
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-orange-500 shrink-0" />Alto</span>
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-amber-400 shrink-0" />Medio</span>
          </div>
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
                  preferito={preferiti.has(prefKey(r.prodotto, r.fornitore))}
                  storico={expandedKey === key ? storico : null}
                  storicoLoading={expandedKey === key && storicoLoading}
                  onToggle={() => toggleCard(r)}
                  onToggleStar={() => toggleStar(r)}
                  onApriFattura={(p) => setAnteprima({ punto: p, prodotto: r.prodotto })}
                />
              );
            })}
          </div>
          {filtered.length === 0 && soloPreferiti && nPreferiti === 0 && (
            <div className="rounded-lg border border-dashed border-border py-10 text-center">
              <Star className="size-7 text-amber-400 mx-auto mb-2" />
              <p className="text-sm font-medium">Non hai ancora prodotti preferiti</p>
              <p className="text-xs text-muted-foreground mt-1">Tocca la ⭐ accanto a un prodotto per seguirne i prezzi qui.</p>
            </div>
          )}
          {filtered.length === 0 && !(soloPreferiti && nPreferiti === 0) && (
            <p className="text-sm text-muted-foreground py-6 text-center">Nessun risultato per i filtri selezionati</p>
          )}
        </>
      )}

      <AnteprimaFatturaDialog
        open={anteprima !== null}
        fileOrigine={anteprima?.punto.fattura ?? null}
        numeroDocumento={anteprima?.punto.numero_documento}
        prodotto={anteprima?.prodotto ?? ""}
        onClose={() => setAnteprima(null)}
      />
    </div>
  );
}
