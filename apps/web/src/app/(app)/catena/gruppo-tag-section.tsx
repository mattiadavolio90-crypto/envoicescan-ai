"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2, Plus, Trash2, Tag as TagIcon, BarChart3, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type {
  GruppoTag,
  GruppoTagDescrizione,
  GruppoTagProdotto,
  GruppoTagAnalisi,
} from "@/lib/gruppo";

function euro(n: number): string {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n);
}

// Tag di catena = FINESTRA della plancia /catena (non una pagina separata).
// Raggruppa lo stesso prodotto su tutti i PV e confronta la spesa per sede.
export function TagCatenaDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [tags, setTags] = useState<GruppoTag[]>([]);
  const [loading, setLoading] = useState(true);
  const [nuovo, setNuovo] = useState("");
  const [creating, setCreating] = useState(false);
  const [prodottiTag, setProdottiTag] = useState<GruppoTag | null>(null);
  const [analisiTag, setAnalisiTag] = useState<GruppoTag | null>(null);

  const loadTags = useCallback(async () => {
    try {
      const res = await fetch("/api/gruppo/tag", { cache: "no-store" });
      if (!res.ok) throw new Error();
      const j = await res.json();
      setTags(j.tags ?? []);
    } catch {
      toast.error("Errore nel caricamento dei tag di catena");
    } finally {
      setLoading(false);
    }
  }, []);

  // Carica solo all'apertura della finestra (lazy → non pesa sulla Sintesi).
  useEffect(() => {
    if (open) loadTags();
  }, [open, loadTags]);

  async function creaTag() {
    const nome = nuovo.trim();
    if (!nome) return;
    setCreating(true);
    try {
      const res = await fetch("/api/gruppo/tag", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome }),
      });
      if (!res.ok) throw new Error();
      setNuovo("");
      await loadTags();
      toast.success("Tag di catena creato");
    } catch {
      toast.error("Impossibile creare il tag");
    } finally {
      setCreating(false);
    }
  }

  async function eliminaTag(id: number) {
    try {
      const res = await fetch(`/api/gruppo/tag/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      setTags((prev) => prev.filter((t) => t.id !== id));
      toast.success("Tag eliminato");
    } catch {
      toast.error("Impossibile eliminare il tag");
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] w-[min(96vw,46rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
          <DialogHeader className="border-b px-5 py-4">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Building2 className="size-5 text-primary" />
              Tag di catena
            </DialogTitle>
          </DialogHeader>
          <div className="max-h-[calc(90vh-5rem)] overflow-auto p-5">
            <p className="text-sm text-muted-foreground">
              Raggruppa gli stessi prodotti su tutti i punti vendita e confronta la spesa
              per sede. Sono separati dai tag del singolo locale.
            </p>

            {/* Crea nuovo tag */}
            <div className="mt-4 flex gap-2">
              <Input
                value={nuovo}
                onChange={(e) => setNuovo(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && creaTag()}
                placeholder="Nuovo tag di catena (es. Salmone, Imballaggi…)"
                disabled={creating}
              />
              <Button onClick={creaTag} disabled={creating || !nuovo.trim()}>
                <Plus className="size-4" />
                Crea
              </Button>
            </div>

            {/* Lista tag */}
            <div className="mt-4 space-y-2">
              {loading ? (
                <p className="text-sm text-muted-foreground">Caricamento…</p>
              ) : tags.length === 0 ? (
                <p className="rounded-xl border border-dashed py-6 text-center text-sm text-muted-foreground">
                  Nessun tag di catena. Creane uno per confrontare un prodotto fra i punti vendita.
                </p>
              ) : (
                tags.map((t) => (
                  <div
                    key={t.id}
                    className="flex items-center gap-3 rounded-xl border bg-background/40 px-4 py-3"
                  >
                    <TagIcon className="size-4 shrink-0 text-muted-foreground" />
                    <span className="flex-1 truncate text-sm font-medium">{t.nome}</span>
                    <span className="text-xs text-muted-foreground">
                      {t.n_prodotti ?? 0} {t.n_prodotti === 1 ? "prodotto" : "prodotti"}
                    </span>
                    <Button variant="ghost" size="sm" onClick={() => setProdottiTag(t)}>
                      <Search className="size-4" />
                      Prodotti
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setAnalisiTag(t)}>
                      <BarChart3 className="size-4" />
                      Analisi
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => eliminaTag(t.id)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {prodottiTag && (
        <ProdottiDialog
          tag={prodottiTag}
          onClose={() => setProdottiTag(null)}
          onChanged={loadTags}
        />
      )}
      {analisiTag && <AnalisiDialog tag={analisiTag} onClose={() => setAnalisiTag(null)} />}
    </>
  );
}

// ─── Dialog: gestione prodotti del tag (aggiungi da descrizioni distinte) ──

function ProdottiDialog({
  tag,
  onClose,
  onChanged,
}: {
  tag: GruppoTag;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [assoc, setAssoc] = useState<GruppoTagProdotto[]>([]);
  const [disponibili, setDisponibili] = useState<GruppoTagDescrizione[]>([]);
  const [risultati, setRisultati] = useState<GruppoTagDescrizione[] | null>(null);
  const [cercando, setCercando] = useState(false);
  const [filtro, setFiltro] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pRes, dRes] = await Promise.all([
        fetch(`/api/gruppo/tag/${tag.id}/prodotti`, { cache: "no-store" }),
        fetch(`/api/gruppo/tag/descrizioni`, { cache: "no-store" }),
      ]);
      const p = pRes.ok ? await pRes.json() : { prodotti: [] };
      const d = dRes.ok ? await dRes.json() : { descrizioni: [] };
      setAssoc(p.prodotti ?? []);
      setDisponibili(d.descrizioni ?? []);
    } catch {
      toast.error("Errore nel caricamento prodotti");
    } finally {
      setLoading(false);
    }
  }, [tag.id]);

  useEffect(() => {
    load();
  }, [load]);

  const giaAssociate = useMemo(
    () => new Set(assoc.map((a) => a.descrizione_key)),
    [assoc],
  );

  // Ricerca SERVER-SIDE (debounce): con ≥2 caratteri interroga il DB su tutte le
  // sedi, così si trovano anche i prodotti oltre le prime 500 per spesa. Sotto i
  // 2 caratteri si mostra/filtra la lista iniziale (top per spesa).
  useEffect(() => {
    const f = filtro.trim();
    if (f.length < 2) {
      setRisultati(null);
      setCercando(false);
      return;
    }
    let alive = true;
    setCercando(true);
    const t = setTimeout(() => {
      fetch(`/api/gruppo/tag/descrizioni?q=${encodeURIComponent(f)}`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((j) => { if (alive) setRisultati(j.descrizioni ?? []); })
        .catch(() => { if (alive) setRisultati([]); })
        .finally(() => { if (alive) setCercando(false); });
    }, 250);
    return () => { alive = false; clearTimeout(t); };
  }, [filtro]);

  const candidati = useMemo(() => {
    const f = filtro.trim();
    if (f.length >= 2) {
      return (risultati ?? [])
        .filter((d) => !giaAssociate.has(d.descrizione_key))
        .slice(0, 60);
    }
    const fu = f.toUpperCase();
    return disponibili
      .filter((d) => !giaAssociate.has(d.descrizione_key))
      .filter((d) => (fu ? d.descrizione.toUpperCase().includes(fu) : true))
      .slice(0, 60);
  }, [disponibili, risultati, giaAssociate, filtro]);

  async function aggiungi(d: GruppoTagDescrizione) {
    try {
      const res = await fetch(`/api/gruppo/tag/${tag.id}/prodotti`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ descrizioni: [{ descrizione: d.descrizione }] }),
      });
      if (!res.ok) throw new Error();
      await load();
      onChanged();
    } catch {
      toast.error("Impossibile aggiungere il prodotto");
    }
  }

  async function rimuovi(assocId: number) {
    try {
      const res = await fetch(`/api/gruppo/tag/prodotti/${assocId}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      setAssoc((prev) => prev.filter((a) => a.id !== assocId));
      onChanged();
    } catch {
      toast.error("Impossibile rimuovere il prodotto");
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] w-[min(96vw,52rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle>Prodotti di «{tag.nome}»</DialogTitle>
        </DialogHeader>
        <div className="grid max-h-[calc(90vh-5rem)] grid-cols-1 gap-4 overflow-auto p-5 sm:grid-cols-2">
          {/* Associati */}
          <div>
            <h3 className="mb-2 text-sm font-semibold">Nel tag ({assoc.length})</h3>
            {assoc.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nessun prodotto ancora.</p>
            ) : (
              <ul className="space-y-1">
                {assoc.map((a) => (
                  <li
                    key={a.id}
                    className="flex items-center gap-2 rounded-lg border bg-background/40 px-3 py-2 text-sm"
                  >
                    <span className="flex-1 truncate">{a.descrizione}</span>
                    <button
                      type="button"
                      onClick={() => rimuovi(a.id)}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {/* Disponibili */}
          <div>
            <h3 className="mb-2 text-sm font-semibold">Aggiungi prodotti</h3>
            <Input
              value={filtro}
              onChange={(e) => setFiltro(e.target.value)}
              placeholder="Cerca una descrizione…"
              className="mb-2"
            />
            {loading ? (
              <p className="text-sm text-muted-foreground">Caricamento…</p>
            ) : cercando && candidati.length === 0 ? (
              <p className="text-sm text-muted-foreground">Cerco fra tutti i punti vendita…</p>
            ) : candidati.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {filtro.trim().length >= 2 ? "Nessun prodotto trovato." : "Nessun prodotto da aggiungere."}
              </p>
            ) : (
              <ul className="space-y-1">
                {candidati.map((d) => (
                  <li key={d.descrizione_key}>
                    <button
                      type="button"
                      onClick={() => aggiungi(d)}
                      className="flex w-full items-center gap-2 rounded-lg border bg-background/40 px-3 py-2 text-left text-sm transition-colors hover:bg-accent"
                    >
                      <Plus className="size-4 shrink-0 text-primary" />
                      <span className="flex-1 truncate">{d.descrizione}</span>
                      <span className="text-xs text-muted-foreground">{euro(d.spesa)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Dialog: analisi macro per PV del tag ──────────────────────────────────

function AnalisiDialog({ tag, onClose }: { tag: GruppoTag; onClose: () => void }) {
  const [data, setData] = useState<GruppoTagAnalisi | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    fetch(`/api/gruppo/tag/${tag.id}/analisi`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (alive) setData(j);
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [tag.id]);

  const max = data ? Math.max(0, ...data.per_pv.map((p) => p.spesa)) : 0;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] w-[min(96vw,48rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
            <span>«{tag.nome}» per punto vendita</span>
            <span className="text-xs font-normal text-muted-foreground">{data?.periodo_label}</span>
          </DialogTitle>
        </DialogHeader>
        <div className="max-h-[calc(90vh-5rem)] overflow-auto p-5">
          {loading && !data ? (
            <p className="py-12 text-center text-sm text-muted-foreground">Caricamento…</p>
          ) : !data || data.per_pv.every((p) => p.spesa === 0) ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              Nessuna spesa nel periodo per questo tag.
            </p>
          ) : (
            <>
              <div className="mb-4 text-sm text-muted-foreground">
                Spesa totale gruppo:{" "}
                <span className="font-semibold text-foreground">{euro(data.spesa_totale)}</span>
              </div>
              <ul className="space-y-2">
                {data.per_pv.map((p) => (
                  <li key={p.ristorante_id} className="rounded-xl border bg-background/40 p-3">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm font-medium">{p.nome}</span>
                      <span className="text-sm font-semibold tabular-nums">{euro(p.spesa)}</span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: max > 0 ? `${(p.spesa / max) * 100}%` : "0%" }}
                      />
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {p.n_righe} righe · {p.n_fornitori}{" "}
                      {p.n_fornitori === 1 ? "fornitore" : "fornitori"}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
