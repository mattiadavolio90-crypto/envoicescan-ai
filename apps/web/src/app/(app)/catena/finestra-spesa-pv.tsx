"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Download } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { type SpesaPivot } from "@/lib/gruppo";

const MESI = [
  "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
];

function euro(n: number): string {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n);
}

// Heatmap a token di tema (dark/light-safe): intensità sfondo dalla frazione
// della cella sul massimo della pivot. Usa la primary con alpha → contrasto su
// entrambi i temi, niente colori hardcoded.
function cellStyle(v: number, max: number): React.CSSProperties {
  if (max <= 0 || v <= 0) return {};
  const a = 0.06 + (v / max) * 0.34;
  return { backgroundColor: `color-mix(in oklab, var(--primary) ${Math.round(a * 100)}%, transparent)` };
}

export function FinestraSpesaPV({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [dimensione, setDimensione] = useState<"categoria" | "fornitore">("categoria");
  // Periodo: "anno" = anno in corso (default), oppure un mese (1-12) dell'anno in corso.
  const [periodo, setPeriodo] = useState<string>("anno");
  const [data, setData] = useState<SpesaPivot | null>(null);
  const [loading, setLoading] = useState(false);
  const reqRef = useRef(0);

  const annoCorrente = new Date().getFullYear();
  const meseCorrente = new Date().getMonth() + 1; // 1-12

  useEffect(() => {
    if (!open) return;
    const my = ++reqRef.current;
    setLoading(true);
    const qs = new URLSearchParams({ dimensione });
    if (periodo !== "anno") {
      const m = Number(periodo);
      const ultimo = new Date(annoCorrente, m, 0).getDate(); // ultimo giorno del mese
      qs.set("data_da", `${annoCorrente}-${String(m).padStart(2, "0")}-01`);
      qs.set("data_a", `${annoCorrente}-${String(m).padStart(2, "0")}-${String(ultimo).padStart(2, "0")}`);
    }
    fetch(`/api/gruppo/spesa-pivot?${qs.toString()}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => {
        if (my === reqRef.current) setData(j);
      })
      .catch(() => {
        if (my === reqRef.current) toast.error("Errore nel caricamento della spesa per PV");
      })
      .finally(() => {
        if (my === reqRef.current) setLoading(false);
      });
  }, [open, dimensione, periodo, annoCorrente]);

  const maxCell = data
    ? Math.max(0, ...data.rows.flatMap((r) => data.pv.map((p) => r.per_pv[p.id] ?? 0)))
    : 0;

  // Export Excel della pivot (xlsx lazy: libreria pesante, solo al click).
  async function exportXls() {
    if (!data) return;
    const XLSX = await import("xlsx");
    const dimLabel = data.dimensione === "fornitore" ? "Fornitore" : "Categoria";
    const header = [dimLabel, ...data.pv.map((p) => p.nome), "Totale", "%"];
    const rows = data.rows.map((r) => {
      const row: Record<string, string | number> = { [dimLabel]: r.dim_val };
      data.pv.forEach((p) => {
        row[p.nome] = Math.round((r.per_pv[p.id] ?? 0) * 100) / 100;
      });
      row["Totale"] = Math.round(r.totale * 100) / 100;
      row["%"] = `${r.incidenza_pct.toFixed(1)}%`;
      return row;
    });
    const totaleRow: Record<string, string | number> = { [dimLabel]: "TOTALE" };
    data.pv.forEach((p) => {
      totaleRow[p.nome] = Math.round((data.totali_pv[p.id] ?? 0) * 100) / 100;
    });
    totaleRow["Totale"] = Math.round(data.grand_total * 100) / 100;
    totaleRow["%"] = "100%";
    const ws = XLSX.utils.json_to_sheet([...rows, totaleRow], { header });
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, dimLabel.slice(0, 31));
    // Nome file coerente col periodo selezionato (es. spesa_per_pv_categoria_giugno-2026.xlsx).
    const periodoSlug = (data.periodo_label || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    XLSX.writeFile(wb, `spesa_per_pv_${data.dimensione}_${periodoSlug || new Date().toISOString().slice(0, 10)}.xlsx`);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[min(96vw,72rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
            <span>Spesa per punto vendita</span>
            <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
              <NativeSelect
                value={periodo}
                onValueChange={setPeriodo}
                className="h-8 w-40 text-xs"
              >
                <option value="anno">Anno in corso ({annoCorrente})</option>
                {MESI.slice(0, meseCorrente).map((m, i) => (
                  <option key={i + 1} value={String(i + 1)}>
                    {m} {annoCorrente}
                  </option>
                ))}
              </NativeSelect>
              <NativeSelect
                value={dimensione}
                onValueChange={(v) => setDimensione(v as "categoria" | "fornitore")}
                className="h-8 w-36 text-xs"
              >
                <option value="categoria">Per categoria</option>
                <option value="fornitore">Per fornitore</option>
              </NativeSelect>
              <button
                type="button"
                onClick={exportXls}
                disabled={!data || data.rows.length === 0}
                className="inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-xs font-medium transition-colors hover:bg-accent disabled:opacity-50"
              >
                <Download className="size-3.5" />
                Esporta
              </button>
            </span>
          </DialogTitle>
        </DialogHeader>

        <div className="max-h-[calc(90vh-5rem)] overflow-auto px-5 pb-5">
          {loading && !data ? (
            <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
          ) : !data || data.rows.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              Nessuna spesa nel periodo.
            </div>
          ) : (
            <table className="w-full border-separate border-spacing-0 text-sm">
              <thead className="sticky top-0 z-10 bg-popover">
                <tr>
                  <th className="sticky left-0 z-20 bg-popover px-3 py-2 text-left font-semibold">
                    {data.dimensione === "fornitore" ? "Fornitore" : "Categoria"}
                  </th>
                  {data.pv.map((p) => (
                    <th key={p.id} className="px-3 py-2 text-right font-semibold">
                      <span className="block max-w-[10rem] truncate">{p.nome}</span>
                    </th>
                  ))}
                  <th className="px-3 py-2 text-right font-semibold">Totale</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => {
                  // PV più caro della riga: lo evidenziamo solo se almeno 2 PV hanno
                  // speso (altrimenti "il più caro" è ovvio e diventa rumore).
                  const conSpesa = data.pv.filter((p) => (row.per_pv[p.id] ?? 0) > 0);
                  const maxPvId =
                    conSpesa.length >= 2
                      ? conSpesa.reduce((a, b) => ((row.per_pv[b.id] ?? 0) > (row.per_pv[a.id] ?? 0) ? b : a)).id
                      : null;
                  return (
                  <tr key={row.dim_val} className="border-t">
                    <td className="sticky left-0 z-10 max-w-[14rem] truncate bg-popover px-3 py-2 font-medium">
                      {row.emoji ? <span className="mr-1.5">{row.emoji}</span> : null}
                      {row.dim_val}
                    </td>
                    {data.pv.map((p) => {
                      const v = row.per_pv[p.id] ?? 0;
                      const isMax = p.id === maxPvId;
                      return (
                        <td
                          key={p.id}
                          style={cellStyle(v, maxCell)}
                          className={cn(
                            "px-3 py-2 text-right tabular-nums",
                            isMax && "font-semibold text-primary",
                          )}
                          title={isMax ? "Punto vendita che spende di più in questa voce" : undefined}
                        >
                          {v > 0 ? (
                            <>
                              {isMax && <span className="mr-1 text-[0.65rem] align-middle">▲</span>}
                              {euro(v)}
                            </>
                          ) : (
                            <span className="text-muted-foreground/40">—</span>
                          )}
                        </td>
                      );
                    })}
                    {/* Totale riga: valore assoluto con l'incidenza % sotto. */}
                    <td className="px-3 py-2 text-right tabular-nums">
                      <span className="block font-semibold">{euro(row.totale)}</span>
                      <span className="block text-xs text-muted-foreground">
                        {row.incidenza_pct.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%
                      </span>
                    </td>
                  </tr>
                  );
                })}
                {/* Riga TOTALE per PV */}
                <tr className="border-t-2 border-foreground/20 font-semibold">
                  <td className="sticky left-0 z-10 bg-popover px-3 py-2">Totale</td>
                  {data.pv.map((p) => {
                    const tot = data.totali_pv[p.id] ?? 0;
                    const inc = data.grand_total > 0 ? (tot / data.grand_total) * 100 : 0;
                    return (
                      <td key={p.id} className="px-3 py-2 text-right tabular-nums">
                        <span className="block">{euro(tot)}</span>
                        <span className="block text-xs font-normal text-muted-foreground">
                          {inc.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%
                        </span>
                      </td>
                    );
                  })}
                  <td className="px-3 py-2 text-right tabular-nums">
                    <span className="block">{euro(data.grand_total)}</span>
                    <span className="block text-xs font-normal text-muted-foreground">100%</span>
                  </td>
                </tr>
              </tbody>
            </table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
