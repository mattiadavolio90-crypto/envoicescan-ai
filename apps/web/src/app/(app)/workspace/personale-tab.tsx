"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Download, CopyPlus, CalendarOff } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { InfoPopover } from "@/components/ui/info-popover";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { VistaMensileGrid } from "./personale-vista-mensile";

// ─── Tipi ────────────────────────────────────────────────────────────────────

export interface Turno {
  id: string;
  dipendente_id: string;
  data_turno: string;
  ora_inizio: string;
  ora_fine: string;
  ora_inizio2?: string | null;
  ora_fine2?: string | null;
  ore_extra?: number | null;
  costo_orario?: number | null;
  costo_orario_extra?: number | null;
  note?: string | null;
  // Righe mensili (inserimento aggregato da busta paga)
  mensile?: boolean | null;
  ore_dichiarate?: number | null;
  lordo_mensile?: number | null;
  importo_extra?: number | null;
  // Stato-giorno esplicito (turno = default lavorato, altrimenti riposo/ferie/malattia)
  tipo_giorno?: TipoGiorno;
  importo_a_carico?: number | null;
}

export type TipoGiorno = "turno" | "riposo" | "ferie" | "malattia";

export const TIPO_GIORNO_LABEL: Record<TipoGiorno, string> = {
  turno: "Turno",
  riposo: "Riposo",
  ferie: "Ferie",
  malattia: "Malattia",
};

export const TIPO_GIORNO_BADGE: Record<Exclude<TipoGiorno, "turno">, string> = {
  riposo: "bg-slate-500/10 text-slate-600 dark:text-slate-400",
  ferie: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  malattia: "bg-red-500/10 text-red-600 dark:text-red-400",
};

export interface Dipendente {
  id: string;
  nome: string;
  costo_orario_default?: number | null;
  attivo?: boolean;
}

export interface CostiNoti {
  std?: number;
  ext?: number;
}

export interface PersonaleResponse {
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
  dipendenti: Dipendente[];
}

// ─── Utilità ──────────────────────────────────────────────────────────────────

