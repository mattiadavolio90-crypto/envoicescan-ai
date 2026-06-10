"use client";

import React, { useEffect, useState } from "react";
import { RefreshCw, Tag, Gift, Building2, Euro, Calendar, Settings2 } from "lucide-react";
import { toast } from "sonner";
import type { ScontiOmaggiResponse } from "@/lib/prezzi";

const ANNO_CORRENTE = new Date().getFullYear();
const MESI_FULL = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];

type PeriodoPreset = "anno_corrente" | "mese_specifico" | "personalizzato";

function fmtItDate(iso: string) {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y.slice(2)}`;
}

function fmtEuro(v: number): string {
  if (v === 0) return "—";
  return `€ ${new Intl.NumberFormat("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)}`;
}

function fmtData(s: string): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

function isoDateRange(anno: number, mese: number | null): { data_da: string; data_a: string } {
  if (mese === null) return { data_da: `${anno}-01-01`, data_a: `${anno}-12-31` };
  const mm = String(mese).padStart(2, "0");
  const lastDay = new Date(anno, mese, 0).getDate();
  return { data_da: `${anno}-${mm}-01`, data_a: `${anno}-${mm}-${lastDay}` };
}

export function ScontiTab() {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [mese, setMese] = useState<number | null>(null);
  const [preset, setPreset] = useState<PeriodoPreset>("anno_corrente");
  const [dataDaCustom, setDataDaCustom] = useState("");
  const [dataACustom, setDataACustom] = useState("");
  const [showMese, setShowMese] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [data, setData] = useState<ScontiOmaggiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [filtroCategoria, setFiltroCategoria] = useState("");
  const [filtroFornitore, setFiltroFornitore] = useState("");

  async function load(da?: string, a?: string) {
    setLoading(true);
    try {
      let data_da: string;
      let data_a: string;
      if (da && a) {
        data_da = da; data_a = a;
      } else {
        const r = isoDateRange(anno, mese);
        data_da = r.data_da; data_a = r.data_a;
      }
      const qs = new URLSearchParams({ data_da, data_a });
      const res = await fetch(`/api/prezzi/sconti-omaggi?${qs}`);
      if (!res.ok) throw new Error();
      setData(await res.json());
    } catch {
      toast.error("Errore nel caricamento dati");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function applyAnno() {
    setPreset("anno_corrente");
    setMese(null);
    setShowMese(false);
    setShowCustom(false);
    const r = isoDateRange(ANNO_CORRENTE, null);
    setAnno(ANNO_CORRENTE);
    load(r.data_da, r.data_a);
  }

  function applyMese(yearMonth: string) {
    if (!yearMonth) return;
    const [y, m] = yearMonth.split("-").map(Number);
    setAnno(y);
    setMese(m);
    setPreset("mese_specifico");
    const r = isoDateRange(y, m);
    load(r.data_da, r.data_a);
  }

  function applyCustom(da: string, a: string) {
    if (!da || !a) return;
    setPreset("personalizzato");
    load(da, a);
  }

  const items = data?.items ?? [];

  const categorie = Array.from(new Set(items.map((r) => r.categoria).filter(Boolean))).sort();
  const fornitori = Array.from(new Set(items.map((r) => r.fornitore).filter(Boolean))).sort();

  const filtered = items.filter((r) => {
    const matchSearch = !search || r.descrizione.toLowerCase().includes(search.toLowerCase()) || r.fornitore.toLowerCase().includes(search.toLowerCase());
    const matchCat = !filtroCategoria || r.categoria === filtroCategoria;
    const matchForn = !filtroFornitore || r.fornitore === filtroFornitore;
    return matchSearch && matchCat && matchForn;
  });

  const nSconti = filtered.filter((r) => r.tipo === "sconto").length;
  const nOmaggi = filtered.filter((r) => r.tipo === "omaggio").length;
  const totaleRisparmiato = filtered.filter((r) => r.tipo === "sconto").reduce((acc, r) => acc + r.valore, 0);
  const nFornitori = new Set(filtered.map((r) => r.fornitore)).size;

  const hasFiltri = !!search || !!filtroCategoria || !!filtroFornitore;

  return (
    <div className="space-y-4">
      {/* Filtro periodo */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {/* Chip preset */}
          {(["anno_corrente", "mese_specifico", "personalizzato"] as PeriodoPreset[]).map((p) => {
            const labels: Record<PeriodoPreset, React.ReactNode> = {
              anno_corrente: "Anno in corso",
              mese_specifico: <><Calendar className="size-3 inline mr-1" />Seleziona mese</>,
              personalizzato: <><Settings2 className="size-3 inline mr-1" />Personalizzato</>,
            };
            const chipBase = "px-3 py-1.5 text-xs font-medium rounded-full border transition-colors inline-flex items-center gap-1";
            const chipActive = "bg-primary text-primary-foreground border-primary";
            const chipIdle = "bg-background border-input hover:bg-muted";
            return (
              <button
                key={p}
                onClick={() => {
                  if (p === "anno_corrente") { applyAnno(); }
                  else if (p === "mese_specifico") { setShowMese(true); setShowCustom(false); setPreset("mese_specifico"); }
                  else { setShowCustom(true); setShowMese(false); setPreset("personalizzato"); }
                }}
                className={`${chipBase} ${preset === p ? chipActive : chipIdle}`}
              >
                {labels[p]}
              </button>
            );
          })}
          {preset === "personalizzato" && dataDaCustom && dataACustom && (
            <span className="ml-2 text-xs font-medium text-sky-500 dark:text-sky-400">
              {fmtItDate(dataDaCustom)} → {fmtItDate(dataACustom)}
            </span>
          )}
          <button
            onClick={() => load()}
            disabled={loading}
            className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
            Aggiorna
          </button>
        </div>

        {/* Select mese */}
        {showMese && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Mese:</span>
            <select
              value={mese != null ? `${anno}-${String(mese).padStart(2, "0")}` : ""}
              onChange={(e) => applyMese(e.target.value)}
              className="h-7 text-xs rounded-md border border-input bg-background px-2"
            >
              <option value="" disabled>Seleziona un mese</option>
              {Array.from({ length: 4 }, (_, i) => ANNO_CORRENTE - i).flatMap((y) =>
                MESI_FULL.map((label, mi) => {
                  const val = `${y}-${String(mi + 1).padStart(2, "0")}`;
                  return <option key={val} value={val}>{label} {y}</option>;
                })
              )}
            </select>
          </div>
        )}

        {/* Range personalizzato */}
        {showCustom && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Dal</span>
            <input
              type="date"
              value={dataDaCustom}
              onChange={(e) => { setDataDaCustom(e.target.value); applyCustom(e.target.value, dataACustom); }}
              className="h-7 text-xs rounded-md border border-input bg-background px-2 w-36"
            />
            <span className="text-xs text-muted-foreground">al</span>
            <input
              type="date"
              value={dataACustom}
              onChange={(e) => { setDataACustom(e.target.value); applyCustom(dataDaCustom, e.target.value); }}
              className="h-7 text-xs rounded-md border border-input bg-background px-2 w-36"
            />
          </div>
        )}
      </div>

      {/* Filtri secondari */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          placeholder="Cerca prodotto o fornitore…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded-md border border-border px-3 py-1.5 text-sm bg-background w-52"
        />
        <select
          value={filtroCategoria}
          onChange={(e) => setFiltroCategoria(e.target.value)}
          className="rounded border border-border px-2 py-1.5 text-sm bg-background"
        >
          <option value="">Tutte le categorie</option>
          {categorie.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select
          value={filtroFornitore}
          onChange={(e) => setFiltroFornitore(e.target.value)}
          className="rounded border border-border px-2 py-1.5 text-sm bg-background"
        >
          <option value="">Tutti i fornitori</option>
          {fornitori.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        {hasFiltri && (
          <button
            onClick={() => { setSearch(""); setFiltroCategoria(""); setFiltroFornitore(""); }}
            className="px-2.5 py-1.5 text-xs rounded-md border border-border text-muted-foreground hover:bg-muted transition-colors"
          >
            Azzera filtri
          </button>
        )}
      </div>

      {/* Banner KPI */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { icon: Euro, label: "Risparmiato (sconti)", value: fmtEuro(totaleRisparmiato), color: "text-emerald-500" },
            { icon: Tag, label: hasFiltri ? `Sconti (filtrati da ${data.n_sconti})` : "Sconti ricevuti", value: String(nSconti), color: "text-emerald-500" },
            { icon: Gift, label: hasFiltri ? `Omaggi (filtrati da ${data.n_omaggi})` : "Omaggi ricevuti", value: String(nOmaggi), color: "text-sky-500" },
            { icon: Building2, label: "Fornitori", value: String(nFornitori), color: "text-muted-foreground" },
          ].map((k) => (
            <div key={k.label} className="rounded-md border border-border p-3 bg-card flex items-start gap-2">
              <k.icon className={`size-4 mt-0.5 shrink-0 ${k.color}`} />
              <div>
                <p className="text-xs text-muted-foreground leading-tight">{k.label}</p>
                <p className="text-base font-bold mt-0.5">{k.value}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Stato vuoto / loading */}
      {loading && (
        <div className="flex items-center justify-center py-16 text-muted-foreground text-sm gap-2">
          <RefreshCw className="size-4 animate-spin" />
          Caricamento…
        </div>
      )}

      {!loading && !data && (
        <p className="text-sm text-muted-foreground py-12 text-center">
          Seleziona il periodo e premi Aggiorna
        </p>
      )}

      {!loading && data && filtered.length === 0 && (
        <p className="text-sm text-muted-foreground py-8 text-center">
          Nessuno sconto o omaggio per il periodo selezionato
        </p>
      )}

      {/* Tabella */}
      {!loading && data && filtered.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-muted/60">
                {["Tipo", "Prodotto", "Categoria", "Fornitore", "Q.tà", "Valore", "Data", "N. Documento", "File"].map((h) => (
                  <th key={h} className="text-left px-3 py-2 font-semibold border-r last:border-r-0 border-border">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => (
                <tr key={i} className="border-t border-border hover:bg-muted/20 transition-colors">
                  <td className="px-3 py-2 border-r border-border whitespace-nowrap">
                    <span
                      className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                        r.tipo === "sconto"
                          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                          : "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400"
                      }`}
                    >
                      {r.tipo === "sconto" ? "Sconto" : "Omaggio"}
                    </span>
                  </td>
                  <td className="px-3 py-2 border-r border-border max-w-[180px] truncate">{r.descrizione}</td>
                  <td className="px-3 py-2 border-r border-border text-muted-foreground">{r.categoria}</td>
                  <td className="px-3 py-2 border-r border-border">{r.fornitore}</td>
                  <td className="px-3 py-2 border-r border-border text-right">
                    {r.quantita !== null ? r.quantita.toFixed(2) : "—"}
                  </td>
                  <td className="px-3 py-2 border-r border-border text-right font-medium text-emerald-600 dark:text-emerald-400">
                    {r.tipo === "sconto" ? fmtEuro(r.valore) : "—"}
                  </td>
                  <td className="px-3 py-2 border-r border-border whitespace-nowrap">{fmtData(r.data)}</td>
                  <td className="px-3 py-2 border-r border-border font-mono text-[11px] whitespace-nowrap">{r.numero_documento || "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground text-[10px] max-w-[140px] truncate">{r.fattura}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
