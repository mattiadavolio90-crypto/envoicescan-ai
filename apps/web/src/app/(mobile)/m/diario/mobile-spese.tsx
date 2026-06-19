"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { ConfirmDialog } from "../confirm-dialog";
import { MESI_LUNGHI as MESI } from "@/lib/mesi";

// ─── Tipi ─────────────────────────────────────────────────────────────────────

type TipoSpesa = "fb" | "generale";

interface Spesa {
  id: string;
  data_spesa: string;
  tipo: TipoSpesa;
  importo: number;
  descrizione: string;
  note?: string | null;
}

interface SpeseResponse {
  voci: Spesa[];
  totale_fb: number;
  totale_generale: number;
  totale: number;
}


function meseISO(anno: number, mese: number) {
  return `${anno}-${String(mese + 1).padStart(2, "0")}`;
}
function ultimoGiornoISO(anno: number, mese: number) {
  const g = new Date(anno, mese + 1, 0).getDate();
  return `${meseISO(anno, mese)}-${String(g).padStart(2, "0")}`;
}
function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function fmtData(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" });
}
function fmtEuro(v: number) {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);
}

const TIPO_LABEL: Record<TipoSpesa, string> = { fb: "Costo F&B", generale: "Spesa Generale" };
const TIPO_BADGE: Record<TipoSpesa, string> = {
  fb: "bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200",
  generale: "bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200",
};

// ─── Dialog spesa ─────────────────────────────────────────────────────────────

interface DialogProps {
  open: boolean;
  spesa: Spesa | null;
  dataDefault: string;
  onClose: () => void;
  onSaved: () => void;
}

