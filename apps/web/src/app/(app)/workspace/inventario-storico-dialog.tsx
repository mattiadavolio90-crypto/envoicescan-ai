"use client";

import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  fmtData,
  confrontaInventari,
  type SnapshotDate,
  type VoceInventario,
  type InventarioResponse,
  type ConfrontoInventari,
} from "@/lib/inventario";

function fmtEuro(v: number | null | undefined) {
  if (v == null) return "—";
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);
}

function fmtDelta(v: number) {
  const s = fmtEuro(Math.abs(v));
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : "—";
}

function fmtQta(v: number) {
  return new Intl.NumberFormat("it-IT", { maximumFractionDigits: 3 }).format(v);
}

const selectCls =
  "h-10 w-full rounded-md border border-input bg-background px-3 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500";

interface Props {
  open: boolean;
  snapshots: SnapshotDate[];
  onClose: () => void;
  onApri: (data: string) => void;
}

async function fetchVoci(data: string): Promise<VoceInventario[]> {
  const res = await fetch(`/api/workspace/inventario?data=${data}`);
  if (!res.ok) throw new Error();
  const d: InventarioResponse = await res.json();
  return d.voci ?? [];
}

export function InventarioStoricoDialog({ open, snapshots, onClose, onApri }: Props) {
  const [tab, setTab] = useState<"storico" | "confronta">("storico");

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="w-full sm:max-w-2xl gap-4">
        <DialogTitle>Inventari</DialogTitle>

        {/* Tab switcher */}
        <div className="flex gap-1 border-b border-border">
          {([["storico", "Storico"], ["confronta", "Confronta"]] as const).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                tab === k
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "storico"
          ? <StoricoTab snapshots={snapshots} onApri={data => { onApri(data); onClose(); }} />
          : <ConfrontaTab snapshots={snapshots} />}
      </DialogContent>
    </Dialog>
  );
}

function StoricoTab({ snapshots, onApri }: { snapshots: SnapshotDate[]; onApri: (data: string) => void }) {
  if (snapshots.length === 0) {
    return <div className="py-10 text-center text-sm text-muted-foreground">Nessun inventario salvato.</div>;
  }

  return (
    <div className="max-h-[60vh] overflow-y-auto rounded-md border border-border divide-y divide-border">
      {snapshots.map(s => (
        <div key={s.data_inventario} className="flex items-center gap-2 px-3 py-2.5">
          <div className="min-w-0 flex-1 flex items-center gap-2">
            <span className="font-medium">{fmtData(s.data_inventario)}</span>
            <span className="text-xs text-muted-foreground">{s.n_articoli} voci</span>
          </div>
          <span className="font-semibold tabular-nums">{fmtEuro(s.valore_totale)}</span>
          <Button size="sm" variant="outline" onClick={() => onApri(s.data_inventario)}>
            Apri
          </Button>
        </div>
      ))}
    </div>
  );
}

