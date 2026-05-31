"use client";

import { useState, useEffect } from "react";
import { Plus, Pencil, Trash2, BarChart3, Download, Copy } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { toast } from "sonner";
import {
  fmtData,
  type InventarioResponse,
  type VoceInventario,
  type SnapshotDate,
} from "@/lib/inventario";
import { InventarioAggiungiDialog } from "./inventario-aggiungi-dialog";
import { InventarioDatePicker } from "./inventario-date-picker";

function fmtEuro(v: number | null | undefined) {
  if (v == null) return "—";
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);
}

function todayISO() {
  return new Date().toISOString().split("T")[0];
}

export function InventarioTab() {
  const [dataInventario, setDataInventario] = useState(todayISO);
  const [inventario, setInventario] = useState<InventarioResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editVoce, setEditVoce] = useState<VoceInventario | null>(null);

  const [categorieAperte, setCategorieAperte] = useState(false);

  const [snapshots, setSnapshots] = useState<SnapshotDate[]>([]);
  const [copiaOpen, setCopiaOpen] = useState(false);
  const [copiaLoading, setCopiaLoading] = useState(false);

  async function load(data = dataInventario) {
    setLoading(true);
    try {
      const res = await fetch(`/api/workspace/inventario?data=${data}`);
      const d: InventarioResponse = await res.json();
      setInventario(d);
    } catch {
      toast.error("Errore caricamento inventario");
    } finally {
      setLoading(false);
    }
  }

  async function loadSnapshots() {
    try {
      const res = await fetch("/api/workspace/inventario/snapshot-dates");
      const d = await res.json();
      setSnapshots(d.snapshots ?? []);
    } catch { /* non critico */ }
  }

  useEffect(() => { load(); loadSnapshots(); }, []);

  function onDataChange(nuovaData: string) {
    setDataInventario(nuovaData);
    load(nuovaData);
  }

  async function elimina(v: VoceInventario) {
    if (!confirm(`Eliminare "${v.nome}"?`)) return;
    await fetch(`/api/workspace/inventario/${v.id}`, { method: "DELETE" });
    toast.success("Voce eliminata");
    load();
  }

  async function copiaSnapshot(dataSource: string) {
    setCopiaLoading(true);
    try {
      const res = await fetch("/api/workspace/inventario/copia-snapshot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data_source: dataSource, data_target: dataInventario }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? "Errore");
      toast.success(`${d.n_articoli} articoli copiati da ${fmtData(dataSource)}`);
      setCopiaOpen(false);
      load();
      loadSnapshots();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore copia snapshot");
    } finally {
      setCopiaLoading(false);
    }
  }

  function esportaCSV() {
    if (!inventario || inventario.voci.length === 0) return;
    const headers = ["Prodotto", "Categoria", "Quantità", "UM", "€/UM", "Valore €", "Note"];
    const rows = inventario.voci.map(v => [
      v.nome,
      v.categoria,
      String(v.quantita).replace(".", ","),
      v.um,
      String(v.prezzo_unitario).replace(".", ","),
      String(v.valore_totale ?? 0).replace(".", ","),
      v.note ?? "",
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(";"))
      .join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `inventario_${dataInventario}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const voci = inventario?.voci ?? [];
  const kpi = inventario?.kpi;
  const categorie = inventario?.categorie ?? [];
  const snapshotsFiltrati = snapshots.filter(s => s.data_inventario !== dataInventario);

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Date picker con evidenziazione giorni inventario */}
        <InventarioDatePicker
          value={dataInventario}
          snapshots={snapshots}
          onChange={onDataChange}
        />

        <Button onClick={() => { setEditVoce(null); setDialogOpen(true); }}>
          <Plus className="size-4 mr-1.5" />Aggiungi prodotto
        </Button>

        {/* Copia da snapshot */}
        <Popover open={copiaOpen} onOpenChange={setCopiaOpen}>
          <PopoverTrigger
            render={
              <Button variant="outline" disabled={snapshotsFiltrati.length === 0}>
                <Copy className="size-4 mr-1.5" />Copia da snapshot
              </Button>
            }
          />
          <PopoverContent className="w-72 p-2" align="start">
            <p className="text-xs text-muted-foreground px-2 py-1 mb-1">
              Importa gli articoli (quantità = 0) da un inventario precedente.
            </p>
            <div className="space-y-0.5">
              {snapshotsFiltrati.map(s => (
                <button
                  key={s.data_inventario}
                  onClick={() => copiaSnapshot(s.data_inventario)}
                  disabled={copiaLoading}
                  className="w-full flex items-center justify-between rounded-md px-3 py-2 text-sm hover:bg-accent transition-colors disabled:opacity-50"
                >
                  <span className="font-medium">{fmtData(s.data_inventario)}</span>
                  <span className="text-xs text-muted-foreground">
                    {s.n_articoli} art · {fmtEuro(s.valore_totale)}
                  </span>
                </button>
              ))}
            </div>
          </PopoverContent>
        </Popover>

        {/* Esporta CSV */}
        {voci.length > 0 && (
          <Button variant="outline" onClick={esportaCSV}>
            <Download className="size-4 mr-1.5" />Esporta CSV
          </Button>
        )}
      </div>

      {/* KPI */}
      {kpi && (
        <div className="grid grid-cols-3 gap-3">
          <Card className="ring-sky-400/60">
            <CardContent className="py-3 px-4">
              <p className="text-xs text-muted-foreground">Valore magazzino</p>
              <p className="text-2xl font-bold">{fmtEuro(kpi.valore_totale)}</p>
            </CardContent>
          </Card>
          <Card className="ring-sky-400/60">
            <CardContent className="py-3 px-4">
              <p className="text-xs text-muted-foreground">Prodotti contati</p>
              <p className="text-2xl font-bold">{kpi.n_articoli}</p>
            </CardContent>
          </Card>
          <Card className="ring-sky-400/60">
            <CardContent className="py-3 px-4">
              <p className="text-xs text-muted-foreground">Categorie</p>
              <p className="text-2xl font-bold">{kpi.n_categorie}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Analisi per categoria */}
      {categorie.length > 0 && (
        <div>
          <Button variant="outline" onClick={() => setCategorieAperte(v => !v)}>
            <BarChart3 className="size-4 mr-1.5" />
            Analisi per categoria
            <span className="ml-1.5 text-muted-foreground">{categorieAperte ? "▾" : "▸"}</span>
          </Button>
          {categorieAperte && (
            <div className="mt-2 rounded-md border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium text-muted-foreground">Categoria</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">Prodotti</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">Valore €</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">% totale</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {categorie.map(c => (
                    <tr key={c.categoria} className="hover:bg-muted/30">
                      <td className="px-4 py-2 font-medium">{c.categoria || "—"}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">{c.n_articoli}</td>
                      <td className="px-3 py-2 text-right">{fmtEuro(c.valore_totale)}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">{c.pct_totale.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tabella voci */}
      {loading ? (
        <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
      ) : voci.length === 0 ? (
        <div className="py-16 text-center text-sm text-muted-foreground">
          Nessun prodotto per questa data. Usa &ldquo;Aggiungi prodotto&rdquo; o &ldquo;Copia da snapshot&rdquo; per iniziare.
        </div>
      ) : (
        <div className="rounded-md border border-border overflow-hidden">
          <table className="w-full text-sm table-fixed">
            <colgroup>
              <col className="w-[30%]" />
              <col className="w-[20%]" />
              <col className="w-[10%]" />
              <col className="w-[8%]" />
              <col className="w-[12%]" />
              <col className="w-[12%]" />
              <col className="w-[8%]" />
            </colgroup>
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Prodotto</th>
                <th className="text-left px-3 py-2.5 font-medium text-muted-foreground">Categoria</th>
                <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">Qtà</th>
                <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">UM</th>
                <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">€/UM</th>
                <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">Valore €</th>
                <th className="px-3 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {voci.map(v => (
                <tr key={v.id} className="hover:bg-muted/30 group">
                  <td className="px-4 py-2.5 font-medium truncate" title={v.nome}>{v.nome}</td>
                  <td className="px-3 py-2.5 text-muted-foreground truncate" title={v.categoria}>{v.categoria || "—"}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{v.quantita}</td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground">{v.um}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">
                    {v.prezzo_unitario > 0
                      ? new Intl.NumberFormat("it-IT", { minimumFractionDigits: 4, maximumFractionDigits: 4 }).format(v.prezzo_unitario)
                      : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right font-medium tabular-nums">{fmtEuro(v.valore_totale)}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7"
                        onClick={() => { setEditVoce(v); setDialogOpen(true); }}
                        title="Modifica"
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7 text-muted-foreground hover:text-destructive"
                        onClick={() => elimina(v)}
                        title="Elimina"
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
            {/* Totale footer */}
            {kpi && kpi.valore_totale > 0 && (
              <tfoot className="bg-muted/50 border-t border-border">
                <tr>
                  <td colSpan={5} className="px-4 py-2.5 text-right text-sm font-medium text-muted-foreground">
                    Totale
                  </td>
                  <td className="px-3 py-2.5 text-right font-bold tabular-nums">{fmtEuro(kpi.valore_totale)}</td>
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}

      <InventarioAggiungiDialog
        open={dialogOpen}
        voce={editVoce}
        dataInventario={dataInventario}
        onClose={() => { setDialogOpen(false); setEditVoce(null); }}
        onSaved={() => { load(); loadSnapshots(); }}
      />
    </div>
  );
}
