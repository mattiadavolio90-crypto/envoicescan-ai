"use client";

import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import type { NoteCreditoResponse } from "@/lib/prezzi";

const ANNO_CORRENTE = new Date().getFullYear();

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

function isoDateRange(anno: number): { data_da: string; data_a: string } {
  return { data_da: `${anno}-01-01`, data_a: `${anno}-12-31` };
}

export function NcTab() {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [data, setData] = useState<NoteCreditoResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [fornitore, setFornitore] = useState("Tutti");

  async function load() {
    setLoading(true);
    try {
      const { data_da, data_a } = isoDateRange(anno);
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

  const note = data?.note ?? [];

  const fornitori = ["Tutti", ...Array.from(new Set(note.map((r) => r.fornitore).filter(Boolean))).sort()];

  const filtered = note.filter((r) => {
    const matchSearch =
      !search ||
      r.descrizione.toLowerCase().includes(search.toLowerCase()) ||
      r.fornitore.toLowerCase().includes(search.toLowerCase());
    const matchForn = fornitore === "Tutti" || r.fornitore === fornitore;
    return matchSearch && matchForn;
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
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
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          Carica
        </button>
      </div>

      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {[
              { label: "Totale Note di Credito", value: fmtEuro(data.totale_credito) },
              { label: "Righe trovate", value: String(data.note.length) },
              { label: "Documenti", value: String(data.n_documenti) },
            ].map((k) => (
              <div key={k.label} className="rounded-md border border-border p-3 bg-card">
                <p className="text-xs text-muted-foreground">{k.label}</p>
                <p className="text-base font-bold mt-0.5">{k.value}</p>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            <input
              type="text"
              placeholder="Cerca descrizione…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="rounded-md border border-border px-3 py-1.5 text-sm bg-background w-48"
            />
            <select
              value={fornitore}
              onChange={(e) => setFornitore(e.target.value)}
              className="rounded border border-border px-2 py-1.5 text-sm bg-background"
            >
              {fornitori.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>

          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              Nessuna nota di credito per il periodo selezionato
            </p>
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="bg-muted/60">
                    {["Documento", "Data", "Fornitore", "Descrizione", "Categoria", "Q.tà", "Credito"].map((h) => (
                      <th key={h} className="text-left px-3 py-2 font-semibold border-r last:border-r-0 border-border">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r, i) => (
                    <tr key={i} className="border-t border-border hover:bg-muted/20 transition-colors">
                      <td className="px-3 py-2 border-r border-border text-[10px] text-muted-foreground max-w-[130px] truncate">
                        {r.documento}
                      </td>
                      <td className="px-3 py-2 border-r border-border whitespace-nowrap">{fmtData(r.data)}</td>
                      <td className="px-3 py-2 border-r border-border">{r.fornitore}</td>
                      <td className="px-3 py-2 border-r border-border max-w-[200px] truncate">{r.descrizione}</td>
                      <td className="px-3 py-2 border-r border-border text-muted-foreground">{r.categoria}</td>
                      <td className="px-3 py-2 border-r border-border text-right">
                        {r.quantita !== null ? r.quantita.toFixed(2) : "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-semibold text-sky-600">
                        {fmtEuro(r.credito)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