// Palette colori dipendenti — ciclica, usata nell'accordion per dipendente.
const DIP_PALETTE = [
  { ring: "ring-sky-500/60",     bg: "bg-sky-500/10"     },
  { ring: "ring-emerald-500/60", bg: "bg-emerald-500/10" },
  { ring: "ring-violet-500/60",  bg: "bg-violet-500/10"  },
  { ring: "ring-rose-500/60",    bg: "bg-rose-500/10"    },
  { ring: "ring-orange-500/60",  bg: "bg-orange-500/10"  },
  { ring: "ring-teal-500/60",    bg: "bg-teal-500/10"    },
  { ring: "ring-pink-500/60",    bg: "bg-pink-500/10"    },
  { ring: "ring-indigo-500/60",  bg: "bg-indigo-500/10"  },
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

export function toISO(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const g = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${g}`;
}

function fmtData(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" });
}

export function fmtOra(t: string | null | undefined) {
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

export function calcolaOreTotali(t: Turno): number {
  // Righe mensili: ore dichiarate da busta paga (gia' ord+extra).
  if (t.mensile) return Math.round((t.ore_dichiarate ?? 0) * 100) / 100;
  // Giornaliero: ore dagli orari (ordinario) + ore extra aggiuntive.
  let tot = calcolaSlotOre(t.ora_inizio, t.ora_fine);
  if (t.ora_inizio2 && t.ora_fine2) tot += calcolaSlotOre(t.ora_inizio2, t.ora_fine2);
  tot += t.ore_extra ?? 0;
  return Math.round(tot * 100) / 100;
}

// Costo di un singolo turno giornaliero: ordinario × costo_orario + extra × costo extra.
function calcolaCostoTurno(t: Turno): number {
  if (t.costo_orario == null) return 0;
  const oreT = calcolaOreTotali(t);
  const ext = t.ore_extra ?? 0;
  const std = Math.max(0, oreT - ext);
  const coExt = t.costo_orario_extra ?? t.costo_orario;
  return std * t.costo_orario + (ext > 0 ? ext * coExt : 0);
}

export function fmtOreDisplay(ore: number): string {
  const h = Math.floor(ore);
  const m = Math.round((ore - h) * 60);
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

export function fmtEuro(v: number): string {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);
}

export function orarioTurno(t: Turno): string {
  let s = `${fmtOra(t.ora_inizio)}–${fmtOra(t.ora_fine)}`;
  if (t.ora_inizio2 && t.ora_fine2) s += ` · ${fmtOra(t.ora_inizio2)}–${fmtOra(t.ora_fine2)}`;
  return s;
}

// ─── Dialog turno ─────────────────────────────────────────────────────────────

interface TurnoDialogProps {
  open: boolean;
  turno: Turno | null;
  dataDefault: string;
  dipendenteIdDefault?: string;
  giorniDisponibili: string[]; // ISO dates della vista corrente
  dipendenti: Dipendente[];
  costiNoti: Record<string, CostiNoti>;
  onClose: () => void;
  onSaved: () => void;
  onDipendenteCreato: () => void;
}

const GIORNI_BREVI = ["Lu", "Ma", "Me", "Gi", "Ve", "Sa", "Do"];

function dowIndex(iso: string): number {
  const d = new Date(iso + "T00:00:00");
  return d.getDay() === 0 ? 6 : d.getDay() - 1;
}

/** Selettore dipendente: scelta da anagrafica + creazione inline.
 *  Da Fase 0 il turno è legato a dipendente_id, non più a un nome libero. */
function SelettoreDipendente({
  dipendenti, valore, onChange, onCreato, autoFocus,
}: {
  dipendenti: Dipendente[];
  valore: string;
  onChange: (id: string) => void;
  onCreato: () => void;
  autoFocus?: boolean;
}) {
  const [nuovoNome, setNuovoNome] = useState("");
  const [creando, setCreando] = useState(false);
  const [modoNuovo, setModoNuovo] = useState(false);

  async function creaDipendente() {
    const nome = nuovoNome.trim();
    if (!nome) { toast.error("Il nome è obbligatorio"); return; }
    setCreando(true);
    try {
      const res = await fetch("/api/workspace/dipendenti", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail ?? j.error ?? "Errore");
      toast.success(`${nome} aggiunto`);
      setNuovoNome("");
      setModoNuovo(false);
      onCreato();
      if (j.id) onChange(j.id);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore creazione dipendente");
    } finally {
      setCreando(false);
    }
  }

  if (modoNuovo) {
    return (
      <div>
        <label className="text-xs font-medium text-muted-foreground mb-1 block">Nuovo dipendente *</label>
        <div className="flex gap-2">
          <Input
            value={nuovoNome}
            onChange={e => setNuovoNome(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); creaDipendente(); } }}
            placeholder="es. Mario Rossi"
            autoFocus
            autoComplete="off"
          />
          <Button type="button" onClick={creaDipendente} disabled={creando}>
            {creando ? "…" : "Crea"}
          </Button>
        </div>
        <button
          type="button"
          onClick={() => { setModoNuovo(false); setNuovoNome(""); }}
          className="text-xs text-muted-foreground hover:text-foreground mt-1.5"
        >
          ← Scegli da elenco
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-medium text-muted-foreground">Dipendente *</label>
        <button
          type="button"
          onClick={() => setModoNuovo(true)}
          className="text-xs text-primary hover:underline"
        >
          + Nuovo dipendente
        </button>
      </div>
      <select
        value={valore}
        onChange={e => onChange(e.target.value)}
        autoFocus={autoFocus}
        className="w-full h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        <option value="">Seleziona…</option>
        {dipendenti.map(d => (
          <option key={d.id} value={d.id}>{d.nome}</option>
        ))}
      </select>
    </div>
  );
}

export function TurnoDialog({ open, turno, dataDefault, dipendenteIdDefault, giorniDisponibili, dipendenti, costiNoti, onClose, onSaved, onDipendenteCreato }: TurnoDialogProps) {
  const [dipendenteId, setDipendenteId] = useState("");
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

  const isNuovo = !turno;

  useEffect(() => {
    if (open) {
      setDipendenteId(turno?.dipendente_id ?? dipendenteIdDefault ?? "");
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
    }
  }, [open, turno, dataDefault, dipendenteIdDefault]);

  // Prefill costi dall'ultimo turno noto del dipendente scelto (solo su nuovo
  // turno: in modifica i costi già salvati sulla riga non vanno sovrascritti).
  function selezionaDipendente(id: string) {
    setDipendenteId(id);
    if (turno) return;
    const nome = dipendenti.find(d => d.id === id)?.nome;
    const noto = nome ? costiNoti[nome] : undefined;
    if (noto) {
      if (noto.std != null) setCostoOrario(String(noto.std).replace(".", ","));
      if (noto.ext != null) setCostoOrarioExtra(String(noto.ext).replace(".", ","));
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

  // Ore extra AGGIUNTIVE all'orario: ordinario = orari, totale = orari + extra.
  const ore1 = oraInizio && oraFine ? calcolaSlotOre(oraInizio, oraFine) : 0;
  const ore2 = spezzato && oraInizio2 && oraFine2 ? calcolaSlotOre(oraInizio2, oraFine2) : 0;
  const stdNum = ore1 + ore2;
  const extraNum = oreExtra ? parseFloat(oreExtra.replace(",", ".")) : 0;
  const oreTot = Math.round((stdNum + extraNum) * 100) / 100;
  const costoNum = costoOrario ? parseFloat(costoOrario.replace(",", ".")) : NaN;
  const costoNumExtra = costoOrarioExtra ? parseFloat(costoOrarioExtra.replace(",", ".")) : NaN;
  const costoEffExtra = !isNaN(costoNumExtra) ? costoNumExtra : costoNum;
  const costoTurno = (!isNaN(costoNum) && oreTot > 0)
    ? (stdNum * costoNum + (extraNum > 0 && !isNaN(costoEffExtra) ? extraNum * costoEffExtra : 0))
    : 0;

  async function salva() {
    if (!dipendenteId) { toast.error("Seleziona un dipendente"); return; }
    if (!oraInizio || !oraFine) { toast.error("Orario obbligatorio"); return; }
    if (spezzato && (!oraInizio2 || !oraFine2)) { toast.error("Inserisci orario del secondo slot"); return; }
    if (oreExtra && (isNaN(extraNum) || extraNum < 0)) { toast.error("Ore extra non valide"); return; }
    if (costoOrario && (isNaN(costoNum) || costoNum < 0)) { toast.error("Costo orario non valido"); return; }
    setSaving(true);
    try {
      if (turno) {
        // Modifica: singolo PATCH come prima
        const payload: Record<string, unknown> = {
          dipendente_id: dipendenteId,
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
          dipendente_id: dipendenteId,
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
          <SelettoreDipendente
            dipendenti={dipendenti}
            valore={dipendenteId}
            onChange={selezionaDipendente}
            onCreato={onDipendenteCreato}
            autoFocus
          />

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
              Totale: {fmtOreDisplay(oreTot)}
              {extraNum > 0 && stdNum > 0 && (
                <span className="ml-1 text-muted-foreground/60">
                  ({fmtOreDisplay(stdNum)} orario + {fmtOreDisplay(extraNum)} extra)
                </span>
              )}
              {!extraNum && spezzato && ore1 > 0 && ore2 > 0 && (
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
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Ore extra (in più)</label>
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

// ─── Dialog stato-giorno (riposo/ferie/malattia) ──────────────────────────────

interface StatoGiornoDialogProps {
  open: boolean;
  turno: Turno | null; // riga di stato in modifica, o null per nuovo
  dipendenti: Dipendente[];
  dipendenteIdDefault: string;
  dataDefault: string;
  onClose: () => void;
  onSaved: () => void;
}

const TIPI_STATO: TipoGiorno[] = ["turno", "riposo", "ferie", "malattia"];

export function StatoGiornoDialog({ open, turno, dipendenti, dipendenteIdDefault, dataDefault, onClose, onSaved }: StatoGiornoDialogProps) {
  const isModifica = !!turno;
  const [modo, setModo] = useState<"giorno" | "intervallo">("giorno");
  const [dipendenteId, setDipendenteId] = useState("");
  const [data, setData] = useState(dataDefault);
  const [dataA, setDataA] = useState(dataDefault);
  const [tipoGiorno, setTipoGiorno] = useState<TipoGiorno>("riposo");
  const [importoACarico, setImportoACarico] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setModo("giorno");
      setDipendenteId(turno?.dipendente_id ?? dipendenteIdDefault);
      setData(turno?.data_turno ?? dataDefault);
      setDataA(turno?.data_turno ?? dataDefault);
      setTipoGiorno((turno?.tipo_giorno as TipoGiorno) ?? "riposo");
      setImportoACarico(turno?.importo_a_carico ? String(turno.importo_a_carico).replace(".", ",") : "");
    }
  }, [open, turno, dipendenteIdDefault, dataDefault]);

  const consenteImporto = tipoGiorno === "ferie" || tipoGiorno === "malattia";
  const importoNum = importoACarico ? parseFloat(importoACarico.replace(",", ".")) : NaN;

  async function salva() {
    if (!dipendenteId) { toast.error("Seleziona un dipendente"); return; }
    if (modo === "intervallo" && dataA < data) { toast.error("Data fine precedente alla data inizio"); return; }
    if (importoACarico && (isNaN(importoNum) || importoNum < 0)) { toast.error("Importo non valido"); return; }
    setSaving(true);
    try {
      const importo = consenteImporto && importoACarico ? importoNum : null;
      if (isModifica) {
        // Riga esistente: PATCH diretto sull'id, niente creazione/skip.
        const res = await fetch(`/api/workspace/personale/${turno!.id}/stato-giorno`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tipo_giorno: tipoGiorno, importo_a_carico: importo }),
        });
        const j = await res.json();
        if (!res.ok) throw new Error(j.detail ?? "Errore");
        toast.success(`Giorno aggiornato su ${TIPO_GIORNO_LABEL[tipoGiorno].toLowerCase()}`);
      } else if (modo === "giorno") {
        // Un giorno singolo: serve l'id della riga esistente (creata come turno di default),
        // quindi passa dall'intervallo di un solo giorno — stessa creazione/skip del backend.
        const res = await fetch("/api/workspace/personale/stato-giorno-intervallo", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            dipendente_id: dipendenteId,
            data_da: data,
            data_a: data,
            tipo_giorno: tipoGiorno,
            importo_a_carico: importo,
          }),
        });
        const j = await res.json();
        if (!res.ok) throw new Error(j.detail ?? "Errore");
        if (j.n_saltati_turno_esistente?.length) {
          toast.warning("Quel giorno ha già un turno lavorato: usa la modifica turno per cambiarlo");
        } else {
          toast.success(`Giorno impostato su ${TIPO_GIORNO_LABEL[tipoGiorno].toLowerCase()}`);
        }
      } else {
        const res = await fetch("/api/workspace/personale/stato-giorno-intervallo", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            dipendente_id: dipendenteId,
            data_da: data,
            data_a: dataA,
            tipo_giorno: tipoGiorno,
            importo_a_carico: importo,
          }),
        });
        const j = await res.json();
        if (!res.ok) throw new Error(j.detail ?? "Errore");
        const nSaltati = j.n_saltati_turno_esistente?.length ?? 0;
        toast.success(
          `${j.n_creati + j.n_aggiornati} giorni impostati su ${TIPO_GIORNO_LABEL[tipoGiorno].toLowerCase()}` +
          (nSaltati ? ` · ${nSaltati} saltati (turno già lavorato)` : "")
        );
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
          <DialogTitle>{isModifica ? "Modifica stato giorno" : "Imposta stato giorno"}</DialogTitle>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="space-y-3 mt-2">
            {!isModifica && (
              <SelettoreDipendente
                dipendenti={dipendenti}
                valore={dipendenteId}
                onChange={setDipendenteId}
                onCreato={() => {}}
                autoFocus
              />
            )}

            {isModifica ? (
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Data</label>
                <Input type="date" value={data} disabled />
              </div>
            ) : (
              <>
                <div className="flex rounded-md border border-border overflow-hidden w-fit">
                  <button
                    type="button"
                    onClick={() => setModo("giorno")}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${modo === "giorno" ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground"}`}
                  >
                    Giorno singolo
                  </button>
                  <button
                    type="button"
                    onClick={() => setModo("intervallo")}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${modo === "intervallo" ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground"}`}
                  >
                    Intervallo di date
                  </button>
                </div>

                {modo === "giorno" ? (
                  <div>
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">Data *</label>
                    <Input type="date" value={data} onChange={e => setData(e.target.value)} />
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground mb-1 block">Dal *</label>
                      <Input type="date" value={data} onChange={e => setData(e.target.value)} />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground mb-1 block">Al *</label>
                      <Input type="date" value={dataA} onChange={e => setDataA(e.target.value)} />
                    </div>
                  </div>
                )}
              </>
            )}

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Stato *</label>
              <div className="flex flex-wrap gap-1.5">
                {TIPI_STATO.map(t => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTipoGiorno(t)}
                    className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
                      tipoGiorno === t
                        ? "bg-primary text-primary-foreground border-primary"
                        : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/40"
                    }`}
                  >
                    {TIPO_GIORNO_LABEL[t]}
                  </button>
                ))}
              </div>
            </div>

            {consenteImporto && (
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  Importo a carico (€) <span className="font-normal opacity-60">opzionale</span>
                </label>
                <Input
                  type="text"
                  inputMode="decimal"
                  value={importoACarico}
                  onChange={e => setImportoACarico(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder="es. 50"
                />
              </div>
            )}
          </div>
        </div>
        <div className="shrink-0 flex justify-end gap-2 pt-3 border-t border-border mt-1">
          <Button variant="outline" onClick={onClose} disabled={saving}>Annulla</Button>
          <Button onClick={salva} disabled={saving}>{saving ? "Salvo…" : "Salva"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Dialog mensile (inserimento da busta paga) ───────────────────────────────

interface MensileDialogProps {
  open: boolean;
  turno: Turno | null;       // riga mensile in modifica, o null per nuovo
  mese: string;              // YYYY-MM
  dipendenti: Dipendente[];
  nomePerId: Record<string, string>;
  onClose: () => void;
  onSaved: () => void;
  onDipendenteCreato: () => void;
}

export function fmtMese(mese: string): string {
  const [ay, am] = mese.split("-").map(Number);
  return new Date(ay, am - 1, 1).toLocaleDateString("it-IT", { month: "long", year: "numeric" });
}

export function MensileDialog({ open, turno, mese, dipendenti, nomePerId, onClose, onSaved, onDipendenteCreato }: MensileDialogProps) {
  const [dipendenteId, setDipendenteId] = useState("");
  // Input separati: ordinarie + extra (il totale è la somma). Lo storage resta
  // ore_totali / ore_extra (di cui), così l'API e il DB non cambiano.
  const [oreOrd, setOreOrd] = useState("");
  const [oreExtra, setOreExtra] = useState("");
  const [importoOrd, setImportoOrd] = useState("");
  const [importoExtra, setImportoExtra] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const isNuovo = !turno;
  const numOr0 = (s: string) => (s ? parseFloat(s.replace(",", ".")) : 0);
  const toInput = (v: number) => String(v).replace(".", ",");

  useEffect(() => {
    if (open) {
      setDipendenteId(turno?.dipendente_id ?? "");
      // Ricostruisce ordinarie = totale − extra dai valori salvati.
      const tot = turno?.ore_dichiarate ?? 0;
      const ext = turno?.ore_extra ?? 0;
      setOreOrd(turno ? toInput(Math.max(0, Math.round((tot - ext) * 100) / 100)) : "");
      setOreExtra(turno?.ore_extra ? toInput(turno.ore_extra) : "");
      const lordo = turno?.lordo_mensile ?? 0;
      const impExt = turno?.importo_extra ?? 0;
      setImportoOrd(turno ? toInput(Math.max(0, Math.round((lordo - impExt) * 100) / 100)) : "");
      setImportoExtra(turno?.importo_extra ? toInput(turno.importo_extra) : "");
      setNote(turno?.note ?? "");
    }
  }, [open, turno]);

  const oreOrdN = numOr0(oreOrd);
  const oreExtN = numOr0(oreExtra);
  const oreTot = Math.round((oreOrdN + oreExtN) * 100) / 100;
  const impOrdN = numOr0(importoOrd);
  const impExtN = numOr0(importoExtra);
  const lordoTot = Math.round((impOrdN + impExtN) * 100) / 100;

  async function salva() {
    if (isNuovo && !dipendenteId) { toast.error("Seleziona un dipendente"); return; }
    if (oreOrdN < 0 || oreExtN < 0) { toast.error("Le ore non possono essere negative"); return; }
    if (impOrdN < 0 || impExtN < 0) { toast.error("Gli importi non possono essere negativi"); return; }
    if (oreTot <= 0 && lordoTot <= 0) { toast.error("Inserisci almeno le ore o il lordo del mese"); return; }
    setSaving(true);
    try {
      const payload = {
        ore_totali: oreTot,
        lordo: lordoTot,
        ore_extra: oreExtN > 0 ? oreExtN : null,
        importo_extra: impExtN > 0 ? impExtN : null,
        note: note || null,
      };
      if (turno) {
        const res = await fetch(`/api/workspace/personale/mensile/${turno.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error((await res.json()).detail ?? "Errore");
        toast.success("Mese aggiornato");
      } else {
        const res = await fetch("/api/workspace/personale/mensile", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ dipendente_id: dipendenteId, mese, ...payload }),
        });
        if (!res.ok) throw new Error((await res.json()).detail ?? "Errore");
        toast.success("Mese inserito");
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
          <DialogTitle>
            {turno
              ? `Modifica ${nomePerId[turno.dipendente_id] ?? ""} · ${fmtMese(mese)}`
              : `Inserisci mese · ${fmtMese(mese)}`}
          </DialogTitle>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="space-y-3 mt-2">
            {isNuovo && (
              <SelettoreDipendente
                dipendenti={dipendenti}
                valore={dipendenteId}
                onChange={setDipendenteId}
                onCreato={onDipendenteCreato}
                autoFocus
              />
            )}

            {/* Ore: ordinarie + extra → totale */}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Ore del mese *</label>
              <div className="grid grid-cols-2 gap-2">
                <Input
                  type="text"
                  inputMode="decimal"
                  value={oreOrd}
                  onChange={e => setOreOrd(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder="ordinarie · es. 148"
                />
                <Input
                  type="text"
                  inputMode="decimal"
                  value={oreExtra}
                  onChange={e => setOreExtra(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder="extra · es. 20"
                />
              </div>
              {oreTot > 0 && (
                <p className="text-xs text-muted-foreground mt-1">Totale ore: <span className="font-semibold tabular-nums">{fmtOreDisplay(oreTot)}</span></p>
              )}
            </div>

            {/* Lordo: ordinario + extra → totale */}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Lordo del mese (€) *</label>
              <div className="grid grid-cols-2 gap-2">
                <Input
                  type="text"
                  inputMode="decimal"
                  value={importoOrd}
                  onChange={e => setImportoOrd(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder="ordinario · es. 1700"
                />
                <Input
                  type="text"
                  inputMode="decimal"
                  value={importoExtra}
                  onChange={e => setImportoExtra(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder="extra · es. 150"
                />
              </div>
              {lordoTot > 0 && (
                <p className="text-xs text-muted-foreground mt-1">Lordo totale: <span className="font-semibold tabular-nums">{fmtEuro(lordoTot)}</span></p>
              )}
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Note</label>
              <Input value={note} onChange={e => setNote(e.target.value)} placeholder="Opzionale…" />
            </div>
          </div>
        </div>
        <div className="shrink-0 flex justify-end gap-2 pt-3 border-t border-border mt-1">
          <Button variant="outline" onClick={onClose} disabled={saving}>Annulla</Button>
          <Button onClick={salva} disabled={saving}>{saving ? "Salvo…" : "Salva"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Selettore periodo ────────────────────────────────────────────────────────

// Modalità è l'unico interruttore temporale: giornaliero = settimana navigabile
// (turno per turno), mensile = totali aggregati del mese. Niente più toggle
// settimana/mese separato (era ridondante con la modalità).
type Modalita = "giornaliero" | "mensile";

// Vista è ortogonale a Modalita e si applica solo dentro "giornaliero":
// settimana = griglia attuale turno-per-turno navigabile, mese = griglia
// dipendenti×giorni dell'intero mese (Fase 4a, sola desktop).
export type Vista = "settimana" | "mese";

// ─── Tab principale ───────────────────────────────────────────────────────────

export function PersonaleTab() {
  const oggi = toISO(new Date());
  const [modalita, setModalita] = useState<Modalita>("giornaliero");
  const [vista, setVista] = useState<Vista>("settimana");
  const [lunedi, setLunedi] = useState<Date>(() => lunediDi(oggi));
  const [meseBase, setMeseBase] = useState(() => oggi.slice(0, 7));
  const [risposta, setRisposta] = useState<PersonaleResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTurno, setEditTurno] = useState<Turno | null>(null);
  const [dataDefault, setDataDefault] = useState(oggi);
  const [dipendenteIdDefaultTurno, setDipendenteIdDefaultTurno] = useState<string | undefined>(undefined);
  const [copiando, setCopiando] = useState(false);
  const [esportandoExcel, setEsportandoExcel] = useState(false);
  const [expandedDip, setExpandedDip] = useState<string | null>(null);
  const [mensileDialogOpen, setMensileDialogOpen] = useState(false);
  const [editMensile, setEditMensile] = useState<Turno | null>(null);
  const [statoGiornoDialogOpen, setStatoGiornoDialogOpen] = useState(false);
  const [statoGiornoDipDefault, setStatoGiornoDipDefault] = useState("");
  const [editStatoGiorno, setEditStatoGiorno] = useState<Turno | null>(null);

  const isMensile = modalita === "mensile";
  const isVistaMese = !isMensile && vista === "mese";

  const [da, fine] = (() => {
    // Modalità mensile (inserimento aggregato) = sempre mese intero.
    // Modalità giornaliero: vista settimana = 7 giorni navigabili,
    // vista mese = mese intero (stesso range della modalità mensile).
    if (!isMensile && vista === "settimana") {
      return [toISO(lunedi), toISO(addDays(lunedi, 6))];
    }
    const [ay, am] = meseBase.split("-").map(Number);
    const ultimoGiorno = new Date(ay, am, 0).getDate();
    return [`${meseBase}-01`, `${meseBase}-${String(ultimoGiorno).padStart(2, "0")}`];
  })();

  const load = useCallback(async (d: string, f: string, soloMensile: boolean) => {
    setLoading(true);
    try {
      // Le due viste non si mischiano mai: mensile=true mostra solo le righe
      // mensili, false solo i turni giornalieri.
      const res = await fetch(`/api/workspace/personale?da=${d}&a=${f}&mensile=${soloMensile}`);
      const j: PersonaleResponse = await res.json();
      setRisposta(j);
    } catch {
      toast.error("Errore caricamento turni");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(da, fine, isMensile); }, [da, fine, isMensile, load]);

  // Vista settimana naviga di 7 giorni, tutte le altre combinazioni (mensile
  // aggregato, o giornaliero in vista mese) navigano di mese intero.
  function navPrev() {
    if (!isMensile && vista === "settimana") setLunedi(d => addDays(d, -7));
    else {
      const [ay, am] = meseBase.split("-").map(Number);
      const prev = new Date(ay, am - 2, 1);
      setMeseBase(`${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`);
    }
  }
  function navNext() {
    if (!isMensile && vista === "settimana") setLunedi(d => addDays(d, 7));
    else {
      const [ay, am] = meseBase.split("-").map(Number);
      const next = new Date(ay, am, 1);
      setMeseBase(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`);
    }
  }

  async function elimina(t: Turno) {
    if (!confirm(`Eliminare turno di ${nomePerId[t.dipendente_id] ?? "questo dipendente"} (${fmtData(t.data_turno)} ${orarioTurno(t)})?`)) return;
    await fetch(`/api/workspace/personale/${t.id}`, { method: "DELETE" });
    toast.success("Turno eliminato");
    load(da, fine, isMensile);
  }

  async function eliminaMensile(t: Turno) {
    if (!confirm(`Eliminare l'inserimento mensile di ${nomePerId[t.dipendente_id] ?? "questo dipendente"} (${fmtMese(meseBase)})?`)) return;
    await fetch(`/api/workspace/personale/${t.id}`, { method: "DELETE" });
    toast.success("Mese eliminato");
    load(da, fine, isMensile);
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
      load(da, fine, isMensile);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore copia settimana");
    } finally {
      setCopiando(false);
    }
  }

  async function esportaExcel() {
    // Deriva il mese dal range effettivamente visualizzato (non da meseBase,
    // che resta fermo al mese d'ingresso quando si naviga in vista settimana).
    const meseExport = da.slice(0, 7);
    setEsportandoExcel(true);
    try {
      const res = await fetch(`/api/workspace/personale/export-mensile?mese=${meseExport}`);
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.error ?? j.detail ?? "Errore export");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `personale_mensile_${meseExport.replace("-", "")}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Excel scaricato");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore export Excel");
    } finally {
      setEsportandoExcel(false);
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
        nomePerId[t.dipendente_id] ?? "",
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
  const dipendenti = risposta?.dipendenti ?? [];

  // Da Fase 0 i turni portano dipendente_id: il nome visualizzato viene dalla
  // anagrafica, così una rinomina si riflette ovunque senza toccare lo storico.
  const nomePerId: Record<string, string> = {};
  for (const d of dipendenti) nomePerId[d.id] = d.nome;

  // Calcola sempre lato frontend dai turni — robusto anche con worker vecchio
  const { oreStdPerPersona, oreExtPerPersona, costoStdPerPersona, costoExtPerPersona, costoPerPersona } = (() => {
    const std: Record<string, number> = {};
    const ext: Record<string, number> = {};
    const cStd: Record<string, number> = {};
    const cExt: Record<string, number> = {};
    const cTot: Record<string, number> = {};
    for (const t of turni) {
      if ((t.tipo_giorno ?? "turno") !== "turno") continue; // riposo/ferie/malattia: fuori da ore/costo lavorato
      const n = nomePerId[t.dipendente_id] ?? t.dipendente_id;
      const ore = calcolaOreTotali(t);
      const extra = t.ore_extra ?? 0;
      const ordinarie = Math.max(0, ore - extra);
      std[n] = (std[n] ?? 0) + ordinarie;
      ext[n] = (ext[n] ?? 0) + extra;
      if (t.mensile) {
        // Riga mensile: costo dal lordo reale, non da tariffa oraria.
        const lordo = t.lordo_mensile ?? 0;
        const impExt = t.importo_extra ?? 0;
        const ordCost = Math.max(0, lordo - impExt);
        cStd[n] = (cStd[n] ?? 0) + ordCost;
        cExt[n] = (cExt[n] ?? 0) + impExt;
        cTot[n] = (cTot[n] ?? 0) + lordo;
        continue;
      }
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

  const giorniSettimana = Array.from({ length: 7 }, (_, i) => toISO(addDays(lunedi, i)));
  const giorniMese = (() => {
    const [ay, am] = meseBase.split("-").map(Number);
    const n = new Date(ay, am, 0).getDate();
    return Array.from({ length: n }, (_, i) => `${meseBase}-${String(i + 1).padStart(2, "0")}`);
  })();
  const giorniDialogoTurno = isVistaMese ? giorniMese : giorniSettimana;

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Interruttore principale: turni giornalieri vs totali mensili.
            È l'unico selettore temporale — etichette parlanti, niente ambiguità. */}
        <div className="flex rounded-md border border-border overflow-hidden">
          <button
            onClick={() => { setModalita("giornaliero"); setExpandedDip(null); }}
            className={`px-3.5 py-1.5 text-sm font-medium transition-colors ${
              !isMensile ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground"
            }`}
          >
            Turni giornalieri
          </button>
          <button
            onClick={() => { setModalita("mensile"); setExpandedDip(null); }}
            className={`px-3.5 py-1.5 text-sm font-medium transition-colors ${
              isMensile ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground"
            }`}
          >
            Totali mensili
          </button>
        </div>

        {/* Info: spiegazione delle due modalità */}
        <InfoPopover title="Come gestire il personale">
          <p className="text-muted-foreground">
            Due modi per registrare le ore e il costo dei dipendenti — scegli quello più comodo per te.
            Per ogni dipendente, in un dato mese, usa <strong>uno solo</strong> dei due (non si mischiano).
          </p>
          <div className="space-y-1.5 text-muted-foreground">
            <p className="font-medium text-foreground">📅 Turni giornalieri</p>
            <p>Inserisci i turni giorno per giorno con gli orari. Comodo per pianificare la settimana. Puoi copiare la settimana precedente per non riscrivere tutto.</p>
          </div>
          <div className="space-y-1.5 text-muted-foreground">
            <p className="font-medium text-foreground">🗓️ Totali mensili</p>
            <p>A fine mese leggi la busta paga e inserisci i totali del dipendente: ore e lordo. Veloce se non vuoi tracciare i singoli turni.</p>
          </div>
          <div className="border-t border-border pt-2 text-muted-foreground">
            <p>In entrambi i casi le <strong>ore extra</strong> si inseriscono a parte e si sommano alle ordinarie: il totale è la somma dei due.</p>
          </div>
        </InfoPopover>

        <div className="flex items-center gap-1 border border-border rounded-md">
          <button onClick={navPrev} className="p-1.5 hover:bg-muted rounded-l-md">
            <ChevronLeft className="size-4" />
          </button>
          <span className="px-3 text-sm font-medium min-w-[160px] text-center capitalize">
            {isMensile || isVistaMese ? fmtMese(meseBase) : `${fmtData(da)} – ${fmtData(fine)}`}
          </span>
          <button onClick={navNext} className="p-1.5 hover:bg-muted rounded-r-md">
            <ChevronRight className="size-4" />
          </button>
        </div>

        {/* Settimana/Mese: solo dentro "Turni giornalieri", scelta forma della vista */}
        {!isMensile && (
          <div className="flex rounded-md border border-border overflow-hidden">
            <button
              onClick={() => setVista("settimana")}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                vista === "settimana" ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground"
              }`}
            >
              Settimana
            </button>
            <button
              onClick={() => setVista("mese")}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                vista === "mese" ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground"
              }`}
            >
              Mese
            </button>
          </div>
        )}

        {/* Destra: azioni */}
        <div className="ml-auto flex items-center gap-2">
          {isMensile ? (
            <Button onClick={() => { setEditMensile(null); setMensileDialogOpen(true); }}>
              <Plus className="size-4 mr-1.5" />Inserisci mese
            </Button>
          ) : (
            <>
              {vista === "settimana" && (
                <Button variant="outline" onClick={copiaSettimana} disabled={copiando}>
                  <CopyPlus className="size-4 mr-1.5" />{copiando ? "Copio…" : "Copia settimana prec."}
                </Button>
              )}

              <Button
                variant="outline"
                onClick={() => { setEditStatoGiorno(null); setStatoGiornoDipDefault(""); setStatoGiornoDialogOpen(true); }}
              >
                <CalendarOff className="size-4 mr-1.5" />Riposo/ferie/malattia
              </Button>

              {turni.length > 0 && (
                <Button variant="outline" onClick={esportaCSV}>
                  <Download className="size-4 mr-1.5" />Esporta CSV
                </Button>
              )}

              <Button variant="outline" onClick={esportaExcel} disabled={esportandoExcel}>
                <Download className="size-4 mr-1.5" />{esportandoExcel ? "Esporto…" : "Esporta Excel"}
              </Button>

              <Button onClick={() => { setEditTurno(null); setDataDefault(oggi >= da && oggi <= fine ? oggi : da); setDipendenteIdDefaultTurno(undefined); setDialogOpen(true); }}>
                <Plus className="size-4 mr-1.5" />Aggiungi turno
              </Button>
            </>
          )}
        </div>
      </div>

      {/* ── KPI cards ── */}
      {(Object.keys(monteOre).length > 0 || isVistaMese) && (
        <div className="space-y-3">
          {/* 3 card principali: in vista mese senza turni si mostrano comunque a zero,
              la griglia sotto resta l'elemento principale della vista. */}
          {Object.keys(monteOre).length > 0 && (
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
          )}

          {/* Vista mese: griglia dipendenti×giorni. Vista settimana: accordion per dipendente. */}
          {isVistaMese ? (
            <VistaMensileGrid
              meseBase={meseBase}
              turni={turni}
              dipendenti={dipendenti}
              nomePerId={nomePerId}
              oggi={oggi}
              onNuovoTurno={(dipendenteId, data) => {
                setEditTurno(null);
                setDataDefault(data);
                setDipendenteIdDefaultTurno(dipendenteId);
                setDialogOpen(true);
              }}
              onModificaTurno={t => { setEditTurno(t); setDialogOpen(true); }}
              onModificaStatoGiorno={t => { setEditStatoGiorno(t); setStatoGiornoDialogOpen(true); }}
            />
          ) : (
          <div className="space-y-1">
            {nomi.map(n => {
              const oreN = monteOre[n] ?? 0;
              const extN = oreExtPerPersona[n] ?? 0;
              const costoN = costoPerPersona[n] ?? 0;
              const turniN = turni
                .filter(t => (nomePerId[t.dipendente_id] ?? t.dipendente_id) === n)
                .sort((a, b) => a.data_turno.localeCompare(b.data_turno));
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
                    <div className="border-t border-border px-4 py-3">
                      {/* Lista turni */}
                      <div className="divide-y divide-border rounded-md border border-border">
                        {turniN.map(t => {
                          const oreT = calcolaOreTotali(t);
                          const costoT = calcolaCostoTurno(t);
                          const statoNonTurno = (t.tipo_giorno ?? "turno") !== "turno";
                          return (
                            <div key={t.id} className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-muted/20 group">
                              {statoNonTurno ? (
                                <>
                                  <span className="text-muted-foreground w-16 shrink-0 tabular-nums">{fmtData(t.data_turno)}</span>
                                  <span className={`text-xs font-medium px-2 py-0.5 rounded-md ${TIPO_GIORNO_BADGE[t.tipo_giorno as Exclude<TipoGiorno, "turno">]}`}>
                                    {TIPO_GIORNO_LABEL[t.tipo_giorno as TipoGiorno]}
                                  </span>
                                  {(t.importo_a_carico ?? 0) > 0 && (
                                    <span className="text-xs text-sky-700 dark:text-sky-400 tabular-nums">{fmtEuro(t.importo_a_carico!)} a carico</span>
                                  )}
                                  <div className="ml-auto flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Button size="icon" variant="ghost" className="size-6" onClick={() => { setEditStatoGiorno(t); setStatoGiornoDialogOpen(true); }}>
                                      <Pencil className="size-3" />
                                    </Button>
                                    <Button size="icon" variant="ghost" className="size-6 text-muted-foreground hover:text-destructive" onClick={() => elimina(t)}>
                                      <Trash2 className="size-3" />
                                    </Button>
                                  </div>
                                </>
                              ) : t.mensile ? (
                                <>
                                  <span className="text-muted-foreground w-24 shrink-0 capitalize">{fmtMese(t.data_turno.slice(0, 7))}</span>
                                  <span className="tabular-nums font-medium">{fmtOreDisplay(oreT)}</span>
                                  {(t.ore_extra ?? 0) > 0 && <span className="text-xs text-amber-600 dark:text-amber-400 tabular-nums">+{fmtOreDisplay(t.ore_extra!)} str.</span>}
                                  {(t.lordo_mensile ?? 0) > 0 && <span className="text-xs text-sky-700 dark:text-sky-400 tabular-nums">{fmtEuro(t.lordo_mensile!)} lordo</span>}
                                  {t.note && <span className="text-xs text-muted-foreground italic truncate flex-1">{t.note}</span>}
                                  <div className="ml-auto flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Button size="icon" variant="ghost" className="size-6" onClick={() => { setEditMensile(t); setMensileDialogOpen(true); }}>
                                      <Pencil className="size-3" />
                                    </Button>
                                    <Button size="icon" variant="ghost" className="size-6 text-muted-foreground hover:text-destructive" onClick={() => eliminaMensile(t)}>
                                      <Trash2 className="size-3" />
                                    </Button>
                                  </div>
                                </>
                              ) : (
                                <>
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
                                </>
                              )}
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
          )}
        </div>
      )}

      {/* Stati vuoti / caricamento. I turni si vedono espandendo il dipendente sopra (vista settimana) o nella griglia (vista mese). */}
      {loading ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Caricamento…</div>
      ) : turni.length === 0 && !isVistaMese ? (
        <div className="py-12 text-center text-sm text-muted-foreground">
          {isMensile
            ? <>Nessun inserimento mensile per {fmtMese(meseBase)}. Usa &ldquo;Inserisci mese&rdquo; per aggiungere i totali da busta paga.</>
            : <>Nessun turno in questo periodo. Usa &ldquo;Aggiungi turno&rdquo; per iniziare.</>}
        </div>
      ) : null}

      <TurnoDialog
        open={dialogOpen}
        turno={editTurno}
        dataDefault={dataDefault}
        dipendenteIdDefault={dipendenteIdDefaultTurno}
        giorniDisponibili={giorniDialogoTurno}
        dipendenti={dipendenti}
        costiNoti={costiNoti}
        onClose={() => { setDialogOpen(false); setEditTurno(null); }}
        onSaved={() => load(da, fine, isMensile)}
        onDipendenteCreato={() => load(da, fine, isMensile)}
      />

      <MensileDialog
        open={mensileDialogOpen}
        turno={editMensile}
        mese={meseBase}
        dipendenti={dipendenti}
        nomePerId={nomePerId}
        onClose={() => { setMensileDialogOpen(false); setEditMensile(null); }}
        onSaved={() => load(da, fine, isMensile)}
        onDipendenteCreato={() => load(da, fine, isMensile)}
      />

      <StatoGiornoDialog
        open={statoGiornoDialogOpen}
        turno={editStatoGiorno}
        dipendenti={dipendenti}
        dipendenteIdDefault={statoGiornoDipDefault}
        dataDefault={dataDefault}
        onClose={() => { setStatoGiornoDialogOpen(false); setEditStatoGiorno(null); }}
        onSaved={() => load(da, fine, isMensile)}
      />
    </div>
  );
}
