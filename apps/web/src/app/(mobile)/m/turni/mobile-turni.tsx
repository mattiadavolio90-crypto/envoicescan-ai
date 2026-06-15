"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight, Banknote, Wallet, Users } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { ConfirmDialog } from "../confirm-dialog";
import { MobileIncassi } from "../diario/mobile-incassi";
import { MobileSpese } from "../diario/mobile-spese";

// ─── Wrapper Movimenti: Incassi / Spese / Turni ─────────────────────────────────
// Questa e' la sezione "Movimenti" della bottom nav (ex "Turni"): raccoglie i
// flussi di denaro (Incassi, Spese) + il costo del personale (Turni). Incassi e
// Spese riusano i componenti di ../diario, dove vivevano prima. Default: Incassi.

type MovTab = "incassi" | "spese" | "turni";

export function MobileTurni() {
  const [tab, setTab] = useState<MovTab>("incassi");

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold tracking-tight">Movimenti</h1>

      <div className="grid grid-cols-3 gap-1 rounded-xl border bg-card p-1">
        {([
          { k: "incassi" as MovTab, l: "Incassi", icon: Banknote },
          { k: "spese" as MovTab, l: "Spese", icon: Wallet },
          { k: "turni" as MovTab, l: "Turni", icon: Users },
        ]).map((s) => {
          const Icon = s.icon;
          return (
            <button
              key={s.k}
              onClick={() => setTab(s.k)}
              className={`inline-flex items-center justify-center gap-1 rounded-lg py-2 text-sm font-medium transition-colors ${
                tab === s.k ? "bg-primary text-primary-foreground" : "text-muted-foreground active:bg-muted"
              }`}
            >
              <Icon className="size-4 shrink-0" />{s.l}
            </button>
          );
        })}
      </div>

      {tab === "incassi" ? <MobileIncassi /> : tab === "spese" ? <MobileSpese /> : <TurniBody />}
    </div>
  );
}

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
  costo_orario_extra?: number | null;
  note?: string | null;
  // Righe mensili (inserimento aggregato da busta paga)
  mensile?: boolean | null;
  ore_dichiarate?: number | null;
  lordo_mensile?: number | null;
  importo_extra?: number | null;
}

// Costi noti per dipendente: tariffa standard ed extra usate l'ultima volta.
interface CostiNoti {
  std?: number;
  ext?: number;
}

interface PersonaleResponse {
  turni: Turno[];
  monte_ore: Record<string, number>;
  nomi: string[];
  costi_noti: Record<string, CostiNoti>;
}

const GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
const MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];

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
function fmtMese(mese: string): string {
  const [ay, am] = mese.split("-").map(Number);
  return new Date(ay, am - 1, 1).toLocaleDateString("it-IT", { month: "long", year: "numeric" });
}
function fmtEuro(v: number): string {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);
}
function calcolaSlotOre(inizio: string, fine: string): number {
  const [ih, im] = inizio.split(":").map(Number);
  const [fh, fm] = fine.split(":").map(Number);
  let minuti = fh * 60 + fm - (ih * 60 + im);
  if (minuti < 0) minuti += 24 * 60;
  return Math.round((minuti / 60) * 100) / 100;
}
// Ore totali del turno: orari (ordinario) + ore extra aggiuntive. Per le righe
// mensili sono le ore dichiarate da busta paga.
function calcolaOreTotali(t: Turno): number {
  if (t.mensile) return Math.round((t.ore_dichiarate ?? 0) * 100) / 100;
  let tot = calcolaSlotOre(t.ora_inizio, t.ora_fine);
  if (t.ora_inizio2 && t.ora_fine2) tot += calcolaSlotOre(t.ora_inizio2, t.ora_fine2);
  tot += t.ore_extra ?? 0;
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

// ─── Dialog turno giornaliero ────────────────────────────────────────────────────

interface DialogProps {
  open: boolean;
  turno: Turno | null;
  dataDefault: string;
  nomiSuggeriti: string[];
  costiNoti: Record<string, CostiNoti>;
  onClose: () => void;
  onSaved: () => void;
}

function TurnoDialog({ open, turno, dataDefault, nomiSuggeriti, costiNoti, onClose, onSaved }: DialogProps) {
  const [nome, setNome] = useState("");
  const [data, setData] = useState(dataDefault);
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
      setCostoOrarioExtra(turno?.costo_orario_extra != null ? String(turno.costo_orario_extra).replace(".", ",") : "");
      setNote(turno?.note ?? "");
      setShowSugg(false);
    }
  }, [open, turno, dataDefault]);

  const suggFiltrati = nome.length > 0
    ? nomiSuggeriti.filter((n) => n.toLowerCase().includes(nome.toLowerCase()) && n !== nome)
    : [];

  // Selezionando un dipendente noto, precompila le tariffe usate l'ultima volta.
  function selezionaNome(n: string) {
    setNome(n);
    setShowSugg(false);
    const noto = costiNoti[n];
    if (noto) {
      if (!costoOrario && noto.std != null) setCostoOrario(String(noto.std).replace(".", ","));
      if (!costoOrarioExtra && noto.ext != null) setCostoOrarioExtra(String(noto.ext).replace(".", ","));
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
    if (!nome.trim()) { toast.error("Il nome è obbligatorio"); return; }
    if (!oraInizio || !oraFine) { toast.error("Orario obbligatorio"); return; }
    if (spezzato && (!oraInizio2 || !oraFine2)) { toast.error("Inserisci il secondo slot"); return; }
    if (oreExtra && (isNaN(extraNum) || extraNum < 0)) { toast.error("Ore extra non valide"); return; }
    if (costoOrario && (isNaN(costoNum) || costoNum < 0)) { toast.error("Costo orario non valido"); return; }
    if (costoOrarioExtra && (isNaN(costoNumExtra) || costoNumExtra < 0)) { toast.error("Costo extra non valido"); return; }
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
        costo_orario_extra: costoOrarioExtra ? costoNumExtra : null,
        note: note || null,
      };
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
      <DialogContent className="flex max-h-[90dvh] max-w-[calc(100vw-2rem)] flex-col rounded-2xl">
        <DialogHeader className="shrink-0">
          <DialogTitle>{turno ? "Modifica turno" : "Nuovo turno"}</DialogTitle>
        </DialogHeader>
        <div className="-mx-1 min-h-0 flex-1 overflow-y-auto px-1">
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
                    onMouseDown={() => selezionaNome(n)}
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
            <p className="text-xs text-muted-foreground">
              Totale: <span className="font-medium text-foreground">{fmtOre(oreTot)}</span>
              {extraNum > 0 && stdNum > 0 && (
                <span className="ml-1 text-muted-foreground/60">({fmtOre(stdNum)} orario + {fmtOre(extraNum)} extra)</span>
              )}
              {costoTurno > 0 && (
                <span className="ml-1 text-muted-foreground/60">· costo turno {fmtEuro(costoTurno)}</span>
              )}
            </p>
          )}

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Ore extra (in più)</label>
              <Input
                type="text"
                inputMode="decimal"
                value={oreExtra}
                onChange={(e) => setOreExtra(e.target.value.replace(/[^0-9,.]/g, ""))}
                placeholder="es. 2"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Costo std (€/h)</label>
              <Input
                type="text"
                inputMode="decimal"
                value={costoOrario}
                onChange={(e) => setCostoOrario(e.target.value.replace(/[^0-9,.]/g, ""))}
                placeholder="es. 12,50"
              />
            </div>
          </div>

          {extraNum > 0 && (
            <div className="grid grid-cols-2 gap-2">
              <div />
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Costo extra (€/h)<span className="ml-1 font-normal opacity-60">se diverso</span>
                </label>
                <Input
                  type="text"
                  inputMode="decimal"
                  value={costoOrarioExtra}
                  onChange={(e) => setCostoOrarioExtra(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder={costoOrario || "es. 15,00"}
                />
              </div>
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Note</label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="opzionale" />
          </div>
        </div>
        </div>

        <div className="mt-1 flex shrink-0 gap-2 border-t border-border pt-3">
          <button onClick={onClose} disabled={saving} className="flex-1 rounded-lg border border-border py-2.5 text-sm font-medium active:scale-[0.98]">
            Annulla
          </button>
          <button onClick={salva} disabled={saving} className="flex-1 rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground active:scale-[0.98] disabled:opacity-50">
            {saving ? "Salvo…" : "Salva"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Dialog mensile (inserimento da busta paga) ──────────────────────────────────

interface MensileDialogProps {
  open: boolean;
  turno: Turno | null;       // riga mensile in modifica, o null per nuovo
  mese: string;              // YYYY-MM
  nomiSuggeriti: string[];
  onClose: () => void;
  onSaved: () => void;
}

function MensileDialog({ open, turno, mese, nomiSuggeriti, onClose, onSaved }: MensileDialogProps) {
  const [nome, setNome] = useState("");
  // Input separati ordinarie + extra; lo storage resta ore_totali / ore_extra
  // (di cui), come il desktop, cosi' API e DB non cambiano.
  const [oreOrd, setOreOrd] = useState("");
  const [oreExtra, setOreExtra] = useState("");
  const [importoOrd, setImportoOrd] = useState("");
  const [importoExtra, setImportoExtra] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [showSugg, setShowSugg] = useState(false);

  const isNuovo = !turno;
  const numOr0 = (s: string) => (s ? parseFloat(s.replace(",", ".")) : 0);
  const toInput = (v: number) => String(v).replace(".", ",");

  useEffect(() => {
    if (open) {
      setNome(turno?.nome ?? "");
      const tot = turno?.ore_dichiarate ?? 0;
      const ext = turno?.ore_extra ?? 0;
      setOreOrd(turno ? toInput(Math.max(0, Math.round((tot - ext) * 100) / 100)) : "");
      setOreExtra(turno?.ore_extra ? toInput(turno.ore_extra) : "");
      const lordo = turno?.lordo_mensile ?? 0;
      const impExt = turno?.importo_extra ?? 0;
      setImportoOrd(turno ? toInput(Math.max(0, Math.round((lordo - impExt) * 100) / 100)) : "");
      setImportoExtra(turno?.importo_extra ? toInput(turno.importo_extra) : "");
      setNote(turno?.note ?? "");
      setShowSugg(false);
    }
  }, [open, turno]);

  const suggFiltrati = nome.length > 0
    ? nomiSuggeriti.filter((n) => n.toLowerCase().includes(nome.toLowerCase()) && n !== nome)
    : [];

  const oreOrdN = numOr0(oreOrd);
  const oreExtN = numOr0(oreExtra);
  const oreTot = Math.round((oreOrdN + oreExtN) * 100) / 100;
  const impOrdN = numOr0(importoOrd);
  const impExtN = numOr0(importoExtra);
  const lordoTot = Math.round((impOrdN + impExtN) * 100) / 100;

  async function salva() {
    if (isNuovo && !nome.trim()) { toast.error("Il nome è obbligatorio"); return; }
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
          body: JSON.stringify({ nome: nome.trim(), mese, ...payload }),
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
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="flex max-h-[90dvh] max-w-[calc(100vw-2rem)] flex-col rounded-2xl">
        <DialogHeader className="shrink-0">
          <DialogTitle className="capitalize">
            {turno ? `Modifica ${turno.nome} · ${fmtMese(mese)}` : `Inserisci mese · ${fmtMese(mese)}`}
          </DialogTitle>
        </DialogHeader>
        <div className="-mx-1 min-h-0 flex-1 overflow-y-auto px-1">
          <div className="mt-1 space-y-3">
            {isNuovo && (
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
            )}

            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Ore del mese *</label>
              <div className="grid grid-cols-2 gap-2">
                <Input
                  type="text"
                  inputMode="decimal"
                  value={oreOrd}
                  onChange={(e) => setOreOrd(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder="ordinarie · es. 148"
                />
                <Input
                  type="text"
                  inputMode="decimal"
                  value={oreExtra}
                  onChange={(e) => setOreExtra(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder="extra · es. 20"
                />
              </div>
              {oreTot > 0 && (
                <p className="mt-1 text-xs text-muted-foreground">Totale ore: <span className="font-semibold tabular-nums text-foreground">{fmtOre(oreTot)}</span></p>
              )}
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Lordo del mese (€) *</label>
              <div className="grid grid-cols-2 gap-2">
                <Input
                  type="text"
                  inputMode="decimal"
                  value={importoOrd}
                  onChange={(e) => setImportoOrd(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder="ordinario · es. 1700"
                />
                <Input
                  type="text"
                  inputMode="decimal"
                  value={importoExtra}
                  onChange={(e) => setImportoExtra(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder="extra · es. 150"
                />
              </div>
              {lordoTot > 0 && (
                <p className="mt-1 text-xs text-muted-foreground">Lordo totale: <span className="font-semibold tabular-nums text-foreground">{fmtEuro(lordoTot)}</span></p>
              )}
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Note</label>
              <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="opzionale" />
            </div>
          </div>
        </div>

        <div className="mt-1 flex shrink-0 gap-2 border-t border-border pt-3">
          <button onClick={onClose} disabled={saving} className="flex-1 rounded-lg border border-border py-2.5 text-sm font-medium active:scale-[0.98]">
            Annulla
          </button>
          <button onClick={salva} disabled={saving} className="flex-1 rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground active:scale-[0.98] disabled:opacity-50">
            {saving ? "Salvo…" : "Salva"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Componente principale ──────────────────────────────────────────────────────

type Modalita = "giornaliero" | "mensile";

function TurniBody() {
  const [modalita, setModalita] = useState<Modalita>("giornaliero");
  const [lunedi, setLunedi] = useState(() => lunediDi(new Date()));
  const [meseBase, setMeseBase] = useState(() => toISO(new Date()).slice(0, 7));
  const [data, setData] = useState<PersonaleResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [giornoSel, setGiornoSel] = useState(() => toISO(new Date()));
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTurno, setEditTurno] = useState<Turno | null>(null);
  const [daEliminare, setDaEliminare] = useState<Turno | null>(null);
  const [mensileDialogOpen, setMensileDialogOpen] = useState(false);
  const [editMensile, setEditMensile] = useState<Turno | null>(null);
  const [daEliminareMensile, setDaEliminareMensile] = useState<Turno | null>(null);

  const isMensile = modalita === "mensile";

  const [da, a] = (() => {
    if (!isMensile) return [toISO(lunedi), toISO(addDays(lunedi, 6))];
    const [ay, am] = meseBase.split("-").map(Number);
    const ultimo = new Date(ay, am, 0).getDate();
    return [`${meseBase}-01`, `${meseBase}-${String(ultimo).padStart(2, "0")}`];
  })();

  const load = useCallback(async (daISO: string, aISO: string, soloMensile: boolean) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/workspace/personale?da=${daISO}&a=${aISO}&mensile=${soloMensile}`);
      if (!res.ok) throw new Error();
      setData(await res.json());
    } catch {
      toast.error("Errore caricamento turni");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(da, a, isMensile); }, [da, a, isMensile, load]);

  // Pull-to-refresh: ricarica la vista corrente. Listener registrato UNA sola
  // volta; legge da/a/modalita correnti da un ref invece di riattaccarsi.
  const vista = useRef({ da, a, isMensile });
  vista.current = { da, a, isMensile };
  useEffect(() => {
    const h = () => load(vista.current.da, vista.current.a, vista.current.isMensile);
    window.addEventListener("oneflux:refresh", h);
    return () => window.removeEventListener("oneflux:refresh", h);
  }, [load]);

  function navPrev() {
    if (!isMensile) { setLunedi((d) => addDays(d, -7)); return; }
    const [ay, am] = meseBase.split("-").map(Number);
    const prev = new Date(ay, am - 2, 1);
    setMeseBase(`${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`);
  }
  function navNext() {
    if (!isMensile) { setLunedi((d) => addDays(d, 7)); return; }
    const [ay, am] = meseBase.split("-").map(Number);
    const next = new Date(ay, am, 1);
    setMeseBase(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`);
  }

  async function elimina(t: Turno) {
    try {
      const res = await fetch(`/api/workspace/personale/${t.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success(t.mensile ? "Mese eliminato" : "Turno eliminato");
      load(da, a, isMensile);
    } catch {
      toast.error("Errore eliminazione");
    }
  }

  const giorni = useMemo(
    () =>
      Array.from({ length: 7 }, (_, i) => {
        const d = addDays(lunedi, i);
        return { iso: toISO(d), label: GIORNI[i], num: d.getDate() };
      }),
    [lunedi],
  );

  const turni = useMemo(() => data?.turni ?? [], [data]);

  const turniGiorno = useMemo(
    () =>
      turni
        .filter((t) => t.data_turno === giornoSel)
        .sort((x, y) => x.ora_inizio.localeCompare(y.ora_inizio)),
    [turni, giornoSel],
  );

  const oggiISO = toISO(new Date());
  const turniPerGiorno = useMemo(() => {
    const m: Record<string, number> = {};
    for (const t of turni) m[t.data_turno] = (m[t.data_turno] ?? 0) + 1;
    return m;
  }, [turni]);

  // Vista mensile: una riga per dipendente (ordinata per nome).
  const righeMensili = useMemo(
    () => [...turni].sort((x, y) => x.nome.localeCompare(y.nome)),
    [turni],
  );
  const costoMeseTot = useMemo(
    () => righeMensili.reduce((s, t) => s + (t.lordo_mensile ?? 0), 0),
    [righeMensili],
  );

  const fmtSett = `${lunedi.getDate()} ${MESI[lunedi.getMonth()]} – ${addDays(lunedi, 6).getDate()} ${MESI[addDays(lunedi, 6).getMonth()]}`;

  return (
    <div className="space-y-4">
      {/* Toggle modalità: turni giornalieri vs totali mensili */}
      <div className="grid grid-cols-2 gap-1 rounded-xl border bg-card p-1">
        {([
          { k: "giornaliero" as Modalita, l: "Giornalieri" },
          { k: "mensile" as Modalita, l: "Totali mensili" },
        ]).map((s) => (
          <button
            key={s.k}
            onClick={() => setModalita(s.k)}
            className={`rounded-lg py-2 text-sm font-medium transition-colors ${
              modalita === s.k ? "bg-primary text-primary-foreground" : "text-muted-foreground active:bg-muted"
            }`}
          >
            {s.l}
          </button>
        ))}
      </div>

      {/* Selettore periodo */}
      <div className="flex items-center justify-between rounded-2xl border bg-card px-2 py-2">
        <button onClick={navPrev} className="rounded-full p-2 active:bg-muted">
          <ChevronLeft className="size-5" />
        </button>
        <span className="text-sm font-semibold capitalize">{isMensile ? fmtMese(meseBase) : fmtSett}</span>
        <button onClick={navNext} className="rounded-full p-2 active:bg-muted">
          <ChevronRight className="size-5" />
        </button>
      </div>

      {isMensile ? (
        // ── Vista mensile ──────────────────────────────────────────────────────
        <>
          {costoMeseTot > 0 && (
            <div className="rounded-2xl ring-1 ring-sky-500/60 bg-sky-50 p-3 dark:bg-sky-950/20">
              <p className="text-xs font-medium text-sky-700 dark:text-sky-500">Costo personale del mese</p>
              <p className="text-lg font-bold tabular-nums text-sky-700 dark:text-sky-400">{fmtEuro(costoMeseTot)}</p>
            </div>
          )}
          <div className="space-y-2.5">
            {loading ? (
              <div className="space-y-2.5">
                {[0, 1].map((i) => <div key={i} className="h-[68px] animate-pulse rounded-xl border bg-muted/40" />)}
              </div>
            ) : righeMensili.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Nessun inserimento mensile. Usa + per aggiungere i totali da busta paga.
              </p>
            ) : (
              righeMensili.map((t) => {
                const ore = calcolaOreTotali(t);
                const ext = t.ore_extra ?? 0;
                return (
                  <div key={t.id} className="flex items-center gap-3 rounded-xl border bg-card p-3.5">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-bold text-primary">
                      {t.nome.slice(0, 2).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{t.nome}</p>
                      <p className="text-xs text-muted-foreground">
                        {fmtOre(ore)}{ext > 0 && <span className="text-amber-600 dark:text-amber-400"> · +{fmtOre(ext)} str.</span>}
                        {(t.lordo_mensile ?? 0) > 0 && <span className="text-sky-700 dark:text-sky-400"> · {fmtEuro(t.lordo_mensile!)}</span>}
                      </p>
                      {t.note && <p className="truncate text-xs text-muted-foreground/80">{t.note}</p>}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <button onClick={() => { setEditMensile(t); setMensileDialogOpen(true); }} className="rounded-md p-1.5 text-muted-foreground active:bg-muted">
                        <Pencil className="size-4" />
                      </button>
                      <button onClick={() => setDaEliminareMensile(t)} className="rounded-md p-1.5 text-muted-foreground active:bg-muted active:text-destructive">
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </>
      ) : (
        // ── Vista giornaliera ──────────────────────────────────────────────────
        <>
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
              <div className="space-y-2.5">
                {[0, 1].map((i) => <div key={i} className="h-[68px] animate-pulse rounded-xl border bg-muted/40" />)}
              </div>
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
                      {orarioTurno(t)} · {fmtOre(calcolaOreTotali(t))}
                      {(t.ore_extra ?? 0) > 0 && <span className="text-amber-600 dark:text-amber-400"> · +{fmtOre(t.ore_extra!)} extra</span>}
                    </p>
                    {t.note && <p className="truncate text-xs text-muted-foreground/80">{t.note}</p>}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <button onClick={() => { setEditTurno(t); setDialogOpen(true); }} className="rounded-md p-1.5 text-muted-foreground active:bg-muted">
                      <Pencil className="size-4" />
                    </button>
                    <button onClick={() => setDaEliminare(t)} className="rounded-md p-1.5 text-muted-foreground active:bg-muted active:text-destructive">
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </>
      )}

      {/* FAB */}
      <button
        onClick={() => {
          if (isMensile) { setEditMensile(null); setMensileDialogOpen(true); }
          else { setEditTurno(null); setDialogOpen(true); }
        }}
        className="fixed right-5 z-40 flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg active:scale-95"
        style={{ bottom: "calc(80px + env(safe-area-inset-bottom))" }}
        aria-label={isMensile ? "Inserisci mese" : "Nuovo turno"}
      >
        <Plus className="size-7" />
      </button>

      <TurnoDialog
        open={dialogOpen}
        turno={editTurno}
        dataDefault={giornoSel}
        nomiSuggeriti={data?.nomi ?? []}
        costiNoti={data?.costi_noti ?? {}}
        onClose={() => { setDialogOpen(false); setEditTurno(null); }}
        onSaved={() => load(da, a, isMensile)}
      />

      <MensileDialog
        open={mensileDialogOpen}
        turno={editMensile}
        mese={meseBase}
        nomiSuggeriti={data?.nomi ?? []}
        onClose={() => { setMensileDialogOpen(false); setEditMensile(null); }}
        onSaved={() => load(da, a, isMensile)}
      />

      <ConfirmDialog
        open={daEliminare !== null}
        titolo="Eliminare il turno?"
        messaggio={daEliminare ? `Il turno di ${daEliminare.nome} verrà rimosso.` : undefined}
        onConferma={() => { if (daEliminare) elimina(daEliminare); }}
        onClose={() => setDaEliminare(null)}
      />

      <ConfirmDialog
        open={daEliminareMensile !== null}
        titolo="Eliminare l'inserimento mensile?"
        messaggio={daEliminareMensile ? `I totali di ${daEliminareMensile.nome} per ${fmtMese(meseBase)} verranno rimossi.` : undefined}
        onConferma={() => { if (daEliminareMensile) elimina(daEliminareMensile); }}
        onClose={() => setDaEliminareMensile(null)}
      />
    </div>
  );
}
