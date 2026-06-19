"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { ConfirmDialog } from "../confirm-dialog";
import { MESI_LUNGHI as MESI } from "@/lib/mesi";

// ─── Tipi ─────────────────────────────────────────────────────────────────────
// Forma allineata a /api/ricavi/giornalieri (GET → items[], POST upsert per data).
// L'incasso e' UNO per giorno (upsert on_conflict ristorante_id,data): non c'e' un
// id-per-riga da usare per la DELETE, si elimina passando la data.

interface Incasso {
  data: string;
  fatturato_iva10: number;
  fatturato_iva22: number;
  altri_ricavi_noiva: number;
  source: "manuale" | "xls" | "email";
}

interface IncassiResponse {
  items: Incasso[];
  totale_iva10: number;
  totale_iva22: number;
  totale_altri: number;
  totale_netto: number;
  giorni_con_dati: number;
}


// Stessa formula di periodi.ts (desktop) e _calc_netto (worker): scorporo IVA.
function scorporoNetto(iva10: number, iva22: number, altri: number): number {
  return iva10 / 1.1 + iva22 / 1.22 + altri;
}

function meseISO(anno: number, mese: number) {
  return `${anno}-${String(mese + 1).padStart(2, "0")}`;
}
function primoGiornoISO(anno: number, mese: number) {
  return `${meseISO(anno, mese)}-01`;
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
function parseImporto(s: string): number {
  return s ? parseFloat(s.replace(",", ".")) || 0 : 0;
}

const SOURCE_BADGE: Record<string, string> = {
  xls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200",
  email: "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200",
};

// ─── Dialog incasso ─────────────────────────────────────────────────────────────

interface DialogProps {
  open: boolean;
  incasso: Incasso | null;
  dataDefault: string;
  onClose: () => void;
  onSaved: () => void;
}

function IncassoDialog({ open, incasso, dataDefault, onClose, onSaved }: DialogProps) {
  const [data, setData] = useState(dataDefault);
  const [iva10, setIva10] = useState("");
  const [iva22, setIva22] = useState("");
  const [altri, setAltri] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setData(incasso?.data ?? dataDefault);
      setIva10(incasso?.fatturato_iva10 ? String(incasso.fatturato_iva10).replace(".", ",") : "");
      setIva22(incasso?.fatturato_iva22 ? String(incasso.fatturato_iva22).replace(".", ",") : "");
      setAltri(incasso?.altri_ricavi_noiva ? String(incasso.altri_ricavi_noiva).replace(".", ",") : "");
    }
  }, [open, incasso, dataDefault]);

  const netto = useMemo(
    () => scorporoNetto(parseImporto(iva10), parseImporto(iva22), parseImporto(altri)),
    [iva10, iva22, altri],
  );

  async function salva() {
    const v10 = parseImporto(iva10);
    const v22 = parseImporto(iva22);
    const vAltri = parseImporto(altri);
    if (v10 <= 0 && v22 <= 0 && vAltri <= 0) {
      toast.error("Inserisci almeno un importo");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        data,
        fatturato_iva10: v10,
        fatturato_iva22: v22,
        altri_ricavi_noiva: vAltri,
      };
      // Un solo endpoint sia per nuovo che per modifica: e' un upsert per data.
      const res = await fetch("/api/ricavi/giornalieri", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error((await res.json()).detail ?? "Errore");
      toast.success(incasso ? "Incasso aggiornato" : "Incasso salvato");
      onSaved();
      onClose();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore salvataggio");
    } finally {
      setSaving(false);
    }
  }

  const campi: { label: string; val: string; set: (v: string) => void }[] = [
    { label: "Corrispettivi IVA 10% (€)", val: iva10, set: setIva10 },
    { label: "Corrispettivi IVA 22% (€)", val: iva22, set: setIva22 },
    { label: "Altri ricavi senza IVA (€)", val: altri, set: setAltri },
  ];

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-[calc(100vw-2rem)] rounded-2xl">
        <DialogHeader>
          <DialogTitle>{incasso ? "Modifica incasso" : "Nuovo incasso"}</DialogTitle>
        </DialogHeader>
        <div className="mt-1 space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Giorno *</label>
            <Input type="date" value={data} onChange={(e) => setData(e.target.value)} disabled={!!incasso} />
          </div>
          {campi.map((c, i) => (
            <div key={c.label}>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">{c.label}</label>
              <Input
                type="text"
                inputMode="decimal"
                value={c.val}
                onChange={(e) => c.set(e.target.value.replace(/[^0-9,.]/g, ""))}
                placeholder="es. 850,00"
                autoFocus={i === 0 && !incasso}
                className="text-right tabular-nums"
              />
            </div>
          ))}
          <div className="flex items-center justify-between rounded-lg bg-muted/40 px-3 py-2 text-sm">
            <span className="text-muted-foreground">Incasso netto</span>
            <strong className="tabular-nums text-primary">{netto > 0 ? fmtEuro(netto) : "—"}</strong>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Inserisci gli importi <strong>lordi</strong> (come sul registratore di cassa). Lo scorporo IVA è automatico.
          </p>
          <div className="flex gap-2 pt-1">
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

