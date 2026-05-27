"use client";

import { useState, useEffect, useTransition } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight, RefreshCw, Save } from "lucide-react";
import { toast } from "sonner";
import type { AnalisiCentriResponse } from "@/lib/margini";

const MESI_NOMI = [
  "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
];
const MESI_SHORT = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];
const ANNO_CORRENTE = new Date().getFullYear();

type CentroKey = "food" | "beverage" | "alcolici" | "dolci";

const CENTRI_CONFIG: { key: CentroKey; label: string }[] = [
  { key: "food",     label: "FOOD"     },
  { key: "beverage", label: "BEVERAGE" },
  { key: "alcolici", label: "ALCOLICI" },
  { key: "dolci",    label: "DOLCI"    },
];

type CentroSplit = {
  fatturato_food: number;
  fatturato_beverage: number;
  fatturato_alcolici: number;
  fatturato_dolci: number;
};

function emptySplit(): CentroSplit {
  return { fatturato_food: 0, fatturato_beverage: 0, fatturato_alcolici: 0, fatturato_dolci: 0 };
}

function fmt(v: number): string {
  if (v === 0) return "—";
  return new Intl.NumberFormat("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(
    Math.round(v),
  );
}

function fmtEuro(v: number): string {
  if (v === 0) return "—";
  const sign = v < 0 ? "-" : "";
  return `${sign}€ ${new Intl.NumberFormat("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(
    Math.abs(Math.round(v)),
  )}`;
}

function fmtPct(v: number): string {
  return v === 0 ? "—" : `${v.toFixed(1)}%`;
}

type Props = { anno: number };

