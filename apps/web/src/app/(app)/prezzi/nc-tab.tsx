"use client";

import { useEffect, useState } from "react";
import { RefreshCw, FileX2, Building2, Euro, FileText } from "lucide-react";
import { toast } from "sonner";
import type { NoteCreditoResponse } from "@/lib/prezzi";

const ANNO_CORRENTE = new Date().getFullYear();
const ANNI = Array.from({ length: 5 }, (_, i) => ANNO_CORRENTE - i);
const MESI = ["Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"];

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

export function NcTab() {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [mese, setMese] = useState<number | null>(null);
  const [data, setData] = useState<NoteCreditoResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [filtroCategoria, setFiltroCategoria] = useState("");
  const [filtroFornitore, setFiltroFornitore] = useState("");

  async function load(a = anno, m = mese) {
    setLoading(true);
    try {
      const { data_da, data_a } = isoDateRange(a, m);
      const qs = new URLSearchParams({ data_da, data_a });
      const res = await fetch(`/api/prezzi/note-credito?${qs}`);
      if (!res.ok) throw new Error();
      setData(await res.json());
    } catch {
      toast.error("Errore nel caricamento dati");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function handleAnno(a: number) { setAnno(a); load(a, mese); }
  function handleMese(m: number | null) { setMese(m); load(anno, m); }

  const note = data?.note ?? [];

  const categorie = Array.from(new Set(note.map((r) => r.categoria).filter(Boolean))).sort();
  const fornitori = Array.from(new Set(note.map((r) => r.fornitore).filter(Boolean))).sort();

  const filtered = note.filter((r) => {
    const matchSearch = !search || r.descrizione.toLowerCase().includes(search.toLowerCase()) || r.fornitore.toLowerCase().includes(search.toLowerCase());
    const matchCat = !filtroCategoria || r.categoria === filtroCategoria;
    const matchForn = !filtroFornitore || r.fornitore === filtroFornitore;
    return matchSearch && matchCat && matchForn;
  });

  const totaleFiltrato = filtered.reduce((acc, r) => acc + r.credito, 0);
  const nDocumentiFiltrati = new Set(filtered.map((r) => r.documento)).size;
  const nFornitori = new Set(filtered.map((r) => r.fornitore)).size;

  const hasFiltri = !!search || !!filtroCategoria || !!filtroFornitore;

  return (
    <div className="space-y-4">
      {/* Filtro periodo */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground">Anno</label>
          <select
            value={anno}
            onChange={(e) => handleAnno(Number(e.target.value))}
            className="rounded border border-border px-2 py-1 text-sm bg-background"
          >
            {ANNI.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div className="flex flex-wrap gap-1">
          <button
            onClick={() => handleMese(null)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
              mese === null
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            }`}
          >
            Tutto l&apos;anno
          </button>
          {MESI.map((label, idx) => (
            <button
              key={idx}
              onClick={() => handleMese(mese === idx + 1 ? null : idx + 1)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                mese === idx + 1
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          onClick={() => load()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          Aggiorna
        </button>
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
            { icon: Euro, label: hasFiltri ? "Totale credito (filtrato)" : "Totale Note di Credito", value: fmtEuro(totaleFiltrato), color: "text-sky-500" },
            { icon: FileX2, label: hasFiltri ? `Righe (filtrate da ${data.note.length})` : "Righe trovate", value: String(filtered.length), color: "text-sky-500" },
            { icon: FileText, label: hasFiltri ? `Documenti (filtrati da ${data.n_documenti})` : "Documenti NC", value: String(nDocumentiFiltrati), color: "text-muted-foreground" },
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
          Nessuna nota di credito per il periodo selezionato
        </p>
      )}

      {/* Tabella */}
      {!loading && data && filtered.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-muted/60">
                {["Data", "Fornitore", "Prodotto", "Categoria", "Q.tà", "Credito", "N. Documento", "File"].map((h) => (
                  <th key={h} className="text-left px-3 py-2 font-semibold border-r last:border-r-0 border-border">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => (
                <tr key={i} className="border-t border-border hover:bg-muted/20 transition-colors">
                  <td className="px-3 py-2 border-r border-border whitespace-nowrap">{fmtData(r.data)}</td>
                  <td className="px-3 py-2 border-r border-border font-medium">{r.fornitore}</td>
                  <td className="px-3 py-2 border-r border-border max-w-[200px] truncate">{r.descrizione}</td>
                  <td className="px-3 py-2 border-r border-border text-muted-foreground">{r.categoria}</td>
                  <td className="px-3 py-2 border-r border-border text-right">
                    {r.quantita !== null ? r.quantita.toFixed(2) : "—"}
                  </td>
                  <td className="px-3 py-2 border-r border-border text-right font-semibold text-sky-600 dark:text-sky-400">
                    {fmtEuro(r.credito)}
                  </td>
                  <td className="px-3 py-2 border-r border-border font-mono text-[11px] whitespace-nowrap">{r.numero_documento || "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground text-[10px] max-w-[140px] truncate">{r.documento}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
