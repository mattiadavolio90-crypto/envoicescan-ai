"use client";

import { useState, useEffect } from "react";
import { Plus, Pencil, Trash2, Info, BookOpen, BarChart3, Copy, ChevronUp, ChevronDown, AlertTriangle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { toast } from "sonner";
import {
  FC_BADGE_CLASS, fmtEuro, fmtPct, coloreFC,
  type RicetteResponse, type Ricetta, type RicettaDettaglio, type CategoriaStats,
} from "@/lib/foodcost";

function BadgeFC({ incidenza }: { incidenza: number | null }) {
  if (incidenza == null) return <span className="text-muted-foreground text-xs">—</span>;
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${FC_BADGE_CLASS[coloreFC(incidenza)]}`}>
      {fmtPct(incidenza)}
    </span>
  );
}
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
      if (!res.ok) throw new Error();
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
      if (!res.ok) throw new Error();
      const d: RicettaDettaglio = await res.json();
      setEditorRicetta(d);
      setEditorOpen(true);
    } catch {
      toast.error("Errore caricamento ricetta");
    }
  }

  async function elimina(r: Ricetta) {
    if (!confirm(`Eliminare "${r.nome}"?`)) return;
    try {
      const res = await fetch(`/api/workspace/foodcost/ricette/${r.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Ricetta eliminata");
      load();
    } catch {
      toast.error("Errore eliminazione ricetta");
    }
  }

  async function duplica(r: Ricetta) {
    try {
      const res = await fetch(`/api/workspace/foodcost/ricette/${r.id}`);
      const d: RicettaDettaglio = await res.json();
      const cr = await fetch("/api/workspace/foodcost/ricette", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nome: `${d.nome} (copia)`,
          categoria: d.categoria,
          prezzo_vendita_ivainc: d.prezzo_vendita_ivainc,
          righe: d.righe,
        }),
      });
      if (!cr.ok) throw new Error();
      toast.success("Ricetta duplicata");
      load();
    } catch {
      toast.error("Errore duplicazione");
    }
  }

  async function sposta(id: string, dir: -1 | 1) {
    const arr = [...ricette];
    const i = arr.findIndex(x => x.id === id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= arr.length) return;
    [arr[i], arr[j]] = [arr[j], arr[i]];
    setData(prev => prev ? { ...prev, ricette: arr } : prev); // ottimistico
    try {
      await fetch("/api/workspace/foodcost/ricette/riordina", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ordine: arr.map(x => x.id) }),
      });
    } catch {
      toast.error("Errore riordino");
      load();
    }
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
            <div className="border-t pt-2 space-y-1 text-muted-foreground">
              <p className="flex items-center gap-1.5"><AlertTriangle className="size-3.5 text-amber-500" /> = il prezzo di un ingrediente è aumentato nelle fatture rispetto a quando hai salvato la ricetta.</p>
              <p>Usa le frecce ▲▼ per ordinare le ricette e l'icona copia per duplicarne una.</p>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      {/* KPI */}
      {kpi && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card className="ring-sky-400/60"><CardContent className="py-3 px-4">
            <p className="text-xs text-muted-foreground">Ricette totali</p>
            <p className="text-2xl font-bold">{kpi.totale}</p>
          </CardContent></Card>
          <Card className="ring-sky-400/60"><CardContent className="py-3 px-4">
            <p className="text-xs text-muted-foreground">Costo medio ricetta</p>
            <p className="text-2xl font-bold">{fmtEuro(kpi.costo_medio)}</p>
          </CardContent></Card>
          <Card className="ring-sky-400/60"><CardContent className="py-3 px-4">
            <p className="text-xs text-muted-foreground">Margine medio</p>
            <p className="text-2xl font-bold">{fmtEuro(kpi.margine_medio)}</p>
          </CardContent></Card>
          <Card className="ring-sky-400/60"><CardContent className="py-3 px-4">
            <p className="text-xs text-muted-foreground">Incidenza FC media</p>
            <p className="text-2xl font-bold">{fmtPct(kpi.incidenza_media)}</p>
          </CardContent></Card>
        </div>
      )}

      {/* Analisi per categoria — sopra le ricette */}
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
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">N.</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">FC totale</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">FC medio</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">Margine medio</th>
                    <th className="text-center px-3 py-2 font-medium text-muted-foreground">Inc. FC%</th>
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
                      <td className="px-3 py-2 text-center"><BadgeFC incidenza={c.incidenza_media} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Ricette — card separate con bordo blu */}
      {loading ? (
        <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
      ) : ricetteFiltrate.length === 0 ? (
        <div className="py-16 text-center text-sm text-muted-foreground">
          {ricette.length === 0
            ? "Nessuna ricetta ancora. Crea la tua prima ricetta con il bottone qui sopra."
            : "Nessuna ricetta per questa categoria."}
        </div>
      ) : (
        <div className="space-y-2">
          {ricetteFiltrate.map((r, idx) => (
            <Card key={r.id} className="ring-sky-400/60 transition-colors hover:ring-sky-400">
              <CardContent className="py-3 px-4 flex items-center gap-3">
                {/* Frecce riordino — solo senza filtro categoria */}
                {filtroCategoria === "TUTTI" && (
                  <div className="flex flex-col -my-1 shrink-0">
                    <button
                      onClick={() => sposta(r.id, -1)}
                      disabled={idx === 0}
                      className="text-muted-foreground hover:text-foreground disabled:opacity-25 disabled:cursor-default p-0.5 leading-none"
                      title="Sposta su"
                    >
                      <ChevronUp className="size-4" />
                    </button>
                    <button
                      onClick={() => sposta(r.id, 1)}
                      disabled={idx === ricetteFiltrate.length - 1}
                      className="text-muted-foreground hover:text-foreground disabled:opacity-25 disabled:cursor-default p-0.5 leading-none"
                      title="Sposta giù"
                    >
                      <ChevronDown className="size-4" />
                    </button>
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="font-medium truncate">{r.nome}</p>
                    {r.alert_prezzo && (
                      <span title={`Prezzo aumentato per: ${(r.ingredienti_aumentati ?? []).join(", ")}`} className="shrink-0">
                        <AlertTriangle className="size-4 text-amber-500" />
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{r.categoria}</p>
                </div>
                <div className="hidden sm:block text-right w-24 shrink-0">
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Foodcost</p>
                  <p className="text-sm font-medium">{fmtEuro(r.foodcost_totale)}</p>
                </div>
                <div className="hidden sm:block text-right w-24 shrink-0">
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Prezzo</p>
                  <p className="text-sm text-muted-foreground">{r.prezzo_vendita_ivainc ? fmtEuro(r.prezzo_vendita_ivainc) : "—"}</p>
                </div>
                <div className="text-right w-24 shrink-0">
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Margine</p>
                  <p className="text-sm font-medium">{fmtEuro(r.margine)}</p>
                </div>
                <div className="w-20 shrink-0 flex flex-col items-center gap-0.5">
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Inc. FC%</p>
                  <BadgeFC incidenza={r.incidenza_pct} />
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Button size="icon" variant="ghost" className="size-8" onClick={() => duplica(r)} title="Duplica">
                    <Copy className="size-4" />
                  </Button>
                  <Button size="icon" variant="ghost" className="size-8" onClick={() => apriModifica(r)} title="Modifica">
                    <Pencil className="size-4" />
                  </Button>
                  <Button size="icon" variant="ghost" className="size-8 text-muted-foreground hover:text-destructive" onClick={() => elimina(r)} title="Elimina">
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
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
