"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Plus, X, RefreshCw, Download, ChevronDown, ChevronUp,
  Search, Check, Trash2, Tags, Lightbulb,
} from "lucide-react";
import { toast } from "sonner";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer,
} from "recharts";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import type {
  CustomTag, TagSuggestion, TagAnalisiResponse,
  TagProdotto, DescrizioneDistinta,
} from "@/lib/tag";

const ANNO_CORRENTE = new Date().getFullYear();
const MESI = ["Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"];

function isoRange(anno: number, mese: number | null) {
  if (mese === null) return { da: `${anno}-01-01`, a: `${anno}-12-31` };
  const last = new Date(anno, mese, 0).getDate();
  const mm = String(mese).padStart(2, "0");
  return { da: `${anno}-${mm}-01`, a: `${anno}-${mm}-${last}` };
}

function fmtEuro(v: number) {
  return `€ ${new Intl.NumberFormat("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)}`;
}
function fmtPct(v: number, signed = false) {
  return `${signed && v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}
function fmtData(s: string) {
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

const TOOLTIP_STYLE = {
  backgroundColor: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: "6px",
  fontSize: 11,
  color: "hsl(var(--foreground))",
};

/* ── Componenti KPI ── */
function KpiCard({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone: string }) {
  return (
    <div className={`rounded-lg border ${tone} bg-card px-4 pt-3 pb-2.5 flex flex-col gap-1 transition-colors`}>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium leading-tight min-h-[28px] flex items-start">{label}</p>
      <p className="text-xl font-bold tracking-tight truncate">{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

/* ── Grafico trend ── */
function TrendChart({ punti, media }: { punti: { data: string; prezzo: number; var_perc: number }[]; media: number }) {
  if (punti.length < 2) return (
    <p className="text-sm text-muted-foreground py-6 text-center">Dati insufficienti per il grafico</p>
  );
  const data = punti.map(p => ({
    data: fmtData(p.data),
    prezzo: p.prezzo,
    var_perc: p.var_perc,
  }));
  const maxAbs = Math.max(...data.map(d => Math.abs(d.var_perc)), 1);
  const domain: [number, number] = [-Math.ceil(maxAbs * 1.2), Math.ceil(maxAbs * 1.2)];
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">
        Media periodo: <span className="font-semibold text-foreground">{fmtEuro(media)}</span>
      </p>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
          <XAxis dataKey="data" tick={{ fontSize: 10, fill: "#94a3b8" }} tickLine={false} axisLine={false} />
          <YAxis domain={domain} tick={{ fontSize: 10, fill: "#94a3b8" }} tickLine={false} axisLine={false}
            tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v}%`} />
          <Tooltip
            formatter={(v) => {
              const n = typeof v === "number" ? v : 0;
              return [`${n > 0 ? "+" : ""}${n.toFixed(1)}%`, "Variazione vs media"];
            }}
            labelStyle={{ fontSize: 11, color: "#94a3b8" }}
            contentStyle={TOOLTIP_STYLE}
          />
          <ReferenceLine y={0} stroke="#f43f5e" strokeDasharray="4 4" strokeWidth={1.5}
            label={{ value: "media", position: "insideTopLeft", fontSize: 10, fill: "#f43f5e", dy: -6, dx: 4 }} />
          <Line type="monotone" dataKey="var_perc" stroke="#60a5fa" strokeWidth={2}
            dot={{ r: 3, fill: "#60a5fa" }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── Dialog Nuovo/Modifica Tag ── */
function TagDialog({
  open, onOpenChange, tag, onSaved,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  tag: CustomTag | null;
  onSaved: (saved: CustomTag, isNew: boolean) => void;
}) {
  const [nome, setNome] = useState("");
  const [emoji, setEmoji] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setNome(tag?.nome ?? "");
      setEmoji(tag?.emoji ?? "");
    }
  }, [open, tag]);

  async function save() {
    const n = nome.trim();
    if (!n) { toast.error("Inserisci un nome per il tag"); return; }
    setSaving(true);
    try {
      const body = { nome: n, emoji: emoji.trim() || null, colore: tag?.colore ?? null };
      const res = tag
        ? await fetch(`/api/tag/${tag.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        : await fetch("/api/tag", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok) {
        const msg = res.status === 401 ? "Sessione scaduta, ricarica la pagina" : "Errore nel salvataggio";
        throw new Error(msg);
      }
      const data = await res.json();
      const saved: CustomTag | null = data?.tag ?? null;
      toast.success(tag ? "Tag aggiornato" : "Tag creato");
      if (saved) onSaved(saved, !tag);
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore nel salvataggio");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{tag ? "Modifica tag" : "Nuovo tag"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <div className="space-y-1">
            <label className="text-sm font-medium">Nome</label>
            <input
              className="w-full rounded-md border border-border px-3 py-2 text-sm bg-background"
              placeholder="Es. Salmone, Pollo, Farina…"
              value={nome}
              maxLength={100}
              onChange={e => setNome(e.target.value)}
              onKeyDown={e => e.key === "Enter" && save()}
              autoFocus
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Emoji <span className="text-muted-foreground font-normal">(opzionale)</span></label>
            <div className="flex flex-wrap gap-1.5">
              {["🐟","🍗","🥩","🐄","🦐","🍕","🍝","🥗","🧀","🥚","🧈","🥛","🍞","🌾","🫒","🍷","🍺","☕","🧃","🌿","🍋","🧅","🥦","🍅","🧄","🥕","🌶️","🍄"].map(e => (
                <button
                  key={e}
                  type="button"
                  onClick={() => setEmoji(prev => prev === e ? "" : e)}
                  className={`w-9 h-9 text-xl rounded-md border transition-colors flex items-center justify-center ${
                    emoji === e
                      ? "border-primary bg-primary/10"
                      : "border-border hover:bg-muted"
                  }`}
                >
                  {e}
                </button>
              ))}
            </div>
            {emoji && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <span>Selezionata: <span className="text-lg">{emoji}</span></span>
                <button type="button" onClick={() => setEmoji("")} className="text-xs hover:text-foreground underline">Rimuovi</button>
              </div>
            )}
          </div>
          <div className="flex gap-2 justify-end pt-1">
            <button onClick={() => onOpenChange(false)}
              className="px-3 py-1.5 text-sm rounded-md border border-border hover:bg-muted transition-colors">
              Annulla
            </button>
            <button onClick={save} disabled={saving || !nome.trim()}
              className="px-3 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors">
              {saving ? "Salvataggio…" : "Salva"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ── Dialog Aggiungi Prodotti ── */
function AggiungiProdottiDialog({
  open, onOpenChange, tagId, prodottiEsistenti, onAdded,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  tagId: number;
  prodottiEsistenti: string[];
  onAdded: () => void;
}) {
  const [search, setSearch] = useState("");
  const [descrizioni, setDescrizioni] = useState<DescrizioneDistinta[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSearch("");
    setSelected(new Set());
    setLoading(true);
    fetch("/api/tag/descrizioni")
      .then(r => r.json())
      .then(d => setDescrizioni(d.descrizioni ?? []))
      .catch(() => toast.error("Errore nel caricamento prodotti"))
      .finally(() => setLoading(false));
  }, [open]);

  const filtered = descrizioni
    .filter(d => !prodottiEsistenti.includes(d.descrizione_key))
    .filter(d => !search || d.descrizione.toLowerCase().includes(search.toLowerCase()))
    .slice(0, 80);

  async function salva() {
    if (selected.size === 0) return;
    setSaving(true);
    try {
      const items = [...selected].map(k => {
        const d = descrizioni.find(x => x.descrizione_key === k);
        return { descrizione: d?.descrizione ?? k, descrizione_key: k, fattore_kg: null };
      });
      const res = await fetch(`/api/tag/${tagId}/prodotti`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ descrizioni: items }),
      });
      if (!res.ok) throw new Error();
      toast.success(`${selected.size} prodott${selected.size === 1 ? "o aggiunto" : "i aggiunti"}`);
      onAdded();
      onOpenChange(false);
    } catch {
      toast.error("Errore nel salvataggio");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-5 pt-5 pb-3 border-b border-border shrink-0">
          <DialogTitle>Aggiungi prodotti al tag</DialogTitle>
        </DialogHeader>
        <div className="px-5 py-3 border-b border-border shrink-0">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              className="w-full rounded-md border border-border pl-9 pr-3 py-2 text-sm bg-background"
              placeholder="Cerca prodotto…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              autoFocus
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-2">
          {loading ? (
            <div className="space-y-2 py-2">
              {[1,2,3,4].map(i => <div key={i} className="h-10 rounded-md bg-muted animate-pulse" />)}
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">Nessun prodotto trovato</p>
          ) : (
            <div className="space-y-0.5">
              {filtered.map(d => {
                const sel = selected.has(d.descrizione_key);
                return (
                  <button key={d.descrizione_key}
                    onClick={() => {
                      const s = new Set(selected);
                      if (sel) s.delete(d.descrizione_key);
                      else s.add(d.descrizione_key);
                      setSelected(s);
                    }}
                    className={`w-full text-left flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${sel ? "bg-primary/10 text-foreground" : "hover:bg-muted"}`}
                  >
                    <span className={`size-4 rounded border flex items-center justify-center shrink-0 transition-colors ${sel ? "bg-primary border-primary" : "border-border"}`}>
                      {sel && <Check className="size-3 text-primary-foreground" />}
                    </span>
                    <span className="flex-1 truncate font-medium">{d.descrizione}</span>
                    <span className="text-xs text-muted-foreground shrink-0">{d.occorrenze} occ.</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <div className="px-5 py-3 border-t border-border shrink-0 flex items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {selected.size > 0 ? `${selected.size} selezionat${selected.size === 1 ? "o" : "i"}` : "Seleziona prodotti"}
          </p>
          <div className="flex gap-2">
            <button onClick={() => onOpenChange(false)}
              className="px-3 py-1.5 text-sm rounded-md border border-border hover:bg-muted transition-colors">
              Annulla
            </button>
            <button onClick={salva} disabled={saving || selected.size === 0}
              className="px-3 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors">
              {saving ? "Salvataggio…" : "Aggiungi"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ── Card suggerimento espandibile ── */
function SuggestionCard({
  s, onAccepted, onDismissed,
}: {
  s: TagSuggestion;
  onAccepted: () => void;
  onDismissed: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [tagName, setTagName] = useState(
    s.suggestion_type === "new_tag" ? (s.suggested_tag_name ?? "") : (s.tag_name ?? "")
  );
  const [selected, setSelected] = useState<Set<string>>(
    new Set(s.items.map(i => i.descrizione_key))
  );
  const [acting, setActing] = useState(false);

  function toggleItem(key: string) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleAll() {
    setSelected(prev =>
      prev.size === s.items.length ? new Set() : new Set(s.items.map(i => i.descrizione_key))
    );
  }

  async function accept() {
    if (selected.size === 0) { toast.error("Seleziona almeno un prodotto"); return; }
    setActing(true);
    try {
      const body = s.suggestion_type === "new_tag"
        ? { suggestion_type: "new_tag", tag_name: tagName.trim() || s.suggested_tag_name }
        : { suggestion_type: "extend_tag", tag_id: s.target_tag_id };
      const res = await fetch(`/api/tag/suggestions/${s.id}/accept`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error();
      toast.success(
        s.suggestion_type === "new_tag"
          ? `Tag "${tagName || s.suggested_tag_name}" creato`
          : `Prodotti aggiunti al tag "${s.tag_name}"`
      );
      onAccepted();
    } catch {
      toast.error("Errore nell'accettazione");
    } finally {
      setActing(false);
    }
  }

  async function dismiss() {
    setActing(true);
    try {
      await fetch(`/api/tag/suggestions/${s.id}/dismiss`, { method: "POST" });
      toast.success("Suggerimento ignorato");
      onDismissed();
    } catch {
      toast.error("Errore");
    } finally {
      setActing(false);
    }
  }

  const isNewTag = s.suggestion_type === "new_tag";

  return (
    <div className="rounded-xl border border-amber-500/30 bg-card overflow-hidden">
      {/* Header cliccabile */}
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full text-left px-4 py-3 hover:bg-amber-500/5 transition-colors"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold">
              {isNewTag ? `Crea tag "${s.suggested_tag_name}"` : `Aggiungi al tag "${s.tag_name}"`}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {s.matched_products_count} prodott{s.matched_products_count === 1 ? "o" : "i"} ·{" "}
              {s.matched_rows_count} acquist{s.matched_rows_count === 1 ? "o" : "i"} negli ultimi 30 giorni
            </p>
            {!expanded && (
              <p className="text-xs text-muted-foreground mt-1 truncate">
                {s.items.slice(0, 3).map(i => i.descrizione).join(" · ")}
                {s.items.length > 3 && ` + altri ${s.items.length - 3}`}
              </p>
            )}
          </div>
          {expanded ? <ChevronUp className="size-4 text-muted-foreground shrink-0 mt-0.5" /> : <ChevronDown className="size-4 text-muted-foreground shrink-0 mt-0.5" />}
        </div>
      </button>

      {/* Dettaglio espanso */}
      {expanded && (
        <div className="border-t border-amber-500/20 px-4 pb-4 pt-3 space-y-3">
          {/* Nome tag modificabile */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {isNewTag ? "Nome del nuovo tag" : "Tag di destinazione"}
            </label>
            <input
              className="w-full rounded-md border border-border px-3 py-1.5 text-sm bg-background font-medium"
              value={tagName}
              onChange={e => setTagName(e.target.value)}
              disabled={!isNewTag}
              placeholder="Nome tag…"
            />
          </div>

          {/* Lista prodotti con checkbox */}
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Prodotti ({selected.size}/{s.items.length} selezionati)
              </label>
              <button
                type="button"
                onClick={toggleAll}
                className="text-xs text-primary hover:underline"
              >
                {selected.size === s.items.length ? "Deseleziona tutti" : "Seleziona tutti"}
              </button>
            </div>
            <div className="rounded-lg border border-border divide-y divide-border max-h-52 overflow-y-auto">
              {s.items.map(item => {
                const sel = selected.has(item.descrizione_key);
                return (
                  <button
                    key={item.descrizione_key}
                    type="button"
                    onClick={() => toggleItem(item.descrizione_key)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted/40 ${sel ? "" : "opacity-50"}`}
                  >
                    <span className={`size-4 rounded border flex items-center justify-center shrink-0 transition-colors ${sel ? "bg-primary border-primary" : "border-border"}`}>
                      {sel && <Check className="size-2.5 text-primary-foreground" />}
                    </span>
                    <span className="flex-1 truncate font-medium">{item.descrizione}</span>
                    <span className="text-xs text-muted-foreground shrink-0">{item.occorrenze} occ.</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Azioni */}
          <div className="flex gap-2 pt-1">
            <button
              onClick={accept}
              disabled={acting || selected.size === 0}
              className="flex-1 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {acting ? "…" : isNewTag ? `✓ Crea tag` : `✓ Aggiungi al tag`}
            </button>
            <button
              onClick={dismiss}
              disabled={acting}
              className="px-4 py-2 text-sm rounded-lg border border-border hover:bg-muted disabled:opacity-50 transition-colors"
            >
              Ignora
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Banner Suggerimenti ── */
function SuggerimentiBanner({
  suggestions, onRefresh, refreshing,
}: {
  suggestions: TagSuggestion[];
  onRefresh: () => void;
  refreshing: boolean;
}) {
  if (suggestions.length === 0) return null;

  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-500/8 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Lightbulb className="size-4 text-amber-500 shrink-0" />
          <span className="text-sm font-semibold text-amber-700 dark:text-amber-400">
            {suggestions.length} suggerimt{suggestions.length === 1 ? "o" : "i"} intelligent{suggestions.length === 1 ? "e" : "i"}
          </span>
        </div>
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="p-1.5 rounded-md hover:bg-amber-500/15 transition-colors text-amber-600 dark:text-amber-400 disabled:opacity-50"
          title="Aggiorna suggerimenti"
        >
          <RefreshCw className={`size-3.5 ${refreshing ? "animate-spin" : ""}`} />
        </button>
      </div>
      <div className="space-y-2">
        {suggestions.slice(0, 5).map(s => (
          <SuggestionCard key={s.id} s={s} onAccepted={onRefresh} onDismissed={onRefresh} />
        ))}
      </div>
    </div>
  );
}