export function MobileIncassi() {
  const today = todayISO();
  const now = new Date();
  const [anno, setAnno] = useState(now.getFullYear());
  const [mese, setMese] = useState(now.getMonth());
  const [risposta, setRisposta] = useState<IncassiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editIncasso, setEditIncasso] = useState<Incasso | null>(null);
  const [daEliminare, setDaEliminare] = useState<Incasso | null>(null);

  const load = useCallback(async (a: number, m: number) => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ data_da: primoGiornoISO(a, m), data_a: ultimoGiornoISO(a, m) });
      const res = await fetch(`/api/ricavi/giornalieri?${qs}`);
      if (!res.ok) throw new Error();
      const d: IncassiResponse = await res.json();
      setRisposta(d);
    } catch {
      toast.error("Errore caricamento incassi");
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

  async function elimina(i: Incasso) {
    try {
      const qs = new URLSearchParams({ data: i.data });
      const res = await fetch(`/api/ricavi/giornalieri?${qs}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Incasso eliminato");
      load(anno, mese);
    } catch {
      toast.error("Errore eliminazione");
    }
  }

  const voci = useMemo(
    () => (risposta?.items ?? []).slice().sort((a, b) => b.data.localeCompare(a.data)),
    [risposta],
  );
  const nettoMese = risposta?.totale_netto ?? 0;
  const giorni = risposta?.giorni_con_dati ?? 0;

  const dataDefault = useMemo(() => {
    return today.startsWith(meseISO(anno, mese)) ? today : primoGiornoISO(anno, mese);
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

      {/* KPI netto mese */}
      <div className="rounded-2xl border border-primary/30 bg-primary/5 p-3">
        <p className="text-xs font-medium text-primary">Incasso netto del mese</p>
        <p className="text-2xl font-bold tabular-nums text-primary">{fmtEuro(nettoMese)}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {giorni} {giorni === 1 ? "giorno inserito" : "giorni inseriti"}
        </p>
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
          <p className="py-8 text-center text-sm text-muted-foreground">Nessun incasso inserito in questo mese.</p>
        ) : (
          voci.map((i) => {
            const netto = scorporoNetto(i.fatturato_iva10, i.fatturato_iva22, i.altri_ricavi_noiva);
            return (
              <div key={i.data} className="flex items-center gap-3 rounded-xl border bg-card p-3">
                <span className="w-10 shrink-0 text-xs tabular-nums text-muted-foreground">{fmtData(i.data)}</span>
                {i.source !== "manuale" && (
                  <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${SOURCE_BADGE[i.source] ?? ""}`}>
                    {i.source === "xls" ? "XLS" : "Email"}
                  </span>
                )}
                <span className="min-w-0 flex-1 text-sm">
                  <span className="font-semibold tabular-nums">{fmtEuro(netto)}</span>
                  <span className="ml-1 text-xs text-muted-foreground">netto</span>
                </span>
                <div className="flex shrink-0 items-center gap-1">
                  <button onClick={() => { setEditIncasso(i); setDialogOpen(true); }} className="rounded-md p-1.5 text-muted-foreground active:bg-muted">
                    <Pencil className="size-4" />
                  </button>
                  <button onClick={() => setDaEliminare(i)} className="rounded-md p-1.5 text-muted-foreground active:bg-muted active:text-destructive">
                    <Trash2 className="size-4" />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* FAB aggiungi */}
      <button
        onClick={() => { setEditIncasso(null); setDialogOpen(true); }}
        className="fixed right-5 z-40 flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg active:scale-95"
        style={{ bottom: "calc(80px + env(safe-area-inset-bottom))" }}
        aria-label="Nuovo incasso"
      >
        <Plus className="size-7" />
      </button>

      <IncassoDialog
        open={dialogOpen}
        incasso={editIncasso}
        dataDefault={dataDefault}
        onClose={() => { setDialogOpen(false); setEditIncasso(null); }}
        onSaved={() => load(anno, mese)}
      />

      <ConfirmDialog
        open={daEliminare !== null}
        titolo="Eliminare l'incasso?"
        messaggio={daEliminare ? `L'incasso del ${fmtData(daEliminare.data)} verrà rimosso.` : undefined}
        onConferma={() => { if (daEliminare) elimina(daEliminare); }}
        onClose={() => setDaEliminare(null)}
      />
    </div>
  );
}