function SpesaDialog({ open, spesa, dataDefault, onClose, onSaved }: DialogProps) {
  const [data, setData] = useState(dataDefault);
  const [tipo, setTipo] = useState<TipoSpesa>("generale");
  const [importo, setImporto] = useState("");
  const [descrizione, setDescrizione] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setData(spesa?.data_spesa ?? dataDefault);
      setTipo(spesa?.tipo ?? "generale");
      setImporto(spesa?.importo ? String(spesa.importo).replace(".", ",") : "");
      setDescrizione(spesa?.descrizione ?? "");
      setNote(spesa?.note ?? "");
    }
  }, [open, spesa, dataDefault]);

  async function salva() {
    const importoNum = importo ? parseFloat(importo.replace(",", ".")) : NaN;
    if (!descrizione.trim()) { toast.error("La descrizione è obbligatoria"); return; }
    if (isNaN(importoNum) || importoNum < 0) { toast.error("Inserisci un importo valido"); return; }
    setSaving(true);
    try {
      const payload = {
        data_spesa: data,
        tipo,
        importo: importoNum,
        descrizione: descrizione.trim(),
        note: note.trim() || null,
      };
      const url = spesa ? `/api/workspace/spese/${spesa.id}` : "/api/workspace/spese";
      const res = await fetch(url, {
        method: spesa ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error((await res.json()).detail ?? "Errore");
      toast.success(spesa ? "Spesa aggiornata" : "Spesa aggiunta");
      onSaved();
      onClose();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore salvataggio");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-[calc(100vw-2rem)] rounded-2xl">
        <DialogHeader>
          <DialogTitle>{spesa ? "Modifica spesa" : "Nuova spesa"}</DialogTitle>
        </DialogHeader>
        <div className="mt-1 space-y-3">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Tipo di spesa *</label>
            <div className="grid grid-cols-2 gap-2">
              {(["fb", "generale"] as TipoSpesa[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTipo(t)}
                  className={`rounded-lg border py-2.5 text-sm font-medium transition-colors ${
                    tipo === t
                      ? t === "fb"
                        ? "border-orange-500 bg-orange-500/10 text-orange-700 dark:text-orange-300"
                        : "border-purple-500 bg-purple-500/10 text-purple-700 dark:text-purple-300"
                      : "border-input text-muted-foreground"
                  }`}
                >
                  {TIPO_LABEL[t]}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Data *</label>
              <Input type="date" value={data} onChange={(e) => setData(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Importo (€) *</label>
              <Input
                type="text"
                inputMode="decimal"
                value={importo}
                onChange={(e) => setImporto(e.target.value.replace(/[^0-9,.]/g, ""))}
                placeholder="es. 120,00"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Descrizione *</label>
            <Input value={descrizione} onChange={(e) => setDescrizione(e.target.value)} placeholder="es. Pesce dal mercato, bolletta gas…" autoFocus />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Note</label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Opzionale…" />
          </div>
          <div className="flex gap-2 pt-2">
            <button
              onClick={onClose}
              disabled={saving}
              className="flex-1 rounded-lg border border-border py-2.5 text-sm font-medium active:scale-[0.98]"
            >
              Annulla
            </button>
            <button
              onClick={salva}
              disabled={saving}
              className="flex-1 rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground active:scale-[0.98] disabled:opacity-50"
            >
              {saving ? "Salvo…" : "Salva"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Componente principale ──────────────────────────────────────────────────────

export function MobileSpese() {
  const today = todayISO();
  const now = new Date();
  const [anno, setAnno] = useState(now.getFullYear());
  const [mese, setMese] = useState(now.getMonth());
  const [risposta, setRisposta] = useState<SpeseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editSpesa, setEditSpesa] = useState<Spesa | null>(null);
  const [daEliminare, setDaEliminare] = useState<Spesa | null>(null);

  const load = useCallback(async (a: number, m: number) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/workspace/spese?da=${meseISO(a, m)}-01&a=${ultimoGiornoISO(a, m)}`);
      if (!res.ok) throw new Error();
      const d: SpeseResponse = await res.json();
      setRisposta(d);
    } catch {
      toast.error("Errore caricamento spese");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(anno, mese); }, [anno, mese, load]);

  const vista = useRef({ anno, mese });
  vista.current = { anno, mese };
  useEffect(() => {
    const h = () => load(vista.current.anno, vista.current.mese);
    window.addEventListener("oneflux:refresh", h);
    return () => window.removeEventListener("oneflux:refresh", h);
  }, [load]);

  function mesePrec() {
    if (mese === 0) { setAnno((a) => a - 1); setMese(11); } else setMese((m) => m - 1);
  }
  function meseSucc() {
    if (mese === 11) { setAnno((a) => a + 1); setMese(0); } else setMese((m) => m + 1);
  }

  async function elimina(s: Spesa) {
    try {
      const res = await fetch(`/api/workspace/spese/${s.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Spesa eliminata");
      load(anno, mese);
    } catch {
      toast.error("Errore eliminazione");
    }
  }

  const voci = useMemo(
    () => (risposta?.voci ?? []).slice().sort((a, b) => b.data_spesa.localeCompare(a.data_spesa)),
    [risposta],
  );
  const totFb = risposta?.totale_fb ?? 0;
  const totGenerale = risposta?.totale_generale ?? 0;

  const dataDefault = useMemo(() => {
    const t = today;
    return t.startsWith(meseISO(anno, mese)) ? t : `${meseISO(anno, mese)}-01`;
  }, [today, anno, mese]);

  return (
    <div className="space-y-4">
      {/* Navigazione mese */}
      <div className="flex items-center justify-between rounded-2xl border bg-card px-2 py-2">
        <button onClick={mesePrec} className="rounded-full p-2 active:bg-muted">
          <ChevronLeft className="size-5" />
        </button>
        <span className="text-sm font-semibold">{MESI[mese]} {anno}</span>
        <button onClick={meseSucc} className="rounded-full p-2 active:bg-muted">
          <ChevronRight className="size-5" />
        </button>
      </div>

      {/* KPI totali */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-2xl ring-1 ring-orange-500/60 bg-orange-50 dark:bg-orange-950/20 p-3">
          <p className="text-xs font-medium text-orange-700 dark:text-orange-500">Costi F&B extra</p>
          <p className="text-lg font-bold tabular-nums text-orange-700 dark:text-orange-400">{fmtEuro(totFb)}</p>
        </div>
        <div className="rounded-2xl ring-1 ring-purple-500/60 bg-purple-50 dark:bg-purple-950/20 p-3">
          <p className="text-xs font-medium text-purple-700 dark:text-purple-500">Spese Generali extra</p>
          <p className="text-lg font-bold tabular-nums text-purple-700 dark:text-purple-400">{fmtEuro(totGenerale)}</p>
        </div>
      </div>

      {/* Lista voci */}
      <div className="space-y-2.5">
        {loading ? (
          <div className="space-y-2.5">
            {[0, 1].map((i) => (
              <div key={i} className="h-14 animate-pulse rounded-xl border bg-muted/40" />
            ))}
          </div>
        ) : voci.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Nessuna spesa extra in questo mese.</p>
        ) : (
          voci.map((s) => (
            <div key={s.id} className="flex items-center gap-3 rounded-xl border bg-card p-3">
              <span className="w-10 shrink-0 text-xs tabular-nums text-muted-foreground">{fmtData(s.data_spesa)}</span>
              <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${TIPO_BADGE[s.tipo]}`}>
                {s.tipo === "fb" ? "F&B" : "Gen."}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm">
                {s.descrizione}
                {s.note && <span className="ml-1 text-xs italic text-muted-foreground">· {s.note}</span>}
              </span>
              <span className="shrink-0 text-sm font-semibold tabular-nums">{fmtEuro(s.importo)}</span>
              <div className="flex shrink-0 items-center gap-1">
                <button onClick={() => { setEditSpesa(s); setDialogOpen(true); }} className="rounded-md p-1.5 text-muted-foreground active:bg-muted">
                  <Pencil className="size-4" />
                </button>
                <button onClick={() => setDaEliminare(s)} className="rounded-md p-1.5 text-muted-foreground active:bg-muted active:text-destructive">
                  <Trash2 className="size-4" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* FAB aggiungi */}
      <button
        onClick={() => { setEditSpesa(null); setDialogOpen(true); }}
        className="fixed right-5 z-40 flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg active:scale-95"
        style={{ bottom: "calc(80px + env(safe-area-inset-bottom))" }}
        aria-label="Nuova spesa"
      >
        <Plus className="size-7" />
      </button>

      <SpesaDialog
        open={dialogOpen}
        spesa={editSpesa}
        dataDefault={dataDefault}
        onClose={() => { setDialogOpen(false); setEditSpesa(null); }}
        onSaved={() => load(anno, mese)}
      />

      <ConfirmDialog
        open={daEliminare !== null}
        titolo="Eliminare la spesa?"
        messaggio={daEliminare ? `"${daEliminare.descrizione}" (${fmtEuro(daEliminare.importo)}) verrà rimossa.` : undefined}
        onConferma={() => { if (daEliminare) elimina(daEliminare); }}
        onClose={() => setDaEliminare(null)}
      />
    </div>
  );
}
