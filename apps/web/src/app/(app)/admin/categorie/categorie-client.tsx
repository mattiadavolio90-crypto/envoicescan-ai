"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import {
  RefreshCw, CheckCircle, Trash2, ArrowRightLeft, Search, Undo2, Activity,
  Lock, Sparkles, Moon, Play,
} from "lucide-react";
import { CATEGORIE_TUTTE } from "@/lib/admin";

// ─── Tipi condivisi ───────────────────────────────────────────────────────────
type ClienteOpzione = { id: string; nome: string };

const FONTE_META: Record<string, { label: string; icon: string; cls: string }> = {
  regola: { label: "Regola", icon: "🔧", cls: "bg-sky-100 text-sky-700" },
  memoria: { label: "Memoria", icon: "🧠", cls: "bg-violet-100 text-violet-700" },
  ai: { label: "AI", icon: "🤖", cls: "bg-amber-100 text-amber-700" },
};

// ─── SCHEDA: Da controllare ────────────────────────────────────────────────────
function DaControllareTab({ clienti, filtroCliente, setFiltroCliente }: {
  clienti: ClienteOpzione[];
  filtroCliente: string;
  setFiltroCliente: (v: string) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [gruppi, setGruppi] = useState<Record<string, unknown>[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [filtroBucket, setFiltroBucket] = useState("tutti");
  const [aiRunning, setAiRunning] = useState(false);
  const [bulkRunning, setBulkRunning] = useState(false);
  const [accepting, setAccepting] = useState<number | null>(null);

  // dialog classifica + conferma globale
  const [classGruppo, setClassGruppo] = useState<Record<string, unknown> | null>(null);
  const [classCategoria, setClassCategoria] = useState("📝 NOTE E DICITURE");
  const [classSaving, setClassSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ scope: "da_controllare" });
      if (filtroBucket !== "tutti") qs.set("bucket", filtroBucket);
      if (filtroCliente !== "tutti") qs.set("cliente_id", filtroCliente);
      const res = await fetch(`/api/admin/qualita-ai/coda?${qs}`);
      if (!res.ok) { toast.error("Errore caricamento coda"); return; }
      const d = await res.json();
      setGruppi(d.gruppi || []);
      setStats(d.stats || {});
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  }, [filtroBucket, filtroCliente]);

  useEffect(() => { load(); }, [load]);

  async function classificaIds(ids: unknown, categoria: string): Promise<number> {
    const res = await fetch("/api/admin/qualita-ai/coda/classifica", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, categoria, salva_memoria: true }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.detail || "Errore");
    return d.righe_aggiornate || 0;
  }

  async function handleRivediAI() {
    const nomeCliente = filtroCliente !== "tutti" ? clienti.find((c) => c.id === filtroCliente)?.nome : null;
    const scope = nomeCliente ? `del cliente "${nomeCliente}"` : "di tutti i clienti";
    if (!confirm(`Chiedere all'AI un suggerimento per le righe dubbie ${scope}? Non modifica nulla: prepara solo i suggerimenti da approvare.`)) return;
    setAiRunning(true);
    try {
      const res = await fetch("/api/admin/qualita-ai/coda/suggerisci-ai", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(filtroCliente !== "tutti" ? { cliente_id: filtroCliente } : {}),
      });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Errore"); return; }
      toast.success(`AI: ${d.suggerite} suggerimenti pronti${d.saltate ? `, ${d.saltate} già risolti` : ""}${d.errori ? ` (${d.errori} errori)` : ""}`);
      load();
    } catch { toast.error("Errore richiesta AI"); }
    finally { setAiRunning(false); }
  }

  // Gruppi "sicuri": suggerimento da regola o memoria (alta fiducia)
  const sicuri = gruppi.filter((g) => g.categoria_suggerita && (g.fonte === "regola" || g.fonte === "memoria"));

  async function handleAccettaSicuri() {
    if (sicuri.length === 0) return;
    if (!confirm(`Accettare ${sicuri.length} suggerimenti sicuri (regola/memoria)? Le categorie verranno salvate in memoria globale e varranno per TUTTI i clienti.`)) return;
    setBulkRunning(true);
    let ok = 0, ko = 0;
    for (const g of sicuri) {
      try { await classificaIds(g.ids, String(g.categoria_suggerita)); ok++; }
      catch { ko++; }
    }
    toast.success(`${ok} approvati${ko ? `, ${ko} errori` : ""}`);
    setBulkRunning(false);
    load();
  }

  async function handleAccetta(g: Record<string, unknown>, idx: number) {
    const suggerita = String(g.categoria_suggerita || "");
    if (!suggerita) return;
    if (!confirm(`Salvare "${suggerita}" per "${g.descrizione}"? Varrà in memoria globale per tutti i clienti.`)) return;
    setAccepting(idx);
    try {
      const n = await classificaIds(g.ids, suggerita);
      toast.success(`${n} righe → ${suggerita}`);
      setGruppi((prev) => prev.filter((_, i) => i !== idx));
    } catch (e) { toast.error(e instanceof Error ? e.message : "Errore"); }
    finally { setAccepting(null); }
  }

  async function handleClassifica() {
    if (!classGruppo || !classCategoria) return;
    if (!confirm(`Salvare "${classCategoria}" per "${classGruppo.descrizione}"? Varrà in memoria globale per tutti i clienti.`)) return;
    setClassSaving(true);
    try {
      const n = await classificaIds(classGruppo.ids, classCategoria);
      toast.success(`${n} righe classificate`);
      const desc = classGruppo.descrizione;
      setClassGruppo(null);
      setGruppi((prev) => prev.filter((g) => g.descrizione !== desc));
    } catch (e) { toast.error(e instanceof Error ? e.message : "Errore"); }
    finally { setClassSaving(false); }
  }

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { k: "totale", label: "Totale in coda", color: "text-foreground" },
          { k: "ambigue", label: "Da decidere", color: "text-red-600" },
          { k: "diciture", label: "Diciture", color: "text-blue-700" },
          { k: "sconti", label: "Sconti/Omaggi", color: "text-green-700" },
        ].map((s) => (
          <Card key={s.k} className="p-3">
            <p className="text-xs text-muted-foreground">{s.label}</p>
            <p className={`text-2xl font-bold tabular-nums ${s.color}`}>{stats[s.k] ?? "—"}</p>
          </Card>
        ))}
      </div>

      {/* Toolbar */}
      <div className="flex gap-2 flex-wrap items-center">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Cliente:</span>
          <Select value={filtroCliente} onValueChange={setFiltroCliente}>
            <SelectTrigger className="w-44 border-border bg-background"><SelectValue placeholder="Tutti i clienti" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="tutti">Tutti i clienti</SelectItem>
              {clienti.map((c) => <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Tipo:</span>
          <Select value={filtroBucket} onValueChange={setFiltroBucket}>
            <SelectTrigger className="w-40 border-border bg-background"><SelectValue placeholder="Tutti i tipi" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="tutti">Tutti i tipi</SelectItem>
              <SelectItem value="da_verificare">Da decidere</SelectItem>
              <SelectItem value="dicitura">Diciture</SelectItem>
              <SelectItem value="sconto_omaggio">Sconti/Omaggi</SelectItem>
              <SelectItem value="storno">Storni</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
        <Button size="sm" variant="outline" onClick={handleRivediAI} disabled={aiRunning}>
          <Sparkles className={`size-4 mr-1 ${aiRunning ? "animate-pulse" : ""}`} />
          {aiRunning ? "AI in corso…" : "Rivedi con AI"}
        </Button>
        {sicuri.length > 0 && (
          <Button size="sm" onClick={handleAccettaSicuri} disabled={bulkRunning} className="ml-auto">
            <CheckCircle className="size-4 mr-1" />
            {bulkRunning ? "Approvo…" : `Accetta tutti i sicuri (${sicuri.length})`}
          </Button>
        )}
      </div>

      {/* Tabella */}
      {gruppi.length === 0 ? (
        <div className="rounded-lg border p-10 text-center">
          {loading ? <p className="text-muted-foreground">Caricamento…</p> : (
            <div className="space-y-2">
              <CheckCircle className="size-10 text-emerald-500 mx-auto" />
              <p className="font-medium">Niente da controllare</p>
              <p className="text-sm text-muted-foreground">Tutte le categorie sono a posto.</p>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left">
                <th className="px-4 py-2 font-medium">Descrizione</th>
                <th className="px-4 py-2 font-medium hidden md:table-cell">Attuale</th>
                <th className="px-4 py-2 font-medium">Suggerita</th>
                <th className="px-4 py-2 font-medium hidden sm:table-cell">Fonte</th>
                <th className="px-4 py-2 font-medium hidden lg:table-cell">Cliente</th>
                <th className="px-4 py-2 font-medium hidden lg:table-cell">Occ.</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {gruppi.map((g, i) => {
                const suggerita = g.categoria_suggerita ? String(g.categoria_suggerita) : null;
                const fonte = g.fonte ? String(g.fonte) : null;
                const fm = fonte ? FONTE_META[fonte] : null;
                return (
                  <tr key={i} className="hover:bg-muted/30">
                    <td className="px-4 py-2 font-medium max-w-xs truncate" title={String(g.descrizione)}>{String(g.descrizione || "—")}</td>
                    <td className="px-4 py-2 hidden md:table-cell text-muted-foreground truncate max-w-[130px] text-xs">{String(g.categoria || "—")}</td>
                    <td className="px-4 py-2">
                      {suggerita ? (
                        <span className="rounded-full bg-emerald-100 text-emerald-700 px-2 py-0.5 text-xs font-semibold truncate inline-block max-w-[140px]" title={suggerita}>{suggerita}</span>
                      ) : <span className="text-xs text-muted-foreground">—</span>}
                    </td>
                    <td className="px-4 py-2 hidden sm:table-cell">
                      {fm ? <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${fm.cls}`}>{fm.icon} {fm.label}</span> : <span className="text-xs text-muted-foreground">—</span>}
                    </td>
                    <td className="px-4 py-2 hidden lg:table-cell text-xs text-muted-foreground truncate max-w-[120px]">{String(g.cliente || "—")}</td>
                    <td className="px-4 py-2 hidden lg:table-cell tabular-nums text-xs">{String(g.count)}</td>
                    <td className="px-4 py-2">
                      <div className="flex gap-1 justify-end">
                        {suggerita && (
                          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-emerald-700 hover:bg-emerald-50"
                            disabled={accepting === i} onClick={() => handleAccetta(g, i)}>
                            {accepting === i ? "…" : "Accetta"}
                          </Button>
                        )}
                        <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => {
                          setClassGruppo(g);
                          setClassCategoria(suggerita || (String(g.bucket) === "dicitura" ? "📝 NOTE E DICITURE" : String(g.categoria || "📝 NOTE E DICITURE")));
                        }}>
                          Scegli
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Dialog classifica */}
      <Dialog open={!!classGruppo} onOpenChange={(o) => !o && setClassGruppo(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Scegli categoria</DialogTitle>
            <DialogDescription className="truncate">{String(classGruppo?.descrizione || "")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-muted-foreground">{String(classGruppo?.count || 0)} occorrenze · {String(classGruppo?.cliente || "")}</p>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Categoria</label>
              <Select value={classCategoria} onValueChange={setClassCategoria}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent className="max-h-72">
                  {CATEGORIE_TUTTE.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <p className="text-xs text-amber-600">⚠️ La scelta verrà salvata in memoria globale e varrà per tutti i clienti.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setClassGruppo(null)} disabled={classSaving}>Annulla</Button>
            <Button onClick={handleClassifica} disabled={classSaving}>
              {classSaving ? "Salvataggio…" : "Applica e salva"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── SCHEDA: Scelte clienti (sola lettura) ──────────────────────────────────────
function ScelteClientiTab({ clienti, filtroCliente, setFiltroCliente }: {
  clienti: ClienteOpzione[];
  filtroCliente: string;
  setFiltroCliente: (v: string) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [gruppi, setGruppi] = useState<Record<string, unknown>[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ scope: "scelte_clienti" });
      if (filtroCliente !== "tutti") qs.set("cliente_id", filtroCliente);
      const res = await fetch(`/api/admin/qualita-ai/coda?${qs}`);
      if (!res.ok) { toast.error("Errore caricamento"); return; }
      const d = await res.json();
      setGruppi(d.gruppi || []);
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  }, [filtroCliente]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex gap-2 items-center flex-wrap">
        <Select value={filtroCliente} onValueChange={setFiltroCliente}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Tutti i clienti" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="tutti">Tutti i clienti</SelectItem>
            {clienti.map((c) => <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>)}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
      </div>
      <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700">
        <Lock className="size-4 mt-0.5 shrink-0" />
        <span>Queste categorie sono state scelte a mano dai clienti (o promosse manualmente). Sono intoccabili: anche se sembrano sbarcate, per il cliente vanno bene così. Non compaiono nella coda &quot;Da controllare&quot;.</span>
      </div>
      {gruppi.length === 0 ? (
        <div className="rounded-lg border p-10 text-center text-sm text-muted-foreground">
          {loading ? "Caricamento…" : "Nessuna scelta manuale in coda speciale."}
        </div>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="border-b bg-muted/50 text-left">
              <th className="px-4 py-2 font-medium">Descrizione</th>
              <th className="px-4 py-2 font-medium">Categoria</th>
              <th className="px-4 py-2 font-medium hidden md:table-cell">Cliente</th>
              <th className="px-4 py-2 font-medium hidden lg:table-cell">Occ.</th>
            </tr></thead>
            <tbody className="divide-y">
              {gruppi.map((g, i) => (
                <tr key={i} className="hover:bg-muted/30">
                  <td className="px-4 py-2 font-medium max-w-xs truncate" title={String(g.descrizione)}>
                    <Lock className="inline size-3 mr-1 text-amber-500" />{String(g.descrizione || "—")}
                  </td>
                  <td className="px-4 py-2 text-xs">{String(g.categoria || "—")}</td>
                  <td className="px-4 py-2 hidden md:table-cell text-xs text-muted-foreground truncate max-w-[140px]">{String(g.cliente || "—")}</td>
                  <td className="px-4 py-2 hidden lg:table-cell tabular-nums text-xs">{String(g.count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── SCHEDA: Memoria globale ────────────────────────────────────────────────────
type ProdRow = { id: string; descrizione: string; categoria: string; volte_visto: number; verified: boolean; classificato_da: string; categoria_suggerita?: string; motivo?: string };

function MemoriaTab() {
  const [rows, setRows] = useState<ProdRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [stato, setStato] = useState("tutti");
  const [editRow, setEditRow] = useState<ProdRow | null>(null);
  const [editCat, setEditCat] = useState("");
  const [editSaving, setEditSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ stato, page: String(page), per_page: "100", ...(search ? { search } : {}) });
      const res = await fetch(`/api/admin/qualita-ai/memoria?${qs}`);
      if (!res.ok) { toast.error("Errore caricamento memoria"); return; }
      const d = await res.json();
      setRows(d.rows || []);
      setTotal(d.total || 0);
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  }, [stato, page, search]);

  useEffect(() => { load(); }, [load]);

  async function handleSalvaEdit() {
    if (!editRow || !editCat) return;
    setEditSaving(true);
    try {
      await fetch(`/api/admin/qualita-ai/memoria/${editRow.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ categoria: editCat }),
      });
      toast.success("Categoria aggiornata");
      setEditRow(null);
      load();
    } catch { toast.error("Errore"); }
    finally { setEditSaving(false); }
  }

  async function handleDelete(id: string) {
    if (!confirm("Eliminare questa voce dalla memoria globale?")) return;
    try {
      await fetch(`/api/admin/qualita-ai/memoria/${id}`, { method: "DELETE" });
      toast.success("Voce eliminata");
      setRows((prev) => prev.filter((r) => r.id !== id));
      setTotal((t) => t - 1);
    } catch { toast.error("Errore"); }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input placeholder="Cerca descrizione…" className="pl-9" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        </div>
        <Select value={stato} onValueChange={(v) => { setStato(v); setPage(1); }}>
          <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="tutti">Tutti</SelectItem>
            <SelectItem value="verified">Verificati</SelectItem>
            <SelectItem value="non_verified">Non verificati</SelectItem>
            <SelectItem value="sospette">Sospetti AI</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">{total} voci · pagina {page}</p>
      <div className="rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="border-b bg-muted/50 text-left">
            <th className="px-4 py-2 font-medium">Descrizione</th>
            <th className="px-4 py-2 font-medium">Categoria</th>
            {stato === "sospette" && <th className="px-4 py-2 font-medium">Suggerita</th>}
            <th className="px-4 py-2 font-medium">×</th>
            <th className="px-4 py-2 font-medium">✓</th>
            <th className="px-4 py-2" />
          </tr></thead>
          <tbody className="divide-y">
            {rows.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">{loading ? "Caricamento…" : "Nessun risultato"}</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="hover:bg-muted/30">
                <td className="px-4 py-2 max-w-[220px] truncate text-xs" title={r.descrizione}>{r.descrizione}</td>
                <td className="px-4 py-2 text-xs text-muted-foreground truncate max-w-[130px]">{r.categoria}</td>
                {stato === "sospette" && <td className="px-4 py-2 text-xs text-amber-600">{r.categoria_suggerita || "—"}</td>}
                <td className="px-4 py-2 tabular-nums text-xs">{r.volte_visto}</td>
                <td className="px-4 py-2">{r.verified ? <CheckCircle className="size-4 text-emerald-500" /> : <span className="text-muted-foreground text-xs">—</span>}</td>
                <td className="px-4 py-2">
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => { setEditRow(r); setEditCat(r.categoria); }}>Modifica</Button>
                    <Button size="sm" variant="ghost" className="h-7 px-2 text-destructive hover:text-destructive" onClick={() => handleDelete(r.id)}>
                      <Trash2 className="size-3" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>← Precedente</Button>
        <Button variant="outline" size="sm" disabled={rows.length < 100} onClick={() => setPage((p) => p + 1)}>Successiva →</Button>
      </div>

      <Dialog open={!!editRow} onOpenChange={(o) => !o && setEditRow(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Modifica categoria</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm truncate text-muted-foreground">{editRow?.descrizione}</p>
            <Select value={editCat} onValueChange={setEditCat}>
              <SelectTrigger><SelectValue placeholder="Seleziona categoria…" /></SelectTrigger>
              <SelectContent className="max-h-72">
                {CATEGORIE_TUTTE.map((cat) => <SelectItem key={cat} value={cat}>{cat}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditRow(null)}>Annulla</Button>
            <Button onClick={handleSalvaEdit} disabled={editSaving}>{editSaving ? "Salvataggio…" : "Salva"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── SCHEDA: Storico (audit + conflitti) ────────────────────────────────────────
type Conflitto = { local_id: string; global_id: string; descrizione: string; categoria_locale: string; categoria_globale: string; email_cliente: string; nome_cliente: string; volte_locale: number; volte_globale: number };

function ConflittiRiquadro() {
  const [conflitti, setConflitti] = useState<Conflitto[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/qualita-ai/conflitti");
      if (res.ok) setConflitti(await res.json());
    } catch { /* silenzioso */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function risolvi(c: Conflitto, azione: "promuovi" | "ignora") {
    try {
      await fetch("/api/admin/qualita-ai/conflitti/risolvi", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ local_id: c.local_id, azione }),
      });
      toast.success(azione === "promuovi" ? "Promossa a globale" : "Conflitto ignorato");
      setConflitti((prev) => prev.filter((x) => x.local_id !== c.local_id));
    } catch { toast.error("Errore"); }
  }

  if (loading && conflitti.length === 0) return null;
  if (conflitti.length === 0) return null;

  return (
    <Card className="p-4 border-amber-500/40">
      <div className="flex items-center gap-2 mb-2">
        <ArrowRightLeft className="size-4 text-amber-600" />
        <h3 className="text-sm font-semibold">Conflitti locale ↔ globale ({conflitti.length})</h3>
      </div>
      <div className="space-y-1.5">
        {conflitti.map((c) => (
          <div key={c.local_id} className="flex items-center justify-between gap-2 text-xs border-b pb-1.5">
            <span className="truncate max-w-[180px]" title={c.descrizione}>{c.descrizione}</span>
            <span className="text-amber-700 shrink-0">{c.categoria_locale}</span>
            <span className="text-muted-foreground shrink-0">vs {c.categoria_globale}</span>
            <div className="flex gap-1 shrink-0">
              <Button size="sm" variant="outline" className="h-6 text-xs" onClick={() => risolvi(c, "promuovi")}>Promuovi</Button>
              <Button size="sm" variant="ghost" className="h-6 text-xs text-muted-foreground" onClick={() => risolvi(c, "ignora")}>Ignora</Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

type LogRow = {
  id: number; created_at: string; attore: string; azione: string; descrizione: string;
  categoria_da: string; categoria_a: string; righe_count: number; nota: string; annullato_at: string | null;
};
const AZIONE_LABEL: Record<string, string> = {
  classifica: "Classifica manuale", auto_review: "Auto-review", risolvi_conflitto: "Risolvi conflitto", annulla: "Annullata",
};
const AZIONE_COLOR: Record<string, string> = {
  classifica: "bg-sky-100 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300",
  auto_review: "bg-violet-100 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300",
  risolvi_conflitto: "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300",
  annulla: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};

function StoricoTab() {
  const [rows, setRows] = useState<LogRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [soloAnnullabili, setSoloAnnullabili] = useState(false);
  const [undoing, setUndoing] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ page: String(page), per_page: "50" });
      if (soloAnnullabili) qs.set("solo_annullabili", "true");
      const res = await fetch(`/api/admin/qualita-ai/audit?${qs}`);
      if (!res.ok) { toast.error("Errore caricamento log"); return; }
      const d = await res.json();
      setRows(d.rows || []);
      setTotal(d.total || 0);
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  }, [page, soloAnnullabili]);

  useEffect(() => { load(); }, [load]);

  async function handleAnnulla(row: LogRow) {
    if (!confirm(`Annullare "${AZIONE_LABEL[row.azione] || row.azione}" su "${row.descrizione || "—"}" (${row.righe_count} righe)?`)) return;
    setUndoing(row.id);
    try {
      const res = await fetch("/api/admin/qualita-ai/audit/annulla", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ log_id: row.id }),
      });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Errore annullamento"); return; }
      toast.success(`Annullato: ${d.righe_ripristinate} righe ripristinate a "${row.categoria_da}"`);
      load();
    } catch { toast.error("Errore di connessione"); }
    finally { setUndoing(null); }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Registro di tutte le modifiche di categoria (chi, quando, da quale categoria a quale). Da qui puoi anche annullare un&apos;azione.
      </p>
      <ConflittiRiquadro />
      <div className="flex gap-2 flex-wrap items-center">
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={soloAnnullabili} onChange={(e) => { setSoloAnnullabili(e.target.checked); setPage(1); }} className="rounded" />
          Solo annullabili
        </label>
        <span className="text-sm text-muted-foreground">{total} azioni totali</span>
      </div>
      <div className="rounded-lg border overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b bg-muted/50 text-left">
              <th className="px-3 py-2 font-medium">Data</th>
              <th className="px-3 py-2 font-medium">Tipo</th>
              <th className="px-3 py-2 font-medium">Descrizione</th>
              <th className="px-3 py-2 font-medium hidden md:table-cell">Da → A</th>
              <th className="px-3 py-2 font-medium">N.</th>
              <th className="px-3 py-2 font-medium hidden lg:table-cell">Attore</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                {loading ? "Caricamento…" : (
                  <div className="space-y-2"><Activity className="size-8 text-muted-foreground/50 mx-auto" /><p>Nessuna azione registrata</p></div>
                )}
              </td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className={`hover:bg-muted/30 ${r.annullato_at ? "opacity-50" : ""}`}>
                <td className="px-3 py-2 tabular-nums whitespace-nowrap text-muted-foreground">
                  {new Date(r.created_at).toLocaleString("it-IT", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                </td>
                <td className="px-3 py-2">
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${AZIONE_COLOR[r.azione] || "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"}`}>
                    {AZIONE_LABEL[r.azione] || r.azione}
                  </span>
                </td>
                <td className="px-3 py-2 max-w-[180px] truncate" title={r.descrizione}>{r.descrizione || "—"}</td>
                <td className="px-3 py-2 hidden md:table-cell">
                  {r.categoria_da ? (<span className="text-muted-foreground">{r.categoria_da} <span className="mx-1">→</span> {r.categoria_a}</span>) : (<span>{r.categoria_a}</span>)}
                </td>
                <td className="px-3 py-2 tabular-nums font-medium">{r.righe_count}</td>
                <td className="px-3 py-2 hidden lg:table-cell text-muted-foreground truncate max-w-[120px]">{r.attore}</td>
                <td className="px-3 py-2">
                  {!r.annullato_at && r.azione !== "annulla" && r.categoria_da && r.righe_count > 0 ? (
                    <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-amber-600 hover:text-amber-700"
                      disabled={undoing === r.id} onClick={() => handleAnnulla(r)} title="Ripristina categoria precedente">
                      <Undo2 className="size-3 mr-1" />{undoing === r.id ? "…" : "Annulla"}
                    </Button>
                  ) : r.annullato_at ? (<span className="text-[10px] text-muted-foreground">Annullata</span>) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>← Precedente</Button>
        <Button variant="outline" size="sm" disabled={rows.length < 50} onClick={() => setPage((p) => p + 1)}>Successiva →</Button>
      </div>
    </div>
  );
}

// ─── Pannello Agent Notturno (dialog) ───────────────────────────────────────────
type AgentStatus = {
  enabled: boolean; ora_utc: number; last_run_at: string | null; last_digest: Record<string, unknown> | null; running: boolean;
};

function AgentNotturnoDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [running, setRunning] = useState(false);
  const [oraUtc, setOraUtc] = useState("2");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/sistema/agent-notturno");
      if (!res.ok) { toast.error("Errore caricamento stato agent"); return; }
      const d: AgentStatus = await res.json();
      setStatus(d);
      setOraUtc(String(d.ora_utc ?? 2));
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (open) load(); }, [open, load]);

  async function handleToggle(enabled: boolean) {
    setToggling(true);
    try {
      const res = await fetch("/api/admin/sistema/agent-notturno/toggle", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled, ora_utc: parseInt(oraUtc) || 2 }),
      });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Errore"); return; }
      toast.success(enabled ? "Agent notturno abilitato" : "Agent notturno disabilitato");
      load();
    } catch { toast.error("Errore di connessione"); }
    finally { setToggling(false); }
  }

  async function handleEseguiOra() {
    if (!confirm("Eseguire subito l'agent notturno? Classifica le diciture/sconti sicuri e prepara i suggerimenti AI sulle righe dubbie.")) return;
    setRunning(true);
    try {
      const res = await fetch("/api/admin/sistema/agent-notturno/esegui-ora", { method: "POST" });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Errore avvio"); return; }
      toast.success(d.message || "Agent avviato — ricarica tra qualche secondo");
      setTimeout(load, 5000);
    } catch { toast.error("Errore di connessione"); }
    finally { setRunning(false); }
  }

  const digest = status?.last_digest as Record<string, unknown> | null;
  const oraItaliana = status ? `${((status.ora_utc + 2) % 24).toString().padStart(2, "0")}:00` : "—";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Moon className="size-5 text-violet-500" /> Agent Notturno AI</DialogTitle>
          <DialogDescription>
            Ogni notte classifica le diciture/sconti sicuri e <strong>prepara i suggerimenti AI</strong> sulle righe dubbie (senza applicarli). La mattina trovi la coda già pronta da approvare.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="flex items-center justify-between">
            <span className="text-sm">Stato</span>
            <span className={`text-sm font-semibold ${status?.enabled ? "text-emerald-600" : "text-muted-foreground"}`}>
              {loading ? "…" : status?.enabled ? "Attivo" : "Disattivato"}
              {status?.running && <span className="ml-2 text-amber-600 animate-pulse">in esecuzione…</span>}
            </span>
          </div>
          <div className="flex flex-wrap gap-3 items-end">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Ora esecuzione (UTC)</label>
              <Select value={oraUtc} onValueChange={setOraUtc}>
                <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                <SelectContent className="max-h-60">
                  {Array.from({ length: 24 }, (_, h) => (
                    <SelectItem key={h} value={String(h)}>{String(h).padStart(2, "0")}:00 UTC ({String((h + 2) % 24).padStart(2, "0")}:00 IT)</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2">
              {status?.enabled ? (
                <Button variant="outline" onClick={() => handleToggle(false)} disabled={toggling}>{toggling ? "…" : "Disabilita"}</Button>
              ) : (
                <Button onClick={() => handleToggle(true)} disabled={toggling}><Moon className="size-4 mr-1" />{toggling ? "…" : "Abilita"}</Button>
              )}
              <Button variant="outline" onClick={handleEseguiOra} disabled={running || status?.running}>
                <Play className="size-4 mr-1" />{running ? "Avvio…" : "Esegui ora"}
              </Button>
            </div>
          </div>
          {status?.enabled && (
            <p className="text-xs text-muted-foreground">Programmato ogni giorno alle <strong>{oraItaliana} ora italiana</strong> ({status.ora_utc}:00 UTC)</p>
          )}
          {status?.last_run_at && digest && !digest.errore && (
            <div className="rounded-md border p-3 space-y-1 text-xs">
              <p className="text-muted-foreground">Ultima esecuzione: {new Date(status.last_run_at).toLocaleString("it-IT", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</p>
              <p>Classificate: <strong>{String(digest.classificate ?? "—")}</strong> · Suggerimenti AI: <strong>{String(digest.suggerite_ai ?? "—")}</strong> · Errori: <strong>{String(digest.errori ?? "—")}</strong></p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── ROOT ───────────────────────────────────────────────────────────────────────
const TABS = ["da_controllare", "scelte_clienti", "memoria", "storico"] as const;
const TAB_LABELS: Record<string, string> = {
  da_controllare: "📋 Da controllare",
  scelte_clienti: "🔒 Scelte clienti",
  memoria: "🌍 Memoria globale",
  storico: "📜 Storico modifiche",
};

export function CategorieClient() {
  const [tab, setTab] = useState<typeof TABS[number]>("da_controllare");
  const [clienti, setClienti] = useState<ClienteOpzione[]>([]);
  const [filtroCliente, setFiltroCliente] = useState("tutti");
  const [agentOpen, setAgentOpen] = useState(false);

  useEffect(() => {
    fetch("/api/admin/clienti")
      .then((r) => r.ok ? r.json() : [])
      .then((data: { id: string; nome_ristorante: string }[]) =>
        setClienti(data.map((c) => ({ id: c.id, nome: c.nome_ristorante || c.id }))))
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex gap-1 border-b flex-1 min-w-0 overflow-x-auto">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
              {TAB_LABELS[t]}
            </button>
          ))}
        </div>
        <Button variant="outline" size="sm" onClick={() => setAgentOpen(true)}>
          <Moon className="size-4 mr-1" /> Agent notturno
        </Button>
      </div>

      {tab === "da_controllare" && <DaControllareTab clienti={clienti} filtroCliente={filtroCliente} setFiltroCliente={setFiltroCliente} />}
      {tab === "scelte_clienti" && <ScelteClientiTab clienti={clienti} filtroCliente={filtroCliente} setFiltroCliente={setFiltroCliente} />}
      {tab === "memoria" && <MemoriaTab />}
      {tab === "storico" && <StoricoTab />}

      <AgentNotturnoDialog open={agentOpen} onOpenChange={setAgentOpen} />
    </div>
  );
}
