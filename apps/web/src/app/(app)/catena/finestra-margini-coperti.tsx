"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { type MarginiCoperti, type MarginiCopertiPV } from "@/lib/gruppo";

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
};
const COLS: Col[] = [
  { key: "margine_perc", label: "Margine %", fmt: pct, altoMeglio: true },
  { key: "fatturato", label: "Fatturato", fmt: euro, altoMeglio: true },
  { key: "coperti", label: "Coperti", fmt: num, altoMeglio: true },
  { key: "scontrino_medio", label: "Scontrino medio", fmt: euro, altoMeglio: true },
  { key: "mp_per_coperto", label: "€ materia prima / coperto", fmt: euro, altoMeglio: false },
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
  const reqRef = useRef(0);

  useEffect(() => {
    if (!open) return;
    const my = ++reqRef.current;
    setLoading(true);
    fetch("/api/gruppo/margini-coperti", { cache: "no-store" })
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
  }, [open]);

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
            <span className="text-xs font-normal text-muted-foreground">{data?.periodo_label}</span>
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
                      <th key={c.key} className="px-3 py-2 text-right font-semibold">
                        {c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.righe.map((r) => (
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
                materia prima / coperto» il valore basso è il migliore.
              </p>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
