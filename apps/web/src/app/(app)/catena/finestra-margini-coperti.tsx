"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowDown, ArrowUp, Download } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/select";
import { type MarginiCoperti, type MarginiCopertiPV } from "@/lib/gruppo";

const MESI = [
  "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
];

function euro(n: number | null): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n);
}
function pct(n: number | null): string {
  if (n == null) return "—";
  return `${n.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`;
}
function num(n: number | null): string {
  if (n == null) return "—";
  return n.toLocaleString("it-IT");
}

// Metriche con la LORO direzione: per €MP/coperto il BASSO è meglio (regola
// catena: NON è sempre "numero alto = verde").
type Col = {
  key: keyof MarginiCopertiPV;
  label: string;
  fmt: (v: number | null) => string;
  altoMeglio: boolean;
  tooltip?: string;
};
const COLS: Col[] = [
  { key: "margine_perc", label: "Margine %", fmt: pct, altoMeglio: true,
    tooltip: "MOL sul fatturato netto: quanto resta dopo food cost, personale e spese." },
  { key: "fatturato", label: "Fatturato", fmt: euro, altoMeglio: true,
    tooltip: "Fatturato al netto dell'IVA (come la pagina Margini del punto vendita)." },
  { key: "coperti", label: "Coperti", fmt: num, altoMeglio: true,
    tooltip: "Numero di coperti serviti nel periodo." },
  { key: "scontrino_medio", label: "Scontrino medio", fmt: euro, altoMeglio: true,
    tooltip: "Fatturato netto diviso i coperti: spesa media per coperto." },
  { key: "mp_per_coperto", label: "€ materia prima / coperto", fmt: euro, altoMeglio: false,
    tooltip: "Quanto costa in materie prime (food & beverage) servire un coperto. Più basso = meglio." },
];

