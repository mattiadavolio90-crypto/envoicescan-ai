"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import {
  RefreshCw, Bot, CheckCircle, AlertTriangle, Zap, Trash2, ArrowRightLeft, Search, Undo2, Activity
} from "lucide-react";
import { CATEGORIE_TUTTE } from "@/lib/admin";

const CATEGORIE_SPECIALI = ["📝 NOTE E DICITURE", "SERVIZI E CONSULENZE", "BEVANDE FREDDE", "FOOD GENERICO", "ALTRI COSTI"];

const BUCKET_LABEL: Record<string, string> = {
  dicitura: "Dicitura",
  sconto_omaggio: "Sconto/Omaggio",
  storno: "Storno",
  da_verificare: "Da verificare",
};
const BUCKET_COLOR: Record<string, string> = {
  dicitura: "bg-blue-100 text-blue-700",
  sconto_omaggio: "bg-green-100 text-green-700",
  storno: "bg-orange-100 text-orange-700",
  da_verificare: "bg-red-100 text-red-700",
};

// ─── TAB CODA ────────────────────────────────────────────────────────────────
type ClienteOpzione = { id: string; nome: string };

function CodaTab() {
  const [loading, setLoading] = useState(false);
  const [gruppi, setGruppi] = useState<Record<string, unknown>[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [filtroBucket, setFiltroBucket] = useState("tutti");
  const [filtroCliente, setFiltroCliente] = useState("tutti");
  const [clienti, setClienti] = useState<ClienteOpzione[]>([]);
  const [autoRunning, setAutoRunning] = useState(false);

  // classify dialog
  const [classDialog, setClassDialog] = useState(false);
  const [classGruppo, setClassGruppo] = useState<Record<string, unknown> | null>(null);
  const [classCategoria, setClassCategoria] = useState("📝 NOTE E DICITURE");
  const [classSaving, setClassSaving] = useState(false);

  useEffect(() => {
    fetch("/api/admin/clienti")
      .then((r) => r.ok ? r.json() : [])
      .then((data: { id: string; nome_ristorante: string }[]) =>
        setClienti(data.map((c) => ({ id: c.id, nome: c.nome_ristorante || c.id })))
      )
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (filtroBucket !== "tutti") qs.set("bucket", filtroBucket);
      if (filtroCliente !== "tutti") qs.set("cliente_id", filtroCliente);
      const res = await fetch(`/api/admin/qualita-ai/coda${qs.toString() ? `?${qs}` : ""}`);
      if (!res.ok) { toast.error("Errore caricamento coda"); return; }
      const d = await res.json();
      setGruppi(d.gruppi || []);
      setStats(d.stats || {});
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  }, [filtroBucket, filtroCliente]);

  useEffect(() => { load(); }, [load]);

  async function handleAutoReview() {
    const nomeCliente = filtroCliente !== "tutti" ? clienti.find((c) => c.id === filtroCliente)?.nome : null;
    const scope = nomeCliente ? `del cliente "${nomeCliente}"` : "di tutti i clienti";
    if (!confirm(`Eseguire auto-classificazione su diciture sicure e sconti/omaggi ${scope}?`)) return;
    setAutoRunning(true);
    try {
      const res = await fetch("/api/admin/qualita-ai/coda/auto-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(filtroCliente !== "tutti" ? { cliente_id: filtroCliente } : {}),
      });
      const d = await res.json();
      toast.success(`Auto-review: ${d.classificate} righe classificate, ${d.salvate_memoria} salvate in memoria${d.errori > 0 ? ` (${d.errori} errori)` : ""}`);
      load();
    } catch { toast.error("Errore auto-review"); }
    finally { setAutoRunning(false); }
  }

  async function handleClassifica() {
    if (!classGruppo || !classCategoria) return;
    setClassSaving(true);
    try {
      const res = await fetch("/api/admin/qualita-ai/coda/classifica", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: classGruppo.ids, categoria: classCategoria, salva_memoria: true }),
      });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Errore"); return; }
      toast.success(`${d.righe_aggiornate} righe classificate`);
      setClassDialog(false);
      setGruppi((prev) => prev.filter((g) => g.descrizione !== classGruppo.descrizione));
    } catch { toast.error("Errore"); }
    finally { setClassSaving(false); }
  }

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {[
          { k: "totale", label: "Totale", color: "text-foreground" },
          { k: "diciture", label: "Diciture", color: "text-blue-700" },
          { k: "sconti", label: "Sconti/Omaggi", color: "text-green-700" },
          { k: "storni", label: "Storni", color: "text-orange-700" },
          { k: "ambigue", label: "Ambigue", color: "text-red-600" },
        ].map((s) => (
          <Card key={s.k} className="p-3">
            <p className="text-xs text-muted-foreground">{s.label}</p>
            <p className={`text-2xl font-bold tabular-nums ${s.color}`}>{stats[s.k] ?? "—"}</p>
          </Card>
        ))}
      </div>

      {/* Toolbar */}
      <div className="flex gap-2 flex-wrap">
        <Select value={filtroCliente} onValueChange={(v) => { setFiltroCliente(v); }}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Tutti i clienti" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="tutti">Tutti i clienti</SelectItem>
            {clienti.map((c) => <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filtroBucket} onValueChange={setFiltroBucket}>
          <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="tutti">Tutti i bucket</SelectItem>
            <SelectItem value="da_verificare">Da verificare</SelectItem>
            <SelectItem value="dicitura">Diciture</SelectItem>
            <SelectItem value="sconto_omaggio">Sconti/Omaggi</SelectItem>
            <SelectItem value="storno">Storni</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
        <Button size="sm" onClick={handleAutoReview} disabled={autoRunning}>
          <Bot className={`size-4 mr-1 ${autoRunning ? "animate-spin" : ""}`} />
          {autoRunning ? "Auto-review…" : "Auto-review"}
        </Button>
      </div>

      {/* Tabella gruppi */}
      {gruppi.length === 0 ? (
        <div className="rounded-lg border p-10 text-center">
          {loading ? <p className="text-muted-foreground">Caricamento…</p> : (
            <div className="space-y-2">
              <CheckCircle className="size-10 text-emerald-500 mx-auto" />
              <p className="font-medium">Coda vuota</p>
              <p className="text-sm text-muted-foreground">Nessuna riga speciale da revisionare</p>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left">
                <th className="px-4 py-2 font-medium">Descrizione</th>
                <th className="px-4 py-2 font-medium">Tipo</th>
                <th className="px-4 py-2 font-medium">Occ.</th>
                <th className="px-4 py-2 font-medium hidden md:table-cell">Categoria attuale</th>
                <th className="px-4 py-2 font-medium hidden lg:table-cell">€ max</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {gruppi.map((g, i) => (
                <tr key={i} className="hover:bg-muted/30">
                  <td className="px-4 py-2 font-medium max-w-xs truncate" title={String(g.descrizione)}>{String(g.descrizione || "—")}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${BUCKET_COLOR[String(g.bucket)] || ""}`}>
                      {BUCKET_LABEL[String(g.bucket)] || String(g.bucket)}
                    </span>
                  </td>
                  <td className="px-4 py-2 tabular-nums">{String(g.count)}</td>
                  <td className="px-4 py-2 hidden md:table-cell text-muted-foreground truncate max-w-[140px]">{String(g.categoria || "—")}</td>
                  <td className="px-4 py-2 hidden lg:table-cell tabular-nums">€{Number(g.prezzo_max).toFixed(2)}</td>
                  <td className="px-4 py-2">
                    <Button size="sm" variant="outline" onClick={() => {
                      setClassGruppo(g);
                      setClassCategoria(String(g.bucket) === "dicitura" ? "📝 NOTE E DICITURE" : String(g.categoria || "📝 NOTE E DICITURE"));
                      setClassDialog(true);
                    }}>
                      Classifica
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Dialog classifica */}
      <Dialog open={classDialog} onOpenChange={setClassDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Classifica gruppo</DialogTitle>
            <DialogDescription className="truncate">{String(classGruppo?.descrizione || "")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-muted-foreground">{String(classGruppo?.count || 0)} occorrenze · bucket: {BUCKET_LABEL[String(classGruppo?.bucket)] || ""}</p>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Categoria</label>
              <Select value={classCategoria} onValueChange={setClassCategoria}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CATEGORIE_SPECIALI.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setClassDialog(false)} disabled={classSaving}>Annulla</Button>
            <Button onClick={handleClassifica} disabled={classSaving}>
              {classSaving ? "Salvataggio…" : "Applica e salva in memoria"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── TAB MEMORIA ──────────────────────────────────────────────────────────────
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

// ─── TAB CONFLITTI ────────────────────────────────────────────────────────────
type Conflitto = { local_id: string; global_id: string; descrizione: string; categoria_locale: string; categoria_globale: string; email_cliente: string; nome_cliente: string; volte_locale: number; volte_globale: number };

function ConflittiTab() {
  const [conflitti, setConflitti] = useState<Conflitto[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/qualita-ai/conflitti");
      if (!res.ok) { toast.error("Errore caricamento conflitti"); return; }
      setConflitti(await res.json());
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  async function risolvi(c: Conflitto, azione: "promuovi" | "ignora") {
    try {
      await fetch("/api/admin/qualita-ai/conflitti/risolvi", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ local_id: c.local_id, azione }),
      });
      toast.success(azione === "promuovi" ? "Categoria locale promossa a globale" : "Conflitto ignorato");
      setConflitti((prev) => prev.filter((x) => x.local_id !== c.local_id));
    } catch { toast.error("Errore"); }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
        <p className="text-sm text-muted-foreground self-center">{conflitti.length} conflitti trovati</p>
      </div>
      {conflitti.length === 0 ? (
        <div className="rounded-lg border p-10 text-center">
          {loading ? <p className="text-muted-foreground">Caricamento…</p> : (
            <div className="space-y-2">
              <CheckCircle className="size-10 text-emerald-500 mx-auto" />
              <p className="font-medium">Nessun conflitto</p>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="border-b bg-muted/50 text-left">
              <th className="px-4 py-2 font-medium">Descrizione</th>
              <th className="px-4 py-2 font-medium">Cat. locale</th>
              <th className="px-4 py-2 font-medium">Cat. globale</th>
              <th className="px-4 py-2 font-medium hidden md:table-cell">Cliente</th>
              <th className="px-4 py-2" />
            </tr></thead>
            <tbody className="divide-y">
              {conflitti.map((c) => (
                <tr key={c.local_id} className="hover:bg-muted/30">
                  <td className="px-4 py-2 max-w-[160px] truncate text-xs" title={c.descrizione}>{c.descrizione}</td>
                  <td className="px-4 py-2 text-xs text-amber-700">{c.categoria_locale}</td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">{c.categoria_globale}</td>
                  <td className="px-4 py-2 hidden md:table-cell text-xs text-muted-foreground truncate max-w-[120px]">{c.nome_cliente}</td>
                  <td className="px-4 py-2">
                    <div className="flex gap-1">
                      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => risolvi(c, "promuovi")} title="Promuovi locale → globale">
                        <ArrowRightLeft className="size-3 mr-1" /> Promuovi
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 text-xs text-muted-foreground" onClick={() => risolvi(c, "ignora")}>Ignora</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── TAB ATTIVITÀ AI ─────────────────────────────────────────────────────────
type LogRow = {
  id: number;
  created_at: string;
  attore: string;
  azione: string;
  descrizione: string;
  categoria_da: string;
  categoria_a: string;
  righe_count: number;
  nota: string;
  annullato_at: string | null;
};

const AZIONE_LABEL: Record<string, string> = {
  classifica: "Classifica manuale",
  auto_review: "Auto-review",
  risolvi_conflitto: "Risolvi conflitto",
  annulla: "Annullata",
};
const AZIONE_COLOR: Record<string, string> = {
  classifica: "bg-sky-100 text-sky-700",
  auto_review: "bg-violet-100 text-violet-700",
  risolvi_conflitto: "bg-amber-100 text-amber-700",
  annulla: "bg-slate-100 text-slate-500",
};

function AttivitaAiTab() {
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
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ log_id: row.id }),
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
      <div className="flex gap-2 flex-wrap items-center">
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={soloAnnullabili}
            onChange={(e) => { setSoloAnnullabili(e.target.checked); setPage(1); }}
            className="rounded"
          />
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
                  <div className="space-y-2">
                    <Activity className="size-8 text-muted-foreground/50 mx-auto" />
                    <p>Nessuna azione registrata</p>
                  </div>
                )}
              </td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className={`hover:bg-muted/30 ${r.annullato_at ? "opacity-50" : ""}`}>
                <td className="px-3 py-2 tabular-nums whitespace-nowrap text-muted-foreground">
                  {new Date(r.created_at).toLocaleString("it-IT", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                </td>
                <td className="px-3 py-2">
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${AZIONE_COLOR[r.azione] || "bg-slate-100 text-slate-600"}`}>
                    {AZIONE_LABEL[r.azione] || r.azione}
                  </span>
                </td>
                <td className="px-3 py-2 max-w-[180px] truncate" title={r.descrizione}>{r.descrizione || "—"}</td>
                <td className="px-3 py-2 hidden md:table-cell">
                  {r.categoria_da ? (
                    <span className="text-muted-foreground">{r.categoria_da} <span className="mx-1">→</span> {r.categoria_a}</span>
                  ) : (
                    <span>{r.categoria_a}</span>
                  )}
                </td>
                <td className="px-3 py-2 tabular-nums font-medium">{r.righe_count}</td>
                <td className="px-3 py-2 hidden lg:table-cell text-muted-foreground truncate max-w-[120px]">{r.attore}</td>
                <td className="px-3 py-2">
                  {!r.annullato_at && r.azione !== "annulla" && r.categoria_da && r.righe_count > 0 ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-xs text-amber-600 hover:text-amber-700"
                      disabled={undoing === r.id}
                      onClick={() => handleAnnulla(r)}
                      title="Ripristina categoria precedente"
                    >
                      <Undo2 className="size-3 mr-1" />
                      {undoing === r.id ? "…" : "Annulla"}
                    </Button>
                  ) : r.annullato_at ? (
                    <span className="text-[10px] text-muted-foreground">Annullata</span>
                  ) : null}
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

// ─── ROOT CLIENT ─────────────────────────────────────────────────────────────
const TABS = ["coda", "memoria", "conflitti", "attivita"] as const;
const TAB_LABELS: Record<string, string> = {
  coda: "Coda review",
  memoria: "Memoria globale",
  conflitti: "Conflitti",
  attivita: "Attività AI",
};

export function QualitaAiClient() {
  const [tab, setTab] = useState<"coda" | "memoria" | "conflitti" | "attivita">("coda");
  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>
      {tab === "coda" && <CodaTab />}
      {tab === "memoria" && <MemoriaTab />}
      {tab === "conflitti" && <ConflittiTab />}
      {tab === "attivita" && <AttivitaAiTab />}
    </div>
  );
}