export function AnalisiTab({ anno }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [, startNav] = useTransition();

  const [meseInizio, setMeseInizio] = useState(1);
  const [meseFine, setMeseFine] = useState(12);
  const [splits, setSplits] = useState<Record<number, CentroSplit>>({});
  const [splitsLoading, setSplitsLoading] = useState(false);
  const [splitsDirty, setSplitsDirty] = useState(false);
  const [splitsSaving, setSplitsSaving] = useState(false);
  const [analysis, setAnalysis] = useState<AnalisiCentriResponse | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);

  function changeAnno(newAnno: number) {
    const params = new URLSearchParams(sp.toString());
    params.set("anno", String(newAnno));
    startNav(() => router.push(`${pathname}?${params.toString()}`));
  }

  useEffect(() => {
    let cancelled = false;
    setSplitsLoading(true);
    setSplitsDirty(false);
    setAnalysis(null);

    Promise.all(
      Array.from({ length: 12 }, (_, i) =>
        fetch(`/api/margini/fatturato-centri?anno=${anno}&mese=${i + 1}`)
          .then(r => (r.ok ? r.json() : null))
          .catch(() => null),
      ),
    ).then(results => {
      if (cancelled) return;
      const next: Record<number, CentroSplit> = {};
      results.forEach((r, i) => {
        next[i + 1] = r
          ? {
              fatturato_food:      r.fatturato_food      ?? 0,
              fatturato_beverage:  r.fatturato_beverage  ?? 0,
              fatturato_alcolici:  r.fatturato_alcolici  ?? 0,
              fatturato_dolci:     r.fatturato_dolci     ?? 0,
            }
          : emptySplit();
      });
      setSplits(next);
      setSplitsLoading(false);
    });

    return () => { cancelled = true; };
  }, [anno]);

  function updateSplit(mese: number, key: CentroKey, raw: string) {
    const val = raw === "" ? 0 : parseFloat(raw.replace(",", ".")) || 0;
    const dbKey = `fatturato_${key}` as keyof CentroSplit;
    setSplits(prev => ({
      ...prev,
      [mese]: { ...(prev[mese] ?? emptySplit()), [dbKey]: val },
    }));
    setSplitsDirty(true);
  }

  async function saveSplits() {
    setSplitsSaving(true);
    try {
      const months = Array.from({ length: meseFine - meseInizio + 1 }, (_, i) => meseInizio + i);
      await Promise.all(
        months.map(m =>
          fetch("/api/margini/fatturato-centri", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ anno, mese: m, ...(splits[m] ?? emptySplit()) }),
          }),
        ),
      );
      setSplitsDirty(false);
      toast.success("Ripartizioni salvate");
    } catch {
      toast.error("Errore nel salvataggio");
    } finally {
      setSplitsSaving(false);
    }
  }

  async function loadAnalysis() {
    setAnalysisLoading(true);
    try {
      const pad = (n: number) => String(n).padStart(2, "0");
      const data_da = `${anno}-${pad(meseInizio)}-01`;
      const lastDay = new Date(anno, meseFine, 0).getDate();
      const data_a = `${anno}-${pad(meseFine)}-${lastDay}`;

      const res = await fetch(
        `/api/margini/analisi-centri?data_da=${encodeURIComponent(data_da)}&data_a=${encodeURIComponent(data_a)}`,
      );
      if (!res.ok) throw new Error();
      setAnalysis(await res.json());
    } catch {
      toast.error("Errore nel caricamento analisi");
    } finally {
      setAnalysisLoading(false);
    }
  }

  const visibleMonths = Array.from(
    { length: meseFine - meseInizio + 1 },
    (_, i) => meseInizio + i,
  );

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => changeAnno(anno - 1)}
            className="size-7 flex items-center justify-center rounded border border-border hover:bg-muted transition-colors"
          >
            <ChevronLeft className="size-4" />
          </button>
          <span className="text-lg font-bold w-14 text-center">{anno}</span>
          <button
            onClick={() => changeAnno(anno + 1)}
            disabled={anno >= ANNO_CORRENTE}
            className="size-7 flex items-center justify-center rounded border border-border hover:bg-muted transition-colors disabled:opacity-40"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Da</span>
          <select
            value={meseInizio}
            onChange={e => setMeseInizio(Number(e.target.value))}
            className="rounded border border-border px-2 py-1 text-sm bg-background"
          >
            {MESI_NOMI.map((m, i) => (
              <option key={i + 1} value={i + 1} disabled={i + 1 > meseFine}>
                {m}
              </option>
            ))}
          </select>
          <span className="text-xs text-muted-foreground">a</span>
          <select
            value={meseFine}
            onChange={e => setMeseFine(Number(e.target.value))}
            className="rounded border border-border px-2 py-1 text-sm bg-background"
          >
            {MESI_NOMI.map((m, i) => (
              <option key={i + 1} value={i + 1} disabled={i + 1 < meseInizio}>
                {m}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={loadAnalysis}
          disabled={analysisLoading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`size-3.5 ${analysisLoading ? "animate-spin" : ""}`} />
          Analizza Periodo
        </button>
      </div>

      {/* Revenue splits */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Ripartizione Ricavi per Centro</h2>
          <button
            onClick={saveSplits}
            disabled={splitsSaving || !splitsDirty || splitsLoading}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md border border-border hover:bg-muted disabled:opacity-50 transition-colors"
          >
            <Save className="size-3" />
            {splitsSaving ? "Salvataggio…" : "Salva Ripartizioni"}
          </button>
        </div>

        {splitsLoading ? (
          <div className="h-24 flex items-center justify-center text-sm text-muted-foreground">
            Caricamento…
          </div>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="min-w-max text-xs border-collapse">
              <thead>
                <tr className="bg-muted/60">
                  <th className="sticky left-0 z-10 bg-muted/80 text-left px-3 py-2 font-semibold border-r border-border min-w-[120px]">
                    Centro
                  </th>
                  {visibleMonths.map(m => (
                    <th
                      key={m}
                      className="text-center px-1 py-2 font-semibold border-r border-border min-w-[88px]"
                    >
                      {MESI_SHORT[m - 1]}
                    </th>
                  ))}
                  <th className="text-center px-2 py-2 font-semibold bg-muted min-w-[100px]">TOT</th>
                </tr>
              </thead>
              <tbody>
                {CENTRI_CONFIG.map(({ key, label }) => {
                  const dbKey = `fatturato_${key}` as keyof CentroSplit;
                  const tot = visibleMonths.reduce((acc, m) => acc + (splits[m]?.[dbKey] ?? 0), 0);
                  return (
                    <tr key={key} className="border-t border-border">
                      <td className="sticky left-0 z-10 bg-background px-3 py-1.5 border-r border-border font-medium whitespace-nowrap">
                        {label}
                      </td>
                      {visibleMonths.map(m => {
                        const val = splits[m]?.[dbKey] ?? 0;
                        return (
                          <td key={m} className="border-r border-border p-0">
                            <input
                              type="number"
                              step="1"
                              min="0"
                              value={val === 0 ? "" : val}
                              placeholder="0"
                              onChange={e => updateSplit(m, key, e.target.value)}
                              className="w-full h-full px-2 py-1.5 text-right bg-transparent border-0 outline-none focus:bg-sky-50 dark:focus:bg-sky-950/20 focus:ring-inset focus:ring-1 focus:ring-sky-400 text-xs"
                            />
                          </td>
                        );
                      })}
                      <td className="text-right px-2 py-1.5 font-medium bg-muted/40 text-muted-foreground">
                        {fmt(tot)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Analysis results */}
      {analysis && (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold">Analisi per Centri di Produzione</h2>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "Fatturato Netto", value: fmtEuro(analysis.fatturato_netto_periodo), color: "" },
              { label: "Costi F&B Totali", value: fmtEuro(analysis.totale_costi_fb), color: "text-rose-600" },
              {
                label: "1° Margine",
                value: fmtEuro(analysis.primo_margine),
                color: analysis.primo_margine >= 0 ? "text-emerald-600" : "text-rose-600",
              },
              {
                label: "1° Margine %",
                value: fmtPct(analysis.primo_margine_pct),
                color:
                  analysis.primo_margine_pct >= 67
                    ? "text-emerald-600"
                    : analysis.primo_margine_pct >= 60
                    ? "text-amber-600"
                    : "text-rose-600",
              },
            ].map(k => (
              <div key={k.label} className="rounded-md border border-border p-3 bg-card">
                <p className="text-xs text-muted-foreground">{k.label}</p>
                <p className={`text-base font-bold mt-0.5 ${k.color}`}>{k.value}</p>
              </div>
            ))}
          </div>

          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="bg-muted/60">
                  <th className="text-left px-3 py-2 font-semibold border-r border-border">Centro</th>
                  <th className="text-left px-3 py-2 font-semibold border-r border-border text-muted-foreground">
                    Categorie
                  </th>
                  <th className="text-right px-3 py-2 font-semibold border-r border-border">Costo F&B</th>
                  <th className="text-right px-3 py-2 font-semibold border-r border-border">Fatturato</th>
                  <th className="text-right px-3 py-2 font-semibold border-r border-border">Margine</th>
                  <th className="text-right px-3 py-2 font-semibold border-r border-border">% su Fatt.</th>
                  <th className="text-right px-3 py-2 font-semibold">% su F&B tot.</th>
                </tr>
              </thead>
              <tbody>
                {analysis.centri.map(c => (
                  <tr key={c.centro} className="border-t border-border hover:bg-muted/20 transition-colors">
                    <td className="px-3 py-2 font-semibold border-r border-border whitespace-nowrap">
                      {c.centro}
                    </td>
                    <td className="px-3 py-2 border-r border-border text-muted-foreground max-w-[200px]">
                      {c.categorie.join(", ")}
                    </td>
                    <td className="text-right px-3 py-2 border-r border-border">{fmtEuro(c.costo_totale)}</td>
                    <td className="text-right px-3 py-2 border-r border-border">{fmtEuro(c.fatturato)}</td>
                    <td
                      className={`text-right px-3 py-2 border-r border-border font-semibold ${
                        c.margine >= 0 ? "text-emerald-600" : "text-rose-600"
                      }`}
                    >
                      {fmtEuro(c.margine)}
                    </td>
                    <td
                      className={`text-right px-3 py-2 border-r border-border ${
                        c.incidenza_su_fatt <= 30
                          ? "text-emerald-600"
                          : c.incidenza_su_fatt <= 35
                          ? "text-amber-600"
                          : "text-rose-600"
                      }`}
                    >
                      {fmtPct(c.incidenza_su_fatt)}
                    </td>
                    <td className="text-right px-3 py-2 text-muted-foreground">
                      {fmtPct(c.incidenza_su_fb)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {analysis.mesi_con_dati.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Mesi con dati: {analysis.mesi_con_dati.map(m => MESI_SHORT[m - 1]).join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
