"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight, Download } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

// ─── Tipi ────────────────────────────────────────────────────────────────────

interface Turno {
  id: string;
  nome: string;
  data_turno: string;
  ora_inizio: string;
  ora_fine: string;
  ora_inizio2?: string | null;
  ora_fine2?: string | null;
  note?: string | null;
}

interface PersonaleResponse {
  turni: Turno[];
  monte_ore: Record<string, number>;
  nomi: string[];
}

// ─── Utilità ──────────────────────────────────────────────────────────────────

const GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];

function lunediDi(iso: string): Date {
  const d = new Date(iso + "T00:00:00");
  const dow = d.getDay() === 0 ? 6 : d.getDay() - 1;
  d.setDate(d.getDate() - dow);
  return d;
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function toISO(d: Date): string {
  return d.toISOString().split("T")[0];
}

function fmtData(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" });
}

function fmtOra(t: string | null | undefined) {
  if (!t) return "";
  return t.slice(0, 5);
}

function calcolaSlotOre(inizio: string, fine: string): number {
  const [ih, im] = inizio.split(":").map(Number);
  const [fh, fm] = fine.split(":").map(Number);
  let minuti = fh * 60 + fm - (ih * 60 + im);
  if (minuti < 0) minuti += 24 * 60;
  return Math.round(minuti / 60 * 100) / 100;
}

function calcolaOreTotali(t: Turno): number {
  let tot = calcolaSlotOre(t.ora_inizio, t.ora_fine);
  if (t.ora_inizio2 && t.ora_fine2) tot += calcolaSlotOre(t.ora_inizio2, t.ora_fine2);
  return Math.round(tot * 100) / 100;
}

function fmtOreDisplay(ore: number): string {
  const h = Math.floor(ore);
  const m = Math.round((ore - h) * 60);
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

function orarioTurno(t: Turno): string {
  let s = `${fmtOra(t.ora_inizio)}–${fmtOra(t.ora_fine)}`;
  if (t.ora_inizio2 && t.ora_fine2) s += ` · ${fmtOra(t.ora_inizio2)}–${fmtOra(t.ora_fine2)}`;
  return s;
}

// ─── Dialog turno ─────────────────────────────────────────────────────────────

interface TurnoDialogProps {
  open: boolean;
  turno: Turno | null;
  dataDefault: string;
  nomiSuggeriti: string[];
  onClose: () => void;
  onSaved: () => void;
}

function TurnoDialog({ open, turno, dataDefault, nomiSuggeriti, onClose, onSaved }: TurnoDialogProps) {
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
    ? nomiSuggeriti.filter(n => n.toLowerCase().includes(nome.toLowerCase()) && n !== nome)
    : [];

  const ore1 = oraInizio && oraFine ? calcolaSlotOre(oraInizio, oraFine) : 0;
  const ore2 = spezzato && oraInizio2 && oraFine2 ? calcolaSlotOre(oraInizio2, oraFine2) : 0;
  const oreTot = ore1 + ore2;

  async function salva() {
    if (!nome.trim()) { toast.error("Il nome è obbligatorio"); return; }
    if (!oraInizio || !oraFine) { toast.error("Orario obbligatorio"); return; }
    if (spezzato && (!oraInizio2 || !oraFine2)) { toast.error("Inserisci orario del secondo slot"); return; }
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        nome: nome.trim(),
        data_turno: data,
        ora_inizio: oraInizio,
        ora_fine: oraFine,
        ora_inizio2: spezzato ? oraInizio2 : null,
        ora_fine2: spezzato ? oraFine2 : null,
        note: note || null,
      };
      const url = turno ? `/api/workspace/personale/${turno.id}` : "/api/workspace/personale";
      const method = turno ? "PATCH" : "POST";
      const res = await fetch(url, {
        method,
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
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{turno ? "Modifica turno" : "Nuovo turno"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          {/* Nome dipendente con autocomplete */}
          <div className="relative">
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Nome dipendente *</label>
            <Input
              value={nome}
              onChange={e => { setNome(e.target.value); setShowSugg(true); }}
              onFocus={() => setShowSugg(true)}
              onBlur={() => setTimeout(() => setShowSugg(false), 150)}
              placeholder="es. Mario, Anna…"
              autoFocus
              autoComplete="off"
            />
            {showSugg && suggFiltrati.length > 0 && (
              <div className="absolute z-10 w-full mt-1 rounded-md border border-border bg-popover shadow-md">
                {suggFiltrati.map(n => (
                  <button
                    key={n}
                    type="button"
                    className="w-full px-3 py-2 text-sm text-left hover:bg-accent transition-colors"
                    onMouseDown={() => { setNome(n); setShowSugg(false); }}
                  >
                    {n}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Data */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Data *</label>
            <Input type="date" value={data} onChange={e => setData(e.target.value)} />
          </div>

          {/* Slot 1 */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">
              {spezzato ? "Primo slot *" : "Orario *"}
            </label>
            <div className="grid grid-cols-2 gap-2">
              <Input type="time" value={oraInizio} onChange={e => setOraInizio(e.target.value)} />
              <Input type="time" value={oraFine} onChange={e => setOraFine(e.target.value)} />
            </div>
          </div>

          {/* Toggle spezzato */}
          <button
            type="button"
            onClick={() => setSpezzato(s => !s)}
            className={`text-xs font-medium px-2 py-1 rounded-md transition-colors ${
              spezzato
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
          >
            {spezzato ? "✓ Turno spezzato" : "+ Aggiungi secondo slot (spezzato)"}
          </button>

          {/* Slot 2 */}
          {spezzato && (
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Secondo slot *</label>
              <div className="grid grid-cols-2 gap-2">
                <Input type="time" value={oraInizio2} onChange={e => setOraInizio2(e.target.value)} />
                <Input type="time" value={oraFine2} onChange={e => setOraFine2(e.target.value)} />
              </div>
            </div>
          )}

          {/* Durata calcolata */}
          {oreTot > 0 && (
            <p className="text-xs text-muted-foreground">
              Durata: {fmtOreDisplay(oreTot)}
              {spezzato && ore1 > 0 && ore2 > 0 && (
                <span className="ml-1 text-muted-foreground/60">
                  ({fmtOreDisplay(ore1)} + {fmtOreDisplay(ore2)})
                </span>
              )}
            </p>
          )}

          {/* Note */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Note</label>
            <Input value={note} onChange={e => setNote(e.target.value)} placeholder="Opzionale…" />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={onClose} disabled={saving}>Annulla</Button>
            <Button onClick={salva} disabled={saving}>{saving ? "Salvo…" : "Salva"}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Selettore periodo ────────────────────────────────────────────────────────

type Periodo = "settimana" | "mese";

// ─── Tab principale ───────────────────────────────────────────────────────────

export function PersonaleTab() {
  const oggi = toISO(new Date());
  const [periodo, setPeriodo] = useState<Periodo>("settimana");
  const [lunedi, setLunedi] = useState<Date>(() => lunediDi(oggi));
  const [meseBase, setMeseBase] = useState(() => oggi.slice(0, 7));
  const [risposta, setRisposta] = useState<PersonaleResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTurno, setEditTurno] = useState<Turno | null>(null);
  const [dataDefault, setDataDefault] = useState(oggi);

  const [da, fine] = (() => {
    if (periodo === "settimana") {
      return [toISO(lunedi), toISO(addDays(lunedi, 6))];
    } else {
      const [ay, am] = meseBase.split("-").map(Number);
      const ultimoGiorno = new Date(ay, am, 0).getDate();
      return [`${meseBase}-01`, `${meseBase}-${String(ultimoGiorno).padStart(2, "0")}`];
    }
  })();

  const load = useCallback(async (d: string, f: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/workspace/personale?da=${d}&a=${f}`);
      const j: PersonaleResponse = await res.json();
      setRisposta(j);
    } catch {
      toast.error("Errore caricamento turni");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(da, fine); }, [da, fine, load]);

  function navPrev() {
    if (periodo === "settimana") setLunedi(d => addDays(d, -7));
    else {
      const [ay, am] = meseBase.split("-").map(Number);
      const prev = new Date(ay, am - 2, 1);
      setMeseBase(`${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`);
    }
  }
  function navNext() {
    if (periodo === "settimana") setLunedi(d => addDays(d, 7));
    else {
      const [ay, am] = meseBase.split("-").map(Number);
      const next = new Date(ay, am, 1);
      setMeseBase(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`);
    }
  }

  function labelPeriodo() {
    if (periodo === "settimana") return `${fmtData(da)} – ${fmtData(fine)}`;
    const [ay, am] = meseBase.split("-").map(Number);
    return new Date(ay, am - 1, 1).toLocaleDateString("it-IT", { month: "long", year: "numeric" });
  }

  async function elimina(t: Turno) {
    if (!confirm(`Eliminare turno di ${t.nome} (${fmtData(t.data_turno)} ${orarioTurno(t)})?`)) return;
    await fetch(`/api/workspace/personale/${t.id}`, { method: "DELETE" });
    toast.success("Turno eliminato");
    load(da, fine);
  }

  function esportaCSV() {
    if (!risposta || risposta.turni.length === 0) return;
    const headers = ["Nome", "Data", "Inizio 1", "Fine 1", "Inizio 2", "Fine 2", "Ore totali", "Note"];
    const rows = risposta.turni.map(t => [
      t.nome,
      fmtData(t.data_turno),
      fmtOra(t.ora_inizio),
      fmtOra(t.ora_fine),
      fmtOra(t.ora_inizio2),
      fmtOra(t.ora_fine2),
      String(calcolaOreTotali(t)).replace(".", ","),
      t.note ?? "",
    ]);
    const totaleOre = Object.values(risposta.monte_ore).reduce((s, o) => s + o, 0);
    rows.push([]);
    rows.push(["TOTALE", "", "", "", "", "", String(Math.round(totaleOre * 100) / 100).replace(".", ","), ""]);

    const csv = [headers, ...rows]
      .map(r => r.map(c => `"${String(c ?? "").replace(/"/g, '""')}"`).join(";"))
      .join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `turni_${da}_${fine}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("CSV scaricato — aprilo con Excel");
  }

  const turni = risposta?.turni ?? [];
  const monteOre = risposta?.monte_ore ?? {};
  const nomi = risposta?.nomi ?? [];
  const totaleOre = Object.values(monteOre).reduce((s, o) => s + o, 0);

  const perData: Record<string, Turno[]> = {};
  for (const t of turni) {
    if (!perData[t.data_turno]) perData[t.data_turno] = [];
    perData[t.data_turno].push(t);
  }

  const giorniVista = periodo === "settimana"
    ? Array.from({ length: 7 }, (_, i) => toISO(addDays(lunedi, i)))
    : Object.keys(perData).sort();

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border border-border overflow-hidden">
          {(["settimana", "mese"] as Periodo[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriodo(p)}
              className={`px-3 py-1.5 text-sm font-medium transition-colors capitalize ${
                periodo === p ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground"
              }`}
            >
              {p}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1 border border-border rounded-md">
          <button onClick={navPrev} className="p-1.5 hover:bg-muted rounded-l-md">
            <ChevronLeft className="size-4" />
          </button>
          <span className="px-3 text-sm font-medium min-w-[160px] text-center capitalize">{labelPeriodo()}</span>
          <button onClick={navNext} className="p-1.5 hover:bg-muted rounded-r-md">
            <ChevronRight className="size-4" />
          </button>
        </div>

        <Button onClick={() => { setEditTurno(null); setDataDefault(oggi); setDialogOpen(true); }}>
          <Plus className="size-4 mr-1.5" />Aggiungi turno
        </Button>

        {turni.length > 0 && (
          <Button variant="outline" onClick={esportaCSV}>
            <Download className="size-4 mr-1.5" />Esporta CSV
          </Button>
        )}
      </div>

      {/* Monte ore per persona */}
      {Object.keys(monteOre).length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
          {Object.entries(monteOre).sort((a, b) => b[1] - a[1]).map(([n, ore]) => (
            <Card key={n} className="ring-sky-400/60">
              <CardContent className="py-3 px-4">
                <p className="text-xs text-muted-foreground truncate">{n}</p>
                <p className="text-xl font-bold tabular-nums">{fmtOreDisplay(ore)}</p>
              </CardContent>
            </Card>
          ))}
          {Object.keys(monteOre).length > 1 && (
            <Card>
              <CardContent className="py-3 px-4">
                <p className="text-xs text-muted-foreground">Totale</p>
                <p className="text-xl font-bold tabular-nums">{fmtOreDisplay(totaleOre)}</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Griglia */}
      {loading ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Caricamento…</div>
      ) : turni.length === 0 && periodo === "mese" ? (
        <div className="py-12 text-center text-sm text-muted-foreground">
          Nessun turno in questo periodo. Usa &ldquo;Aggiungi turno&rdquo; per iniziare.
        </div>
      ) : periodo === "settimana" ? (
        <div className="grid grid-cols-7 gap-1.5">
          {giorniVista.map((iso, idx) => {
            const isOggi = iso === oggi;
            const turniGiorno = (perData[iso] ?? []).sort((a, b) => a.ora_inizio.localeCompare(b.ora_inizio));
            return (
              <div key={iso} className={`rounded-lg border ${isOggi ? "border-primary/60" : "border-border"} p-1.5 min-h-[120px]`}>
                <div className={`text-center mb-1.5 ${isOggi ? "text-primary font-semibold" : "text-muted-foreground"}`}>
                  <div className="text-[11px] font-medium">{GIORNI[idx]}</div>
                  <div className="text-sm font-bold leading-none">{iso.split("-")[2]}</div>
                </div>
                <div className="space-y-1">
                  {turniGiorno.map(t => (
                    <div
                      key={t.id}
                      className="rounded bg-sky-100 dark:bg-sky-900/40 px-1.5 py-1 cursor-pointer hover:bg-sky-200 dark:hover:bg-sky-900/60 transition-colors"
                      onClick={() => { setEditTurno(t); setDialogOpen(true); }}
                    >
                      <div className="text-[11px] font-semibold text-sky-800 dark:text-sky-200 truncate">{t.nome}</div>
                      <div className="text-[10px] text-sky-600 dark:text-sky-300">
                        {fmtOra(t.ora_inizio)}–{fmtOra(t.ora_fine)}
                      </div>
                      {t.ora_inizio2 && t.ora_fine2 && (
                        <div className="text-[10px] text-sky-500 dark:text-sky-400">
                          {fmtOra(t.ora_inizio2)}–{fmtOra(t.ora_fine2)}
                        </div>
                      )}
                    </div>
                  ))}
                  <button
                    className="w-full text-[10px] text-muted-foreground/50 hover:text-muted-foreground text-center py-0.5"
                    onClick={() => { setEditTurno(null); setDataDefault(iso); setDialogOpen(true); }}
                  >
                    + turno
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="space-y-3">
          {giorniVista.map(iso => {
            const turniGiorno = (perData[iso] ?? []).sort((a, b) => a.nome.localeCompare(b.nome));
            if (turniGiorno.length === 0) return null;
            return (
              <div key={iso}>
                <p className="text-xs font-semibold text-muted-foreground mb-1.5">
                  {new Date(iso + "T00:00:00").toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" })}
                </p>
                <div className="space-y-1">
                  {turniGiorno.map(t => (
                    <div key={t.id} className="flex items-center gap-3 rounded-md border border-border px-3 py-2 hover:bg-muted/40 group">
                      <span className="font-medium text-sm min-w-[100px]">{t.nome}</span>
                      <span className="text-sm text-muted-foreground tabular-nums">
                        {fmtOra(t.ora_inizio)}–{fmtOra(t.ora_fine)}
                        {t.ora_inizio2 && t.ora_fine2 && (
                          <span className="ml-1.5 text-muted-foreground/70">· {fmtOra(t.ora_inizio2)}–{fmtOra(t.ora_fine2)}</span>
                        )}
                      </span>
                      <span className="text-xs text-muted-foreground">{fmtOreDisplay(calcolaOreTotali(t))}</span>
                      {t.note && <span className="text-xs text-muted-foreground italic truncate flex-1">{t.note}</span>}
                      <div className="ml-auto flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button size="icon" variant="ghost" className="size-7" onClick={() => { setEditTurno(t); setDialogOpen(true); }}>
                          <Pencil className="size-3.5" />
                        </Button>
                        <Button size="icon" variant="ghost" className="size-7 text-muted-foreground hover:text-destructive" onClick={() => elimina(t)}>
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <TurnoDialog
        open={dialogOpen}
        turno={editTurno}
        dataDefault={dataDefault}
        nomiSuggeriti={nomi}
        onClose={() => { setDialogOpen(false); setEditTurno(null); }}
        onSaved={() => load(da, fine)}
      />
    </div>
  );
}
