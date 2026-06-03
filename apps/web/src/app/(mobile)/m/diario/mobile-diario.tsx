"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { ConfirmDialog } from "../confirm-dialog";

// ─── Tipi ─────────────────────────────────────────────────────────────────────

interface EventoDiario {
  id: string;
  data_evento: string;
  titolo: string;
  descrizione?: string | null;
  ora_inizio?: string | null;
  ora_fine?: string | null;
  colore: string;
}

const COLORI: { key: string; label: string; dot: string }[] = [
  { key: "sky", label: "Blu", dot: "bg-sky-500" },
  { key: "green", label: "Verde", dot: "bg-green-500" },
  { key: "amber", label: "Arancio", dot: "bg-amber-500" },
  { key: "red", label: "Rosso", dot: "bg-red-500" },
  { key: "purple", label: "Viola", dot: "bg-purple-500" },
  { key: "gray", label: "Grigio", dot: "bg-gray-400" },
];

function coloreInfo(key: string) {
  return COLORI.find((c) => c.key === key) ?? COLORI[0];
}

const MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];
const GIORNI_BREVI = ["L", "M", "M", "G", "V", "S", "D"];

function meseISO(anno: number, mese: number) {
  return `${anno}-${String(mese + 1).padStart(2, "0")}`;
}
function primoGiornoMese(anno: number, mese: number): number {
  const d = new Date(anno, mese, 1).getDay();
  return d === 0 ? 6 : d - 1;
}
function giorniNelMese(anno: number, mese: number) {
  return new Date(anno, mese + 1, 0).getDate();
}
function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function fmtOra(t: string | null | undefined) {
  return t ? t.slice(0, 5) : "";
}

// ─── Dialog evento ──────────────────────────────────────────────────────────────

interface DialogProps {
  open: boolean;
  evento: EventoDiario | null;
  dataDefault: string;
  onClose: () => void;
  onSaved: () => void;
}

