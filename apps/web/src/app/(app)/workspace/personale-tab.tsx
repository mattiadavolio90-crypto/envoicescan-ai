"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight, Download, CopyPlus, LayoutGrid, List } from "lucide-react";
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
  ore_extra?: number | null;
  costo_orario?: number | null;
  note?: string | null;
}

interface PersonaleResponse {
  turni: Turno[];
  monte_ore: Record<string, number>;
  extra_per_persona: Record<string, number>;
  costo_per_persona: Record<string, number>;
  extra_totale: number;
  costo_totale: number;
  nomi: string[];
  costi_noti: Record<string, number>;
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
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const g = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${g}`;
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

function fmtEuro(v: number): string {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);
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
  costiNoti: Record<string, number>;
  onClose: () => void;
  onSaved: () => void;
}

function TurnoDialog({ open, turno, dataDefault, nomiSuggeriti, costiNoti, onClose, onSaved }: TurnoDialogProps) {
  const [nome, setNome] = useState("");
  const [data, setData] = useState(dataDefault);
  const [oraInizio, setOraInizio] = useState("09:00");
  const [oraFine, setOraFine] = useState("17:00");
  const [spezzato, setSpezzato] = useState(false);
  const [oraInizio2, setOraInizio2] = useState("19:00");
  const [oraFine2, setOraFine2] = useState("23:00");
  const [oreExtra, setOreExtra] = useState("");
  const [costoOrario, setCostoOrario] = useState("");
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
      setOreExtra(turno?.ore_extra ? String(turno.ore_extra).replace(".", ",") : "");
      setCostoOrario(turno?.costo_orario != null ? String(turno.costo_orario).replace(".", ",") : "");
      setNote(turno?.note ?? "");
      setShowSugg(false);
    }
  }, [open, turno, dataDefault]);

  const suggFiltrati = nome.length > 0
    ? nomiSuggeriti.filter(n => n.toLowerCase().includes(nome.toLowerCase()) && n !== nome)
    : [];

  function selezionaNome(n: string) {
    setNome(n);
    setShowSugg(false);
    // Prefill costo orario dall'ultimo turno noto della persona (solo se non già impostato)
    if (!costoOrario && costiNoti[n] != null) setCostoOrario(String(costiNoti[n]).replace(".", ","));
  }

  const ore1 = oraInizio && oraFine ? calcolaSlotOre(oraInizio, oraFine) : 0;
  const ore2 = spezzato && oraInizio2 && oraFine2 ? calcolaSlotOre(oraInizio2, oraFine2) : 0;
  const oreTot = ore1 + ore2;
  const extraNum = oreExtra ? parseFloat(oreExtra.replace(",", ".")) : 0;
  const costoNum = costoOrario ? parseFloat(costoOrario.replace(",", ".")) : NaN;
  const costoTurno = !isNaN(costoNum) && oreTot > 0 ? oreTot * costoNum : 0;

  async function salva() {
    if (!nome.trim()) { toast.error("Il nome è obbligatorio"); return; }
    if (!oraInizio || !oraFine) { toast.error("Orario obbligatorio"); return; }
    if (spezzato && (!oraInizio2 || !oraFine2)) { toast.error("Inserisci orario del secondo slot"); return; }
    if (oreExtra && (isNaN(extraNum) || extraNum < 0)) { toast.error("Ore extra non valide"); return; }
    if (extraNum > oreTot + 0.01) { toast.error("Le ore extra non possono superare le ore totali del turno"); return; }
    if (costoOrario && (isNaN(costoNum) || costoNum < 0)) { toast.error("Costo orario non valido"); return; }
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        nome: nome.trim(),
        data_turno: data,
        ora_inizio: oraInizio,
        ora_fine: oraFine,
        ora_inizio2: spezzato ? oraInizio2 : null,
        ora_fine2: spezzato ? oraFine2 : null,
        ore_extra: oreExtra ? extraNum : null,
        costo_orario: costoOrario ? costoNum : null,
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
                    onMouseDown={() => selezionaNome(n)}
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
              {costoTurno > 0 && (
                <span className="ml-1 text-muted-foreground/60">· costo turno {fmtEuro(costoTurno)}</span>
              )}
            </p>
          )}

          {/* Extra + costo orario */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">di cui extra (h)</label>
              <Input
                type="text"
                inputMode="decimal"
                value={oreExtra}
                onChange={e => setOreExtra(e.target.value.replace(/[^0-9,.]/g, ""))}
                placeholder="es. 2"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Costo orario (€/h)</label>
              <Input
                type="text"
                inputMode="decimal"
                value={costoOrario}
                onChange={e => setCostoOrario(e.target.value.replace(/[^0-9,.]/g, ""))}
                placeholder="es. 12,50"
              />
            </div>
          </div>

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
type Vista = "calendario" | "lista";

// ─── Tab principale ───────────────────────────────────────────────────────────

export function PersonaleTab() {
  const oggi = toISO(new Date());
  const [periodo, setPeriodo] = useState<Periodo>("settimana");
  const [vista, setVista] = useState<Vista>("calendario");
  const [lunedi, setLunedi] = useState<Date>(() => lunediDi(oggi));
  const [meseBase, setMeseBase] = useState(() => oggi.slice(0, 7));
  const [risposta, setRisposta] = useState<PersonaleResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTurno, setEditTurno] = useState<Turno | null>(null);
  const [dataDefault, setDataDefault] = useState(oggi);
  const [copiando, setCopiando] = useState(false);

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

  async function copiaSettimana() {
    if (!confirm("Copiare i turni della settimana precedente su questa settimana? I giorni che hanno già turni verranno saltati.")) return;
    setCopiando(true);
    try {
      const res = await fetch("/api/workspace/personale/copia-settimana", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ da, a: fine }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail ?? "Errore");
      if (j.n_copiati === 0) {
        toast.info(j.messaggio ?? "Nessun turno da copiare");
      } else {
        toast.success(`${j.n_copiati} turni copiati${j.n_saltati ? ` · ${j.n_saltati} saltati (giorni già pieni)` : ""}`);
      }
      load(da, fine);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore copia settimana");
    } finally {
      setCopiando(false);
    }
  }

  function esportaCSV() {
    if (!risposta || risposta.turni.length === 0) return;
    const num = (v: number) => String(Math.round(v * 100) / 100).replace(".", ",");
    const headers = ["Nome", "Data", "Inizio 1", "Fine 1", "Inizio 2", "Fine 2", "Ore totali", "Di cui extra", "Costo orario", "Costo turno", "Note"];
    const rows = risposta.turni.map(t => {
      const ore = calcolaOreTotali(t);
      const co = t.costo_orario ?? null;
      return [
        t.nome,
        fmtData(t.data_turno),
        fmtOra(t.ora_inizio),
        fmtOra(t.ora_fine),
        fmtOra(t.ora_inizio2),
        fmtOra(t.ora_fine2),
        num(ore),
        t.ore_extra ? num(t.ore_extra) : "",
        co != null ? num(co) : "",
        co != null ? num(ore * co) : "",
        t.note ?? "",
      ];
    });
    const totaleOre = Object.values(risposta.monte_ore).reduce((s, o) => s + o, 0);
    rows.push([]);
    rows.push(["TOTALE", "", "", "", "", "", num(totaleOre), num(extraTotale), "", costoTotale > 0 ? num(costoTotale) : "", ""]);

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
  const extraPerPersona = risposta?.extra_per_persona ?? {};
  const costoPerPersona = risposta?.costo_per_persona ?? {};
  const nomi = risposta?.nomi ?? [];
  const costiNoti = risposta?.costi_noti ?? {};
  const totaleOre = Object.values(monteOre).reduce((s, o) => s + o, 0);
  const extraTotale = risposta?.extra_totale ?? 0;
  const costoTotale = risposta?.costo_totale ?? 0;

  const perData: Record<string, Turno[]> = {};
  for (const t of turni) {
    if (!perData[t.data_turno]) perData[t.data_turno] = [];
    perData[t.data_turno].push(t);
  }

  const giorniSettimana = Array.from({ length: 7 }, (_, i) => toISO(addDays(lunedi, i)));

  const giorniMese = (() => {
    const [ay, am] = meseBase.split("-").map(Number);
    const ultGiorno = new Date(ay, am, 0).getDate();
    return Array.from({ length: ultGiorno }, (_, i) =>
      `${meseBase}-${String(i + 1).padStart(2, "0")}`
    );
  })();

  const giorniVista = periodo === "settimana" ? giorniSettimana
    : vista === "calendario" ? giorniMese
    : Object.keys(perData).sort();

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Sinistra: periodo + navigazione + vista */}
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

        {/* Toggle vista calendario / lista */}
        <div className="flex rounded-md border border-border overflow-hidden">
          <button
            onClick={() => setVista("calendario")}
            title="Vista calendario"
            className={`px-2.5 py-1.5 transition-colors ${vista === "calendario" ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground"}`}
          >
            <LayoutGrid className="size-4" />
          </button>
          <button
            onClick={() => setVista("lista")}
            title="Vista lista"
            className={`px-2.5 py-1.5 transition-colors ${vista === "lista" ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground"}`}
          >
            <List className="size-4" />
          </button>
        </div>

        {/* Destra: azioni */}
        <div className="ml-auto flex items-center gap-2">
          {periodo === "settimana" && (
            <Button variant="outline" onClick={copiaSettimana} disabled={copiando}>
              <CopyPlus className="size-4 mr-1.5" />{copiando ? "Copio…" : "Copia settimana prec."}
            </Button>
          )}

          {turni.length > 0 && (
            <Button variant="outline" onClick={esportaCSV}>
              <Download className="size-4 mr-1.5" />Esporta CSV
            </Button>
          )}

          <Button onClick={() => { setEditTurno(null); setDataDefault(oggi >= da && oggi <= fine ? oggi : da); setDialogOpen(true); }}>
            <Plus className="size-4 mr-1.5" />Aggiungi turno
          </Button>
        </div>
      </div>

      {/* Monte ore per persona */}
      {Object.keys(monteOre).length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
          {/* Totale ore — sempre prima, verde */}
          <Card className="ring-1 ring-green-500/60 bg-green-950/20">
            <CardContent className="py-3 px-4">
              <p className="text-xs font-medium text-green-500">Totale ore</p>
              <p className="text-xl font-bold tabular-nums text-green-400">{fmtOreDisplay(totaleOre)}</p>
            </CardContent>
          </Card>
          {/* Totale extra — seconda, ambra (mostrata sempre se c'è almeno una persona) */}
          <Card className="ring-1 ring-amber-500/60 bg-amber-950/20">
            <CardContent className="py-3 px-4">
              <p className="text-xs font-medium text-amber-500">Totale extra</p>
              <p className="text-xl font-bold tabular-nums text-amber-400">{fmtOreDisplay(extraTotale)}</p>
            </CardContent>
          </Card>
          {/* Costo lavoro — solo se almeno un costo orario impostato */}
          {costoTotale > 0 && (
            <Card className="ring-1 ring-sky-500/60 bg-sky-950/20">
              <CardContent className="py-3 px-4">
                <p className="text-xs font-medium text-sky-400">Costo lavoro</p>
                <p className="text-xl font-bold tabular-nums text-sky-300">{fmtEuro(costoTotale)}</p>
              </CardContent>
            </Card>
          )}
          {Object.entries(monteOre).sort((a, b) => b[1] - a[1]).map(([n, ore]) => (
            <Card key={n} className="ring-sky-400/60">
              <CardContent className="py-3 px-4">
                <p className="text-xs text-muted-foreground truncate">{n}</p>
                <p className="text-xl font-bold tabular-nums">{fmtOreDisplay(ore)}</p>
                <div className="mt-0.5 flex flex-wrap gap-x-2 text-[11px] leading-tight text-muted-foreground">
                  {extraPerPersona[n] > 0 && <span className="text-amber-500">di cui {fmtOreDisplay(extraPerPersona[n])} extra</span>}
                  {costoPerPersona[n] > 0 && <span className="text-sky-400">{fmtEuro(costoPerPersona[n])}</span>}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Vista */}
      {loading ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Caricamento…</div>
      ) : vista === "calendario" ? (
        // ── Vista calendario (settimana: 7 col fisse; mese: griglia con offset) ──
        <>
          {/* Intestazioni giorni */}
          <div className="grid grid-cols-7 gap-1.5 mb-1">
            {GIORNI.map(g => (
              <div key={g} className="text-center text-[11px] font-medium text-muted-foreground">{g}</div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1.5">
            {periodo === "mese" && (() => {
              const primoGiorno = new Date(giorniMese[0] + "T00:00:00");
              const dow = primoGiorno.getDay() === 0 ? 6 : primoGiorno.getDay() - 1;
              return Array.from({ length: dow }, (_, i) => <div key={`pad-${i}`} />);
            })()}
            {giorniVista.map((iso) => {
              const isOggi = iso === oggi;
              const turniGiorno = (perData[iso] ?? []).sort((a, b) => a.ora_inizio.localeCompare(b.ora_inizio));
              return (
                <div key={iso} className={`rounded-lg border ${isOggi ? "border-primary/60" : "border-border"} p-1.5 min-h-[80px]`}>
                  <div className={`text-center mb-1 ${isOggi ? "text-primary font-semibold" : "text-muted-foreground"}`}>
                    <div className="text-sm font-bold leading-none">{iso.split("-")[2]}</div>
                  </div>
                  <div className="space-y-0.5">
                    {turniGiorno.map(t => (
                      <div
                        key={t.id}
                        className="rounded bg-sky-100 dark:bg-sky-900/40 px-1 py-0.5 cursor-pointer hover:bg-sky-200 dark:hover:bg-sky-900/60 transition-colors"
                        onClick={() => { setEditTurno(t); setDialogOpen(true); }}
                      >
                        <div className="text-[10px] font-semibold text-sky-800 dark:text-sky-200 truncate">{t.nome}</div>
                        <div className="text-[9px] text-sky-600 dark:text-sky-300">
                          {fmtOra(t.ora_inizio)}–{fmtOra(t.ora_fine)}
                        </div>
                        {!!t.ore_extra && t.ore_extra > 0 && (
                          <div className="text-[9px] font-medium text-amber-600 dark:text-amber-400">
                            +{fmtOreDisplay(t.ore_extra)} extra
                          </div>
                        )}
                      </div>
                    ))}
                    <button
                      className="w-full text-[9px] text-muted-foreground/40 hover:text-muted-foreground text-center py-0.5"
                      onClick={() => { setEditTurno(null); setDataDefault(iso); setDialogOpen(true); }}
                    >
                      +
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        // ── Vista lista ────────────────────────────────────────────────────────
        turni.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            Nessun turno in questo periodo. Usa &ldquo;Aggiungi turno&rdquo; per iniziare.
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
                        <span className="text-xs text-muted-foreground tabular-nums">{fmtOreDisplay(calcolaOreTotali(t))}</span>
                        {!!t.ore_extra && t.ore_extra > 0 && (
                          <span className="text-[11px] text-amber-500 tabular-nums">+{fmtOreDisplay(t.ore_extra)} extra</span>
                        )}
                        {t.costo_orario != null && (
                          <span className="text-[11px] text-sky-400 tabular-nums">{fmtEuro(calcolaOreTotali(t) * t.costo_orario)}</span>
                        )}
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
        )
      )}

      <TurnoDialog
        open={dialogOpen}
        turno={editTurno}
        dataDefault={dataDefault}
        nomiSuggeriti={nomi}
        costiNoti={costiNoti}
        onClose={() => { setDialogOpen(false); setEditTurno(null); }}
        onSaved={() => load(da, fine)}
      />
    </div>
  );
}
