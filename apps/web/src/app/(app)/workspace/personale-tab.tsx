"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Download, CopyPlus, LayoutGrid, List } from "lucide-react";
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
  costo_orario_extra?: number | null;
  note?: string | null;
}

interface CostiNoti {
  std?: number;
  ext?: number;
}

interface PersonaleResponse {
  turni: Turno[];
  monte_ore: Record<string, number>;
  ore_standard_per_persona: Record<string, number>;
  ore_extra_per_persona: Record<string, number>;
  costo_standard_per_persona: Record<string, number>;
  costo_extra_per_persona: Record<string, number>;
  costo_per_persona: Record<string, number>;
  ore_standard_totale: number;
  ore_extra_totale: number;
  costo_standard_totale: number;
  costo_extra_totale: number;
  extra_totale: number;
  costo_totale: number;
  nomi: string[];
  costi_noti: Record<string, CostiNoti>;
}

// ─── Utilità ──────────────────────────────────────────────────────────────────

const GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];

// Palette colori dipendenti — ciclica, usata sia nell'expander che nel calendario
const DIP_PALETTE = [
  { ring: "ring-sky-500/60",     bg: "bg-sky-500/10",     bgChip: "bg-sky-100 dark:bg-sky-900/50",     textChip: "text-sky-800 dark:text-sky-200",     subChip: "text-sky-600 dark:text-sky-300"     },
  { ring: "ring-emerald-500/60", bg: "bg-emerald-500/10", bgChip: "bg-emerald-100 dark:bg-emerald-900/50", textChip: "text-emerald-800 dark:text-emerald-200", subChip: "text-emerald-600 dark:text-emerald-300" },
  { ring: "ring-violet-500/60",  bg: "bg-violet-500/10",  bgChip: "bg-violet-100 dark:bg-violet-900/50",  textChip: "text-violet-800 dark:text-violet-200",  subChip: "text-violet-600 dark:text-violet-300"  },
  { ring: "ring-rose-500/60",    bg: "bg-rose-500/10",    bgChip: "bg-rose-100 dark:bg-rose-900/50",    textChip: "text-rose-800 dark:text-rose-200",    subChip: "text-rose-600 dark:text-rose-300"    },
  { ring: "ring-orange-500/60",  bg: "bg-orange-500/10",  bgChip: "bg-orange-100 dark:bg-orange-900/50",  textChip: "text-orange-800 dark:text-orange-200",  subChip: "text-orange-600 dark:text-orange-300"  },
  { ring: "ring-teal-500/60",    bg: "bg-teal-500/10",    bgChip: "bg-teal-100 dark:bg-teal-900/50",    textChip: "text-teal-800 dark:text-teal-200",    subChip: "text-teal-600 dark:text-teal-300"    },
  { ring: "ring-pink-500/60",    bg: "bg-pink-500/10",    bgChip: "bg-pink-100 dark:bg-pink-900/50",    textChip: "text-pink-800 dark:text-pink-200",    subChip: "text-pink-600 dark:text-pink-300"    },
  { ring: "ring-indigo-500/60",  bg: "bg-indigo-500/10",  bgChip: "bg-indigo-100 dark:bg-indigo-900/50",  textChip: "text-indigo-800 dark:text-indigo-200",  subChip: "text-indigo-600 dark:text-indigo-300"  },
] as const;

function getDipColor(nomi: string[], nome: string) {
  const idx = nomi.indexOf(nome);
  return DIP_PALETTE[idx >= 0 ? idx % DIP_PALETTE.length : 0];
}

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
  giorniDisponibili: string[]; // ISO dates della vista corrente
  nomiSuggeriti: string[];
  costiNoti: Record<string, CostiNoti>;
  onClose: () => void;
  onSaved: () => void;
}

const GIORNI_BREVI = ["Lu", "Ma", "Me", "Gi", "Ve", "Sa", "Do"];

function dowIndex(iso: string): number {
  const d = new Date(iso + "T00:00:00");
  return d.getDay() === 0 ? 6 : d.getDay() - 1;
}

