"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

// ─── Tipi ─────────────────────────────────────────────────────────────────────

interface Turno {
  id: string;
  nome: string;
  data_turno: string;
  ora_inizio: string;
  ora_fine: string;
  ora_inizio2?: string | null;
  ora_fine2?: string | null;
  ore_extra?: number | null;
  costo_orario?: number | null;
  note?: string | null;
}

interface PersonaleResponse {
  turni: Turno[];
  monte_ore: Record<string, number>;
  nomi: string[];
  costi_noti: Record<string, number>;
}

const GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];

function lunediDi(d: Date): Date {
  const r = new Date(d);
  const dow = r.getDay() === 0 ? 6 : r.getDay() - 1;
  r.setDate(r.getDate() - dow);
  r.setHours(0, 0, 0, 0);
  return r;
}
function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}
function toISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function fmtOra(t: string | null | undefined) {
  return t ? t.slice(0, 5) : "";
}
function calcolaSlotOre(inizio: string, fine: string): number {
  const [ih, im] = inizio.split(":").map(Number);
  const [fh, fm] = fine.split(":").map(Number);
  let minuti = fh * 60 + fm - (ih * 60 + im);
  if (minuti < 0) minuti += 24 * 60;
  return Math.round((minuti / 60) * 100) / 100;
}
function oreTurno(t: Turno): number {
  let tot = calcolaSlotOre(t.ora_inizio, t.ora_fine);
  if (t.ora_inizio2 && t.ora_fine2) tot += calcolaSlotOre(t.ora_inizio2, t.ora_fine2);
  return Math.round(tot * 100) / 100;
}
function fmtOre(ore: number): string {
  const h = Math.floor(ore);
  const m = Math.round((ore - h) * 60);
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}
function orarioTurno(t: Turno): string {
  let s = `${fmtOra(t.ora_inizio)}–${fmtOra(t.ora_fine)}`;
  if (t.ora_inizio2 && t.ora_fine2) s += ` · ${fmtOra(t.ora_inizio2)}–${fmtOra(t.ora_fine2)}`;
  return s;
}

// ─── Dialog turno ──────────────────────────────────────────────────────────────

interface DialogProps {
  open: boolean;
  turno: Turno | null;
  dataDefault: string;
  nomiSuggeriti: string[];
  onClose: () => void;
  onSaved: () => void;
}