/* ── Componente principale ── */
export function AnalisiETagClient({
  initialTags,
  initialSuggestions,
}: {
  initialTags: CustomTag[];
  initialSuggestions: TagSuggestion[];
}) {
  const [tags, setTags] = useState<CustomTag[]>(initialTags);
  const [suggestions, setSuggestions] = useState<TagSuggestion[]>(initialSuggestions);
  const [selectedTagId, setSelectedTagId] = useState<number | null>(initialTags[0]?.id ?? null);

  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [mese, setMese] = useState<number | null>(null);

  const [analisi, setAnalisi] = useState<TagAnalisiResponse | null>(null);
  const [loadingAnalisi, setLoadingAnalisi] = useState(false);

  const [prodotti, setProdotti] = useState<TagProdotto[]>([]);
  const [loadingProdotti, setLoadingProdotti] = useState(false);
  const [removingId, setRemovingId] = useState<number | null>(null);

  const [dialogTag, setDialogTag] = useState<{ open: boolean; tag: CustomTag | null }>({ open: false, tag: null });
  const [dialogAggiungi, setDialogAggiungi] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const [refreshingSuggestions, setRefreshingSuggestions] = useState(false);
  const [showTrend, setShowTrend] = useState(true);
  const [showFornitori, setShowFornitori] = useState(true);

  // ── Load analisi ──
  const loadAnalisi = useCallback(async (tagId: number, a: number, m: number | null) => {
    setLoadingAnalisi(true);
    setAnalisi(null);
    const { da, a: dataA } = isoRange(a, m);
    try {
      const res = await fetch(`/api/tag/${tagId}/analisi?data_da=${da}&data_a=${dataA}`);
      if (!res.ok) throw new Error();
      setAnalisi(await res.json());
    } catch {
      toast.error("Errore nel caricamento analisi");
    } finally {
      setLoadingAnalisi(false);
    }
  }, []);

  // ── Load prodotti ──
  const loadProdotti = useCallback(async (tagId: number) => {
    setLoadingProdotti(true);
    try {
      const res = await fetch(`/api/tag/${tagId}/prodotti`);
      if (!res.ok) throw new Error();
      const d = await res.json();
      setProdotti(d.prodotti ?? []);
    } catch {
      toast.error("Errore nel caricamento prodotti");
    } finally {
      setLoadingProdotti(false);
    }
  }, []);

  // ── Load tags e suggestions ──
  const reloadTags = useCallback(async () => {
    const [tagsRes, sugRes] = await Promise.all([
      fetch("/api/tag").then(r => r.json()).catch(() => null),
      fetch("/api/tag/suggestions").then(r => r.json()).catch(() => null),
    ]);
    if (tagsRes?.tags) setTags(tagsRes.tags);
    if (sugRes?.suggestions) setSuggestions(sugRes.suggestions);
  }, []);

  const refreshSuggestions = useCallback(async () => {
    setRefreshingSuggestions(true);
    try {
      const res = await fetch("/api/tag/suggestions?refresh=true");
      const d = await res.json();
      setSuggestions(d.suggestions ?? []);
    } catch {
      toast.error("Errore aggiornamento suggerimenti");
    } finally {
      setRefreshingSuggestions(false);
    }
  }, []);

  // Seleziona tag → carica analisi e prodotti
  function selectTag(id: number) {
    setSelectedTagId(id);
    setDeleteConfirm(null);
    loadAnalisi(id, anno, mese);
    loadProdotti(id);
  }

  // Mount: carica analisi + prodotti del primo tag selezionato
  useEffect(() => {
    if (selectedTagId) {
      loadAnalisi(selectedTagId, anno, mese);
      loadProdotti(selectedTagId);
    }
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Rimuovi prodotto ──
  async function removeProdotto(assocId: number) {
    setRemovingId(assocId);
    try {
      const res = await fetch(`/api/tag/prodotti/${assocId}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      setProdotti(p => p.filter(x => x.id !== assocId));
      toast.success("Prodotto rimosso");
    } catch {
      toast.error("Errore nella rimozione");
    } finally {
      setRemovingId(null);
    }
  }

  // ── Elimina tag ──
  async function deleteTag(tagId: number) {
    setDeletingId(tagId);
    try {
      const res = await fetch(`/api/tag/${tagId}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Tag eliminato");
      const newTags = tags.filter(t => t.id !== tagId);
      setTags(newTags);
      setDeleteConfirm(null);
      if (selectedTagId === tagId) {
        const next = newTags[0] ?? null;
        setSelectedTagId(next?.id ?? null);
        setAnalisi(null);
        setProdotti([]);
        if (next) { loadAnalisi(next.id, anno, mese); loadProdotti(next.id); }
      }
    } catch {
      toast.error("Errore nell'eliminazione");
    } finally {
      setDeletingId(null);
    }
  }

  // ── Export XLS ──
  async function exportXls() {
    if (!selectedTagId || !analisi || analisi.vuoto) return;
    const tag = tags.find(t => t.id === selectedTagId);
    const { da, a } = isoRange(anno, mese);
    try {
      const { utils, writeFile } = await import("xlsx");
      const wb = utils.book_new();

      // Sheet KPI
      if (analisi.kpi) {
        const kpiData = [
          ["Metrica", "Valore"],
          ["Spesa Totale", analisi.kpi.spesa_totale],
          ["Quantità Normalizzata", analisi.kpi.quantita_norm_totale],
          ["Prezzo Medio Ponderato", analisi.kpi.prezzo_medio_ponderato ?? "—"],
          ["Fornitori Distinti", analisi.kpi.num_fornitori],
          ["Fatture Coinvolte", analisi.kpi.num_fatture],
        ];
        utils.book_append_sheet(wb, utils.aoa_to_sheet(kpiData), "KPI");
      }

      // Sheet Trend
      if (analisi.trend.punti.length > 0) {
        const header = ["Data", "Prezzo", "Var% vs media"];
        const rows = analisi.trend.punti.map(p => [p.data, p.prezzo, p.var_perc]);
        utils.book_append_sheet(wb, utils.aoa_to_sheet([header, ...rows]), "Trend prezzi");
      }

      // Sheet Fornitori
      if (analisi.fornitori.fornitori.length > 0) {
        const header = ["Fornitore", "Spesa (€)", "Acquisti", "Q.tà", "Prezzo medio", "Δ% vs media", "% sul tag"];
        const rows = analisi.fornitori.fornitori.map(f => [
          f.fornitore, f.spesa_totale, f.num_acquisti, f.quantita_totale,
          f.prezzo_medio ?? "—", f.delta_pct, f.incidenza_spesa,
        ]);
        utils.book_append_sheet(wb, utils.aoa_to_sheet([header, ...rows]), "Fornitori");
      }

      const nomeTag = tag?.nome ?? "tag";
      writeFile(wb, `analisi_${nomeTag}_${da}_${a}.xlsx`);
    } catch {
      toast.error("Errore nell'export");
    }
  }

  const selectedTag = tags.find(t => t.id === selectedTagId) ?? null;
  const { kpi, trend, fornitori } = analisi ?? { kpi: null, trend: { punti: [], prezzo_medio_periodo: 0 }, fornitori: { fornitori: [], aggregati: null } };

  /* ══════════════════════════════════════════════════════════ RENDER */
  return (
    <div className="space-y-4">
      {/* ── Suggerimenti ── */}
      <SuggerimentiBanner
        suggestions={suggestions}
        onRefresh={async () => { await refreshSuggestions(); await reloadTags(); }}
        refreshing={refreshingSuggestions}
      />

      {/* ── Chip tag + azioni ── */}
      <div className="flex flex-wrap items-center gap-2">
        {tags.map(tag => (
          <button
            key={tag.id}
            onClick={() => selectTag(tag.id)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
              tag.id === selectedTagId
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/40"
            }`}
          >
            {tag.emoji && <span>{tag.emoji}</span>}
            {tag.nome}
          </button>
        ))}
        <button
          onClick={() => setDialogTag({ open: true, tag: null })}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-sm border border-dashed border-border text-muted-foreground hover:text-foreground hover:border-foreground/40 transition-colors"
        >
          <Plus className="size-3.5" />
          Nuovo tag
        </button>

        {/* Bottone suggerimenti — widget colorato */}
        <button
          onClick={async () => { await refreshSuggestions(); await reloadTags(); }}
          disabled={refreshingSuggestions}
          className={`inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium border transition-all disabled:opacity-60 ml-auto ${
            suggestions.length > 0
              ? "bg-amber-500/15 border-amber-500/50 text-amber-700 dark:text-amber-400 hover:bg-amber-500/25"
              : "bg-muted border-border text-muted-foreground hover:text-foreground hover:bg-muted/80"
          }`}
          title="Analizza prodotti non taggati e trova suggerimenti"
        >
          {refreshingSuggestions
            ? <RefreshCw className="size-3.5 animate-spin" />
            : <Lightbulb className="size-3.5" />
          }
          {refreshingSuggestions
            ? "Analisi in corso…"
            : suggestions.length > 0
              ? <><span className="inline-flex items-center justify-center size-5 rounded-full bg-amber-500 text-white text-[10px] font-bold">{suggestions.length}</span> Suggerimenti</>
              : "Suggerimenti"
          }
        </button>
      </div>

      {/* ── Empty state ── */}
      {tags.length === 0 && (
        <div className="rounded-lg border border-dashed border-border py-16 text-center">
          <Tags className="size-10 text-muted-foreground mx-auto mb-3" />
          <p className="text-sm font-medium">Nessun tag ancora</p>
          <p className="text-xs text-muted-foreground mt-1 mb-4">Crea il primo tag per raggruppare i tuoi prodotti e analizzare la spesa</p>
          <button
            onClick={() => setDialogTag({ open: true, tag: null })}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Plus className="size-4" />
            Crea primo tag
          </button>
        </div>
      )}

      {/* ── Dettaglio tag selezionato ── */}
      {selectedTag && (
        <div className="space-y-5">
          {/* Header tag + azioni */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              {selectedTag.emoji && <span className="text-2xl">{selectedTag.emoji}</span>}
              <h2 className="text-lg font-semibold">{selectedTag.nome}</h2>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setDialogTag({ open: true, tag: selectedTag })}
                className="px-3 py-1.5 text-xs rounded-md border border-border hover:bg-muted transition-colors"
              >
                Modifica
              </button>
              {deleteConfirm === selectedTag.id ? (
                <div className="flex gap-1">
                  <button
                    onClick={() => deleteTag(selectedTag.id)}
                    disabled={deletingId === selectedTag.id}
                    className="px-3 py-1.5 text-xs font-medium rounded-md bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50 transition-colors"
                  >
                    {deletingId === selectedTag.id ? "…" : "Conferma eliminazione"}
                  </button>
                  <button
                    onClick={() => setDeleteConfirm(null)}
                    className="px-2 py-1.5 text-xs rounded-md border border-border hover:bg-muted transition-colors"
                  >
                    Annulla
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setDeleteConfirm(selectedTag.id)}
                  className="p-1.5 text-xs rounded-md border border-border text-muted-foreground hover:text-rose-600 hover:border-rose-300 transition-colors"
                  title="Elimina tag"
                >
                  <Trash2 className="size-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Filtro periodo */}
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={anno}
              onChange={e => {
                const y = Number(e.target.value);
                setAnno(y);
                if (selectedTagId) loadAnalisi(selectedTagId, y, mese);
              }}
              className="rounded-md border border-border px-2 py-1.5 text-sm bg-background"
            >
              {Array.from({ length: 4 }, (_, i) => ANNO_CORRENTE - i).map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
            <button
              onClick={() => { setMese(null); if (selectedTagId) loadAnalisi(selectedTagId, anno, null); }}
              className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${mese === null ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:text-foreground"}`}
            >
              Tutto
            </button>
            {MESI.map((label, i) => {
              const m = i + 1;
              return (
                <button key={m}
                  onClick={() => { setMese(m); if (selectedTagId) loadAnalisi(selectedTagId, anno, m); }}
                  className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${mese === m ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:text-foreground"}`}
                >
                  {label}
                </button>
              );
            })}
          </div>

          {/* KPI bar */}
          {loadingAnalisi && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[1,2,3,4,5].map(i => <div key={i} className="h-20 rounded-lg border bg-card animate-pulse" />)}
            </div>
          )}
          {!loadingAnalisi && analisi?.vuoto === false && kpi && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <KpiCard label="Totale spesa" value={fmtEuro(kpi.spesa_totale)} tone="border-sky-500/40 hover:border-sky-500/70" />
              <KpiCard label={kpi.quantita_label} value={kpi.quantita_norm_totale.toLocaleString("it-IT", { maximumFractionDigits: 1 })} tone="border-violet-500/40 hover:border-violet-500/70" />
              <KpiCard label={kpi.prezzo_label} value={kpi.prezzo_medio_ponderato != null ? fmtEuro(kpi.prezzo_medio_ponderato) : "—"} tone="border-emerald-500/40 hover:border-emerald-500/70" />
              <KpiCard label="Fornitori" value={String(kpi.num_fornitori)} tone="border-orange-500/40 hover:border-orange-500/70" />
              <KpiCard label="Fatture" value={String(kpi.num_fatture)} tone="border-pink-500/40 hover:border-pink-500/70" />
            </div>
          )}
          {!loadingAnalisi && analisi?.vuoto && (
            <div className="rounded-lg border border-border bg-card py-8 text-center">
              <p className="text-sm text-muted-foreground">Nessun dato nel periodo selezionato per questo tag.</p>
            </div>
          )}

          {/* Trend + Fornitori */}
          {!loadingAnalisi && analisi?.vuoto === false && (
            <div className="space-y-3">
              {/* Trend */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                {/* Header cliccabile: <div role=button> e non <button> perché
                    contiene il bottone "Esporta XLS" (un button non può annidare
                    un altro button → hydration error). */}
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => setShowTrend(v => !v)}
                  onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setShowTrend(v => !v); } }}
                  className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium hover:bg-muted/40 transition-colors cursor-pointer select-none"
                >
                  <span>Trend prezzi nel periodo</span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={e => { e.stopPropagation(); exportXls(); }}
                      className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                      title="Esporta XLS"
                    >
                      <Download className="size-3.5" />
                    </button>
                    {showTrend ? <ChevronUp className="size-4 text-muted-foreground" /> : <ChevronDown className="size-4 text-muted-foreground" />}
                  </div>
                </div>
                {showTrend && (
                  <div className="px-4 pb-4 border-t border-border">
                    <TrendChart punti={trend.punti} media={trend.prezzo_medio_periodo} />
                  </div>
                )}
              </div>

              {/* Fornitori */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <button
                  onClick={() => setShowFornitori(v => !v)}
                  className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium hover:bg-muted/40 transition-colors"
                >
                  <span>Analisi fornitori</span>
                  {showFornitori ? <ChevronUp className="size-4 text-muted-foreground" /> : <ChevronDown className="size-4 text-muted-foreground" />}
                </button>
                {showFornitori && fornitori.fornitori.length > 0 && (
                  <div className="border-t border-border overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border bg-muted/30">
                          <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">Fornitore</th>
                          <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">Spesa</th>
                          <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">Acquisti</th>
                          <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">Prezzo medio</th>
                          <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">Vs media</th>
                          <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">% sul tag</th>
                        </tr>
                      </thead>
                      <tbody>
                        {fornitori.fornitori.map((f, i) => (
                          <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors">
                            <td className="px-4 py-2.5 font-medium">{f.fornitore}</td>
                            <td className="px-4 py-2.5 text-right tabular-nums">{fmtEuro(f.spesa_totale)}</td>
                            <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">{f.num_acquisti}</td>
                            <td className="px-4 py-2.5 text-right tabular-nums">{f.prezzo_medio != null ? fmtEuro(f.prezzo_medio) : "—"}</td>
                            <td className={`px-4 py-2.5 text-right tabular-nums font-semibold ${f.delta_pct > 5 ? "text-rose-600" : f.delta_pct < -5 ? "text-emerald-600" : "text-muted-foreground"}`}>
                              {fmtPct(f.delta_pct, true)}
                            </td>
                            <td className="px-4 py-2.5 text-right">
                              <div className="flex items-center gap-2 justify-end">
                                <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden">
                                  <div className="h-full bg-primary rounded-full" style={{ width: `${Math.min(100, f.incidenza_spesa)}%` }} />
                                </div>
                                <span className="tabular-nums text-xs w-10">{f.incidenza_spesa.toFixed(1)}%</span>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {showFornitori && fornitori.fornitori.length === 0 && (
                  <p className="px-4 pb-4 text-sm text-muted-foreground border-t border-border pt-4">Nessun dato fornitori.</p>
                )}
              </div>
            </div>
          )}

          {/* ── Prodotti associati ── */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">
                Prodotti associati{prodotti.length > 0 && <span className="ml-2 text-muted-foreground font-normal">({prodotti.length})</span>}
              </h3>
              <button
                onClick={() => setDialogAggiungi(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-border hover:bg-muted transition-colors"
              >
                <Plus className="size-3.5" />
                Aggiungi prodotti
              </button>
            </div>

            {loadingProdotti && (
              <div className="space-y-1">
                {[1,2,3].map(i => <div key={i} className="h-10 rounded-md bg-muted animate-pulse" />)}
              </div>
            )}

            {!loadingProdotti && prodotti.length === 0 && (
              <div className="rounded-lg border border-dashed border-border py-8 text-center">
                <p className="text-sm text-muted-foreground">Nessun prodotto associato.</p>
                <button
                  onClick={() => setDialogAggiungi(true)}
                  className="mt-2 text-xs text-primary hover:underline"
                >
                  Aggiungi il primo prodotto
                </button>
              </div>
            )}

            {!loadingProdotti && prodotti.length > 0 && (
              <div className="rounded-lg border border-border divide-y divide-border">
                {prodotti.map(p => (
                  <div key={p.id} className="flex items-center justify-between px-4 py-2.5 hover:bg-muted/20 transition-colors">
                    <span className="text-sm font-medium">{p.descrizione}</span>
                    <button
                      onClick={() => removeProdotto(p.id)}
                      disabled={removingId === p.id}
                      className="p-1 rounded text-muted-foreground hover:text-rose-600 disabled:opacity-50 transition-colors"
                      title="Rimuovi"
                    >
                      {removingId === p.id ? <RefreshCw className="size-3.5 animate-spin" /> : <X className="size-3.5" />}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Dialogs ── */}
      <TagDialog
        open={dialogTag.open}
        onOpenChange={v => setDialogTag(d => ({ ...d, open: v }))}
        tag={dialogTag.tag}
        onSaved={(saved, isNew) => {
          if (isNew) {
            setTags(prev => [...prev, saved].sort((a, b) => a.nome.localeCompare(b.nome)));
            selectTag(saved.id);
          } else {
            setTags(prev => prev.map(t => (t.id === saved.id ? saved : t)));
          }
        }}
      />

      {selectedTagId && (
        <AggiungiProdottiDialog
          open={dialogAggiungi}
          onOpenChange={setDialogAggiungi}
          tagId={selectedTagId}
          prodottiEsistenti={prodotti.map(p => p.descrizione_key)}
          onAdded={() => { if (selectedTagId) { loadProdotti(selectedTagId); loadAnalisi(selectedTagId, anno, mese); } }}
        />
      )}
    </div>
  );
}