export function FinestraMarginiCoperti({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [data, setData] = useState<MarginiCoperti | null>(null);
  const [loading, setLoading] = useState(false);
  const [periodo, setPeriodo] = useState<string>("anno");
  const [sortKey, setSortKey] = useState<keyof MarginiCopertiPV>("margine_perc");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const reqRef = useRef(0);

  const annoCorrente = new Date().getFullYear();
  const meseCorrente = new Date().getMonth() + 1;

  useEffect(() => {
    if (!open) return;
    const my = ++reqRef.current;
    setLoading(true);
    const qs = periodo !== "anno" ? `?mese=${periodo}` : "";
    fetch(`/api/gruppo/margini-coperti${qs}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => {
        if (my === reqRef.current) setData(j);
      })
      .catch(() => {
        if (my === reqRef.current) toast.error("Errore nel caricamento di margini e coperti");
      })
      .finally(() => {
        if (my === reqRef.current) setLoading(false);
      });
  }, [open, periodo]);

  function toggleSort(k: keyof MarginiCopertiPV) {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir("desc"); }
  }

  // Ordina i PV per la colonna scelta; gli incompleti restano sempre in fondo.
  const righeSorted = [...(data?.righe ?? [])].sort((a, b) => {
    if (a.dati_incompleti !== b.dati_incompleti) return a.dati_incompleti ? 1 : -1;
    const va = a[sortKey] as number | null;
    const vb = b[sortKey] as number | null;
    const na = va == null ? -Infinity : va;
    const nb = vb == null ? -Infinity : vb;
    return sortDir === "desc" ? nb - na : na - nb;
  });

  // Export Excel (xlsx lazy: libreria pesante, solo al click).
  async function exportXls() {
    if (!data) return;
    const XLSX = await import("xlsx");
    const header = ["Punto vendita", ...COLS.map((c) => c.label)];
    const toRow = (r: MarginiCopertiPV): Record<string, string | number> => {
      const row: Record<string, string | number> = { "Punto vendita": r.nome };
      COLS.forEach((c) => {
        const v = r[c.key] as number | null;
        row[c.label] = r.dati_incompleti ? "dati incompleti" : v == null ? "—" : v;
      });
      return row;
    };
    const rows = [...righeSorted.map(toRow), toRow(data.gruppo)];
    const ws = XLSX.utils.json_to_sheet(rows, { header });
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Margini e coperti");
    const slug = (data.periodo_label || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    XLSX.writeFile(wb, `margini_coperti_${slug || new Date().toISOString().slice(0, 10)}.xlsx`);
  }

  // Per ogni colonna, individua best/worst tra i PV con dati (esclude incompleti
  // e valori null). Se c'è un solo PV con dato, niente evidenza (non c'è confronto).
  const completi = (data?.righe ?? []).filter((r) => !r.dati_incompleti);
  const extremes: Record<string, { best: number | null; worst: number | null }> = {};
  for (const col of COLS) {
    const vals = completi
      .map((r) => r[col.key] as number | null)
      .filter((v): v is number => v != null);
    if (vals.length < 2) {
      extremes[col.key] = { best: null, worst: null };
      continue;
    }
    const hi = Math.max(...vals);
    const lo = Math.min(...vals);
    extremes[col.key] = col.altoMeglio ? { best: hi, worst: lo } : { best: lo, worst: hi };
  }

  function cellTone(col: Col, r: MarginiCopertiPV): string {
    if (r.dati_incompleti) return "";
    const v = r[col.key] as number | null;
    if (v == null) return "";
    const ex = extremes[col.key];
    if (ex.best == null) return "";
    if (v === ex.best && v !== ex.worst) return "text-emerald-600 dark:text-emerald-500 font-semibold";
    if (v === ex.worst && v !== ex.best) return "text-rose-600 dark:text-rose-500 font-semibold";
    return "";
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[min(96vw,68rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
            <span>Margini e coperti per punto vendita</span>
            <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
              <NativeSelect value={periodo} onValueChange={setPeriodo} className="h-8 w-40 text-xs">
                <option value="anno">Anno in corso ({annoCorrente})</option>
                {MESI.slice(0, meseCorrente).map((m, i) => (
                  <option key={i + 1} value={String(i + 1)}>{m} {annoCorrente}</option>
                ))}
              </NativeSelect>
              <button
                type="button"
                onClick={exportXls}
                disabled={!data}
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
          ) : !data ? (
            <div className="py-16 text-center text-sm text-muted-foreground">Nessun dato disponibile.</div>
          ) : (
            <>
              <table className="w-full border-separate border-spacing-0 text-sm">
                <thead className="sticky top-0 z-10 bg-popover">
                  <tr>
                    <th className="sticky left-0 z-20 bg-popover px-3 py-2 text-left font-semibold">
                      Punto vendita
                    </th>
                    {COLS.map((c) => (
                      <th key={c.key} className="px-3 py-2 text-right font-semibold" title={c.tooltip}>
                        <button
                          type="button"
                          onClick={() => toggleSort(c.key)}
                          className="inline-flex items-center gap-1 hover:text-foreground"
                        >
                          {c.label}
                          {sortKey === c.key ? (
                            sortDir === "desc" ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />
                          ) : null}
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {righeSorted.map((r) => (
                    <tr key={r.ristorante_id} className="border-t">
                      <td className="sticky left-0 z-10 max-w-[14rem] truncate bg-popover px-3 py-2 font-medium">
                        {r.nome}
                      </td>
                      {r.dati_incompleti ? (
                        <td colSpan={COLS.length} className="px-3 py-2 text-right text-xs text-muted-foreground">
                          dati incompleti
                        </td>
                      ) : (
                        COLS.map((c) => (
                          <td
                            key={c.key}
                            className={cn("px-3 py-2 text-right tabular-nums", cellTone(c, r))}
                          >
                            {c.fmt(r[c.key] as number | null)}
                          </td>
                        ))
                      )}
                    </tr>
                  ))}
                  {/* Riga GRUPPO in fondo */}
                  <tr className="border-t-2 border-foreground/20 font-semibold">
                    <td className="sticky left-0 z-10 bg-popover px-3 py-2">{data.gruppo.nome}</td>
                    {COLS.map((c) => (
                      <td key={c.key} className="px-3 py-2 text-right tabular-nums">
                        {c.fmt(data.gruppo[c.key] as number | null)}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
              <p className="mt-3 text-xs text-muted-foreground">
                <span className="text-emerald-600 dark:text-emerald-500">verde</span> = migliore della
                catena, <span className="text-rose-600 dark:text-rose-500">rosso</span> = peggiore. Per «€
                materia prima / coperto» il valore basso è il migliore. «dati incompleti» = al punto
                vendita mancano fatturato, fatture costo o costo personale del periodo. Importi al
                <span className="font-medium"> netto IVA</span> (i «conti del gruppo» mostrano il lordo, IVA inclusa).
              </p>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