function EventoDialog({ open, evento, dataDefault, onClose, onSaved }: DialogProps) {
  const [titolo, setTitolo] = useState("");
  const [descrizione, setDescrizione] = useState("");
  const [data, setData] = useState(dataDefault);
  const [oraInizio, setOraInizio] = useState("");
  const [oraFine, setOraFine] = useState("");
  const [colore, setColore] = useState("sky");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setTitolo(evento?.titolo ?? "");
      setDescrizione(evento?.descrizione ?? "");
      setData(evento?.data_evento ?? dataDefault);
      setOraInizio(fmtOra(evento?.ora_inizio));
      setOraFine(fmtOra(evento?.ora_fine));
      setColore(evento?.colore ?? "sky");
    }
  }, [open, evento, dataDefault]);

  async function salva() {
    if (!titolo.trim()) {
      toast.error("Il titolo è obbligatorio");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        titolo: titolo.trim(),
        descrizione: descrizione.trim() || null,
        data_evento: data,
        ora_inizio: oraInizio || null,
        ora_fine: oraFine || null,
        colore,
      };
      const url = evento ? `/api/workspace/diario/${evento.id}` : "/api/workspace/diario";
      const res = await fetch(url, {
        method: evento ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error((await res.json()).detail ?? "Errore");
      toast.success(evento ? "Evento aggiornato" : "Evento aggiunto");
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
          <DialogTitle>{evento ? "Modifica evento" : "Nuovo evento"}</DialogTitle>
        </DialogHeader>
        <div className="mt-1 space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Titolo *</label>
            <Input value={titolo} onChange={(e) => setTitolo(e.target.value)} placeholder="es. Chiusura, Manutenzione frigo…" autoFocus />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Data *</label>
            <Input type="date" value={data} onChange={(e) => setData(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Ora inizio</label>
              <Input type="time" value={oraInizio} onChange={(e) => setOraInizio(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Ora fine</label>
              <Input type="time" value={oraFine} onChange={(e) => setOraFine(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Note</label>
            <textarea
              value={descrizione}
              onChange={(e) => setDescrizione(e.target.value)}
              rows={2}
              placeholder="Dettagli…"
              className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>
          <div>
            <label className="mb-2 block text-xs font-medium text-muted-foreground">Colore</label>
            <div className="flex gap-3">
              {COLORI.map((c) => (
                <button
                  key={c.key}
                  title={c.label}
                  onClick={() => setColore(c.key)}
                  className={`size-8 rounded-full ${c.dot} transition-transform ${colore === c.key ? "scale-110 ring-2 ring-foreground/30 ring-offset-2" : "opacity-60"}`}
                />
              ))}
            </div>
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

// ─── Calendario ───────────────────────────────────────────────────────────────

function Calendario({ anno, mese, eventi, selezionato, onSelect }: {
  anno: number;
  mese: number;
  eventi: EventoDiario[];
  selezionato: string;
  onSelect: (d: string) => void;
}) {
  const oggi = todayISO();
  const n = giorniNelMese(anno, mese);
  const offset = primoGiornoMese(anno, mese);

  // Raggruppamento eventi-per-giorno e griglia celle memoizzati: non si
  // ricalcolano quando il genitore ri-renderizza per motivi estranei (es.
  // apertura di un dialog), ma solo se cambiano eventi o il mese mostrato.
  const perGiorno = useMemo(() => {
    const m: Record<string, EventoDiario[]> = {};
    for (const e of eventi) (m[e.data_evento] ??= []).push(e);
    return m;
  }, [eventi]);

  const celle: (number | null)[] = useMemo(
    () => [...Array(offset).fill(null), ...Array.from({ length: n }, (_, i) => i + 1)],
    [offset, n],
  );

  return (
    <div className="select-none">
      <div className="mb-1 grid grid-cols-7">
        {GIORNI_BREVI.map((g, i) => (
          <div key={i} className="py-1 text-center text-[10px] font-medium text-muted-foreground">{g}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-y-1">
        {celle.map((giorno, i) => {
          if (!giorno) return <div key={i} />;
          const iso = `${anno}-${String(mese + 1).padStart(2, "0")}-${String(giorno).padStart(2, "0")}`;
          const isOggi = iso === oggi;
          const isSel = iso === selezionato;
          const dots = (perGiorno[iso] ?? []).slice(0, 3);
          return (
            <button
              key={iso}
              onClick={() => onSelect(iso)}
              className={`mx-auto flex size-10 flex-col items-center justify-center rounded-full text-sm transition-colors
                ${isSel ? "bg-primary font-semibold text-primary-foreground" : isOggi ? "font-semibold ring-1 ring-primary" : "active:bg-muted"}`}
            >
              <span>{giorno}</span>
              {dots.length > 0 && (
                <div className="mt-0.5 flex gap-0.5">
                  {dots.map((e, di) => (
                    <span key={di} className={`size-1 rounded-full ${coloreInfo(e.colore).dot} ${isSel ? "opacity-80" : ""}`} />
                  ))}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Componente principale ──────────────────────────────────────────────────────

export function MobileDiario() {
  const today = todayISO();
  const now = new Date();
  const [anno, setAnno] = useState(now.getFullYear());
  const [mese, setMese] = useState(now.getMonth());
  const [eventi, setEventi] = useState<EventoDiario[]>([]);
  const [loading, setLoading] = useState(false);
  const [giornoSel, setGiornoSel] = useState<string>(today);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editEvento, setEditEvento] = useState<EventoDiario | null>(null);
  const [daEliminare, setDaEliminare] = useState<EventoDiario | null>(null);

  const load = useCallback(async (a: number, m: number) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/workspace/diario?mese=${meseISO(a, m)}`);
      if (!res.ok) throw new Error();
      const d = await res.json();
      setEventi(d.eventi ?? []);
    } catch {
      toast.error("Errore caricamento diario");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(anno, mese); }, [anno, mese, load]);

  // Pull-to-refresh: ricarica il mese visualizzato. Il listener si registra UNA
  // sola volta; legge anno/mese correnti da un ref, cosi' non viene staccato e
  // riattaccato a ogni cambio mese (prima le deps includevano anno/mese).
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

  async function elimina(e: EventoDiario) {
    try {
      const res = await fetch(`/api/workspace/diario/${e.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Evento eliminato");
      load(anno, mese);
    } catch {
      toast.error("Errore eliminazione");
    }
  }

  const eventiGiorno = useMemo(
    () =>
      eventi
        .filter((e) => e.data_evento === giornoSel)
        .sort((a, b) => (a.ora_inizio ?? "99:99").localeCompare(b.ora_inizio ?? "99:99")),
    [eventi, giornoSel],
  );

  const fmtGiorno = (iso: string) =>
    new Date(iso + "T00:00:00").toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold tracking-tight">Diario</h1>

      {/* Calendario */}
      <div className="rounded-2xl border bg-card p-4">
        <div className="mb-2 flex items-center justify-between">
          <button onClick={mesePrec} className="rounded-full p-2 active:bg-muted">
            <ChevronLeft className="size-5" />
          </button>
          <span className="text-sm font-semibold">{MESI[mese]} {anno}</span>
          <button onClick={meseSucc} className="rounded-full p-2 active:bg-muted">
            <ChevronRight className="size-5" />
          </button>
        </div>
        <Calendario anno={anno} mese={mese} eventi={eventi} selezionato={giornoSel} onSelect={setGiornoSel} />
      </div>

      {/* Eventi del giorno */}
      <div className="space-y-2.5">
        <h2 className="text-sm font-semibold capitalize">{fmtGiorno(giornoSel)}</h2>
        {loading ? (
          <div className="space-y-2.5">
            {[0, 1].map((i) => (
              <div key={i} className="h-16 animate-pulse rounded-xl border bg-muted/40" />
            ))}
          </div>
        ) : eventiGiorno.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Nessun evento per questo giorno.</p>
        ) : (
          eventiGiorno.map((e) => {
            const col = coloreInfo(e.colore);
            return (
              <div key={e.id} className="flex items-start gap-3 rounded-xl border bg-card p-3.5">
                <div className={`mt-1 size-2.5 shrink-0 rounded-full ${col.dot}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">{e.titolo}</span>
                    {(e.ora_inizio || e.ora_fine) && (
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {fmtOra(e.ora_inizio)}{e.ora_fine ? `–${fmtOra(e.ora_fine)}` : ""}
                      </span>
                    )}
                  </div>
                  {e.descrizione && (
                    <p className="mt-0.5 whitespace-pre-wrap text-xs text-muted-foreground">{e.descrizione}</p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button onClick={() => { setEditEvento(e); setDialogOpen(true); }} className="rounded-md p-1.5 text-muted-foreground active:bg-muted">
                    <Pencil className="size-4" />
                  </button>
                  <button onClick={() => setDaEliminare(e)} className="rounded-md p-1.5 text-muted-foreground active:bg-muted active:text-destructive">
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
        onClick={() => { setEditEvento(null); setDialogOpen(true); }}
        className="fixed right-5 z-40 flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg active:scale-95"
        style={{ bottom: "calc(80px + env(safe-area-inset-bottom))" }}
        aria-label="Nuovo evento"
      >
        <Plus className="size-7" />
      </button>

      <EventoDialog
        open={dialogOpen}
        evento={editEvento}
        dataDefault={giornoSel}
        onClose={() => { setDialogOpen(false); setEditEvento(null); }}
        onSaved={() => load(anno, mese)}
      />

      <ConfirmDialog
        open={daEliminare !== null}
        titolo="Eliminare l'evento?"
        messaggio={daEliminare ? `"${daEliminare.titolo}" verrà rimosso dal diario.` : undefined}
        onConferma={() => { if (daEliminare) elimina(daEliminare); }}
        onClose={() => setDaEliminare(null)}
      />
    </div>
  );
}
