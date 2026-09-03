"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowDown, ArrowUp, Download, AlertTriangle, Sprout } from "lucide-react";
import { cn } from "@/lib/utils";
import { MESI_LUNGHI as MESI } from "@/lib/mesi";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/select";
import { type MarginiCoperti, type MarginiCopertiPV, type SprecoCategorie } from "@/lib/gruppo";
import {
  headerMargini,
  nomeFileMargini,
  notaIncompleti,
  rigaExportGruppo,
  rigaExportMargini,
} from "@/lib/catena-export";
import {
  type Col as ColConfronto,
  HEAT,
  calcolaExtremes,
  calcolaHeatMax,
  cellTone as cellToneOf,
  heatStyle,
  margineDot,
  ordinaRighe,
  rigaExtremes,
} from "@/lib/catena-confronti";

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
type Col = ColConfronto & {
  fmt: (v: number | null) => string;
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
  const [loadError, setLoadError] = useState(false);
  const [periodo, setPeriodo] = useState<string>("anno");
  const [sortKey, setSortKey] = useState<keyof MarginiCopertiPV>("margine_perc");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [categorieOpen, setCategorieOpen] = useState(false);
  const reqRef = useRef(0);

  const annoCorrente = new Date().getFullYear();
  const meseCorrente = new Date().getMonth() + 1;

  const carica = useCallback(() => {
    const my = ++reqRef.current;
    setLoading(true);
    setLoadError(false);
    const qs = periodo !== "anno" ? `?mese=${periodo}` : "";
    fetch(`/api/gruppo/margini-coperti${qs}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => {
        if (my === reqRef.current) setData(j);
      })
      .catch(() => {
        if (my === reqRef.current) {
          setLoadError(true);
          toast.error("Errore nel caricamento di margini e coperti");
        }
      })
      .finally(() => {
        if (my === reqRef.current) setLoading(false);
      });
  }, [periodo]);

  useEffect(() => {
    if (!open) return;
    carica();
  }, [open, carica]);

  function toggleSort(k: keyof MarginiCopertiPV) {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir("desc"); }
  }

  // Ordina i PV per la colonna scelta; gli incompleti restano sempre in fondo.
  const righeSorted = ordinaRighe(data?.righe ?? [], sortKey, sortDir);

  // Massimo per colonna (solo PV con dati) per la heatmap di fatturato/coperti.
  const heatMax = calcolaHeatMax(data?.righe ?? []);

  // Export Excel (xlsx lazy: libreria pesante, solo al click).
  async function exportXls() {
    if (!data) return;
    const XLSX = await import("xlsx");
    const header = headerMargini(COLS);
    const toRow = (r: MarginiCopertiPV) => rigaExportMargini(r, COLS);
    // La riga gruppo esce con la stessa qualificazione che ha a schermo: senza,
    // il file scaricato afferma un margine che l'UI dichiara parziale.
    const gruppoRow = rigaExportGruppo(data.gruppo, COLS, data.n_incompleti);
    const rows = [...righeSorted.map(toRow), gruppoRow];
    const ws = XLSX.utils.json_to_sheet(rows, { header });
    const nota = notaIncompleti(data.n_incompleti);
    if (nota) {
      XLSX.utils.sheet_add_aoa(ws, [[nota]], { origin: -1 });
    }
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Margini e coperti");
    XLSX.writeFile(wb, nomeFileMargini(data.periodo_label, new Date().toISOString().slice(0, 10)));
  }

  // Per ogni colonna, individua best/worst tra i PV con dati (esclude incompleti
  // e valori null). Se c'è un solo PV con dato, niente evidenza (non c'è confronto).
  const extremes = calcolaExtremes(data?.righe ?? [], COLS);

  function cellTone(col: Col, r: MarginiCopertiPV): string {
    return cellToneOf(col, r, extremes);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] flex-col gap-0 w-[min(96vw,68rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="shrink-0 border-b px-5 py-4">
          <DialogTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
            <span>Margini e coperti per punto vendita</span>
            <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
              <NativeSelect value={periodo} onValueChange={setPeriodo} className="h-8 w-48 text-xs">
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

        <div className="min-h-0 flex-1 overflow-auto px-5 pb-5">
          {loading && !data ? (
            <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
          ) : loadError && !data ? (
            <div className="flex flex-col items-center gap-3 py-16 text-center">
              <AlertTriangle className="size-7 text-rose-500" />
              <p className="text-sm text-muted-foreground">
                Non è stato possibile caricare i dati.
              </p>
              <Button size="sm" variant="outline" onClick={carica} disabled={loading}>
                Riprova
              </Button>
            </div>
          ) : !data ? (
            <div className="py-16 text-center text-sm text-muted-foreground">Nessun dato disponibile.</div>
          ) : (
            <>
              <table className="w-full border-separate border-spacing-0 text-sm">
                <thead className="sticky top-0 z-30 bg-popover">
                  <tr>
                    <th className="sticky left-0 z-40 bg-popover px-3 py-2 text-left font-semibold">
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
  const [loadError, setLoadError] = useState(false);
  const reqRef = useRef(0);

  // Su errore NON si azzera `data`: un refetch fallito (cambio mese) deve lasciare
  // a schermo i dati precedenti, non sostituirli con "nessun dato".
  const carica = useCallback(() => {
    const my = ++reqRef.current;
    setLoading(true);
    setLoadError(false);
    const qs = mese ? `?mese=${mese}` : "";
    fetch(`/api/gruppo/spreco-categorie${qs}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => { if (my === reqRef.current) setData(j); })
      .catch(() => {
        if (my === reqRef.current) {
          setLoadError(true);
          toast.error("Errore nel caricamento dello spreco per categoria");
        }
      })
      .finally(() => { if (my === reqRef.current) setLoading(false); });
  }, [mese]);

  useEffect(() => {
    carica();
  }, [carica]);

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="flex max-h-[88vh] flex-col gap-0 w-[min(96vw,68rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="shrink-0 border-b px-5 py-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Sprout className="size-4 text-emerald-500" />
            Spreco per categoria · confronto punti vendita
            {data?.periodo_label && (
              <span className="text-xs font-normal text-muted-foreground">· {data.periodo_label}</span>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-auto px-5 pb-5">
          {loading && !data ? (
            <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
          ) : loadError && !data ? (
            <div className="flex flex-col items-center gap-3 py-16 text-center">
              <AlertTriangle className="size-7 text-rose-500" />
              <p className="text-sm text-muted-foreground">
                Non è stato possibile caricare i dati.
              </p>
              <Button size="sm" variant="outline" onClick={carica} disabled={loading}>
                Riprova
              </Button>
            </div>
          ) : !data || data.righe.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              Nessun dato: servono coperti e fatture F&amp;B classificate nel periodo.
            </div>
          ) : (
            <>
              <table className="w-full border-separate border-spacing-0 text-sm">
                <thead className="sticky top-0 z-30 bg-popover">
                  <tr>
                    <th className="sticky left-0 z-40 bg-popover px-3 py-2 text-left font-semibold">
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