function TurnoDialog({ open, turno, dataDefault, nomiSuggeriti, onClose, onSaved }: DialogProps) {
  const [nome, setNome] = useState("");
  const [data, setData] = useState(dataDefault);
  const [oraInizio, setOraInizio] = useState("09:00");
  const [oraFine, setOraFine] = useState("17:00");
  const [spezzato, setSpezzato] = useState(false);
  const [oraInizio2, setOraInizio2] = useState("19:00");
  const [oraFine2, setOraFine2] = useState("23:00");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [showSugg, setShowSugg] = useState(false);

  useEffect(() => {
    if (open) {
      setNome(turno?.nome ?? "");
      setData(turno?.data_turno ?? dataDefault);
      setOraInizio(turno ? fmtOra(turno.ora_inizio) : "09:00");
      setOraFine(turno ? fmtOra(turno.ora_fine) : "17:00");
      const hasSpezzato = !!(turno?.ora_inizio2 && turno?.ora_fine2);
      setSpezzato(hasSpezzato);
      setOraInizio2(hasSpezzato ? fmtOra(turno!.ora_inizio2) : "19:00");
      setOraFine2(hasSpezzato ? fmtOra(turno!.ora_fine2) : "23:00");
      setNote(turno?.note ?? "");
      setShowSugg(false);
    }
  }, [open, turno, dataDefault]);

  const suggFiltrati = nome.length > 0
    ? nomiSuggeriti.filter((n) => n.toLowerCase().includes(nome.toLowerCase()) && n !== nome)
    : [];

  const ore1 = oraInizio && oraFine ? calcolaSlotOre(oraInizio, oraFine) : 0;
  const ore2 = spezzato && oraInizio2 && oraFine2 ? calcolaSlotOre(oraInizio2, oraFine2) : 0;
  const oreTot = ore1 + ore2;

  async function salva() {
    if (!nome.trim()) { toast.error("Il nome è obbligatorio"); return; }
    if (!oraInizio || !oraFine) { toast.error("Orario obbligatorio"); return; }
    if (spezzato && (!oraInizio2 || !oraFine2)) { toast.error("Inserisci il secondo slot"); return; }
    setSaving(true);
    try {
      // costo_orario/ore_extra restano gestiti da desktop: qui null per non toccarli
      const payload: Record<string, unknown> = {
        nome: nome.trim(),
        data_turno: data,
        ora_inizio: oraInizio,
        ora_fine: oraFine,
        ora_inizio2: spezzato ? oraInizio2 : null,
        ora_fine2: spezzato ? oraFine2 : null,
        note: note || null,
      };
      // Su modifica preserviamo costo/extra esistenti del turno
      if (turno) {
        payload.ore_extra = turno.ore_extra ?? null;
        payload.costo_orario = turno.costo_orario ?? null;
      }
      const url = turno ? `/api/workspace/personale/${turno.id}` : "/api/workspace/personale";
      const res = await fetch(url, {
        method: turno ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error((await res.json()).detail ?? "Errore");
      toast.success(turno ? "Turno aggiornato" : "Turno aggiunto");
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
          <DialogTitle>{turno ? "Modifica turno" : "Nuovo turno"}</DialogTitle>
        </DialogHeader>
        <div className="mt-1 space-y-3">
          <div className="relative">
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Nome dipendente *</label>
            <Input
              value={nome}
              onChange={(e) => { setNome(e.target.value); setShowSugg(true); }}
              onFocus={() => setShowSugg(true)}
              onBlur={() => setTimeout(() => setShowSugg(false), 150)}
              placeholder="es. Mario, Anna…"
              autoFocus
              autoComplete="off"
            />
            {showSugg && suggFiltrati.length > 0 && (
              <div className="absolute z-10 mt-1 w-full rounded-md border border-border bg-popover shadow-md">
                {suggFiltrati.map((n) => (
                  <button
                    key={n}
                    type="button"
                    className="w-full px-3 py-2.5 text-left text-sm active:bg-accent"
                    onMouseDown={() => { setNome(n); setShowSugg(false); }}
                  >
                    {n}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Data *</label>
            <Input type="date" value={data} onChange={(e) => setData(e.target.value)} />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              {spezzato ? "Primo slot *" : "Orario *"}
            </label>
            <div className="grid grid-cols-2 gap-2">
              <Input type="time" value={oraInizio} onChange={(e) => setOraInizio(e.target.value)} />
              <Input type="time" value={oraFine} onChange={(e) => setOraFine(e.target.value)} />
            </div>
          </div>

          <button
            type="button"
            onClick={() => setSpezzato((s) => !s)}
            className={`rounded-md px-2 py-1 text-xs font-medium transition-colors ${
              spezzato ? "bg-primary/10 text-primary" : "text-muted-foreground active:bg-muted"
            }`}
          >
            {spezzato ? "✓ Turno spezzato" : "+ Aggiungi secondo slot"}
          </button>

          {spezzato && (
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Secondo slot *</label>
              <div className="grid grid-cols-2 gap-2">
                <Input type="time" value={oraInizio2} onChange={(e) => setOraInizio2(e.target.value)} />
                <Input type="time" value={oraFine2} onChange={(e) => setOraFine2(e.target.value)} />
              </div>
            </div>
          )}

          {oreTot > 0 && (
            <p className="text-xs text-muted-foreground">Durata: <span className="font-medium text-foreground">{fmtOre(oreTot)}</span></p>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Note</label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="opzionale" />
          </div>

          <div className="flex gap-2 pt-1">
            <button onClick={onClose} disabled={saving} className="flex-1 rounded-lg border border-border py-2.5 text-sm font-medium active:scale-[0.98]">
              Annulla
            </button>
            <button onClick={salva} disabled={saving} className="flex-1 rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground active:scale-[0.98] disabled:opacity-50">
              {saving ? "Salvo…" : "Salva"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Componente principale ──────────────────────────────────────────────────────

export function MobileTurni() {
  const [lunedi, setLunedi] = useState(() => lunediDi(new Date()));
  const [data, setData] = useState<PersonaleResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [giornoSel, setGiornoSel] = useState(() => toISO(new Date()));
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTurno, setEditTurno] = useState<Turno | null>(null);

  const da = toISO(lunedi);
  const a = toISO(addDays(lunedi, 6));

  const load = useCallback(async (daISO: string, aISO: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/workspace/personale?da=${daISO}&a=${aISO}`);
      if (!res.ok) throw new Error();
      setData(await res.json());
    } catch {
      toast.error("Errore caricamento turni");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(da, a); }, [da, a, load]);

  function settPrec() { setLunedi((d) => addDays(d, -7)); }
  function settSucc() { setLunedi((d) => addDays(d, 7)); }

  async function elimina(t: Turno) {
    if (!confirm(`Eliminare il turno di ${t.nome}?`)) return;
    try {
      const res = await fetch(`/api/workspace/personale/${t.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Turno eliminato");
      load(da, a);
    } catch {
      toast.error("Errore eliminazione");
    }
  }

  const giorni = Array.from({ length: 7 }, (_, i) => {
    const d = addDays(lunedi, i);
    return { iso: toISO(d), label: GIORNI[i], num: d.getDate() };
  });

  const turni = data?.turni ?? [];
  const turniGiorno = turni
    .filter((t) => t.data_turno === giornoSel)
    .sort((a, b) => a.ora_inizio.localeCompare(b.ora_inizio));

  const oggiISO = toISO(new Date());
  const turniPerGiorno: Record<string, number> = {};
  for (const t of turni) turniPerGiorno[t.data_turno] = (turniPerGiorno[t.data_turno] ?? 0) + 1;

  const fmtSett = `${lunedi.getDate()} ${["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"][lunedi.getMonth()]} – ${addDays(lunedi, 6).getDate()} ${["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"][addDays(lunedi, 6).getMonth()]}`;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold tracking-tight">Turni</h1>

      {/* Selettore settimana */}
      <div className="flex items-center justify-between rounded-2xl border bg-card px-2 py-2">
        <button onClick={settPrec} className="rounded-full p-2 active:bg-muted">
          <ChevronLeft className="size-5" />
        </button>
        <span className="text-sm font-semibold">{fmtSett}</span>
        <button onClick={settSucc} className="rounded-full p-2 active:bg-muted">
          <ChevronRight className="size-5" />
        </button>
      </div>

      {/* Strip giorni */}
      <div className="grid grid-cols-7 gap-1">
        {giorni.map((g) => {
          const isSel = g.iso === giornoSel;
          const isOggi = g.iso === oggiISO;
          const n = turniPerGiorno[g.iso] ?? 0;
          return (
            <button
              key={g.iso}
              onClick={() => setGiornoSel(g.iso)}
              className={`flex flex-col items-center gap-0.5 rounded-xl py-2 transition-colors
                ${isSel ? "bg-primary text-primary-foreground" : isOggi ? "ring-1 ring-primary" : "active:bg-muted"}`}
            >
              <span className="text-[10px] font-medium opacity-80">{g.label}</span>
              <span className="text-sm font-semibold">{g.num}</span>
              <span className={`size-1.5 rounded-full ${n > 0 ? (isSel ? "bg-primary-foreground" : "bg-primary") : "bg-transparent"}`} />
            </button>
          );
        })}
      </div>

      {/* Turni del giorno */}
      <div className="space-y-2.5">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Caricamento…</p>
        ) : turniGiorno.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Nessun turno per questo giorno.</p>
        ) : (
          turniGiorno.map((t) => (
            <div key={t.id} className="flex items-center gap-3 rounded-xl border bg-card p-3.5">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-bold text-primary">
                {t.nome.slice(0, 2).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{t.nome}</p>
                <p className="text-xs text-muted-foreground">
                  {orarioTurno(t)} · {fmtOre(oreTurno(t))}
                </p>
                {t.note && <p className="truncate text-xs text-muted-foreground/80">{t.note}</p>}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button onClick={() => { setEditTurno(t); setDialogOpen(true); }} className="rounded-md p-1.5 text-muted-foreground active:bg-muted">
                  <Pencil className="size-4" />
                </button>
                <button onClick={() => elimina(t)} className="rounded-md p-1.5 text-muted-foreground active:bg-muted active:text-destructive">
                  <Trash2 className="size-4" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* FAB */}
      <button
        onClick={() => { setEditTurno(null); setDialogOpen(true); }}
        className="fixed right-5 z-40 flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg active:scale-95"
        style={{ bottom: "calc(80px + env(safe-area-inset-bottom))" }}
        aria-label="Nuovo turno"
      >
        <Plus className="size-7" />
      </button>

      <TurnoDialog
        open={dialogOpen}
        turno={editTurno}
        dataDefault={giornoSel}
        nomiSuggeriti={data?.nomi ?? []}
        onClose={() => { setDialogOpen(false); setEditTurno(null); }}
        onSaved={() => load(da, a)}
      />
    </div>
  );
}
