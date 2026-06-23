"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowDown, ArrowUp, Download, AlertTriangle, Sprout } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/select";
import { type MarginiCoperti, type MarginiCopertiPV, type SprecoCategorie } from "@/lib/gruppo";

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

// Heatmap a token di tema (come "Spesa per PV"): intensità sfondo dalla frazione
// sul massimo di colonna. Dà "forma" alla tabella senza colori hardcoded.
function heatStyle(v: number | null, max: number): React.CSSProperties {
  if (v == null || max <= 0 || v <= 0) return {};
  const a = 0.05 + (v / max) * 0.30;
  return { backgroundColor: `color-mix(in oklab, var(--primary) ${Math.round(a * 100)}%, transparent)` };
}
// Pallino salute dal margine % — stesse soglie del ranking (≥15 verde, ≥8 giallo).
function margineDot(perc: number | null, incompleti: boolean): string {
  if (incompleti || perc == null) return "bg-muted-foreground/30";
  if (perc >= 15) return "bg-emerald-500";
  if (perc >= 8) return "bg-amber-500";
  return "bg-rose-500";
}
// Colonne "di grandezza" su cui applicare la heatmap.
const HEAT: ReadonlySet<string> = new Set(["fatturato", "coperti"]);

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
  const [categorieOpen, setCategorieOpen] = useState(false);
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

  // Massimo per colonna (solo PV con dati) per la heatmap di fatturato/coperti.
  const heatMax: Record<string, number> = {};
  for (const k of HEAT) {
    heatMax[k] = Math.max(0, ...(data?.righe ?? []).map((r) => (r[k as keyof MarginiCopertiPV] as number) ?? 0));
  }

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
                onClick={() => setCategorieOpen(true)}
                disabled={!data || data.righe.length === 0}
                className="inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-xs font-medium transition-colors hover:bg-accent disabled:opacity-50"
                title="Costo materia prima per coperto, per categoria, a confronto tra i punti vendita"
              >
                <Sprout className="size-3.5 text-emerald-500" />
                Categorie
              </button>
              <button
                type="button"
                onClick={exportXls}
                disabled={!data || data.righe.length === 0}
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
                    <tr
                      key={r.ristorante_id}
                      className={cn(
                        "border-t transition-colors",
                        r.dati_incompleti ? "bg-muted/20" : "hover:bg-muted/30",
                      )}
                    >
                      <td className="sticky left-0 z-10 max-w-[14rem] bg-popover px-3 py-2 font-medium">
                        <span className="flex items-center gap-2">
                          <span className={cn("size-2 shrink-0 rounded-full", margineDot(r.margine_perc, r.dati_incompleti))} />
                          <span className="truncate">{r.nome}</span>
                        </span>
                      </td>
                      {r.dati_incompleti ? (
                        <td colSpan={COLS.length} className="px-3 py-2 text-right text-xs text-muted-foreground">
                          dati incompleti
                        </td>
                      ) : (
                        COLS.map((c) => (
                          <td
                            key={c.key}
                            style={HEAT.has(c.key) ? heatStyle(r[c.key] as number | null, heatMax[c.key]) : undefined}
                            className={cn("px-3 py-2 text-right tabular-nums", cellTone(c, r))}
                          >
                            {c.fmt(r[c.key] as number | null)}
                          </td>
                        ))
                      )}
                    </tr>
                  ))}
                  {/* Riga GRUPPO in fondo */}
                  <tr className="border-t-2 border-foreground/20 bg-primary/5 font-semibold">
                    <td className="sticky left-0 z-10 bg-popover px-3 py-2">
                      <span className="flex items-center gap-2">
                        <span className="size-2 shrink-0 rounded-full bg-primary" />
                        <span className="truncate">{data.gruppo.nome}</span>
                      </span>
                    </td>
                    {COLS.map((c) => (
                      <td key={c.key} className="px-3 py-2 text-right tabular-nums">
                        {c.fmt(data.gruppo[c.key] as number | null)}
                        {/* Margine di gruppo parziale: alcune sedi non hanno i costi. */}
                        {c.key === "margine_perc" && data.n_incompleti > 0 && (
                          <span className="ml-1 align-middle text-[10px] font-normal text-amber-600 dark:text-amber-500">
                            parziale
                          </span>
                        )}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
              {data.n_incompleti > 0 && (
                <p className="mt-3 flex items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="size-3.5 shrink-0" />
                  Margine di gruppo <span className="font-medium">parziale</span>: {data.n_incompleti}{" "}
                  {data.n_incompleti === 1 ? "sede non ha" : "sedi non hanno"} ancora i costi caricati.
                </p>
              )}
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

      {categorieOpen && (
        <FinestraSprecoCategorie
          mese={periodo !== "anno" ? Number(periodo) : null}
          onClose={() => setCategorieOpen(false)}
        />
      )}
    </Dialog>
  );
}

// ─── Dialog: spreco (€MP/coperto) per categoria, confronto fra PV ───────────

function euro2(n: number | null): string {
  if (n == null) return "—";
  return `${n.toFixed(2).replace(".", ",")} €`;
}

function FinestraSprecoCategorie({
  mese,
  onClose,
}: {
  mese: number | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<SprecoCategorie | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const qs = mese ? `?mese=${mese}` : "";
    fetch(`/api/gruppo/spreco-categorie${qs}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => { if (alive) setData(j); })
      .catch(() => { if (alive) { setData(null); toast.error("Errore nel caricamento dello spreco per categoria"); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [mese]);

  // Best/worst per RIGA (categoria) tra i PV con dato: la cella più bassa è la
  // migliore (meno materia prima per coperto = meno spreco), la più alta peggiore.
  function rigaExtremes(r: SprecoCategorie["righe"][number]): { best: number | null; worst: number | null } {
    const vals = r.per_pv.map((c) => c.valore).filter((v): v is number => v != null);
    if (vals.length < 2) return { best: null, worst: null };
    return { best: Math.min(...vals), worst: Math.max(...vals) };
  }

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-h-[88vh] w-[min(96vw,68rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Sprout className="size-4 text-emerald-500" />
            Spreco per categoria · confronto punti vendita
            {data?.periodo_label && (
              <span className="text-xs font-normal text-muted-foreground">· {data.periodo_label}</span>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="max-h-[calc(88vh-5rem)] overflow-auto px-5 pb-5">
          {loading && !data ? (
            <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
          ) : !data || data.righe.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              Nessun dato: servono coperti e fatture F&amp;B classificate nel periodo.
            </div>
          ) : (
            <>
              <table className="w-full border-separate border-spacing-0 text-sm">
                <thead className="sticky top-0 z-10 bg-popover">
                  <tr>
                    <th className="sticky left-0 z-20 bg-popover px-3 py-2 text-left font-semibold">
                      Categoria
                    </th>
                    {data.pv.map((p) => (
                      <th
                        key={p.ristorante_id}
                        className="max-w-[10rem] px-3 py-2 text-right font-semibold"
                        title={p.nome}
                      >
                        <span className="block truncate">{p.nome}</span>
                      </th>
                    ))}
                    <th className="px-3 py-2 text-right font-bold text-emerald-700 dark:text-emerald-400">
                      Media gruppo
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.righe.map((r) => {
                    const ex = rigaExtremes(r);
                    return (
                      <tr key={r.categoria} className="border-t transition-colors hover:bg-muted/30">
                        <td className="sticky left-0 z-10 max-w-[16rem] bg-popover px-3 py-2 font-medium">
                          <span className="block truncate">{r.categoria}</span>
                        </td>
                        {r.per_pv.map((c) => {
                          const v = c.valore;
                          const tone =
                            v == null || ex.best == null
                              ? ""
                              : v === ex.best && v !== ex.worst
                                ? "text-emerald-600 dark:text-emerald-500 font-semibold"
                                : v === ex.worst && v !== ex.best
                                  ? "text-rose-600 dark:text-rose-500 font-semibold"
                                  : "";
                          return (
                            <td key={c.ristorante_id} className={cn("px-3 py-2 text-right tabular-nums", tone)}>
                              {euro2(v)}
                            </td>
                          );
                        })}
                        <td className="px-3 py-2 text-right font-bold tabular-nums text-emerald-700 dark:text-emerald-400">
                          {euro2(r.media_gruppo)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="mt-3 text-xs text-muted-foreground">
                Quanto costa in <span className="font-medium">materie prime per coperto</span> ogni
                categoria, a confronto tra i punti vendita. Per categoria:{" "}
                <span className="font-medium">spesa F&amp;B ÷ coperti</span> dei soli mesi con fatture
                caricate. <span className="text-emerald-600 dark:text-emerald-500">verde</span> = il PV
                più efficiente sulla categoria, <span className="text-rose-600 dark:text-rose-500">rosso</span>{" "}
                = il più caro. SHOP escluso (merce da rivendita). «—» = nessun dato per quel PV.
              </p>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
