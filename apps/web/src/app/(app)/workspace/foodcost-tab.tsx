"use client";

import { useState, useEffect } from "react";
import { Plus, Pencil, Trash2, Info, BookOpen } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { toast } from "sonner";
import {
  FC_BADGE_CLASS, fmtEuro, fmtPct,
  type RicetteResponse, type Ricetta, type RicettaDettaglio, type CategoriaStats,
} from "@/lib/foodcost";
import { RicettaEditor } from "./ricetta-editor";
import { IngredientiManualiDialog } from "./ingredienti-manuali-dialog";

export function FoodcostTab() {
  const [data, setData] = useState<RicetteResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtroCategoria, setFiltroCategoria] = useState<string>("TUTTI");

  const [editorOpen, setEditorOpen] = useState(false);
  const [editorRicetta, setEditorRicetta] = useState<RicettaDettaglio | null>(null);
  const [manualiOpen, setManualiOpen] = useState(false);

  const [categorieAperte, setCategorieAperte] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const res = await fetch("/api/workspace/foodcost/ricette");
      const d: RicetteResponse = await res.json();
      setData(d);
    } catch {
      toast.error("Errore caricamento ricette");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function apriModifica(ricetta: Ricetta) {
    try {
      const res = await fetch(`/api/workspace/foodcost/ricette/${ricetta.id}`);
      const d: RicettaDettaglio = await res.json();
      setEditorRicetta(d);
      setEditorOpen(true);
    } catch {
      toast.error("Errore caricamento ricetta");
    }
  }

  async function elimina(r: Ricetta) {
    if (!confirm(`Eliminare "${r.nome}"?`)) return;
    await fetch(`/api/workspace/foodcost/ricette/${r.id}`, { method: "DELETE" });
    toast.success("Ricetta eliminata");
    load();
  }

  const ricette = data?.ricette ?? [];
  const kpi = data?.kpi;
  const categorie = data?.categorie ?? [];

  const categorieFiltro = ["TUTTI", ...Array.from(new Set(ricette.map(r => r.categoria))).sort()];
  const ricetteFiltrate = filtroCategoria === "TUTTI"
    ? ricette
    : ricette.filter(r => r.categoria === filtroCategoria);

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => { setEditorRicetta(null); setEditorOpen(true); }}>
          <Plus className="size-4 mr-1.5" />Nuova ricetta
        </Button>
        <Button variant="outline" onClick={() => setManualiOpen(true)}>
          <BookOpen className="size-4 mr-1.5" />Ingredienti manuali
        </Button>

        {/* Filtro categoria */}
        <div className="flex flex-wrap gap-1 ml-auto">
          {categorieFiltro.map(c => (
            <button
              key={c}
              onClick={() => setFiltroCategoria(c)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                filtroCategoria === c
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/30"
              }`}
            >
              {c}
            </button>
          ))}
        </div>

        {/* Info popover */}
        <Popover>
          <PopoverTrigger
            render={
              <Button variant="ghost" size="icon" className="size-8 text-muted-foreground">
                <Info className="size-4" />
              </Button>
            }
          />
          <PopoverContent className="w-96 text-sm space-y-3" align="end">
            <p className="font-semibold">Come usare il Foodcost</p>
            <ol className="list-decimal list-inside space-y-1.5 text-muted-foreground">
              <li>Clicca <strong>Nuova ricetta</strong>, scegli categoria e nome.</li>
              <li>Cerca gli ingredienti: usa i prodotti dalle tue fatture reali (🟢) o crea ingredienti manuali con prezzi stimati (📝).</li>
              <li>Imposta quantità e unità di misura — il costo si aggiorna in tempo reale.</li>
              <li>Aggiungi il prezzo di vendita (IVA 10% inclusa) per vedere margine e incidenza food cost.</li>
              <li>I <strong>Semilavorati</strong> (es. besciamella, ragù) si riusano come ingredienti in altre ricette.</li>
            </ol>
            <div className="border-t pt-2 space-y-1 text-muted-foreground">
              <p className="font-medium text-foreground text-xs">Colori incidenza food cost:</p>
              <p>🟢 ≤30% ottimo · 🟡 30–40% accettabile · 🔴 &gt;40% da rivedere</p>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      {/* KPI */}
      {kpi && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card><CardContent className="py-3 px-4">
            <p className="text-xs text-muted-foreground">Ricette totali</p>
            <p className="text-2xl font-bold">{kpi.totale}</p>
          </CardContent></Card>
          <Card><CardContent className="py-3 px-4">
            <p className="text-xs text-muted-foreground">Costo medio ricetta</p>
            <p className="text-2xl font-bold">{fmtEuro(kpi.costo_medio)}</p>
          </CardContent></Card>
          <Card><CardContent className="py-3 px-4">
            <p className="text-xs text-muted-foreground">Margine medio</p>
            <p className="text-2xl font-bold">{fmtEuro(kpi.margine_medio)}</p>
          </CardContent></Card>
          <Card><CardContent className="py-3 px-4">
            <p className="text-xs text-muted-foreground">Incidenza FC media</p>
            <p className="text-2xl font-bold">{fmtPct(kpi.incidenza_media)}</p>
          </CardContent></Card>
        </div>
      )}

      {/* Tabella ricette */}
      {loading ? (
        <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
      ) : ricetteFiltrate.length === 0 ? (
        <div className="py-16 text-center text-sm text-muted-foreground">
          {ricette.length === 0
            ? "Nessuna ricetta ancora. Crea la tua prima ricetta con il bottone qui sopra."
            : "Nessuna ricetta per questa categoria."}
        </div>
      ) : (
        <div className="rounded-md border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Ricetta</th>
                <th className="text-left px-3 py-2.5 font-medium text-muted-foreground">Categoria</th>
                <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">Foodcost</th>
                <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">Prezzo</th>
                <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">Margine</th>
                <th className="text-center px-3 py-2.5 font-medium text-muted-foreground">Inc. FC%</th>
                <th className="w-20" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {ricetteFiltrate.map(r => (
                <tr key={r.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-2.5 font-medium">{r.nome}</td>
                  <td className="px-3 py-2.5 text-muted-foreground text-xs">{r.categoria}</td>
                  <td className="px-3 py-2.5 text-right">{fmtEuro(r.foodcost_totale)}</td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground">
                    {r.prezzo_vendita_ivainc ? fmtEuro(r.prezzo_vendita_ivainc) : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right">{fmtEuro(r.margine)}</td>
                  <td className="px-3 py-2.5 text-center">
                    {r.incidenza_pct !== null ? (
                      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${FC_BADGE_CLASS[r.colore_fc]}`}>
                        {fmtPct(r.incidenza_pct)}
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </td>
                  <td className="px-2 py-2.5">
                    <div className="flex items-center gap-1">
                      <Button size="icon" variant="ghost" className="size-7" onClick={() => apriModifica(r)} title="Modifica">
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button size="icon" variant="ghost" className="size-7 text-muted-foreground hover:text-destructive" onClick={() => elimina(r)} title="Elimina">
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Analisi per categoria */}
      {categorie.length > 0 && (
        <div>
          <button
            className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => setCategorieAperte(v => !v)}
          >
            {categorieAperte ? "▾" : "▸"} Analisi per categoria
          </button>
          {categorieAperte && (
            <div className="mt-2 rounded-md border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium text-muted-foreground">Categoria</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">N.</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">FC totale</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">FC medio</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">Margine medio</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">Inc. FC%</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {categorie.map((c: CategoriaStats) => (
                    <tr key={c.categoria} className="hover:bg-muted/30">
                      <td className="px-4 py-2 font-medium">{c.categoria}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">{c.n_ricette}</td>
                      <td className="px-3 py-2 text-right">{fmtEuro(c.fc_totale)}</td>
                      <td className="px-3 py-2 text-right">{fmtEuro(c.fc_medio)}</td>
                      <td className="px-3 py-2 text-right">{fmtEuro(c.margine_medio)}</td>
                      <td className="px-3 py-2 text-right">{fmtPct(c.incidenza_media)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <RicettaEditor
        open={editorOpen}
        ricetta={editorRicetta}
        onClose={() => { setEditorOpen(false); setEditorRicetta(null); }}
        onSaved={load}
      />
      <IngredientiManualiDialog
        open={manualiOpen}
        onClose={() => setManualiOpen(false)}
        onSaved={load}
      />
    </div>
  );
}
