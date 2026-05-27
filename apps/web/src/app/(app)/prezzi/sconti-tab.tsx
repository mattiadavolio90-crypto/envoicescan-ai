"use client";

import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import type { ScontiOmaggiResponse } from "@/lib/prezzi";

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
  return {
    data_da: `${anno}-01-01`,
    data_a: `${anno}-12-31`,
  };
}

export function ScontiTab() {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [data, setData] = useState<ScontiOmaggiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");

  async function load() {
    setLoading(true);
    try {
      const { data_da, data_a } = isoDateRange(anno);
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

  const items = data?.items ?? [];
  const filtered = search
    ? items.filter(
        (r) =>
          r.descrizione.toLowerCase().includes(search.toLowerCase()) ||
          r.fornitore.toLowerCase().includes(search.toLowerCase()),
      )
    : items;

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
              { label: "Totale Sconti + Omaggi", value: fmtEuro(data.totale_risparmiato) },
              { label: "Sconti ricevuti", value: String(data.n_sconti) },
              { label: "Omaggi ricevuti", value: String(data.n_omaggi) },
            ].map((k) => (
              <div key={k.label} className="rounded-md border border-border p-3 bg-card">
                <p className="text-xs text-muted-foreground">{k.label}</p>
                <p className="text-base font-bold mt-0.5">{k.value}</p>
              </div>
            ))}
          </div>

          <input
            type="text"
            placeholder="Cerca prodotto o fornitore…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full max-w-sm rounded-md border border-border px-3 py-1.5 text-sm bg-background"
          />

          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              Nessuno sconto o omaggio per il periodo selezionato
            </p>
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="bg-muted/60">
                    {["Tipo", "Prodotto", "Categoria", "Fornitore", "Q.tà", "Valore", "Data", "Documento"].map((h) => (
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
                          {r.tipo === "sconto" ? "💸 Sconto" : "🎁 Omaggio"}
                        </span>
                      </td>
                      <td className="px-3 py-2 border-r border-border max-w-[180px] truncate">{r.descrizione}</td>
                      <td className="px-3 py-2 border-r border-border text-muted-foreground">{r.categoria}</td>
                      <td className="px-3 py-2 border-r border-border">{r.fornitore}</td>
                      <td className="px-3 py-2 border-r border-border text-right">
                        {r.quantita !== null ? r.quantita.toFixed(2) : "—"}
                      </td>
                      <td className="px-3 py-2 border-r border-border text-right font-medium text-emerald-600">
                        {r.tipo === "sconto" ? fmtEuro(r.valore) : "—"}
                      </td>
                      <td className="px-3 py-2 border-r border-border whitespace-nowrap">{fmtData(r.data)}</td>
                      <td className="px-3 py-2 text-muted-foreground text-[10px] max-w-[140px] truncate">{r.fattura}</td>
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