function TurnoDialog({ open, turno, dataDefault, giorniDisponibili, nomiSuggeriti, costiNoti, onClose, onSaved }: TurnoDialogProps) {
  const [nome, setNome] = useState("");
  const [data, setData] = useState(dataDefault);
  const [giorniSelezionati, setGiorniSelezionati] = useState<Set<string>>(new Set([dataDefault]));
  const [oraInizio, setOraInizio] = useState("09:00");
  const [oraFine, setOraFine] = useState("17:00");
  const [spezzato, setSpezzato] = useState(false);
  const [oraInizio2, setOraInizio2] = useState("19:00");
  const [oraFine2, setOraFine2] = useState("23:00");
  const [oreExtra, setOreExtra] = useState("");
  const [costoOrario, setCostoOrario] = useState("");
  const [costoOrarioExtra, setCostoOrarioExtra] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [showSugg, setShowSugg] = useState(false);

  const isNuovo = !turno;

  useEffect(() => {
    if (open) {
      setNome(turno?.nome ?? "");
      setData(turno?.data_turno ?? dataDefault);
      setGiorniSelezionati(new Set([turno?.data_turno ?? dataDefault]));
      setOraInizio(turno ? fmtOra(turno.ora_inizio) : "09:00");
      setOraFine(turno ? fmtOra(turno.ora_fine) : "17:00");
      const hasSpezzato = !!(turno?.ora_inizio2 && turno?.ora_fine2);
      setSpezzato(hasSpezzato);
      setOraInizio2(hasSpezzato ? fmtOra(turno!.ora_inizio2) : "19:00");
      setOraFine2(hasSpezzato ? fmtOra(turno!.ora_fine2) : "23:00");
      setOreExtra(turno?.ore_extra ? String(turno.ore_extra).replace(".", ",") : "");
      setCostoOrario(turno?.costo_orario != null ? String(turno.costo_orario).replace(".", ",") : "");
      setCostoOrarioExtra(turno?.costo_orario_extra != null ? String(turno.costo_orario_extra).replace(".", ",") : "");
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
    const noto = costiNoti[n];
    if (noto) {
      if (!costoOrario && noto.std != null) setCostoOrario(String(noto.std).replace(".", ","));
      if (!costoOrarioExtra && noto.ext != null) setCostoOrarioExtra(String(noto.ext).replace(".", ","));
    }
  }

  function toggleGiorno(iso: string) {
    setGiorniSelezionati(prev => {
      const next = new Set(prev);
      if (next.has(iso)) {
        if (next.size === 1) return prev; // almeno uno sempre selezionato
        next.delete(iso);
      } else {
        next.add(iso);
      }
      return next;
    });
  }

  function toggleTuttaSettimana() {
    if (giorniSelezionati.size === giorniDisponibili.length) {
      // deseleziona tutto tranne il primo
      setGiorniSelezionati(new Set([giorniDisponibili[0]]));
    } else {
      setGiorniSelezionati(new Set(giorniDisponibili));
    }
  }

  const ore1 = oraInizio && oraFine ? calcolaSlotOre(oraInizio, oraFine) : 0;
  const ore2 = spezzato && oraInizio2 && oraFine2 ? calcolaSlotOre(oraInizio2, oraFine2) : 0;
  const oreTot = ore1 + ore2;
  const extraNum = oreExtra ? parseFloat(oreExtra.replace(",", ".")) : 0;
  const stdNum = Math.max(0, oreTot - extraNum);
  const costoNum = costoOrario ? parseFloat(costoOrario.replace(",", ".")) : NaN;
  const costoNumExtra = costoOrarioExtra ? parseFloat(costoOrarioExtra.replace(",", ".")) : NaN;
  const costoEffExtra = !isNaN(costoNumExtra) ? costoNumExtra : costoNum;
  const costoTurno = (!isNaN(costoNum) && oreTot > 0)
    ? (stdNum * costoNum + (extraNum > 0 && !isNaN(costoEffExtra) ? extraNum * costoEffExtra : 0))
    : 0;

  async function salva() {
    if (!nome.trim()) { toast.error("Il nome è obbligatorio"); return; }
    if (!oraInizio || !oraFine) { toast.error("Orario obbligatorio"); return; }
    if (spezzato && (!oraInizio2 || !oraFine2)) { toast.error("Inserisci orario del secondo slot"); return; }
    if (oreExtra && (isNaN(extraNum) || extraNum < 0)) { toast.error("Ore extra non valide"); return; }
    if (extraNum > oreTot + 0.01) { toast.error("Le ore extra non possono superare le ore totali del turno"); return; }
    if (costoOrario && (isNaN(costoNum) || costoNum < 0)) { toast.error("Costo orario non valido"); return; }
    setSaving(true);
    try {
      if (turno) {
        // Modifica: singolo PATCH come prima
        const payload: Record<string, unknown> = {
          nome: nome.trim(),
          data_turno: data,
          ora_inizio: oraInizio,
          ora_fine: oraFine,
          ora_inizio2: spezzato ? oraInizio2 : null,
          ora_fine2: spezzato ? oraFine2 : null,
          ore_extra: oreExtra ? extraNum : null,
          costo_orario: costoOrario ? costoNum : null,
          costo_orario_extra: costoOrarioExtra ? costoNumExtra : null,
          note: note || null,
        };
        const res = await fetch(`/api/workspace/personale/${turno.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error((await res.json()).detail ?? "Errore");
        toast.success("Turno aggiornato");
      } else {
        // Creazione: un POST per ogni giorno selezionato, in parallelo
        const giorni = [...giorniSelezionati].sort();
        const basePayload = {
          nome: nome.trim(),
          ora_inizio: oraInizio,
          ora_fine: oraFine,
          ora_inizio2: spezzato ? oraInizio2 : null,
          ora_fine2: spezzato ? oraFine2 : null,
          ore_extra: oreExtra ? extraNum : null,
          costo_orario: costoOrario ? costoNum : null,
          costo_orario_extra: costoOrarioExtra ? costoNumExtra : null,
          note: note || null,
        };
        const results = await Promise.allSettled(
          giorni.map(g =>
            fetch("/api/workspace/personale", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ ...basePayload, data_turno: g }),
            }).then(r => { if (!r.ok) throw new Error(); })
          )
        );
        const ok = results.filter(r => r.status === "fulfilled").length;
        const fail = results.filter(r => r.status === "rejected").length;
        if (fail === 0) {
          toast.success(ok === 1 ? "Turno aggiunto" : `${ok} turni aggiunti`);
        } else {
          toast.warning(`${ok} turni aggiunti, ${fail} non salvati`);
        }
      }
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
      <DialogContent className="flex max-h-[90dvh] flex-col max-w-md">
        <DialogHeader className="shrink-0">
          <DialogTitle>{turno ? "Modifica turno" : "Nuovo turno"}</DialogTitle>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto">
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

          {/* Selezione giorni: multi per nuovo turno, singola per modifica */}
          {isNuovo ? (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  Giorni *
                  {giorniSelezionati.size > 1 && (
                    <span className="ml-1.5 text-primary font-semibold">{giorniSelezionati.size} selezionati</span>
                  )}
                </label>
                {giorniDisponibili.length > 1 && (
                  <button
                    type="button"
                    onClick={toggleTuttaSettimana}
                    className="text-xs text-primary hover:underline"
                  >
                    {giorniSelezionati.size === giorniDisponibili.length ? "Deseleziona tutti" : "Seleziona tutti"}
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {giorniDisponibili.map(iso => {
                  const sel = giorniSelezionati.has(iso);
                  const dow = dowIndex(iso);
                  const giorno = iso.split("-")[2];
                  return (
                    <button
                      key={iso}
                      type="button"
                      onClick={() => toggleGiorno(iso)}
                      className={`flex flex-col items-center px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-colors min-w-[40px] ${
                        sel
                          ? "bg-primary text-primary-foreground border-primary"
                          : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/40"
                      }`}
                    >
                      <span className="text-[10px] opacity-70">{GIORNI_BREVI[dow]}</span>
                      <span className="font-bold">{giorno}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Data *</label>
              <Input type="date" value={data} onChange={e => setData(e.target.value)} />
            </div>
          )}

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
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Costo std (€/h)</label>
              <Input
                type="text"
                inputMode="decimal"
                value={costoOrario}
                onChange={e => setCostoOrario(e.target.value.replace(/[^0-9,.]/g, ""))}
                placeholder="es. 12,50"
              />
            </div>
          </div>
          {extraNum > 0 && (
            <div className="grid grid-cols-2 gap-2">
              <div />
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  Costo extra (€/h)
                  <span className="ml-1 font-normal opacity-60">se diverso</span>
                </label>
                <Input
                  type="text"
                  inputMode="decimal"
                  value={costoOrarioExtra}
                  onChange={e => setCostoOrarioExtra(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder={costoOrario || "es. 15,00"}
                />
              </div>
            </div>
          )}

          {/* Note */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Note</label>
            <Input value={note} onChange={e => setNote(e.target.value)} placeholder="Opzionale…" />
          </div>

        </div>
        </div>
        <div className="shrink-0 flex justify-end gap-2 pt-3 border-t border-border mt-1">
          <Button variant="outline" onClick={onClose} disabled={saving}>Annulla</Button>
          <Button onClick={salva} disabled={saving}>
            {saving ? "Salvo…" : isNuovo && giorniSelezionati.size > 1 ? `Salva ${giorniSelezionati.size} turni` : "Salva"}
          </Button>
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
  const [expandedDip, setExpandedDip] = useState<string | null>(null);

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
    rows.push(["TOTALE", "", "", "", "", "", num(totaleOre), num(oreExtTotale), "", costoTotale > 0 ? num(costoTotale) : "", ""]);

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
  const costiNoti = risposta?.costi_noti ?? {};

  // Calcola sempre lato frontend dai turni — robusto anche con worker vecchio
  const { oreStdPerPersona, oreExtPerPersona, costoStdPerPersona, costoExtPerPersona, costoPerPersona } = (() => {
    const std: Record<string, number> = {};
    const ext: Record<string, number> = {};
    const cStd: Record<string, number> = {};
    const cExt: Record<string, number> = {};
    const cTot: Record<string, number> = {};
    for (const t of turni) {
      const n = t.nome;
      const ore = calcolaOreTotali(t);
      const extra = t.ore_extra ?? 0;
      const ordinarie = Math.max(0, ore - extra);
      std[n] = (std[n] ?? 0) + ordinarie;
      ext[n] = (ext[n] ?? 0) + extra;
      const coStd = t.costo_orario ?? null;
      const coExt = t.costo_orario_extra ?? coStd;
      if (coStd != null) {
        cStd[n] = (cStd[n] ?? 0) + ordinarie * coStd;
        cExt[n] = (cExt[n] ?? 0) + extra * (coExt ?? coStd);
        cTot[n] = (cTot[n] ?? 0) + ordinarie * coStd + extra * (coExt ?? coStd);
      }
    }
    return { oreStdPerPersona: std, oreExtPerPersona: ext, costoStdPerPersona: cStd, costoExtPerPersona: cExt, costoPerPersona: cTot };
  })();

  const oreStdTotale = Object.values(oreStdPerPersona).reduce((s, v) => s + v, 0);
  const oreExtTotale = Object.values(oreExtPerPersona).reduce((s, v) => s + v, 0);
  const costoStdTotale = Object.values(costoStdPerPersona).reduce((s, v) => s + v, 0);
  const costoExtTotale = Object.values(costoExtPerPersona).reduce((s, v) => s + v, 0);
  const costoTotale = costoStdTotale + costoExtTotale;
  const totaleOre = oreStdTotale + oreExtTotale;

  // Giorni distinti con almeno un turno
  const giorniConTurni = new Set(turni.map(t => t.data_turno)).size;
  const mediaGiornaliera = giorniConTurni > 0 ? totaleOre / giorniConTurni : 0;

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

      {/* ── KPI cards ── */}
      {Object.keys(monteOre).length > 0 && (
        <div className="space-y-3">
          {/* 3 card principali */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* Card 1: Ore ordinarie */}
            <Card className="ring-1 ring-green-500/50 bg-green-50/60 dark:bg-green-950/20">
              <CardContent className="py-5 px-6 space-y-2">
                <div className="flex justify-between">
                  <p className="text-xs font-semibold uppercase tracking-widest text-green-700 dark:text-green-500">Ore ordinarie</p>
                  <p className="text-xs font-semibold uppercase tracking-widest text-green-700 dark:text-green-500">Costo ordinarie</p>
                </div>
                <div className="flex items-end justify-between gap-2">
                  <p className="text-4xl font-black tabular-nums text-green-700 dark:text-green-400 leading-none">{fmtOreDisplay(oreStdTotale)}</p>
                  <p className="text-4xl font-black tabular-nums text-green-600 dark:text-green-500 leading-none text-right">
                    {costoStdTotale > 0 ? fmtEuro(costoStdTotale) : <span className="text-green-600/30">—</span>}
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Card 2: Straordinario */}
            <Card className="ring-1 ring-amber-500/50 bg-amber-50/60 dark:bg-amber-950/20">
              <CardContent className="py-5 px-6 space-y-2">
                <div className="flex justify-between">
                  <p className="text-xs font-semibold uppercase tracking-widest text-amber-700 dark:text-amber-500">Ore straord.</p>
                  <p className="text-xs font-semibold uppercase tracking-widest text-amber-700 dark:text-amber-500">Costo straord.</p>
                </div>
                <div className="flex items-end justify-between gap-2">
                  <p className="text-4xl font-black tabular-nums text-amber-700 dark:text-amber-400 leading-none">{fmtOreDisplay(oreExtTotale)}</p>
                  <p className="text-4xl font-black tabular-nums text-amber-600 dark:text-amber-500 leading-none text-right">
                    {costoExtTotale > 0 ? fmtEuro(costoExtTotale) : <span className="text-amber-600/30">—</span>}
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Card 3: Totale */}
            <Card className="ring-1 ring-sky-500/50 bg-sky-50/60 dark:bg-sky-950/20">
              <CardContent className="py-5 px-6 space-y-2">
                <div className="flex justify-between">
                  <p className="text-xs font-semibold uppercase tracking-widest text-sky-700 dark:text-sky-400">Totale ore</p>
                  <p className="text-xs font-semibold uppercase tracking-widest text-sky-700 dark:text-sky-400">Costo totale</p>
                </div>
                <div className="flex items-end justify-between gap-2">
                  <p className="text-4xl font-black tabular-nums text-sky-700 dark:text-sky-300 leading-none">{fmtOreDisplay(totaleOre)}</p>
                  <p className="text-4xl font-black tabular-nums text-sky-600 dark:text-sky-400 leading-none text-right">
                    {costoTotale > 0
                      ? fmtEuro(costoTotale)
                      : giorniConTurni > 1
                        ? <span className="text-xl font-semibold text-sky-600/60 dark:text-sky-400/60">~{fmtOreDisplay(mediaGiornaliera)}/g</span>
                        : <span className="text-sky-600/30">—</span>
                    }
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Riepilogo per dipendente — accordion */}
          <div className="space-y-1">
            {nomi.map(n => {
              const oreN = monteOre[n] ?? 0;
              const stdN = oreStdPerPersona[n] ?? 0;
              const extN = oreExtPerPersona[n] ?? 0;
              const costoN = costoPerPersona[n] ?? 0;
              const costoStdN = costoStdPerPersona[n] ?? 0;
              const costoExtN = costoExtPerPersona[n] ?? 0;
              const turniN = turni.filter(t => t.nome === n).sort((a, b) => a.data_turno.localeCompare(b.data_turno));
              const isOpen = expandedDip === n;
              const col = getDipColor(nomi, n);
              return (
                <div key={n} className={`rounded-lg border ring-1 ${col.ring} overflow-hidden`}>
                  <button
                    onClick={() => setExpandedDip(isOpen ? null : n)}
                    className={`w-full flex items-center justify-between px-4 py-3 hover:${col.bg} transition-colors`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-semibold text-sm">{n}</span>
                      <span className="text-sm tabular-nums text-muted-foreground">{fmtOreDisplay(oreN)}</span>
                      {extN > 0 && <span className="text-xs text-amber-600 dark:text-amber-400 tabular-nums">+{fmtOreDisplay(extN)} str.</span>}
                      {costoN > 0 && <span className="text-xs text-sky-700 dark:text-sky-400 font-semibold tabular-nums">{fmtEuro(costoN)}</span>}
                    </div>
                    {isOpen ? <ChevronUp className="size-4 text-muted-foreground shrink-0" /> : <ChevronDown className="size-4 text-muted-foreground shrink-0" />}
                  </button>

                  {isOpen && (
                    <div className="border-t border-border px-4 py-3 space-y-3">
                      {/* Riepilogo numerico */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        <div className="rounded-md bg-muted/40 px-3 py-2">
                          <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">Ore ord.</p>
                          <p className="text-lg font-bold tabular-nums">{fmtOreDisplay(stdN)}</p>
                          {costoStdN > 0 && <p className="text-xs text-green-600 dark:text-green-400">{fmtEuro(costoStdN)}</p>}
                        </div>
                        <div className="rounded-md bg-amber-500/8 px-3 py-2">
                          <p className="text-[10px] uppercase tracking-wide text-amber-600 dark:text-amber-400 font-medium">Straord.</p>
                          <p className="text-lg font-bold tabular-nums text-amber-700 dark:text-amber-300">{fmtOreDisplay(extN)}</p>
                          {costoExtN > 0 && <p className="text-xs text-amber-600 dark:text-amber-400">{fmtEuro(costoExtN)}</p>}
                        </div>
                        <div className="rounded-md bg-sky-500/8 px-3 py-2">
                          <p className="text-[10px] uppercase tracking-wide text-sky-600 dark:text-sky-400 font-medium">Totale ore</p>
                          <p className="text-lg font-bold tabular-nums text-sky-700 dark:text-sky-300">{fmtOreDisplay(oreN)}</p>
                        </div>
                        {costoN > 0 && (
                          <div className="rounded-md bg-sky-500/8 px-3 py-2">
                            <p className="text-[10px] uppercase tracking-wide text-sky-600 dark:text-sky-400 font-medium">Costo totale</p>
                            <p className="text-lg font-bold tabular-nums text-sky-700 dark:text-sky-300">{fmtEuro(costoN)}</p>
                          </div>
                        )}
                      </div>

                      {/* Lista turni */}
                      <div className="divide-y divide-border rounded-md border border-border">
                        {turniN.map(t => {
                          const oreT = calcolaOreTotali(t);
                          const costoT = t.costo_orario != null
                            ? (() => {
                                const ext = t.ore_extra ?? 0;
                                const std = Math.max(0, oreT - ext);
                                const coExt = t.costo_orario_extra ?? t.costo_orario;
                                return std * t.costo_orario! + (ext > 0 ? ext * coExt! : 0);
                              })()
                            : 0;
                          return (
                            <div key={t.id} className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-muted/20 group">
                              <span className="text-muted-foreground w-16 shrink-0 tabular-nums">{fmtData(t.data_turno)}</span>
                              <span className="tabular-nums text-muted-foreground">
                                {fmtOra(t.ora_inizio)}–{fmtOra(t.ora_fine)}
                                {t.ora_inizio2 && t.ora_fine2 && <span className="opacity-60 ml-1">· {fmtOra(t.ora_inizio2)}–{fmtOra(t.ora_fine2)}</span>}
                              </span>
                              <span className="tabular-nums font-medium">{fmtOreDisplay(oreT)}</span>
                              {(t.ore_extra ?? 0) > 0 && <span className="text-xs text-amber-600 dark:text-amber-400 tabular-nums">+{fmtOreDisplay(t.ore_extra!)} str.</span>}
                              {costoT > 0 && <span className="text-xs text-sky-700 dark:text-sky-400 tabular-nums">{fmtEuro(costoT)}</span>}
                              {t.note && <span className="text-xs text-muted-foreground italic truncate flex-1">{t.note}</span>}
                              <div className="ml-auto flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <Button size="icon" variant="ghost" className="size-6" onClick={() => { setEditTurno(t); setDialogOpen(true); }}>
                                  <Pencil className="size-3" />
                                </Button>
                                <Button size="icon" variant="ghost" className="size-6 text-muted-foreground hover:text-destructive" onClick={() => elimina(t)}>
                                  <Trash2 className="size-3" />
                                </Button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
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
                    {turniGiorno.map(t => {
                      const chipCol = getDipColor(nomi, t.nome);
                      return (
                        <div
                          key={t.id}
                          className={`rounded ${chipCol.bgChip} px-1 py-0.5 cursor-pointer transition-colors hover:opacity-80`}
                          onClick={() => { setEditTurno(t); setDialogOpen(true); }}
                        >
                          <div className={`text-[10px] font-semibold ${chipCol.textChip} truncate`}>{t.nome}</div>
                          <div className={`text-[9px] ${chipCol.subChip}`}>
                            {fmtOra(t.ora_inizio)}–{fmtOra(t.ora_fine)}
                          </div>
                          {!!t.ore_extra && t.ore_extra > 0 && (
                            <div className="text-[9px] font-medium text-amber-600 dark:text-amber-400">
                              +{fmtOreDisplay(t.ore_extra)} extra
                            </div>
                          )}
                        </div>
                      );
                    })}
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
                    {turniGiorno.map(t => {
                      const rowCol = getDipColor(nomi, t.nome);
                      return (
                      <div key={t.id} className={`flex items-center gap-3 rounded-md border px-3 py-2 hover:${rowCol.bg} group ring-1 ${rowCol.ring}`}>
                        <span className={`font-semibold text-sm min-w-[100px] ${rowCol.textChip}`}>{t.nome}</span>
                        <span className="text-sm text-muted-foreground tabular-nums">
                          {fmtOra(t.ora_inizio)}–{fmtOra(t.ora_fine)}
                          {t.ora_inizio2 && t.ora_fine2 && (
                            <span className="ml-1.5 text-muted-foreground/70">· {fmtOra(t.ora_inizio2)}–{fmtOra(t.ora_fine2)}</span>
                          )}
                        </span>
                        <span className="text-xs text-muted-foreground tabular-nums">{fmtOreDisplay(calcolaOreTotali(t))}</span>
                        {!!t.ore_extra && t.ore_extra > 0 && (
                          <span className="text-[11px] text-amber-600 dark:text-amber-500 tabular-nums">+{fmtOreDisplay(t.ore_extra)} extra</span>
                        )}
                        {t.costo_orario != null && (
                          <span className="text-[11px] text-sky-700 dark:text-sky-400 tabular-nums">{fmtEuro(calcolaOreTotali(t) * t.costo_orario)}</span>
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
                      );
                    })}
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
        giorniDisponibili={periodo === "settimana" ? giorniSettimana : giorniMese}
        nomiSuggeriti={nomi}
        costiNoti={costiNoti}
        onClose={() => { setDialogOpen(false); setEditTurno(null); }}
        onSaved={() => load(da, fine)}
      />
    </div>
  );
}