function ConfrontaTab({ snapshots }: { snapshots: SnapshotDate[] }) {
  const [dataA, setDataA] = useState("");
  const [dataB, setDataB] = useState("");
  const [confronto, setConfronto] = useState<ConfrontoInventari | null>(null);
  const [loading, setLoading] = useState(false);

  async function calcola(a: string, b: string) {
    if (!a || !b || a === b) { setConfronto(null); return; }
    setLoading(true);
    try {
      const [vociA, vociB] = await Promise.all([fetchVoci(a), fetchVoci(b)]);
      setConfronto(confrontaInventari(vociA, vociB));
    } catch {
      toast.error("Errore confronto inventari");
      setConfronto(null);
    } finally {
      setLoading(false);
    }
  }

  function onChangeA(v: string) { setDataA(v); calcola(v, dataB); }
  function onChangeB(v: string) { setDataB(v); calcola(dataA, v); }

  if (snapshots.length < 2) {
    return (
      <div className="py-10 text-center text-sm text-muted-foreground">
        Servono almeno due inventari salvati per fare un confronto.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Selettori A → B */}
      <div className="flex items-end gap-2">
        <div className="flex-1 space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Da (precedente)</label>
          <select value={dataA} onChange={e => onChangeA(e.target.value)} className={selectCls}>
            <option value="">Seleziona…</option>
            {snapshots.map(s => (
              <option key={s.data_inventario} value={s.data_inventario} disabled={s.data_inventario === dataB}>
                {fmtData(s.data_inventario)} · {fmtEuro(s.valore_totale)}
              </option>
            ))}
          </select>
        </div>
        <ArrowRight className="size-5 mb-2.5 shrink-0 text-muted-foreground" />
        <div className="flex-1 space-y-1">
          <label className="text-xs font-medium text-muted-foreground">A (successivo)</label>
          <select value={dataB} onChange={e => onChangeB(e.target.value)} className={selectCls}>
            <option value="">Seleziona…</option>
            {snapshots.map(s => (
              <option key={s.data_inventario} value={s.data_inventario} disabled={s.data_inventario === dataA}>
                {fmtData(s.data_inventario)} · {fmtEuro(s.valore_totale)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && <p className="py-8 text-center text-sm text-muted-foreground">Calcolo…</p>}

      {!loading && confronto && (
        <>
          {/* KPI */}
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-md border border-border px-3 py-2">
              <p className="text-xs text-muted-foreground">Valore {fmtData(dataA)}</p>
              <p className="text-lg font-bold tabular-nums">{fmtEuro(confronto.valore_a)}</p>
            </div>
            <div className="rounded-md border border-border px-3 py-2">
              <p className="text-xs text-muted-foreground">Valore {fmtData(dataB)}</p>
              <p className="text-lg font-bold tabular-nums">{fmtEuro(confronto.valore_b)}</p>
            </div>
            <div className={`rounded-md border px-3 py-2 ${
              confronto.delta_valore > 0
                ? "border-emerald-500/40 bg-emerald-50 dark:bg-emerald-900/10"
                : confronto.delta_valore < 0
                  ? "border-red-500/40 bg-red-50 dark:bg-red-900/10"
                  : "border-border"
            }`}>
              <p className="text-xs text-muted-foreground">Differenza</p>
              <p className={`text-lg font-bold tabular-nums ${
                confronto.delta_valore > 0 ? "text-emerald-600 dark:text-emerald-400"
                : confronto.delta_valore < 0 ? "text-red-600 dark:text-red-400" : ""
              }`}>{fmtDelta(confronto.delta_valore)}</p>
            </div>
          </div>

          {/* Tabella differenze */}
          <div className="max-h-[42vh] overflow-y-auto rounded-md border border-border">
            <table className="w-full text-xs">
              <thead className="bg-muted/50 sticky top-0">
                <tr className="text-muted-foreground">
                  <th className="text-left px-3 py-2 font-medium">Prodotto</th>
                  <th className="text-right px-2 py-2 font-medium">Qtà A</th>
                  <th className="text-right px-2 py-2 font-medium">Qtà B</th>
                  <th className="text-right px-2 py-2 font-medium">Δ Qtà</th>
                  <th className="text-right px-3 py-2 font-medium">Δ Valore</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {confronto.righe.map((r, i) => (
                  <tr key={i} className="hover:bg-muted/30">
                    <td className="px-3 py-1.5">
                      <span className="font-medium">{r.nome}</span>
                      {r.stato === "nuovo" && <span className="ml-1.5 text-[10px] rounded px-1 py-0.5 bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">nuovo</span>}
                      {r.stato === "uscito" && <span className="ml-1.5 text-[10px] rounded px-1 py-0.5 bg-red-500/15 text-red-700 dark:text-red-400">uscito</span>}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">{r.stato === "nuovo" ? "—" : fmtQta(r.qta_a)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">{r.stato === "uscito" ? "—" : fmtQta(r.qta_b)}</td>
                    <td className={`px-2 py-1.5 text-right tabular-nums ${
                      r.delta_qta > 0 ? "text-emerald-600 dark:text-emerald-400"
                      : r.delta_qta < 0 ? "text-red-600 dark:text-red-400" : "text-muted-foreground"
                    }`}>{r.delta_qta === 0 ? "—" : (r.delta_qta > 0 ? "+" : "−") + fmtQta(Math.abs(r.delta_qta))}</td>
                    <td className={`px-3 py-1.5 text-right tabular-nums font-medium ${
                      r.delta_valore > 0 ? "text-emerald-600 dark:text-emerald-400"
                      : r.delta_valore < 0 ? "text-red-600 dark:text-red-400" : "text-muted-foreground"
                    }`}>{fmtDelta(r.delta_valore)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
