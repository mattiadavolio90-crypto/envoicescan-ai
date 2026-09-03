"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Building2, Plus, Trash2, Tag as TagIcon, BarChart3, Search, Check, Download, Truck } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { formatEuro as euro } from "@/lib/format";
import { MESI_LUNGHI as MESI_LABEL } from "@/lib/mesi";
import { calcolaCandidati, MIN_LETTERE_RICERCA } from "@/lib/tag-candidati";
import {
  altezzaBarraTrend,
  analisiVuota,
  classePrezzo,
  estremiPrezzo,
  larghezzaBarra,
  massimoSpesa,
  nomeFileExport,
  righeExportFornitori,
  righeExportPv,
  soloUnPvConSpesa,
  tuttiSelezionati as calcolaTuttiSelezionati,
} from "@/lib/catena-tag";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
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

function euro2(n: number | null): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 2 }).format(n);
}
function num(n: number): string {
  return n.toLocaleString("it-IT", { maximumFractionDigits: 1 });
}
function pct(n: number): string {
  return `${n.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`;
}

// Stessi preset emoji del tag di sede (parità UX).
const EMOJI = ["🐟","🍗","🥩","🐄","🦐","🍕","🍝","🥗","🧀","🥚","🧈","🥛","🍞","🌾","🫒","🍷","🍺","☕","🧃","🌿","🍋","🧅","🥦","🍅","🧄","🥕","🌶️","🍄"];

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
  const [nuovaEmoji, setNuovaEmoji] = useState("");
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
        body: JSON.stringify({ nome, emoji: nuovaEmoji || null }),
      });
      if (!res.ok) throw new Error();
      const j = await res.json().catch(() => null);
      setNuovo("");
      setNuovaEmoji("");
      await loadTags();
      toast.success("Tag di catena creato");
      // Flusso fluido: appena creato, apre subito "Prodotti" per riempirlo.
      if (j?.tag) setProdottiTag(j.tag as GruppoTag);
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
        <DialogContent className="flex max-h-[90vh] flex-col gap-0 w-[min(96vw,46rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
          <DialogHeader className="shrink-0 border-b px-5 py-4">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Building2 className="size-5 text-primary" />
              Tag di catena
            </DialogTitle>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-auto p-5">
            <p className="text-sm text-muted-foreground">
              Raggruppa gli stessi prodotti su tutti i punti vendita e confronta la spesa
              per sede. Sono separati dai tag del singolo locale.
            </p>

            {/* Crea nuovo tag: nome + emoji (opzionale) → poi si aprono i prodotti */}
            <div className="mt-4 space-y-2">
              <div className="flex gap-2">
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
              <div className="flex flex-wrap items-center gap-1">
                <span className="mr-1 text-xs text-muted-foreground">Emoji:</span>
                {EMOJI.map((em) => (
                  <button
                    key={em}
                    type="button"
                    onClick={() => setNuovaEmoji((p) => (p === em ? "" : em))}
                    className={`flex size-7 items-center justify-center rounded-md border text-base transition-colors ${
                      nuovaEmoji === em ? "border-primary bg-primary/10" : "border-transparent hover:bg-muted"
                    }`}
                  >
                    {em}
                  </button>
                ))}
              </div>
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
                    {t.emoji ? (
                      <span className="shrink-0 text-base">{t.emoji}</span>
                    ) : (
                      <TagIcon className="size-4 shrink-0 text-muted-foreground" />
                    )}
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{t.nome}</span>
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
  const [ricercaError, setRicercaError] = useState(false);
  const [filtro, setFiltro] = useState("");
  const [loading, setLoading] = useState(true);
  // Selezione multipla (key → descrizione): si conferma con un solo "Aggiungi".
  const [selected, setSelected] = useState<Map<string, string>>(new Map());
  const [salvando, setSalvando] = useState(false);

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
    if (f.length < MIN_LETTERE_RICERCA) {
      setRisultati(null);
      setCercando(false);
      return;
    }
    let alive = true;
    setCercando(true);
    setRicercaError(false);
    const t = setTimeout(() => {
      fetch(`/api/gruppo/tag/descrizioni?q=${encodeURIComponent(f)}`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((j) => { if (alive) setRisultati(j.descrizioni ?? []); })
        // Lista vuota su errore direbbe "nessun prodotto trovato": è una ricerca
        // fallita, non un prodotto che non esiste.
        .catch(() => { if (alive) setRicercaError(true); })
        .finally(() => { if (alive) setCercando(false); });
    }, 250);
    return () => { alive = false; clearTimeout(t); };
  }, [filtro]);

  // Logica in lib/tag-candidati.ts: qui era un useMemo anonimo che nessun test
  // poteva raggiungere, ed e' dove F7 aveva misurato la soglia dopo i filtri.
  // `risposta` e' cio' che il server ha mandato, NON filtrato: e' il contratto
  // di calcolaCandidati, e va passata cosi'.
  const { candidati, nascosti, poolSaturo } = useMemo(() => {
    const inRicerca = filtro.trim().length >= MIN_LETTERE_RICERCA;
    const risposta = inRicerca ? (risultati ?? []) : disponibili;
    return calcolaCandidati(risposta, giaAssociate, filtro, inRicerca);
  }, [disponibili, risultati, giaAssociate, filtro]);

  function toggle(d: GruppoTagDescrizione) {
    setSelected((prev) => {
      const m = new Map(prev);
      if (m.has(d.descrizione_key)) m.delete(d.descrizione_key);
      else m.set(d.descrizione_key, d.descrizione);
      return m;
    });
  }

  const tuttiSelezionati = calcolaTuttiSelezionati(candidati, selected);

  function toggleTutti() {
    setSelected((prev) => {
      // Il "sono gia' tutti selezionati?" si ricalcola da `prev`, non si legge
      // dalla closure: `tuttiSelezionati` e' il valore del render in cui il
      // click e' partito, e dentro l'updater puo' essere gia' stantio (un
      // toggle() nello stesso batch lo invalida). Con lo stato vecchio il
      // pulsante fa l'azione opposta a quella che mostra.
      const tutti = calcolaTuttiSelezionati(candidati, prev);
      const m = new Map(prev);
      if (tutti) {
        candidati.forEach((d) => m.delete(d.descrizione_key));
      } else {
        candidati.forEach((d) => m.set(d.descrizione_key, d.descrizione));
      }
      return m;
    });
  }

  async function salvaSelezionati() {
    if (selected.size === 0) return;
    setSalvando(true);
    try {
      const items = [...selected.values()].map((descrizione) => ({ descrizione }));
      const res = await fetch(`/api/gruppo/tag/${tag.id}/prodotti`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ descrizioni: items }),
      });
      if (!res.ok) throw new Error();
      const n = selected.size;
      setSelected(new Map());
      await load();
      onChanged();
      toast.success(`${n} ${n === 1 ? "prodotto aggiunto" : "prodotti aggiunti"}`);
    } catch {
      toast.error("Impossibile aggiungere i prodotti");
    } finally {
      setSalvando(false);
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
      <DialogContent className="flex max-h-[90vh] w-[min(96vw,52rem)] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="shrink-0 border-b px-5 py-4">
          <DialogTitle>Prodotti di «{tag.nome}»</DialogTitle>
        </DialogHeader>
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-hidden p-5 sm:grid-cols-2">
          {/* Associati */}
          <div className="flex min-h-0 min-w-0 flex-col">
            <h3 className="mb-2 shrink-0 text-sm font-semibold">Nel tag ({assoc.length})</h3>
            <div className="min-h-0 flex-1 overflow-y-auto">
            {assoc.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nessun prodotto ancora.</p>
            ) : (
              <ul className="space-y-1">
                {assoc.map((a) => (
                  <li
                    key={a.id}
                    className="flex items-center gap-2 rounded-lg border bg-background/40 px-3 py-2 text-sm"
                  >
                    <span className="min-w-0 flex-1 truncate">{a.descrizione}</span>
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
          </div>
          {/* Disponibili */}
          <div className="flex min-h-0 min-w-0 flex-col">
            <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">Aggiungi prodotti</h3>
              {candidati.length > 0 && (
                <button
                  type="button"
                  onClick={toggleTutti}
                  className="text-xs font-medium text-primary hover:underline"
                >
                  {tuttiSelezionati
                    ? "Deseleziona tutti"
                    : nascosti > 0
                      ? `Seleziona questi ${candidati.length}`
                      : "Seleziona tutti"}
                </button>
              )}
            </div>
            <Input
              value={filtro}
              onChange={(e) => setFiltro(e.target.value)}
              placeholder="Cerca una descrizione…"
              className="mb-2 shrink-0"
            />
            <div className="min-h-0 flex-1 overflow-y-auto">
            {loading ? (
              <p className="text-sm text-muted-foreground">Caricamento…</p>
            ) : cercando && candidati.length === 0 ? (
              <p className="text-sm text-muted-foreground">Cerco fra tutti i punti vendita…</p>
            ) : ricercaError && candidati.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Non è stato possibile cercare i prodotti. Riprova a scrivere per ripetere la ricerca.
              </p>
            ) : candidati.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {filtro.trim().length >= MIN_LETTERE_RICERCA ? "Nessun prodotto trovato." : "Nessun prodotto da aggiungere."}
              </p>
            ) : (
              <ul className="space-y-1">
                {candidati.map((d) => {
                  const sel = selected.has(d.descrizione_key);
                  return (
                    <li key={d.descrizione_key}>
                      <button
                        type="button"
                        onClick={() => toggle(d)}
                        className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                          sel ? "border-primary/50 bg-primary/10" : "bg-background/40 hover:bg-accent"
                        }`}
                      >
                        <span
                          className={`flex size-4 shrink-0 items-center justify-center rounded border transition-colors ${
                            sel ? "border-primary bg-primary" : "border-border"
                          }`}
                        >
                          {sel && <Check className="size-3 text-primary-foreground" />}
                        </span>
                        <span className="min-w-0 flex-1 truncate">{d.descrizione}</span>
                        <span className="text-xs text-muted-foreground">{euro(d.spesa)}</span>
                      </button>
                    </li>
                  );
                })}
                {nascosti > 0 && (
                  <li className="px-3 py-2 text-xs text-muted-foreground">
                    {poolSaturo
                      ? "Altri prodotti non mostrati"
                      : `Altri ${nascosti} prodotti non mostrati`}
                    : scrivi almeno 2 lettere per cercarli fra tutti i punti vendita.
                  </li>
                )}
              </ul>
            )}
            </div>
          </div>
        </div>
        {/* Footer: un solo Salva per tutta la selezione */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-t bg-popover px-5 py-3">
          <span className="text-sm text-muted-foreground">
            {selected.size > 0
              ? `${selected.size} ${selected.size === 1 ? "selezionato" : "selezionati"}`
              : "Seleziona i prodotti da aggiungere"}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose} disabled={salvando}>
              Chiudi
            </Button>
            <Button onClick={salvaSelezionati} disabled={salvando || selected.size === 0}>
              {salvando ? "Salvataggio…" : <><Plus className="size-4" /> Aggiungi</>}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Dialog: analisi macro per PV del tag ──────────────────────────────────

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-background/40 px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground/70">{label}</div>
      <div className="mt-0.5 text-lg font-bold tabular-nums">{value}</div>
    </div>
  );
}

function AnalisiDialog({ tag, onClose }: { tag: GruppoTag; onClose: () => void }) {
  const [data, setData] = useState<GruppoTagAnalisi | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [periodo, setPeriodo] = useState<string>("anno");
  const reqRef = useRef(0);

  const annoCorrente = new Date().getFullYear();
  const meseCorrente = new Date().getMonth() + 1;

  // `r.ok ? r.json() : null` faceva arrivare i 5xx nel ramo di successo come
  // data=null, bypassando il catch: l'errore diventava "nessuna spesa nel periodo".
  const carica = useCallback(() => {
    const my = ++reqRef.current;
    setLoading(true);
    setLoadError(false);
    const qs = periodo !== "anno" ? `?mese=${periodo}` : "";
    fetch(`/api/gruppo/tag/${tag.id}/analisi${qs}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => { if (my === reqRef.current) setData(j); })
      .catch(() => { if (my === reqRef.current) setLoadError(true); })
      .finally(() => { if (my === reqRef.current) setLoading(false); });
  }, [tag.id, periodo]);

  useEffect(() => {
    carica();
  }, [carica]);

  const maxPv = data ? massimoSpesa(data.per_pv) : 0;
  const maxForn = data ? massimoSpesa(data.fornitori) : 0;
  const maxTrend = data ? massimoSpesa(data.trend) : 0;
  // Prezzo medio: evidenzia chi paga meno (verde) e di più (rosso), se ≥2 PV con dato.
  const { minPrezzo, maxPrezzo } = estremiPrezzo(data?.per_pv);

  async function exportXls() {
    if (!data) return;
    const XLSX = await import("xlsx");
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(righeExportPv(data.per_pv)), "Per punto vendita");
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(righeExportFornitori(data.fornitori)), "Fornitori");
    XLSX.writeFile(wb, nomeFileExport(data.nome, data.periodo_label));
  }

  const vuoto = analisiVuota(data);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="flex max-h-[90vh] flex-col gap-0 w-[min(96vw,68rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="shrink-0 border-b px-5 py-4">
          <DialogTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
            <span className="flex items-center gap-2">
              {(data?.emoji || tag.emoji) && <span>{data?.emoji || tag.emoji}</span>}
              «{tag.nome}» per punto vendita
            </span>
            <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
              <NativeSelect value={periodo} onValueChange={setPeriodo} className="h-8 w-48 text-xs">
                <option value="anno">Anno in corso ({annoCorrente})</option>
                {MESI_LABEL.slice(0, meseCorrente).map((m, i) => (
                  <option key={i + 1} value={String(i + 1)}>{m} {annoCorrente}</option>
                ))}
              </NativeSelect>
              <button
                type="button"
                onClick={exportXls}
                disabled={vuoto}
                className="inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-xs font-medium transition-colors hover:bg-accent disabled:opacity-50"
              >
                <Download className="size-3.5" /> Esporta
              </button>
            </span>
          </DialogTitle>
        </DialogHeader>
        <div className="min-h-0 flex-1 space-y-5 overflow-auto p-5">
          {loading && !data ? (
            <p className="py-12 text-center text-sm text-muted-foreground">Caricamento…</p>
          ) : loadError && !data ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <p className="text-sm text-muted-foreground">
                Non è stato possibile caricare i dati.
              </p>
              <Button size="sm" variant="outline" onClick={carica} disabled={loading}>
                Riprova
              </Button>
            </div>
          ) : vuoto ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              Nessuna spesa nel periodo per questo tag.
            </p>
          ) : (
            <>
              {/* KPI di gruppo */}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                <KpiCard label="Spesa totale" value={euro(data!.spesa_totale)} />
                <KpiCard label="Quantità" value={num(data!.quantita_totale)} />
                <KpiCard label="Prezzo medio" value={euro2(data!.prezzo_medio)} />
                <KpiCard label="Fornitori" value={String(data!.n_fornitori)} />
                <KpiCard label="Righe" value={String(data!.per_pv.reduce((s, p) => s + p.n_righe, 0))} />
              </div>

              {/* Per punto vendita */}
              <div>
                <h3 className="mb-2 text-sm font-semibold">Per punto vendita</h3>
                <ul className="space-y-2">
                  {data!.per_pv.map((p) => (
                    <li key={p.ristorante_id} className="rounded-xl border bg-background/40 p-3">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-sm font-medium">{p.nome}</span>
                        <span className="text-sm font-semibold tabular-nums">{euro(p.spesa)}</span>
                      </div>
                      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                        <div className="h-full rounded-full bg-primary"
                          style={{ width: larghezzaBarra(p.spesa, maxPv) }} />
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                        <span>{pct(p.incidenza_pct)} del gruppo</span>
                        <span>·</span>
                        <span>
                          prezzo medio{" "}
                          <span className={cn(
                            "font-medium tabular-nums",
                            classePrezzo(p.prezzo_medio, minPrezzo, maxPrezzo),
                          )}>{euro2(p.prezzo_medio)}</span>
                        </span>
                        <span>·</span>
                        <span>{p.n_righe} righe · {p.n_fornitori} forn.</span>
                      </div>
                    </li>
                  ))}
                </ul>
                {/* Hint: se un solo PV ha spesa, le descrizioni del tag sono di
                    quella sede → il confronto prezzi tra PV si abilita aggiungendo
                    le varianti delle altre. */}
                {soloUnPvConSpesa(data!.per_pv) && (
                  <p className="mt-2 rounded-md border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-xs text-sky-700 dark:text-sky-400">
                    Solo un punto vendita ha spesa: aggiungi al tag anche le descrizioni «{tag.nome}» delle
                    altre sedi (da «Prodotti») per confrontare i prezzi tra i punti vendita.
                  </p>
                )}
              </div>

              {/* Fornitori del gruppo */}
              {data!.fornitori.length > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-semibold">Fornitori (tutto il gruppo)</h3>
                  <ul className="space-y-1.5">
                    {data!.fornitori.map((f) => (
                      <li key={f.nome} className="rounded-lg border bg-background/40 px-3 py-2">
                        <div className="flex items-baseline justify-between gap-2 text-sm">
                          <span className="flex min-w-0 items-center gap-1.5">
                            <Truck className="size-3.5 shrink-0 text-muted-foreground/60" />
                            <span className="truncate font-medium">{f.nome}</span>
                          </span>
                          <span className="shrink-0 tabular-nums">{euro(f.spesa)} · {pct(f.incidenza_pct)}</span>
                        </div>
                        <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full bg-primary/70"
                            style={{ width: larghezzaBarra(f.spesa, maxForn) }} />
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Trend mensile (solo se più di un mese nel periodo) */}
              {data!.trend.length > 1 && (
                <div>
                  <h3 className="mb-2 text-sm font-semibold">Andamento mensile</h3>
                  <div className="flex items-end gap-1.5">
                    {data!.trend.map((t) => (
                      <div key={`${t.anno}-${t.mese}`} className="flex flex-1 flex-col items-center gap-1">
                        <div className="flex h-24 w-full items-end">
                          <div className="w-full rounded-t bg-primary/70" title={euro(t.spesa)}
                            style={{ height: altezzaBarraTrend(t.spesa, maxTrend) }} />
                        </div>
                        <span className="text-[10px] text-muted-foreground">{MESI_LABEL[t.mese - 1].slice(0, 3)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
