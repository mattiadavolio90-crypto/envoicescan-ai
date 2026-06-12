"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronDown, ChevronUp, RefreshCw, TrendingUp,
  PieChart as PieChartIcon, Settings2, ChevronLeft, ChevronRight, X as XIcon, BarChart3,
} from "lucide-react";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  BarChart, Bar, Cell as RCell,
} from "recharts";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { formatEuro, formatEuroCompact, MESI_NOMI_SHORT } from "./periodi";

/* ────────────────────────────────────────────────────────────────────────────
   TIPI
   ──────────────────────────────────────────────────────────────────────────── */
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

type AnalisiAvanzataResponse = {
  centri: CentroDetailItem[];
  andamento_mensile: AndamentoMese[];
  commenti: { kpi_nome: string; percentuale: string; commento: string; emoji: string; colore: string }[];
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

const CENTRI_FATT = ["FOOD", "BEVERAGE", "ALCOLICI", "DOLCI"] as const;
type CentroFatt = (typeof CENTRI_FATT)[number];
type SplitEuro = Record<Lowercase<CentroFatt>, number>;

type Props = { dataDa: string; dataA: string };

/* ────────────────────────────────────────────────────────────────────────────
   RIPARTIZIONE DIALOG (mensile: % o € di fatturato per centro)
   ──────────────────────────────────────────────────────────────────────────── */

function buildMesiList(dataDa: string, dataA: string) {
  const mesi: { anno: number; mese: number; label: string }[] = [];
  const y0 = parseInt(dataDa.slice(0, 4), 10), m0 = parseInt(dataDa.slice(5, 7), 10);
  const y1 = parseInt(dataA.slice(0, 4), 10), m1 = parseInt(dataA.slice(5, 7), 10);
  for (let y = y0; y <= y1; y++) {
    const mFrom = y === y0 ? m0 : 1;
    const mTo = y === y1 ? m1 : 12;
    for (let m = mFrom; m <= mTo; m++) {
      mesi.push({ anno: y, mese: m, label: `${MESI_NOMI_SHORT[m - 1]} ${y}` });
    }
  }
  return mesi;
}

function RipartizioneDialog({
  open, onOpenChange, dataDa, dataA, onSaved,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  dataDa: string;
  dataA: string;
  onSaved: () => void;
}) {
  const mesi = useMemo(() => buildMesiList(dataDa, dataA), [dataDa, dataA]);
  const [meseSel, setMeseSel] = useState(() => mesi[mesi.length - 1]);
  const [mode, setMode] = useState<"euro" | "perc">("perc");
  const [vals, setVals] = useState<SplitEuro>({ food: 0, beverage: 0, alcolici: 0, dolci: 0 });
  const [netto, setNetto] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const meseKey = meseSel ? `${meseSel.anno}-${String(meseSel.mese).padStart(2, "0")}` : "";

  useEffect(() => {
    if (!meseSel || !open) return;
    setLoading(true);
    const mm = String(meseSel.mese).padStart(2, "0");
    const lastDay = new Date(meseSel.anno, meseSel.mese, 0).getDate();
    Promise.all([
      fetch(`/api/margini/fatturato-centri?anno=${meseSel.anno}&mese=${meseSel.mese}`)
        .then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`/api/ricavi/giornalieri?${new URLSearchParams({
        data_da: `${meseSel.anno}-${mm}-01`,
        data_a: `${meseSel.anno}-${mm}-${String(lastDay).padStart(2, "0")}`,
      })}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]).then(([split, ricavi]) => {
      setVals({
        food: split?.fatturato_food ?? 0,
        beverage: split?.fatturato_beverage ?? 0,
        alcolici: split?.fatturato_alcolici ?? 0,
        dolci: split?.fatturato_dolci ?? 0,
      });
      setNetto(ricavi?.totale_netto ?? 0);
      setLoading(false);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meseKey, open]);

  const totale = vals.food + vals.beverage + vals.alcolici + vals.dolci;
  const valid = netto > 0 && Math.abs(totale - netto) < 1;

  function setField(k: keyof SplitEuro, raw: string) {
    let v = parseFloat(raw.replace(",", ".")) || 0;
    if (mode === "perc") v = (v / 100) * netto;
    setVals((prev) => ({ ...prev, [k]: v }));
  }

  async function handleSave() {
    if (!meseSel) return;
    setSaving(true);
    try {
      const res = await fetch("/api/margini/fatturato-centri", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          anno: meseSel.anno,
          mese: meseSel.mese,
          fatturato_food: vals.food,
          fatturato_beverage: vals.beverage,
          fatturato_alcolici: vals.alcolici,
          fatturato_dolci: vals.dolci,
        }),
      });
      if (!res.ok) throw new Error();
      toast.success(`Ripartizione ${meseSel.label} salvata`);
      onSaved();
      onOpenChange(false);
    } catch {
      toast.error("Errore nel salvataggio");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false} className="!max-w-[min(720px,92vw)] w-full max-h-[90vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 pt-5 pb-4 border-b border-border shrink-0 flex-row items-start justify-between gap-4">
          <div className="space-y-1">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Settings2 className="size-4 text-primary" />
              Ripartizione ricavi per centro
            </DialogTitle>
            <p className="text-xs text-muted-foreground">
              Imposta quanto del fatturato netto mensile è attribuito a ciascun centro.
            </p>
          </div>
          <button onClick={() => onOpenChange(false)} className="size-8 flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted transition-colors shrink-0"><XIcon className="size-4" /></button>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {/* Selettore mese + toggle €/% */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => { const i = mesi.findIndex((m) => m.label === meseSel?.label); if (i > 0) setMeseSel(mesi[i - 1]); }}
                disabled={mesi[0]?.label === meseSel?.label}
                className="size-9 flex items-center justify-center rounded-md border border-input hover:bg-muted disabled:opacity-30 transition-colors"
              ><ChevronLeft className="size-4" /></button>
              <select
                value={meseSel?.label}
                onChange={(e) => { const f = mesi.find((m) => m.label === e.target.value); if (f) setMeseSel(f); }}
                className="rounded-md border border-input bg-background px-3 py-2 text-sm font-semibold min-w-32"
              >
                {mesi.map((m) => <option key={m.label} value={m.label}>{m.label}</option>)}
              </select>
              <button
                onClick={() => { const i = mesi.findIndex((m) => m.label === meseSel?.label); if (i < mesi.length - 1) setMeseSel(mesi[i + 1]); }}
                disabled={mesi[mesi.length - 1]?.label === meseSel?.label}
                className="size-9 flex items-center justify-center rounded-md border border-input hover:bg-muted disabled:opacity-30 transition-colors"
              ><ChevronRight className="size-4" /></button>
            </div>
            <div className="flex rounded-md border border-input overflow-hidden text-xs ml-auto">
              <button onClick={() => setMode("perc")} className={`px-4 py-2 font-medium transition-colors ${mode === "perc" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>%</button>
              <button onClick={() => setMode("euro")} className={`px-4 py-2 font-medium border-l border-input transition-colors ${mode === "euro" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>€</button>
            </div>
          </div>

          {loading ? (
            <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
          ) : netto <= 0 ? (
            <div className="py-12 text-center space-y-1">
              <p className="text-sm font-medium">Nessun ricavo per {meseSel?.label}</p>
              <p className="text-xs text-muted-foreground">Carica prima i ricavi del mese da &quot;Carica ricavi&quot; nel tab Marginalità.</p>
            </div>
          ) : (
            <div className="space-y-4 max-w-lg">
              <p className="text-xs text-muted-foreground">
                Fatturato netto di <strong>{meseSel?.label}</strong>: <strong className="text-foreground">{formatEuro(netto)}</strong>. La somma dei centri deve corrispondere.
              </p>
              <div className="space-y-3">
                {CENTRI_FATT.map((k) => {
                  const key = k.toLowerCase() as keyof SplitEuro;
                  const euro = vals[key];
                  const pct = netto > 0 ? (euro / netto) * 100 : 0;
                  const display = mode === "euro"
                    ? (euro === 0 ? "" : Math.round(euro).toString())
                    : (pct === 0 ? "" : pct.toFixed(1));
                  const color = CENTRO_COLOR[k];
                  return (
                    <div key={k} className="flex items-center gap-3">
                      <div className="flex items-center gap-2 w-28 shrink-0">
                        <div className="size-2.5 rounded-full" style={{ backgroundColor: color }} />
                        <label className="text-sm font-semibold" style={{ color }}>{k}</label>
                      </div>
                      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                        <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(100, pct)}%`, backgroundColor: color, opacity: 0.8 }} />
                      </div>
                      <div className="flex items-center gap-1 w-24 shrink-0">
                        <input type="number" min={0} step={mode === "euro" ? 1 : 0.1} value={display} placeholder="0"
                          onChange={(e) => setField(key, e.target.value)}
                          className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm tabular-nums text-right focus:outline-none focus:ring-2 focus:ring-primary/50"
                        />
                        <span className="text-sm text-muted-foreground">{mode === "euro" ? "€" : "%"}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm font-semibold ${
                valid ? "border-emerald-500/40 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300"
                : totale > netto ? "border-rose-500/40 bg-rose-500/5 text-rose-700 dark:text-rose-400"
                : "border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-300"
              }`}>
                <div className="flex-1 bg-muted/50 rounded-full h-2 overflow-hidden">
                  <div className="h-full rounded-full transition-all" style={{ width: `${netto > 0 ? Math.min((totale / netto) * 100, 100) : 0}%`, backgroundColor: valid ? "#22c55e" : totale > netto ? "#ef4444" : "#f59e0b" }} />
                </div>
                <span className="shrink-0 tabular-nums">
                  {mode === "euro" ? `${formatEuro(totale)} / ${formatEuro(netto)}` : `${netto > 0 ? ((totale / netto) * 100).toFixed(1) : "0.0"}% / 100%`}
                  {valid ? " ✓" : ""}
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="px-6 pb-5 pt-3 border-t border-border flex items-center justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => { onSaved(); onOpenChange(false); }}>
            <RefreshCw className="size-3 mr-1" />
            Aggiorna e chiudi
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={saving || netto <= 0}
            className="min-w-28"
          >
            {saving ? "Salvataggio…" : `Salva ${meseSel?.label ?? ""}`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ────────────────────────────────────────────────────────────────────────────
   MAIN TAB
   ──────────────────────────────────────────────────────────────────────────── */
export function AnalisiTab({ dataDa, dataA }: Props) {
  const [data, setData] = useState<AnalisiAvanzataResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [chartMode, setChartMode] = useState<"euro" | "perc">("euro");
  const [ripartizioneOpen, setRipartizioneOpen] = useState(false);
  const [dettaglioOpen, setDettaglioOpen] = useState(false);
  const [dettaglioCentroSel, setDettaglioCentroSel] = useState<string | null>(null);

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
          Carica fatture e inserisci ricavi per popolare l&apos;analisi per centri.
        </p>
      </div>
    );
  }

  const centriConCosto = data.centri.filter((c) => c.costo_totale > 0);

  const annoRef = parseInt(dataA.slice(0, 4), 10);
  const meseRef = parseInt(dataA.slice(5, 7), 10);
  const meseLabelRef = `${MESI_NOMI_SHORT[meseRef - 1]} ${annoRef}`;

  // Solo i centri che possono avere fatturato proprio (no SHOP)
  const centriFatturato = centriConCosto.filter((c) => (CENTRI_FATT as readonly string[]).includes(c.centro));
  const centroDettaglio = centriFatturato.find((c) => c.centro === dettaglioCentroSel) ?? centriFatturato[0] ?? null;

  function openDettaglio() {
    setDettaglioCentroSel(centriFatturato[0]?.centro ?? null);
    setDettaglioOpen(true);
  }

  return (
    <div className="space-y-5">
      {/* Toolbar */}
      <div className="flex items-center gap-2 ml-auto">
        <button
          onClick={openDettaglio}
          disabled={centriFatturato.length === 0}
          title={centriFatturato.length === 0 ? "Configura prima la ripartizione per centro" : undefined}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border border-input hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <BarChart3 className="size-3" />
          Dettaglio giornaliero
        </button>
        <button
          onClick={() => setRipartizioneOpen(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Settings2 className="size-3" />
          Ripartizione centri
        </button>
      </div>

      <RipartizioneDialog
        open={ripartizioneOpen}
        onOpenChange={setRipartizioneOpen}
        dataDa={dataDa}
        dataA={dataA}
        onSaved={load}
      />

      {dettaglioOpen && centroDettaglio && (
        <DettaglioCentroDialog
          anno={annoRef}
          mese={meseRef}
          meseLabel={meseLabelRef}
          centro={dettaglioCentroSel ?? centroDettaglio.centro}
          color={CENTRO_COLOR[dettaglioCentroSel ?? centroDettaglio.centro] ?? "#94a3b8"}
          centri={centriFatturato}
          onCentroChange={(c) => setDettaglioCentroSel(c)}
          onClose={() => setDettaglioOpen(false)}
        />
      )}

      {/* Tabella centri */}
      <CentriTable centri={centriConCosto} />

      {/* Grafici */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-2 rounded-lg border border-border bg-card p-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
            <PieChartIcon className="size-4 text-primary" />
            Distribuzione Costi per Centro
          </h3>
          <CentriDonutChart centri={centriConCosto} />
        </div>
        <div className="lg:col-span-3 rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold flex items-center gap-1.5">
              <TrendingUp className="size-4 text-primary" />
              Andamento mensile per Centro
            </h3>
            <div className="flex rounded-md border border-input overflow-hidden text-xs">
              <button onClick={() => setChartMode("euro")} className={`px-2 py-0.5 ${chartMode === "euro" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>€</button>
              <button onClick={() => setChartMode("perc")} className={`px-2 py-0.5 border-l border-input ${chartMode === "perc" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>%</button>
            </div>
          </div>
          <AndamentoLineChart andamento={data.andamento_mensile} centri={centriConCosto} mode={chartMode} />
        </div>
      </div>

      {/* Commenti */}
      {data.commenti.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">💬 Analisi automatica per centro</h3>
          <div className="space-y-1.5">
            {data.commenti.map((c, i) => (
              <div key={i} className="flex items-start gap-3 rounded-md border border-border bg-card p-3" style={{ borderLeftWidth: 4, borderLeftColor: c.colore }}>
                <span className="text-base font-bold shrink-0" style={{ color: c.colore }}>{c.emoji} {c.percentuale}</span>
                <div className="text-sm"><strong>{c.kpi_nome}</strong><span className="text-muted-foreground"> · {c.commento}</span></div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────────
   TABELLA CENTRI
   ──────────────────────────────────────────────────────────────────────────── */
function CentriTable({ centri }: { centri: CentroDetailItem[] }) {
  return (
    <div className="space-y-1.5">
      <h3 className="text-sm font-semibold mb-2">Dettaglio Centri / Categorie</h3>
      {centri.map((c) => <CentroCard key={c.centro} centro={c} totali={centri} />)}
    </div>
  );
}

function MiniBar({ pct, color, opacity = 0.75 }: { pct: number; color: string; opacity?: number }) {
  const w = Math.min(100, Math.max(0, pct));
  return (
    <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden mt-1">
      <div className="h-full rounded-full" style={{ width: `${w}%`, backgroundColor: color, opacity }} />
    </div>
  );
}

function CentroCard({ centro, totali }: { centro: CentroDetailItem; totali: CentroDetailItem[] }) {
  const [expanded, setExpanded] = useState(false);
  const color = CENTRO_COLOR[centro.centro] ?? "#94a3b8";

  const fc = centro.incidenza_su_fatt;
  const incidenzaColor = !centro.has_fatturato ? "text-muted-foreground" : "text-sky-600 dark:text-sky-400";

  const margineColor =
    !centro.has_fatturato ? "text-muted-foreground"
    : centro.margine >= 0 ? "text-emerald-600 dark:text-emerald-400"
    : "text-rose-600 dark:text-rose-400";

  // Massimi tra tutti i centri per normalizzare le barre dell'header
  const maxCosto = Math.max(1, ...totali.map((c) => c.costo_totale));
  const maxMargine = Math.max(1, ...totali.filter((c) => c.has_fatturato).map((c) => Math.abs(c.margine)));

  // Massimo costo tra le categorie per normalizzare le barre delle categorie
  const maxCatCosto = Math.max(1, ...centro.categorie_dettaglio.map((c) => c.costo));

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden" style={{ borderLeftWidth: 3, borderLeftColor: color }}>
      {/* Header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full text-left px-5 py-4 hover:bg-muted/20 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-lg shrink-0">{centro.icona}</span>
          <span className="text-base font-bold w-28 shrink-0" style={{ color }}>{centro.centro}</span>

          {/* 3 colonne metriche con barretta sotto il valore */}
          <div className="flex-1 grid grid-cols-3 gap-6 text-right">
            {/* Costo F&B */}
            <div>
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Costo F&B</p>
              <p className="text-lg font-bold tabular-nums text-orange-600 dark:text-orange-400">
                {formatEuroCompact(centro.costo_totale)}
              </p>
              <p className="text-[11px] tabular-nums text-orange-500/70 dark:text-orange-400/60 mt-0.5">
                {centro.incidenza_su_fb.toFixed(1)}% su tot. F&B
              </p>
              <MiniBar pct={(centro.costo_totale / maxCosto) * 100} color="#f97316" />
            </div>
            {/* Incidenza */}
            <div>
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Incid. Fatturato</p>
              <p className={`text-lg font-bold tabular-nums ${incidenzaColor}`}>
                {centro.has_fatturato ? `${fc.toFixed(1)}%` : "—"}
              </p>
              {centro.has_fatturato
                ? <MiniBar pct={fc} color="#0ea5e9" />
                : <div className="h-1.5 mt-1" />}
            </div>
            {/* Margine */}
            <div>
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Margine</p>
              <p className={`text-lg font-bold tabular-nums ${margineColor}`}>
                {centro.has_fatturato ? formatEuroCompact(centro.margine) : "—"}
              </p>
              {centro.has_fatturato
                ? <MiniBar pct={(Math.abs(centro.margine) / maxMargine) * 100} color={centro.margine >= 0 ? "#22c55e" : "#ef4444"} opacity={0.9} />
                : <div className="h-1.5 mt-1" />}
            </div>
          </div>

          {expanded ? <ChevronUp className="size-5 text-muted-foreground shrink-0 ml-2" /> : <ChevronDown className="size-5 text-muted-foreground shrink-0 ml-2" />}
        </div>
      </button>

      {/* Categorie espanse */}
      {expanded && centro.categorie_dettaglio.length > 0 && (
        <div className="border-t border-border bg-muted/10 px-5 py-3 space-y-0">
          {/* Header colonne */}
          <div className="flex items-center gap-3 pb-2 border-b border-border/50 mb-2">
            <div className="w-7 shrink-0" />
            <div className="w-36 shrink-0" />
            <div className="flex-1 grid grid-cols-3 gap-6 text-right text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
              <span>% costo cat / Costo</span>
              <span>% costo cat / Fatt.</span>
              <span>% costo cat / Marg.</span>
            </div>
            <div className="w-7 shrink-0" />
          </div>

          {centro.categorie_dettaglio.map((cat) => (
            <div key={cat.categoria} className="flex items-center gap-3 py-2 border-b border-border/20 last:border-0">
              <div className="w-7 shrink-0" />
              <span className="text-sm text-muted-foreground w-36 shrink-0 truncate">{cat.categoria}</span>
              <div className="flex-1 grid grid-cols-3 gap-6 items-start">
                {/* Col 1: costo + % su costo centro + barra */}
                <div className="text-right">
                  <p className="text-sm font-semibold tabular-nums text-orange-600 dark:text-orange-400">
                    {formatEuroCompact(cat.costo)}
                  </p>
                  <p className="text-[10px] tabular-nums text-orange-500/70 dark:text-orange-400/60">
                    {centro.costo_totale > 0 ? `${((cat.costo / centro.costo_totale) * 100).toFixed(1)}%` : "—"}
                  </p>
                  <MiniBar pct={(cat.costo / maxCatCosto) * 100} color="#f97316" opacity={0.6} />
                </div>
                {/* Col 2: % su centro + barra blu */}
                <div className="text-right">
                  <p className="text-sm tabular-nums text-sky-600 dark:text-sky-400">
                    {cat.pct_su_centro.toFixed(1)}%
                  </p>
                  <MiniBar pct={cat.pct_su_centro} color="#0ea5e9" opacity={0.65} />
                </div>
                {/* Col 3: peso % sul centro — verde/rosso per semaforo */}
                {(() => {
                  const peso = centro.costo_totale > 0 ? (cat.costo / centro.costo_totale) * 100 : 0;
                  const pesoColor = { text: "text-emerald-600 dark:text-emerald-400", bar: "#22c55e" };
                  return (
                    <div className="text-right">
                      <p className={`text-sm tabular-nums ${pesoColor.text}`}>
                        {centro.costo_totale > 0 ? `${peso.toFixed(1)}%` : "—"}
                      </p>
                      <MiniBar pct={peso} color={pesoColor.bar} opacity={0.7} />
                    </div>
                  );
                })()}
              </div>
              <div className="w-7 shrink-0" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────────
   GRAFICI
   ──────────────────────────────────────────────────────────────────────────── */
function CentriDonutChart({ centri }: { centri: CentroDetailItem[] }) {
  const chartData = centri.map((c) => ({ name: c.centro, value: c.costo_totale, fill: CENTRO_COLOR[c.centro] ?? "#94a3b8" }));
  if (chartData.length === 0) return <p className="text-sm text-muted-foreground py-8 text-center">Nessun costo nel periodo</p>;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie data={chartData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} dataKey="value" stroke="var(--card)" strokeWidth={2}>
          {chartData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
        </Pie>
        <Tooltip formatter={(v: unknown) => formatEuro(typeof v === "number" ? v : 0)} contentStyle={{ fontSize: 12, borderRadius: 8, backgroundColor: "var(--card)", borderColor: "var(--border)", color: "var(--foreground)" }} labelStyle={{ color: "var(--foreground)", fontWeight: 600 }} itemStyle={{ color: "var(--foreground)" }} />
        <Legend wrapperStyle={{ fontSize: 12, color: "var(--foreground)" }} iconType="circle" />
      </PieChart>
    </ResponsiveContainer>
  );
}

/* ────────────────────────────────────────────────────────────────────────────
   DETTAGLIO GIORNALIERO CENTRO
   ──────────────────────────────────────────────────────────────────────────── */
type GiornoFatturatoCentro = {
  data: string;
  fatturato: number;
};

function DettaglioCentroDialog({
  anno, mese, meseLabel, centro, color, centri, onCentroChange, onClose,
}: {
  anno: number;
  mese: number;
  meseLabel: string;
  centro: string;
  color: string;
  centri: CentroDetailItem[];
  onCentroChange: (c: string) => void;
  onClose: () => void;
}) {
  const [giorni, setGiorni] = useState<GiornoFatturatoCentro[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const pad = (n: number) => String(n).padStart(2, "0");
    const lastDay = new Date(anno, mese, 0).getDate();

    // Carica i dati giornalieri per tutti i centri dal mese
    fetch(`/api/margini/fatturato-centri-giorni?anno=${anno}&mese=${mese}`)
      .then((r) => r.ok ? r.json() : [])
      .then((d: { data: string; food: number; beverage: number; alcolici: number; dolci: number; shop: number }[]) => {
        const centroKey = centro.toLowerCase() as "food" | "beverage" | "alcolici" | "dolci" | "shop";
        const byDate = new Map(d.map((row) => [row.data, row[centroKey] ?? 0]));
        const result: GiornoFatturatoCentro[] = [];
        for (let day = 1; day <= lastDay; day++) {
          const key = `${anno}-${pad(mese)}-${pad(day)}`;
          result.push({ data: key, fatturato: byDate.get(key) ?? 0 });
        }
        setGiorni(result);
      })
      .catch(() => setGiorni([]))
      .finally(() => setLoading(false));
  }, [anno, mese, centro]);

  const compilati = giorni.filter((g) => g.fatturato > 0);
  const totale = compilati.reduce((s, g) => s + g.fatturato, 0);
  const media = compilati.length > 0 ? totale / compilati.length : 0;
  const migliore = compilati.reduce<GiornoFatturatoCentro | null>((best, g) => (!best || g.fatturato > best.fatturato) ? g : best, null);
  const peggiore = compilati.reduce<GiornoFatturatoCentro | null>((worst, g) => (!worst || g.fatturato < worst.fatturato) ? g : worst, null);

  const chartData = giorni.map((g) => ({
    giorno: parseInt(g.data.slice(8), 10),
    valore: g.fatturato,
  }));

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent showCloseButton={false} className="!max-w-[min(760px,92vw)] w-full p-0 gap-0">
        <DialogHeader className="px-6 pt-5 pb-4 border-b border-border shrink-0">
          <div className="flex items-center justify-between gap-4">
            <DialogTitle className="flex items-center gap-2 text-base">
              📅 {meseLabel} · Fatturato giornaliero per centro
            </DialogTitle>
            <button onClick={onClose} className="size-8 flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted transition-colors shrink-0">
              <XIcon className="size-4" />
            </button>
          </div>
          {/* Selettore centro */}
          <div className="flex flex-wrap gap-1.5 mt-3">
            {centri.map((c) => {
              const cColor = CENTRO_COLOR[c.centro] ?? "#94a3b8";
              const active = c.centro === centro;
              return (
                <button
                  key={c.centro}
                  onClick={() => onCentroChange(c.centro)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold border transition-colors ${
                    active ? "text-white border-transparent" : "border-input hover:bg-muted"
                  }`}
                  style={active ? { backgroundColor: cColor, borderColor: cColor } : { color: cColor }}
                >
                  <span>{c.icona}</span>
                  {c.centro}
                </button>
              );
            })}
          </div>
        </DialogHeader>

        <div className="px-6 py-5 space-y-5">
          {loading ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Caricamento…</p>
          ) : compilati.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              Nessun dato giornaliero per {meseLabel}.<br />
              <span className="text-xs">Configura la ripartizione per centro tramite &quot;Ripartizione centri&quot;.</span>
            </p>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.4} vertical={false} />
                  <XAxis
                    dataKey="giorno"
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    tickLine={false}
                    axisLine={false}
                    interval={1}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    tickLine={false}
                    axisLine={false}
                    width={52}
                    tickFormatter={(v: number) => formatEuroCompact(v)}
                  />
                  <Tooltip
                    cursor={{ fill: "var(--muted)", opacity: 0.4 }}
                    formatter={(v: unknown) => [formatEuro(typeof v === "number" ? v : 0), `Fatturato ${centro}`]}
                    labelFormatter={(l) => `Giorno ${l}`}
                    contentStyle={{ fontSize: 12, borderRadius: 8, backgroundColor: "var(--card)", borderColor: "var(--border)", color: "var(--foreground)" }}
                    labelStyle={{ color: "var(--foreground)", fontWeight: 600 }}
                    itemStyle={{ color: "var(--foreground)" }}
                  />
                  <Bar dataKey="valore" radius={[3, 3, 0, 0]} maxBarSize={28}>
                    {chartData.map((entry, i) => (
                      <RCell key={i} fill={entry.valore > 0 ? color : "var(--muted)"} opacity={entry.valore > 0 ? 0.9 : 0.3} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatBox label="Giorni compilati" value={`${compilati.length} / ${giorni.length}`} />
                <StatBox label="Media giornaliera" value={formatEuro(media)} color="text-sky-600 dark:text-sky-400" />
                <StatBox
                  label="Giorno migliore"
                  value={migliore ? formatEuro(migliore.fatturato) : "—"}
                  sub={migliore ? `${parseInt(migliore.data.slice(8), 10)} ${meseLabel}` : undefined}
                  color="text-emerald-600 dark:text-emerald-400"
                />
                <StatBox
                  label="Giorno peggiore"
                  value={peggiore ? formatEuro(peggiore.fatturato) : "—"}
                  sub={peggiore ? `${parseInt(peggiore.data.slice(8), 10)} ${meseLabel}` : undefined}
                  color="text-rose-600 dark:text-rose-400"
                />
              </div>
            </>
          )}
        </div>

        <div className="px-6 pb-5 flex justify-end">
          <button onClick={onClose} className="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md border border-border hover:bg-muted transition-colors">
            Chiudi
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function StatBox({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-1">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${color ?? ""}`}>{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

function AndamentoLineChart({ andamento, centri, mode }: { andamento: AndamentoMese[]; centri: CentroDetailItem[]; mode: "euro" | "perc" }) {
  const centriAttivi = centri.filter((c) => c.costo_totale > 0).map((c) => c.centro);
  const chartData = andamento.map((m) => {
    const out: Record<string, number | string> = { label: m.label };
    for (const centro of centriAttivi) {
      const key = centro.toLowerCase() as keyof AndamentoMese;
      const v = (m[key] as number) ?? 0;
      const total = m.food + m.beverage + m.alcolici + m.dolci + m.shop;
      out[centro] = mode === "perc" ? (total > 0 ? Math.round((v / total) * 1000) / 10 : 0) : v;
    }
    return out;
  });
  if (chartData.length === 0 || centriAttivi.length === 0) return <p className="text-sm text-muted-foreground py-8 text-center">Dati insufficienti</p>;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.5} />
        <XAxis dataKey="label" tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={{ stroke: "var(--border)" }} />
        <YAxis tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} width={56} tickFormatter={(v: number) => mode === "perc" ? `${v.toFixed(0)}%` : formatEuroCompact(v)} />
        <Tooltip
          formatter={(value: unknown, name: unknown) => {
            const v = typeof value === "number" ? value : 0;
            return [mode === "perc" ? `${v.toFixed(1)}%` : formatEuro(v), String(name ?? "")];
          }}
          contentStyle={{ fontSize: 12, borderRadius: 8, backgroundColor: "var(--card)", borderColor: "var(--border)", color: "var(--foreground)" }}
          labelStyle={{ color: "var(--muted-foreground)", marginBottom: 4 }}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: "var(--foreground)" }} iconType="circle" />
        {centriAttivi.map((centro) => (
          <Line key={centro} type="monotone" dataKey={centro} stroke={CENTRO_COLOR[centro] ?? "#94a3b8"} strokeWidth={2} dot={{ r: 3, fill: CENTRO_COLOR[centro] ?? "#94a3b8" }} activeDot={{ r: 5, stroke: "var(--card)", strokeWidth: 2 }} name={centro} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
