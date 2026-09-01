"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Download, CalendarDays, Users, UserMinus, CalendarSync } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { InfoPopover } from "@/components/ui/info-popover";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { toast } from "sonner";
import { parseDecimaleIt, parseDecimaleItOZero, parseNumeroIt, parseNumeroItOZero } from "@/lib/format";

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

export function giorniDelMese(meseBase: string): string[] {
  const [ay, am] = meseBase.split("-").map(Number);
  const n = new Date(ay, am, 0).getDate();
  return Array.from({ length: n }, (_, i) => `${meseBase}-${String(i + 1).padStart(2, "0")}`);
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

const TIPI_STATO: TipoGiorno[] = ["turno", "riposo", "ferie", "malattia"];

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
        className="w-full h-9 rounded-md border border-input bg-background text-foreground px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 [&>option]:bg-background [&>option]:text-foreground"
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
  // Stato del giorno scelto qui dentro, non da un bottone separato in toolbar:
  // "lavora" e "non lavora" sono la stessa decisione, presa nello stesso posto.
  const [tipoGiorno, setTipoGiorno] = useState<TipoGiorno>("turno");
  const [importoACarico, setImportoACarico] = useState("");

  const isNuovo = !turno;
  const isAssenza = tipoGiorno !== "turno";

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
      setTipoGiorno((turno?.tipo_giorno as TipoGiorno) ?? "turno");
      setImportoACarico(turno?.importo_a_carico ? String(turno.importo_a_carico).replace(".", ",") : "");
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
  const extraNum = parseDecimaleItOZero(oreExtra);
  const oreTot = Math.round((stdNum + extraNum) * 100) / 100;
  const costoNum = parseDecimaleIt(costoOrario);
  const costoNumExtra = parseDecimaleIt(costoOrarioExtra);
  const costoEffExtra = !isNaN(costoNumExtra) ? costoNumExtra : costoNum;
  const costoTurno = (!isNaN(costoNum) && oreTot > 0)
    ? (stdNum * costoNum + (extraNum > 0 && !isNaN(costoEffExtra) ? extraNum * costoEffExtra : 0))
    : 0;

  const importoNum = parseNumeroIt(importoACarico);

  // Riposo/ferie/malattia: stesso dialog, altro endpoint. La multi-selezione
  // dei giorni vale anche qui — 5 giorni di ferie si salvano in un colpo.
  async function salvaAssenza() {
    const giorni = isNuovo ? [...giorniSelezionati].sort() : [data];
    const importo = importoACarico ? importoNum : null;
    if (turno) {
      const res = await fetch(`/api/workspace/personale/${turno.id}/stato-giorno`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tipo_giorno: tipoGiorno, importo_a_carico: importo }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail ?? "Errore");
      toast.success(`Giorno aggiornato su ${TIPO_GIORNO_LABEL[tipoGiorno].toLowerCase()}`);
      return;
    }
    const res = await fetch("/api/workspace/personale/stato-giorno-intervallo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dipendente_id: dipendenteId,
        data_da: giorni[0],
        data_a: giorni[giorni.length - 1],
        giorni,
        tipo_giorno: tipoGiorno,
        importo_a_carico: importo,
      }),
    });
    const j = await res.json();
    if (!res.ok) throw new Error(j.detail ?? "Errore");
    const nSaltati = j.n_saltati_turno_esistente?.length ?? 0;
    const nOk = (j.n_creati ?? 0) + (j.n_aggiornati ?? 0);
    const etichetta = TIPO_GIORNO_LABEL[tipoGiorno].toLowerCase();
    toast.success(
      (nOk === 1 ? `Giorno impostato su ${etichetta}` : `${nOk} giorni impostati su ${etichetta}`) +
      (nSaltati ? ` · ${nSaltati} saltati (turno già lavorato)` : "")
    );
  }

  async function salva() {
    if (!dipendenteId) { toast.error("Seleziona un dipendente"); return; }
    if (isAssenza) {
      if (importoACarico && (isNaN(importoNum) || importoNum < 0)) { toast.error("Importo non valido"); return; }
      setSaving(true);
      try {
        await salvaAssenza();
        onSaved();
        onClose();
      } catch (e: unknown) {
        toast.error(e instanceof Error ? e.message : "Errore salvataggio");
      } finally {
        setSaving(false);
      }
      return;
    }
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
        // Assenza riportata a "Lavora": il PATCH del turno non tocca
        // tipo_giorno (non è fra i campi di AggiornaTurnoBody), quindi la riga
        // resterebbe ferie/malattia con orari nuovi — fuori da ore e costi.
        if ((turno.tipo_giorno ?? "turno") !== "turno") {
          const resStato = await fetch(`/api/workspace/personale/${turno.id}/stato-giorno`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tipo_giorno: "turno", importo_a_carico: null }),
          });
          if (!resStato.ok) throw new Error((await resStato.json()).detail ?? "Errore");
        }
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
          <DialogTitle>
            {isAssenza
              ? `${turno ? "Modifica" : "Registra"} ${TIPO_GIORNO_LABEL[tipoGiorno].toLowerCase()}`
              : turno ? "Modifica turno" : "Nuovo turno"}
          </DialogTitle>
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

          {/* Orari e secondo slot: solo se il giorno è lavorato. Su un'assenza
              non hanno senso e sparire è più chiaro che restare disabilitati. */}
          {!isAssenza && (
            <>
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
            </>
          )}

          {/* Stato del giorno: lavorato o assenza, deciso qui e non altrove. */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
              Il dipendente quel giorno
            </label>
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
                  {t === "turno" ? "Lavora" : TIPO_GIORNO_LABEL[t]}
                </button>
              ))}
            </div>
          </div>

          {/* Importo a carico: solo ferie/malattia, dove l'azienda paga senza ore. */}
          {(tipoGiorno === "ferie" || tipoGiorno === "malattia") && (
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

          {/* Durata calcolata */}
          {!isAssenza && oreTot > 0 && (
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
          {!isAssenza && (
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
          )}
          {!isAssenza && extraNum > 0 && (
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
            {saving
              ? "Salvo…"
              : isNuovo && giorniSelezionati.size > 1
                ? `Salva ${giorniSelezionati.size} ${isAssenza ? "giorni" : "turni"}`
                : "Salva"}
          </Button>
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
  // Chi ha già turni giornalieri (o già una riga mensile) in questo mese: il
  // totale da busta paga sommerebbe due volte le stesse ore.
  dipendentiConTurniGiornalieri?: Set<string>;
  dipendentiConMensile?: Set<string>;
  onClose: () => void;
  onSaved: () => void;
  onDipendenteCreato: () => void;
}

export function fmtMese(mese: string): string {
  const [ay, am] = mese.split("-").map(Number);
  return new Date(ay, am - 1, 1).toLocaleDateString("it-IT", { month: "long", year: "numeric" });
}

export function MensileDialog({ open, turno, mese, dipendenti, nomePerId, dipendentiConTurniGiornalieri, dipendentiConMensile, onClose, onSaved, onDipendenteCreato }: MensileDialogProps) {
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
  // DUE helper, non uno: `numOr0` serviva sia le ore sia il lordo mensile, che
  // sono grandezze diverse in campi `type="text"` (testo libero, quindi
  // l'italiano puo' scriverci il separatore di migliaia).
  //   ore   "148"    -> 148      un monte ore non ha migliaia
  //   lordo "1.700"  -> 1700     uno stipendio si', ed e' la forma naturale
  // Con un helper solo, "1.700" di lordo diventava 1,7 EUR.
  const oreOr0 = (s: string) => parseDecimaleItOZero(s);
  const euroOr0 = (s: string) => parseNumeroItOZero(s);
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

  const oreOrdN = oreOr0(oreOrd);
  const oreExtN = oreOr0(oreExtra);
  const oreTot = Math.round((oreOrdN + oreExtN) * 100) / 100;
  const impOrdN = euroOr0(importoOrd);
  const impExtN = euroOr0(importoExtra);
  const lordoTot = Math.round((impOrdN + impExtN) * 100) / 100;

  const nomeSelezionato = dipendenti.find(d => d.id === dipendenteId)?.nome ?? "Questo dipendente";
  const haGiaTurni = isNuovo && !!dipendenteId && !!dipendentiConTurniGiornalieri?.has(dipendenteId);
  const haGiaMensile = isNuovo && !!dipendenteId && !!dipendentiConMensile?.has(dipendenteId);

  async function salva() {
    if (isNuovo && !dipendenteId) { toast.error("Seleziona un dipendente"); return; }
    if (haGiaTurni) {
      toast.error(`${nomeSelezionato} ha già turni giornalieri in ${fmtMese(mese)}: le ore si conterebbero due volte.`);
      return;
    }
    if (haGiaMensile) {
      toast.error(`${nomeSelezionato} ha già un totale mensile per ${fmtMese(mese)}: modifica quello invece di aggiungerne un altro.`);
      return;
    }
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

            {(haGiaTurni || haGiaMensile) && (
              <div className="rounded-md border border-amber-500/50 bg-amber-50/60 dark:bg-amber-950/20 px-3 py-2">
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  {haGiaTurni ? (
                    <>
                      <strong>{nomeSelezionato}</strong> ha già turni giornalieri in {fmtMese(mese)}.
                      Aggiungere anche il totale da busta paga conterebbe le ore due volte:
                      per questo mese usa un metodo solo.
                    </>
                  ) : (
                    <>
                      <strong>{nomeSelezionato}</strong> ha già un totale mensile per {fmtMese(mese)}.
                      Modifica quello dall&apos;elenco invece di aggiungerne un altro.
                    </>
                  )}
                </p>
              </div>
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
          <Button onClick={salva} disabled={saving || haGiaTurni || haGiaMensile}>{saving ? "Salvo…" : "Salva"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Dialog gestione anagrafica dipendenti ────────────────────────────────────

interface GestioneDipendentiDialogProps {
  open: boolean;
  onClose: () => void;
  onCambiato: () => void;
}

/** Rinomina, costo orario di default, disattiva/riattiva ed elimina.
 *  L'eliminazione vera passa solo per chi non ha turni: il worker rifiuta
 *  (409) chi ne ha, perché cancellarlo cambierebbe i costi di mesi chiusi. */
export function GestioneDipendentiDialog({ open, onClose, onCambiato }: GestioneDipendentiDialogProps) {
  const [attivi, setAttivi] = useState<Dipendente[]>([]);
  const [disattivati, setDisattivati] = useState<Dipendente[]>([]);
  const [loading, setLoading] = useState(false);
  const [mostraDisattivati, setMostraDisattivati] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [editNome, setEditNome] = useState("");
  const [editCosto, setEditCosto] = useState("");
  const [busy, setBusy] = useState(false);
  const [daDisattivare, setDaDisattivare] = useState<Dipendente | null>(null);
  const [daEliminare, setDaEliminare] = useState<Dipendente | null>(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [rA, rD] = await Promise.all([
        fetch("/api/workspace/dipendenti?attivo=true").then(r => r.json()),
        fetch("/api/workspace/dipendenti?attivo=false").then(r => r.json()),
      ]);
      setAttivi(rA?.dipendenti ?? []);
      setDisattivati(rD?.dipendenti ?? []);
    } catch {
      toast.error("Errore caricamento dipendenti");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (open) { carica(); setEditId(null); setMostraDisattivati(false); } }, [open, carica]);

  function apriModifica(d: Dipendente) {
    setEditId(d.id);
    setEditNome(d.nome);
    setEditCosto(d.costo_orario_default != null ? String(d.costo_orario_default).replace(".", ",") : "");
  }

  async function salvaModifica() {
    const nome = editNome.trim();
    if (!nome) { toast.error("Il nome è obbligatorio"); return; }
    const costoNum = editCosto ? parseDecimaleIt(editCosto) : null;
    if (editCosto && (costoNum == null || isNaN(costoNum) || costoNum < 0)) {
      toast.error("Costo orario non valido"); return;
    }
    setBusy(true);
    try {
      const res = await fetch(`/api/workspace/dipendenti/${editId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome, costo_orario_default: costoNum }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail ?? j.error ?? "Errore");
      toast.success("Dipendente aggiornato");
      setEditId(null);
      await carica();
      onCambiato();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore salvataggio");
    } finally {
      setBusy(false);
    }
  }

  async function cambiaStato(d: Dipendente, azione: "disattiva" | "riattiva") {
    if (azione === "disattiva") { setDaDisattivare(d); return; }
    await eseguiCambiaStato(d, azione);
  }

  async function eseguiCambiaStato(d: Dipendente, azione: "disattiva" | "riattiva") {
    setBusy(true);
    try {
      const res = await fetch(`/api/workspace/dipendenti/${d.id}/${azione}`, { method: "PATCH" });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail ?? j.error ?? "Errore");
      toast.success(azione === "disattiva" ? `${d.nome} disattivato` : `${d.nome} riattivato`);
      await carica();
      onCambiato();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    } finally {
      setBusy(false);
    }
  }

  async function elimina(d: Dipendente) {
    setBusy(true);
    try {
      const res = await fetch(`/api/workspace/dipendenti/${d.id}`, { method: "DELETE" });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail ?? j.error ?? "Errore");
      toast.success(`${d.nome} eliminato`);
      await carica();
      onCambiato();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore eliminazione");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="flex max-h-[90dvh] flex-col max-w-lg">
        <DialogHeader className="shrink-0">
          <DialogTitle>Gestisci dipendenti</DialogTitle>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {loading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Caricamento…</p>
          ) : attivi.length === 0 && disattivati.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Nessun dipendente. Creane uno da &ldquo;Aggiungi turno&rdquo;.
            </p>
          ) : (
            <div className="space-y-1 mt-1">
              {attivi.map(d => (
                <div key={d.id} className="rounded-md border border-border">
                  {editId === d.id ? (
                    <div className="p-3 space-y-2">
                      <div>
                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Nome *</label>
                        <Input value={editNome} onChange={e => setEditNome(e.target.value)} autoFocus />
                      </div>
                      <div>
                        <label className="text-xs font-medium text-muted-foreground mb-1 block">
                          Costo orario di default (€/h) <span className="font-normal opacity-60">opzionale</span>
                        </label>
                        <Input
                          type="text"
                          inputMode="decimal"
                          value={editCosto}
                          onChange={e => setEditCosto(e.target.value.replace(/[^0-9,.]/g, ""))}
                          placeholder="es. 12,50"
                        />
                        <p className="text-[11px] text-muted-foreground mt-1">
                          Serve solo a precompilare i nuovi turni: i turni già salvati non cambiano.
                        </p>
                      </div>
                      <div className="flex justify-end gap-2 pt-1">
                        <Button variant="outline" size="sm" onClick={() => setEditId(null)} disabled={busy}>Annulla</Button>
                        <Button size="sm" onClick={salvaModifica} disabled={busy}>{busy ? "Salvo…" : "Salva"}</Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 px-3 py-2 group">
                      <span className="min-w-0 font-medium text-sm flex-1 truncate">{d.nome}</span>
                      {d.costo_orario_default != null && (
                        <span className="text-xs text-muted-foreground tabular-nums shrink-0">
                          {fmtEuro(d.costo_orario_default)}/h
                        </span>
                      )}
                      <div className="flex gap-1 shrink-0">
                        <Button size="icon" variant="ghost" className="size-7" title="Modifica" onClick={() => apriModifica(d)} disabled={busy}>
                          <Pencil className="size-3.5" />
                        </Button>
                        <Button size="icon" variant="ghost" className="size-7" title="Disattiva" onClick={() => cambiaStato(d, "disattiva")} disabled={busy}>
                          <UserMinus className="size-3.5" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-7 text-muted-foreground hover:text-destructive"
                          title="Elimina (solo se non ha turni)"
                          onClick={() => setDaEliminare(d)}
                          disabled={busy}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {disattivati.length > 0 && (
                <div className="pt-2">
                  <button
                    type="button"
                    onClick={() => setMostraDisattivati(v => !v)}
                    className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                  >
                    {mostraDisattivati ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
                    Disattivati ({disattivati.length})
                  </button>
                  {mostraDisattivati && (
                    <div className="space-y-1 mt-1.5">
                      {disattivati.map(d => (
                        <div key={d.id} className="flex items-center gap-2 px-3 py-2 rounded-md border border-dashed border-border">
                          <span className="min-w-0 text-sm flex-1 truncate text-muted-foreground">{d.nome}</span>
                          <Button size="sm" variant="outline" onClick={() => cambiaStato(d, "riattiva")} disabled={busy}>
                            Riattiva
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="size-7 text-muted-foreground hover:text-destructive"
                            title="Elimina (solo se non ha turni)"
                            onClick={() => elimina(d)}
                            disabled={busy}
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="shrink-0 flex justify-between items-center gap-2 pt-3 border-t border-border mt-1">
          <p className="text-[11px] text-muted-foreground">
            Disattivare conserva lo storico. Eliminare si può solo senza turni.
          </p>
          <Button variant="outline" onClick={onClose}>Chiudi</Button>
        </div>
      </DialogContent>

      <ConfirmDialog
        open={daDisattivare !== null}
        titolo={daDisattivare ? `Disattivare ${daDisattivare.nome}?` : ""}
        messaggio="Sparirà dalle selezioni e dai nuovi inserimenti, ma i turni già registrati restano nei costi storici."
        confermaLabel="Disattiva"
        onConferma={() => { if (daDisattivare) eseguiCambiaStato(daDisattivare, "disattiva"); }}
        onClose={() => setDaDisattivare(null)}
      />

      <ConfirmDialog
        open={daEliminare !== null}
        titolo={daEliminare ? `Eliminare definitivamente ${daEliminare.nome}?` : ""}
        messaggio="Possibile solo se non ha nessun turno registrato."
        onConferma={() => { if (daEliminare) elimina(daEliminare); }}
        onClose={() => setDaEliminare(null)}
      />
    </Dialog>
  );
}

// ─── Copia mese precedente ─────────────────────────────────────────────────────

interface CopiaMeseDialogProps {
  open: boolean;
  mese: string;
  dipendenti: Dipendente[];
  onClose: () => void;
  onCopiato: () => void;
}

export function CopiaMeseDialog({ open, mese, dipendenti, onClose, onCopiato }: CopiaMeseDialogProps) {
  const [selezionati, setSelezionati] = useState<Set<string>>(new Set());
  const [copiando, setCopiando] = useState(false);

  useEffect(() => { if (open) setSelezionati(new Set()); }, [open]);

  function toggle(id: string) {
    setSelezionati(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function copia() {
    if (selezionati.size === 0) return;
    setCopiando(true);
    try {
      const res = await fetch("/api/workspace/personale/copia-mese", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mese, dipendente_ids: [...selezionati] }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail ?? j.error ?? "Errore copia");
      toast.success(`${j.n_copiati} turni copiati, ${j.n_saltati} saltati (già presenti)`);
      onClose();
      onCopiato();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore copia mese");
    } finally {
      setCopiando(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Copia mese precedente</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Copia turni e assenze del mese scorso su {fmtMese(mese)}, allineando per giorno della settimana. I giorni già occupati vengono saltati.
        </p>
        <div className="space-y-1.5 max-h-[40dvh] overflow-y-auto">
          {dipendenti.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nessun dipendente disponibile.</p>
          ) : dipendenti.map(d => (
            <label key={d.id} className="flex items-center gap-2 p-2 rounded-md hover:bg-muted cursor-pointer text-sm">
              <input
                type="checkbox"
                checked={selezionati.has(d.id)}
                onChange={() => toggle(d.id)}
                className="size-4"
              />
              {d.nome}
            </label>
          ))}
        </div>
        <div className="shrink-0 flex justify-end gap-2 pt-3 border-t border-border mt-1">
          <Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button onClick={copia} disabled={selezionati.size === 0 || copiando}>
            {copiando ? "Copio…" : "Copia"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Tab principale ───────────────────────────────────────────────────────────

// Niente modalità: turni giornalieri e totali da busta paga convivono nello
// stesso elenco. Il metodo è una proprietà del singolo dipendente (chi ha turni
// mostra i turni, chi ha la busta paga mostra la riga mensile), non un
// interruttore di pagina — che mostrava i totali di una vista con la lista
// dell'altra vuota. Il calendario vive in Agenda: qui si fa data entry.

export function PersonaleTab() {
  const oggi = toISO(new Date());
  const [meseBase, setMeseBase] = useState(() => oggi.slice(0, 7));
  const [risposta, setRisposta] = useState<PersonaleResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTurno, setEditTurno] = useState<Turno | null>(null);
  const [dataDefault, setDataDefault] = useState(oggi);
  const [dipendenteIdDefaultTurno, setDipendenteIdDefaultTurno] = useState<string | undefined>(undefined);
  const [esportandoExcel, setEsportandoExcel] = useState(false);
  const [expandedDip, setExpandedDip] = useState<string | null>(null);
  const [mensileDialogOpen, setMensileDialogOpen] = useState(false);
  const [editMensile, setEditMensile] = useState<Turno | null>(null);
  const [gestioneDipOpen, setGestioneDipOpen] = useState(false);
  const [copiaMeseOpen, setCopiaMeseOpen] = useState(false);
  const [turnoDaEliminare, setTurnoDaEliminare] = useState<Turno | null>(null);
  const [mensileDaEliminare, setMensileDaEliminare] = useState<Turno | null>(null);

  const [da, fine] = (() => {
    const [ay, am] = meseBase.split("-").map(Number);
    const ultimoGiorno = new Date(ay, am, 0).getDate();
    return [`${meseBase}-01`, `${meseBase}-${String(ultimoGiorno).padStart(2, "0")}`];
  })();

  // Una sola fetch per vista: le due chiamate (giornaliero + mensile) si fondono
  // in un elenco unico. I totali del backend sono per-vista, quindi si ricalcola
  // tutto lato client dai turni fusi — come già faceva prima.
  const load = useCallback(async (d: string, f: string) => {
    setLoading(true);
    try {
      const [rG, rM] = await Promise.all([
        fetch(`/api/workspace/personale?da=${d}&a=${f}&mensile=false`).then(r => r.json()),
        fetch(`/api/workspace/personale?da=${d}&a=${f}&mensile=true`).then(r => r.json()),
      ]);
      const base: PersonaleResponse = rG ?? {};
      setRisposta({
        ...base,
        turni: [...(rG?.turni ?? []), ...(rM?.turni ?? [])],
      });
    } catch {
      toast.error("Errore caricamento turni");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(da, fine); }, [da, fine, load]);

  function navPrev() {
    const [ay, am] = meseBase.split("-").map(Number);
    const prev = new Date(ay, am - 2, 1);
    setMeseBase(`${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`);
  }
  function navNext() {
    const [ay, am] = meseBase.split("-").map(Number);
    const next = new Date(ay, am, 1);
    setMeseBase(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`);
  }

  function descriviTurno(t: Turno): string {
    const chi = nomePerId[t.dipendente_id] ?? "questo dipendente";
    return (t.tipo_giorno ?? "turno") !== "turno"
      ? `${TIPO_GIORNO_LABEL[t.tipo_giorno as TipoGiorno].toLowerCase()} di ${chi} (${fmtData(t.data_turno)})`
      : `turno di ${chi} (${fmtData(t.data_turno)} ${orarioTurno(t)})`;
  }

  async function elimina(t: Turno) {
    await fetch(`/api/workspace/personale/${t.id}`, { method: "DELETE" });
    toast.success("Eliminato");
    load(da, fine);
  }

  async function eliminaMensile(t: Turno) {
    await fetch(`/api/workspace/personale/${t.id}`, { method: "DELETE" });
    toast.success("Mese eliminato");
    load(da, fine);
  }

  async function esportaExcel() {
    // L'export è sempre del mese intero, anche con una settimana in zoom.
    setEsportandoExcel(true);
    try {
      const res = await fetch(`/api/workspace/personale/export-mensile?mese=${meseBase}`);
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.error ?? j.detail ?? "Errore export");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `personale_mensile_${meseBase.replace("-", "")}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Excel scaricato");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore export Excel");
    } finally {
      setEsportandoExcel(false);
    }
  }

  const turni = risposta?.turni ?? [];
  const costiNoti = risposta?.costi_noti ?? {};
  const dipendenti = risposta?.dipendenti ?? [];

  // Da Fase 0 i turni portano dipendente_id: il nome visualizzato viene dalla
  // anagrafica, così una rinomina si riflette ovunque senza toccare lo storico.
  const nomePerId: Record<string, string> = {};
  for (const d of dipendenti) nomePerId[d.id] = d.nome;

  // `nomi` dal worker sono i soli dipendenti ATTIVI. Chi viene disattivato a
  // metà mese ha però turni che entrano nei totali in alto: senza aggiungerlo
  // qui sparirebbe dall'elenco e la somma delle righe non farebbe il totale.
  const nomi = [...(risposta?.nomi ?? [])];
  for (const t of turni) {
    const n = nomePerId[t.dipendente_id] ?? t.dipendente_id;
    if (!nomi.includes(n)) nomi.push(n);
  }

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
  // Solo giorni effettivamente lavorati: contare anche riposi e ferie
  // diluirebbe la media oraria mostrata sulla card Totale.
  const giorniConTurni = new Set(
    turni.filter(t => !t.mensile && (t.tipo_giorno ?? "turno") === "turno").map(t => t.data_turno)
  ).size;
  const mediaGiornaliera = giorniConTurni > 0 ? totaleOre / giorniConTurni : 0;

  // I chip-giorno del dialog sono sempre quelli del mese in vista.
  const giorniDialogoTurno = giorniDelMese(meseBase);
  const giornoDefaultDialogo = giorniDialogoTurno.includes(oggi) ? oggi : giorniDialogoTurno[0];

  // Chi ha già turni giornalieri nel mese non può ricevere anche il totale da
  // busta paga: sommerebbe due volte le stesse ore. La guardia sta anche lato
  // worker; qui serve a non far nemmeno aprire la strada sbagliata.
  const dipConTurniGiornalieri = new Set(
    turni.filter(t => !t.mensile).map(t => t.dipendente_id)
  );
  const dipConMensile = new Set(
    turni.filter(t => t.mensile).map(t => t.dipendente_id)
  );

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Info: spiegazione dei due modi di registrare */}
        <InfoPopover title="Come gestire il personale">
          <p className="text-muted-foreground">
            Due modi per registrare le ore e il costo dei dipendenti — scegli quello più comodo per te.
            Per ogni dipendente, in un dato mese, usa <strong>uno solo</strong> dei due (non si mischiano).
          </p>
          <div className="space-y-1.5 text-muted-foreground">
            <p className="font-medium text-foreground">📅 Turni giornalieri</p>
            <p>Inserisci i turni giorno per giorno con gli orari, anche più giorni in un colpo solo. Nello stesso riquadro segni se il dipendente quel giorno è a riposo, in ferie o in malattia.</p>
          </div>
          <div className="space-y-1.5 text-muted-foreground">
            <p className="font-medium text-foreground">🗓️ Totale mensile</p>
            <p>A fine mese leggi la busta paga e inserisci i totali del dipendente: ore e lordo. Veloce se non vuoi tracciare i singoli turni.</p>
          </div>
          <div className="border-t border-border pt-2 text-muted-foreground">
            <p>I due modi convivono nella stessa pagina: ogni dipendente usa il suo. Per lo <strong>stesso</strong> dipendente nello <strong>stesso</strong> mese però va usato uno solo, altrimenti le ore si conterebbero due volte.</p>
            <p className="mt-1.5">Per vedere i turni sul calendario, insieme ad appuntamenti e spese, vai su <strong>Agenda → Tutto</strong>.</p>
          </div>
        </InfoPopover>

        <div className="flex items-center gap-1 border border-border rounded-md">
          <button onClick={navPrev} className="p-1.5 hover:bg-muted rounded-l-md" title="Mese precedente">
            <ChevronLeft className="size-4" />
          </button>
          <span className="px-3 text-sm font-medium min-w-[150px] text-center capitalize">
            {fmtMese(meseBase)}
          </span>
          <button onClick={navNext} className="p-1.5 hover:bg-muted rounded-r-md" title="Mese successivo">
            <ChevronRight className="size-4" />
          </button>
        </div>

        {/* Destra: azioni */}
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" onClick={() => setGestioneDipOpen(true)}>
            <Users className="size-4 mr-1.5" />Gestisci dipendenti
          </Button>

          <Button variant="outline" onClick={() => setCopiaMeseOpen(true)}>
            <CalendarSync className="size-4 mr-1.5" />Copia mese prec.
          </Button>

          <Button variant="outline" onClick={esportaExcel} disabled={esportandoExcel}>
            <Download className="size-4 mr-1.5" />{esportandoExcel ? "Esporto…" : "Excel"}
          </Button>

          <Button variant="outline" onClick={() => { setEditMensile(null); setMensileDialogOpen(true); }}>
            <CalendarDays className="size-4 mr-1.5" />Totale mensile
          </Button>

          <Button onClick={() => { setEditTurno(null); setDataDefault(giornoDefaultDialogo); setDipendenteIdDefaultTurno(undefined); setDialogOpen(true); }}>
            <Plus className="size-4 mr-1.5" />Aggiungi turno
          </Button>
        </div>
      </div>

      {/* ── KPI cards ── */}
      {turni.length > 0 && (
        <div className="space-y-3">
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

          {/* Elenco per dipendente: turni giornalieri e righe da busta paga
              nello stesso posto, ognuno col metodo che usa davvero. */}
          <div className="space-y-1">
            {nomi.map(n => {
              // Ricalcolato dai turni fusi, non da monte_ore: quello arriva
              // dalla sola fetch giornaliera e darebbe 0h a chi è a busta paga.
              const oreN = (oreStdPerPersona[n] ?? 0) + (oreExtPerPersona[n] ?? 0);
              const extN = oreExtPerPersona[n] ?? 0;
              const costoN = costoPerPersona[n] ?? 0;
              const turniN = turni
                .filter(t => (nomePerId[t.dipendente_id] ?? t.dipendente_id) === n)
                .sort((a, b) => a.data_turno.localeCompare(b.data_turno));
              const isOpen = expandedDip === n;
              const col = getDipColor(nomi, n);
              const dipId = dipendenti.find(d => d.nome === n)?.id;
              // Non è fra gli attivi ma ha turni nel mese: disattivato a mese
              // iniziato. Va detto, o la sua riga sembra un dato incoerente.
              const disattivato = !dipId;
              const daBustaPaga = turniN.some(t => t.mensile);
              const assenzeN = turniN.filter(t => (t.tipo_giorno ?? "turno") !== "turno").length;
              return (
                <div key={n} className={`rounded-lg border ring-1 ${col.ring} overflow-hidden`}>
                  <div className={`w-full flex items-center justify-between px-4 py-3 hover:${col.bg} transition-colors`}>
                    <button
                      onClick={() => setExpandedDip(isOpen ? null : n)}
                      className="flex items-center gap-3 flex-1 min-w-0 text-left"
                    >
                      <span className="font-semibold text-sm truncate">{n}</span>
                      <span className="text-sm tabular-nums text-muted-foreground shrink-0">{fmtOreDisplay(oreN)}</span>
                      {extN > 0 && <span className="text-xs text-amber-600 dark:text-amber-400 tabular-nums shrink-0">+{fmtOreDisplay(extN)} str.</span>}
                      {costoN > 0 && <span className="text-xs text-sky-700 dark:text-sky-400 font-semibold tabular-nums shrink-0">{fmtEuro(costoN)}</span>}
                      {assenzeN > 0 && (
                        <span className="text-xs text-muted-foreground shrink-0">
                          {assenzeN} {assenzeN === 1 ? "assenza" : "assenze"}
                        </span>
                      )}
                      {/* Il metodo è del dipendente: dirlo qui evita la domanda
                          "perché questo non ha turni giornalieri?". */}
                      {turniN.length > 0 && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${
                          daBustaPaga
                            ? "bg-violet-500/10 text-violet-600 dark:text-violet-400"
                            : "bg-muted text-muted-foreground"
                        }`}>
                          {daBustaPaga ? "busta paga" : "a turni"}
                        </span>
                      )}
                      {disattivato && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded shrink-0 bg-amber-500/10 text-amber-600 dark:text-amber-400">
                          disattivato
                        </span>
                      )}
                    </button>
                    <div className="flex items-center gap-1 shrink-0">
                      {dipId && !daBustaPaga && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs"
                          onClick={() => {
                            setEditTurno(null);
                            setDataDefault(giornoDefaultDialogo);
                            setDipendenteIdDefaultTurno(dipId);
                            setDialogOpen(true);
                          }}
                        >
                          <Plus className="size-3.5 mr-1" />Turno
                        </Button>
                      )}
                      <button onClick={() => setExpandedDip(isOpen ? null : n)} className="p-1">
                        {isOpen ? <ChevronUp className="size-4 text-muted-foreground" /> : <ChevronDown className="size-4 text-muted-foreground" />}
                      </button>
                    </div>
                  </div>

                  {isOpen && (
                    <div className="border-t border-border px-4 py-3">
                      {turniN.length === 0 && (
                        <p className="text-xs text-muted-foreground py-2 text-center">
                          Nessun turno per {fmtMese(meseBase)}.
                        </p>
                      )}
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
                                    <Button size="icon" variant="ghost" className="size-6" onClick={() => { setEditTurno(t); setDialogOpen(true); }}>
                                      <Pencil className="size-3" />
                                    </Button>
                                    <Button size="icon" variant="ghost" className="size-6 text-muted-foreground hover:text-destructive" onClick={() => setTurnoDaEliminare(t)}>
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
                                  {t.note && <span className="min-w-0 text-xs text-muted-foreground italic truncate flex-1">{t.note}</span>}
                                  <div className="ml-auto flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Button size="icon" variant="ghost" className="size-6" onClick={() => { setEditMensile(t); setMensileDialogOpen(true); }}>
                                      <Pencil className="size-3" />
                                    </Button>
                                    <Button size="icon" variant="ghost" className="size-6 text-muted-foreground hover:text-destructive" onClick={() => setMensileDaEliminare(t)}>
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
                                  {t.note && <span className="min-w-0 text-xs text-muted-foreground italic truncate flex-1">{t.note}</span>}
                                  <div className="ml-auto flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Button size="icon" variant="ghost" className="size-6" onClick={() => { setEditTurno(t); setDialogOpen(true); }}>
                                      <Pencil className="size-3" />
                                    </Button>
                                    <Button size="icon" variant="ghost" className="size-6 text-muted-foreground hover:text-destructive" onClick={() => setTurnoDaEliminare(t)}>
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
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Caricamento…</div>
      ) : turni.length === 0 ? (
        <div className="py-12 text-center space-y-1.5">
          <p className="text-sm text-muted-foreground">
            Niente registrato per {fmtMese(meseBase)}.
          </p>
          <p className="text-xs text-muted-foreground">
            Usa <strong>Aggiungi turno</strong> per i turni giorno per giorno,
            oppure <strong>Totale mensile</strong> per i totali da busta paga.
          </p>
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
        onSaved={() => load(da, fine)}
        onDipendenteCreato={() => load(da, fine)}
      />

      <MensileDialog
        open={mensileDialogOpen}
        turno={editMensile}
        mese={meseBase}
        dipendenti={dipendenti}
        nomePerId={nomePerId}
        dipendentiConTurniGiornalieri={dipConTurniGiornalieri}
        dipendentiConMensile={dipConMensile}
        onClose={() => { setMensileDialogOpen(false); setEditMensile(null); }}
        onSaved={() => load(da, fine)}
        onDipendenteCreato={() => load(da, fine)}
      />

      <GestioneDipendentiDialog
        open={gestioneDipOpen}
        onClose={() => setGestioneDipOpen(false)}
        onCambiato={() => load(da, fine)}
      />

      <CopiaMeseDialog
        open={copiaMeseOpen}
        mese={meseBase}
        dipendenti={dipendenti}
        onClose={() => setCopiaMeseOpen(false)}
        onCopiato={() => load(da, fine)}
      />

      <ConfirmDialog
        open={turnoDaEliminare !== null}
        titolo={turnoDaEliminare ? `Eliminare ${descriviTurno(turnoDaEliminare)}?` : ""}
        onConferma={() => { if (turnoDaEliminare) elimina(turnoDaEliminare); }}
        onClose={() => setTurnoDaEliminare(null)}
      />

      <ConfirmDialog
        open={mensileDaEliminare !== null}
        titolo={mensileDaEliminare ? `Eliminare l'inserimento mensile di ${nomePerId[mensileDaEliminare.dipendente_id] ?? "questo dipendente"} (${fmtMese(meseBase)})?` : ""}
        onConferma={() => { if (mensileDaEliminare) eliminaMensile(mensileDaEliminare); }}
        onClose={() => setMensileDaEliminare(null)}
      />
    </div>
  );
}
