"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { toast } from "sonner";
import {
  AlertTriangle, Calendar, CalendarDays, Check, ChevronDown, ChevronRight,
  List, Pencil, Plus, Settings2, Trash2, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  type Documento, type CalendarGiorno, type RegolaPagamento,
  computeKpi, bucketizeDocumenti, formatEuro, formatDate, MODALITA_LABELS,
} from "@/lib/scadenziario";

// ── KPI Bar ──────────────────────────────────────────────────────────────────

type KpiCardProps = {
  label: string;
  count: number;
  totale: number;
  tone: "rose" | "orange" | "sky" | "emerald";
};

const TONE_CLASSES = {
  rose:    "border-rose-500/40 hover:border-rose-500/70 [--val:theme(colors.rose.600)]",
  orange:  "border-orange-500/40 hover:border-orange-500/70 [--val:theme(colors.orange.600)]",
  sky:     "border-sky-500/40 hover:border-sky-500/70 [--val:theme(colors.sky.600)]",
  emerald: "border-emerald-500/40 hover:border-emerald-500/70 [--val:theme(colors.emerald.600)]",
};
const TONE_VALUE = {
  rose:    "text-rose-600 dark:text-rose-400",
  orange:  "text-orange-600 dark:text-orange-400",
  sky:     "text-sky-600 dark:text-sky-400",
  emerald: "text-emerald-600 dark:text-emerald-400",
};

function KpiCard({ label, count, totale, tone }: KpiCardProps) {
  return (
    <div className={`rounded-lg border bg-card px-4 pt-3 pb-3 transition-colors flex flex-col gap-1 ${TONE_CLASSES[tone]}`}>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <p className={`text-2xl font-bold tracking-tight ${TONE_VALUE[tone]}`}>{formatEuro(totale)}</p>
      <p className="text-[11px] text-muted-foreground">{count} fattur{count === 1 ? "a" : "e"}</p>
    </div>
  );
}

// ── Source badge ─────────────────────────────────────────────────────────────

function ScadenzaBadge({ source }: { source: string | null }) {
  if (!source || source === "stored") return null;
  const map: Record<string, { label: string; className: string }> = {
    override: { label: "manuale", className: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400" },
    xml:      { label: "da fattura", className: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400" },
    fornitore: { label: "da regola", className: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400" },
    fornitore_rid: { label: "RID", className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400" },
    none: { label: "nessuna", className: "bg-muted text-muted-foreground" },
  };
  const entry = map[source] ?? { label: source, className: "bg-muted text-muted-foreground" };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${entry.className}`}>
      {entry.label}
    </span>
  );
}

// ── Documento row ────────────────────────────────────────────────────────────

type DocumentoRowProps = {
  doc: Documento;
  selected: boolean;
  onToggleSelect: () => void;
  onPaga: (doc: Documento) => void;
  onPeek: (doc: Documento) => void;
};

function DocumentoRow({ doc, selected, onToggleSelect, onPaga, onPeek }: DocumentoRowProps) {
  const isOverdue = !doc.pagata && doc.scadenza_effettiva && new Date(doc.scadenza_effettiva) < new Date();

  return (
    <div
      className={`flex items-center gap-3 px-3 py-2.5 rounded-md transition-colors cursor-pointer group
        ${selected ? "bg-primary/8" : "hover:bg-muted/50"}
        ${isOverdue && !doc.pagata ? "border-l-2 border-rose-500/60" : ""}`}
      onClick={() => onPeek(doc)}
    >
      <input
        type="checkbox"
        checked={selected}
        className="size-4 cursor-pointer flex-shrink-0 accent-primary"
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => { e.stopPropagation(); onToggleSelect(); }}
      />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm truncate max-w-[200px]">{doc.fornitore}</span>
          {doc.numero_documento && (
            <span className="text-xs text-muted-foreground">#{doc.numero_documento}</span>
          )}
          <ScadenzaBadge source={doc.scadenza_source} />
        </div>
        <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground flex-wrap">
          {doc.data_documento && <span>Fattura: {formatDate(doc.data_documento)}</span>}
          {doc.scadenza_effettiva && (
            <span className={isOverdue && !doc.pagata ? "text-rose-600 font-medium" : ""}>
              Scade: {formatDate(doc.scadenza_effettiva)}
            </span>
          )}
        </div>
      </div>

      <div className="text-right flex-shrink-0">
        <p className="font-semibold text-sm">{formatEuro(doc.totale_documento)}</p>
      </div>

      {!doc.pagata && (
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs flex-shrink-0 gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={(e) => { e.stopPropagation(); onPaga(doc); }}
        >
          <Check className="size-3" /> Paga
        </Button>
      )}
    </div>
  );
}

// ── Agenda section ───────────────────────────────────────────────────────────

type AgendaSectionProps = {
  title: string;
  docs: Documento[];
  defaultOpen?: boolean;
  selectedFileOrigini: Set<string>;
  onToggleSelect: (fo: string) => void;
  onPaga: (doc: Documento) => void;
  onPeek: (doc: Documento) => void;
  accentClass?: string;
};

function AgendaSection({
  title, docs, defaultOpen = true,
  selectedFileOrigini, onToggleSelect, onPaga, onPeek, accentClass = "",
}: AgendaSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  if (docs.length === 0) return null;

  const totale = docs.reduce((s, d) => s + (d.totale_documento || 0), 0);

  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/30 transition-colors"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="size-4 text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}
          <span className={`font-semibold text-sm ${accentClass}`}>{title}</span>
          <span className="text-xs text-muted-foreground bg-muted rounded-full px-2 py-0.5">{docs.length}</span>
        </div>
        <span className="text-sm font-medium text-muted-foreground">{formatEuro(totale)}</span>
      </button>

      {open && (
        <div className="border-t divide-y divide-border/50">
          {docs.map((doc) => (
            <DocumentoRow
              key={doc.file_origine}
              doc={doc}
              selected={selectedFileOrigini.has(doc.file_origine)}
              onToggleSelect={() => onToggleSelect(doc.file_origine)}
              onPaga={onPaga}
              onPeek={onPeek}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Calendar view ────────────────────────────────────────────────────────────

const MESI = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];
const GIORNI_SETTIMANA = ["Lun","Mar","Mer","Gio","Ven","Sab","Dom"];

type CalendarViewProps = {
  documenti: Documento[];
};

function CalendarView({ documenti }: CalendarViewProps) {
  const today = new Date();
  const [anno, setAnno] = useState(today.getFullYear());
  const [mese, setMese] = useState(today.getMonth()); // 0-based
  const [selectedDay, setSelectedDay] = useState<number | null>(null);

  const agg = useMemo(() => {
    const map: Record<number, { totale: number; count: number }> = {};
    for (const doc of documenti) {
      if (doc.pagata || !doc.scadenza_effettiva) continue;
      const dt = new Date(doc.scadenza_effettiva);
      if (dt.getFullYear() === anno && dt.getMonth() === mese) {
        const d = dt.getDate();
        if (!map[d]) map[d] = { totale: 0, count: 0 };
        map[d].totale += doc.totale_documento || 0;
        map[d].count += 1;
      }
    }
    return map;
  }, [documenti, anno, mese]);

  const maxVal = useMemo(() => Math.max(0, ...Object.values(agg).map(v => v.totale)), [agg]);

  const firstDay = new Date(anno, mese, 1).getDay(); // 0=domenica
  const startOffset = firstDay === 0 ? 6 : firstDay - 1; // lun=0
  const daysInMonth = new Date(anno, mese + 1, 0).getDate();

  function prevMonth() {
    if (mese === 0) { setAnno(a => a - 1); setMese(11); }
    else setMese(m => m - 1);
    setSelectedDay(null);
  }
  function nextMonth() {
    if (mese === 11) { setAnno(a => a + 1); setMese(0); }
    else setMese(m => m + 1);
    setSelectedDay(null);
  }

  const dayDocs = useMemo(() => {
    if (!selectedDay) return [];
    return documenti.filter(d => {
      if (d.pagata || !d.scadenza_effettiva) return false;
      const dt = new Date(d.scadenza_effettiva);
      return dt.getFullYear() === anno && dt.getMonth() === mese && dt.getDate() === selectedDay;
    });
  }, [documenti, anno, mese, selectedDay]);

  const cells: (number | null)[] = [
    ...Array(startOffset).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  return (
    <div className="rounded-lg border bg-card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="icon" className="size-8" onClick={prevMonth}>
          <ChevronRight className="size-4 rotate-180" />
        </Button>
        <span className="font-semibold text-sm">{MESI[mese]} {anno}</span>
        <Button variant="ghost" size="icon" className="size-8" onClick={nextMonth}>
          <ChevronRight className="size-4" />
        </Button>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {GIORNI_SETTIMANA.map(g => (
          <div key={g} className="text-center text-[10px] text-muted-foreground font-medium py-1">{g}</div>
        ))}
        {cells.map((day, i) => {
          if (!day) return <div key={`e-${i}`} />;
          const data = agg[day];
          const totale = data?.totale || 0;
          const count = data?.count || 0;
          const isToday = anno === today.getFullYear() && mese === today.getMonth() && day === today.getDate();
          const hasAmount = totale > 0;
          const intensity = hasAmount && maxVal > 0 ? totale / maxVal : 0;
          const bgOpacity = hasAmount ? Math.max(0.18, intensity * 0.85) : 0;
          const isSelected = selectedDay === day;
          // testo bianco su sfondi scuri (intensity > 0.3), grigio scuro su sfondi chiari
          const onBg = !isSelected && hasAmount ? (intensity > 0.35 ? "text-white" : "text-orange-950") : "";

          return (
            <button
              key={day}
              onClick={() => setSelectedDay(isSelected ? null : day)}
              className={`relative flex flex-col items-center justify-center rounded-md py-1.5 transition-colors text-xs gap-0
                ${isToday ? "ring-2 ring-primary ring-offset-1" : ""}
                ${isSelected ? "bg-primary text-primary-foreground" : hasAmount ? "" : "hover:bg-muted/50"}
              `}
              style={hasAmount && !isSelected ? { backgroundColor: `rgba(194,65,12,${bgOpacity})` } : {}}
            >
              <span className={`font-semibold leading-none ${isToday && !isSelected ? "text-primary" : ""} ${onBg}`}>{day}</span>
              {hasAmount && (
                <>
                  <span className={`text-[9px] leading-none mt-0.5 font-medium ${isSelected ? "text-primary-foreground/90" : onBg}`}>
                    {totale >= 1000 ? `${(totale / 1000).toFixed(1)}k` : Math.round(totale).toString()}€
                  </span>
                  <span className={`text-[8px] leading-none mt-0.5 ${isSelected ? "text-primary-foreground/70" : onBg} opacity-80`}>
                    {count} fatt.
                  </span>
                </>
              )}
            </button>
          );
        })}
      </div>

      {selectedDay && dayDocs.length > 0 && (
        <div className="border-t pt-3 space-y-2">
          <p className="text-xs font-medium text-muted-foreground">{selectedDay} {MESI[mese]} — {dayDocs.length} fattur{dayDocs.length === 1 ? "a" : "e"}</p>
          {dayDocs.map(doc => (
            <div key={doc.file_origine} className="flex items-center justify-between text-sm px-1">
              <span className="truncate max-w-[200px] text-muted-foreground">{doc.fornitore}</span>
              <span className="font-medium ml-2">{formatEuro(doc.totale_documento)}</span>
            </div>
          ))}
          <p className="text-right text-xs font-semibold pt-1 border-t">
            Totale: {formatEuro(dayDocs.reduce((s, d) => s + (d.totale_documento || 0), 0))}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Peek Dialog (centrato) ────────────────────────────────────────────────────

type RigaFattura = {
  numero_riga: number;
  descrizione: string;
  quantita: number | null;
  unita_misura: string | null;
  prezzo_unitario: number | null;
  iva_percentuale: number | null;
  totale_riga: number;
  categoria: string | null;
};

type PeekDialogProps = {
  doc: Documento | null;
  onClose: () => void;
  onPaga: (doc: Documento, pagata: boolean) => void;
  onSetScadenza: (doc: Documento, data: string | null) => Promise<void>;
};

function PeekDialog({ doc, onClose, onPaga, onSetScadenza }: PeekDialogProps) {
  const [editingScadenza, setEditingScadenza] = useState(false);
  const [scadenzaInput, setScadenzaInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [anteprimaOpen, setAnteprimaOpen] = useState(false);
  const [righe, setRighe] = useState<RigaFattura[]>([]);
  const [loadingRighe, setLoadingRighe] = useState(false);

  useEffect(() => {
    if (doc) { setScadenzaInput(doc.scadenza_effettiva ?? ""); }
    setEditingScadenza(false);
    setAnteprimaOpen(false);
    setRighe([]);
  }, [doc]);

  async function handleToggleAnteprima() {
    if (anteprimaOpen) { setAnteprimaOpen(false); return; }
    if (righe.length > 0) { setAnteprimaOpen(true); return; }
    if (!doc) return;
    setLoadingRighe(true);
    setAnteprimaOpen(true);
    try {
      const res = await fetch(`/api/scadenziario/anteprima?file_origine=${encodeURIComponent(doc.file_origine)}`);
      if (res.ok) { const d = await res.json(); setRighe(d.righe ?? []); }
    } catch { /* silenzioso */ }
    finally { setLoadingRighe(false); }
  }

  async function handleSaveScadenza() {
    if (!doc) return;
    setSaving(true);
    try {
      await onSetScadenza(doc, scadenzaInput || null);
      setEditingScadenza(false);
      toast.success("Scadenza aggiornata");
    } catch {
      toast.error("Errore nel salvataggio");
    } finally {
      setSaving(false);
    }
  }

  async function handleResetScadenza() {
    if (!doc) return;
    setSaving(true);
    try {
      await onSetScadenza(doc, null);
      setScadenzaInput("");
      setEditingScadenza(false);
      toast.success("Scadenza manuale rimossa");
    } catch {
      toast.error("Errore");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={!!doc} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        {doc && (
          <>
            <DialogHeader>
              <DialogTitle>{doc.fornitore}</DialogTitle>
              <DialogDescription>
                {doc.numero_documento ? `Fattura #${doc.numero_documento}` : "Documento"} · {formatDate(doc.data_documento)}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-5 pt-2">
              {/* Riepilogo */}
              <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Totale documento</span>
                  <span className="font-bold text-lg">{formatEuro(doc.totale_documento)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Tipo</span>
                  <span>{doc.tipo_documento || "TD01"}</span>
                </div>
                <div className="flex justify-between text-sm items-center gap-2">
                  <span className="text-muted-foreground">Stato</span>
                  <span className={`font-medium ${doc.pagata ? "text-emerald-600" : ""}`}>
                    {doc.pagata ? `Pagata${doc.pagata_at ? ` il ${formatDate(doc.pagata_at)}` : ""}` : doc.stato_scadenza}
                  </span>
                </div>
              </div>

              {/* Scadenza */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label className="text-sm font-medium">Scadenza</Label>
                  {!editingScadenza && (
                    <Button variant="ghost" size="sm" className="h-7 text-xs gap-1" onClick={() => setEditingScadenza(true)}>
                      <Pencil className="size-3" /> Modifica data
                    </Button>
                  )}
                </div>
                {!editingScadenza ? (
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm">{formatDate(doc.scadenza_effettiva)}</span>
                    <ScadenzaBadge source={doc.scadenza_source} />
                    {doc.scadenza_source === "override" && (
                      <Button variant="ghost" size="sm" className="h-6 text-xs text-muted-foreground ml-auto gap-1"
                        onClick={handleResetScadenza} disabled={saving}>
                        <X className="size-3" /> Rimuovi
                      </Button>
                    )}
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <Input type="date" value={scadenzaInput} onChange={(e) => setScadenzaInput(e.target.value)} disabled={saving} className="flex-1" />
                    <Button size="sm" className="h-9" onClick={handleSaveScadenza} disabled={saving || !scadenzaInput}>
                      {saving ? "..." : "Salva"}
                    </Button>
                    <Button variant="outline" size="sm" className="h-9" onClick={() => setEditingScadenza(false)}>Annulla</Button>
                  </div>
                )}
              </div>

              <Separator />

              {/* Anteprima fattura */}
              <div>
                <button
                  className="flex items-center gap-2 text-sm font-medium w-full text-left hover:text-primary transition-colors"
                  onClick={handleToggleAnteprima}
                >
                  {anteprimaOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                  Anteprima fattura
                  {!anteprimaOpen && righe.length === 0 && (
                    <span className="text-xs text-muted-foreground ml-1">(clicca per caricare)</span>
                  )}
                  {righe.length > 0 && (
                    <span className="text-xs text-muted-foreground ml-1">{righe.length} righe</span>
                  )}
                </button>

                {anteprimaOpen && (
                  <div className="mt-3 rounded-lg border overflow-hidden">
                    {loadingRighe ? (
                      <div className="px-4 py-6 text-center text-sm text-muted-foreground">Caricamento...</div>
                    ) : righe.length === 0 ? (
                      <div className="px-4 py-6 text-center text-sm text-muted-foreground">Nessuna riga trovata.</div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead className="bg-muted/50">
                            <tr>
                              <th className="text-left px-3 py-2 text-muted-foreground font-medium">Descrizione</th>
                              <th className="text-right px-3 py-2 text-muted-foreground font-medium">Qtà</th>
                              <th className="text-left px-3 py-2 text-muted-foreground font-medium">UM</th>
                              <th className="text-right px-3 py-2 text-muted-foreground font-medium">Prezzo</th>
                              <th className="text-right px-3 py-2 text-muted-foreground font-medium">IVA%</th>
                              <th className="text-right px-3 py-2 text-muted-foreground font-medium">Totale</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/50">
                            {righe.map((r, i) => (
                              <tr key={i} className="hover:bg-muted/20">
                                <td className="px-3 py-2 max-w-[260px]">
                                  <p className="truncate" title={r.descrizione}>{r.descrizione}</p>
                                  {r.categoria && <p className="text-[10px] text-muted-foreground">{r.categoria}</p>}
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums">{r.quantita ?? "—"}</td>
                                <td className="px-3 py-2 text-muted-foreground">{r.unita_misura ?? ""}</td>
                                <td className="px-3 py-2 text-right tabular-nums">
                                  {r.prezzo_unitario != null ? `€${r.prezzo_unitario.toFixed(4)}` : "—"}
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{r.iva_percentuale ?? "—"}%</td>
                                <td className="px-3 py-2 text-right tabular-nums font-medium">{formatEuro(r.totale_riga)}</td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot className="border-t bg-muted/30">
                            <tr>
                              <td colSpan={5} className="px-3 py-2 text-right text-xs font-semibold text-muted-foreground">Totale</td>
                              <td className="px-3 py-2 text-right font-bold">
                                {formatEuro(righe.reduce((s, r) => s + (r.totale_riga || 0), 0))}
                              </td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <Separator />

              {/* Azione pagamento */}
              <div>
                {doc.pagata ? (
                  <Button variant="outline" className="w-full" onClick={() => { onPaga(doc, false); onClose(); }}>
                    Segna come non pagata
                  </Button>
                ) : (
                  <Button className="w-full gap-2" onClick={() => { onPaga(doc, true); onClose(); }}>
                    <Check className="size-4" /> Segna come pagata
                  </Button>
                )}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ── Regole Dialog (centrato) ──────────────────────────────────────────────────

type FornitoreOption = { fornitore: string; piva_fornitore: string | null };

type RegoleDialogProps = {
  open: boolean;
  onClose: () => void;
};

function RegoleDialog({ open, onClose }: RegoleDialogProps) {
  const [regole, setRegole] = useState<RegolaPagamento[]>([]);
  const [fornitori, setFornitori] = useState<FornitoreOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [selectedFornitore, setSelectedFornitore] = useState<FornitoreOption | null>(null);
  const [pivaManuale, setPivaManuale] = useState("");
  const [modalitaInput, setModalitaInput] = useState("30gg");
  const [noteInput, setNoteInput] = useState("");
  const [saving, setSaving] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [resRegole, resFornitori] = await Promise.all([
        fetch("/api/scadenziario/regole"),
        fetch("/api/scadenziario/fornitori"),
      ]);
      if (resRegole.ok) {
        const d = await resRegole.json();
        setRegole(d.regole ?? []);
      }
      if (resFornitori.ok) {
        const d = await resFornitori.json();
        setFornitori(d.fornitori ?? []);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (open) loadAll(); }, [open, loadAll]);

  // Fornitori già configurati → non mostrarli nel select
  const fornitoriDisponibili = useMemo(() => {
    const giaCon = new Set(regole.map(r => r.piva_fornitore));
    return fornitori.filter(f => !f.piva_fornitore || !giaCon.has(f.piva_fornitore));
  }, [fornitori, regole]);

  const pivaEffettiva = selectedFornitore?.piva_fornitore ?? pivaManuale.trim();
  const canSave = !!selectedFornitore && !!pivaEffettiva;

  async function handleAdd() {
    if (!selectedFornitore || !pivaEffettiva) return;
    setSaving(true);
    try {
      const res = await fetch("/api/scadenziario/regole", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          piva_fornitore: pivaEffettiva,
          modalita: modalitaInput,
          note: noteInput || undefined,
        }),
      });
      if (!res.ok) {
        const d = await res.json();
        toast.error(d.detail || "Errore salvataggio");
        return;
      }
      toast.success("Regola salvata");
      setSelectedFornitore(null); setPivaManuale(""); setNoteInput(""); setAdding(false);
      await loadAll();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await fetch(`/api/scadenziario/regole/${id}`, { method: "DELETE" });
      setRegole(r => r.filter(x => x.id !== id));
      toast.success("Regola eliminata");
    } catch {
      toast.error("Errore eliminazione");
    }
  }

  // Mappa piva → nome fornitore per mostrarlo nella lista regole
  const pivaToNome = useMemo(() => {
    const m: Record<string, string> = {};
    for (const f of fornitori) if (f.piva_fornitore) m[f.piva_fornitore] = f.fornitore;
    return m;
  }, [fornitori]);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { setAdding(false); onClose(); } }}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Regole Scadenza Fornitori</DialogTitle>
          <DialogDescription>
            Definisci i termini di pagamento per fornitore. Sovrascrivono i dati della fattura XML.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 pt-2">
          {loading ? (
            <p className="text-sm text-muted-foreground text-center py-6">Caricamento...</p>
          ) : (
            <>
              {regole.length === 0 && !adding && (
                <p className="text-sm text-muted-foreground text-center py-6">Nessuna regola configurata.</p>
              )}

              {regole.map(reg => (
                <div key={reg.id} className="flex items-start justify-between gap-3 rounded-lg border bg-muted/20 p-3">
                  <div className="space-y-0.5 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {pivaToNome[reg.piva_fornitore] || reg.piva_fornitore}
                    </p>
                    <p className="text-xs text-muted-foreground font-mono">{reg.piva_fornitore}</p>
                    <p className="text-xs text-muted-foreground">{MODALITA_LABELS[reg.modalita] ?? reg.modalita}</p>
                    {reg.note && <p className="text-xs text-muted-foreground italic">{reg.note}</p>}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-8 text-muted-foreground hover:text-destructive flex-shrink-0"
                    onClick={() => handleDelete(reg.id)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              ))}

              {adding ? (
                <div className="rounded-lg border p-4 space-y-3 bg-muted/10">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Nuova regola</p>

                  <div className="space-y-1.5">
                    <Label>Fornitore</Label>
                    <Select
                      value={selectedFornitore?.fornitore ?? ""}
                      onValueChange={(nome) => {
                        const found = fornitoriDisponibili.find(f => f.fornitore === nome);
                        setSelectedFornitore(found ?? null);
                        setPivaManuale("");
                      }}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Seleziona fornitore…" />
                      </SelectTrigger>
                      <SelectContent>
                        {fornitoriDisponibili.length === 0 ? (
                          <div className="px-3 py-2 text-sm text-muted-foreground">
                            Tutti i fornitori hanno già una regola.
                          </div>
                        ) : (
                          fornitoriDisponibili.map(f => (
                            <SelectItem key={f.fornitore} value={f.fornitore}>
                              <span className="font-medium">{f.fornitore}</span>
                              {f.piva_fornitore && (
                                <span className="ml-2 text-xs text-muted-foreground font-mono">{f.piva_fornitore}</span>
                              )}
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>
                  </div>

                  {selectedFornitore && !selectedFornitore.piva_fornitore && (
                    <div className="space-y-1.5">
                      <Label>
                        P.IVA fornitore
                        <span className="ml-1 text-xs text-muted-foreground">(non rilevata dall'XML, inserisci manualmente)</span>
                      </Label>
                      <Input
                        placeholder="12345678901"
                        value={pivaManuale}
                        onChange={e => setPivaManuale(e.target.value)}
                        disabled={saving}
                        className="font-mono"
                      />
                    </div>
                  )}

                  {selectedFornitore?.piva_fornitore && (
                    <p className="text-xs text-muted-foreground font-mono">
                      P.IVA: {selectedFornitore.piva_fornitore}
                    </p>
                  )}

                  <div className="space-y-1.5">
                    <Label>Modalità pagamento</Label>
                    <Select value={modalitaInput} onValueChange={setModalitaInput}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(MODALITA_LABELS).map(([k, v]) => (
                          <SelectItem key={k} value={k}>{v}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <Label>Note (opzionale)</Label>
                    <Input
                      placeholder="es. addebito IBAN IT..."
                      value={noteInput}
                      onChange={e => setNoteInput(e.target.value)}
                      disabled={saving}
                    />
                  </div>

                  <div className="flex gap-2 pt-1">
                    <Button
                      size="sm"
                      className="flex-1"
                      onClick={handleAdd}
                      disabled={saving || !canSave}
                    >
                      {saving ? "Salvataggio..." : "Salva regola"}
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => { setAdding(false); setSelectedFornitore(null); setPivaManuale(""); }}>
                      Annulla
                    </Button>
                  </div>
                </div>
              ) : fornitoriDisponibili.length > 0 ? (
                <Button variant="outline" className="w-full gap-2" onClick={() => setAdding(true)}>
                  <Plus className="size-4" /> Aggiungi regola
                </Button>
              ) : fornitori.length > 0 ? (
                <p className="text-xs text-center text-muted-foreground py-2">
                  Tutti i fornitori hanno già una regola configurata.
                </p>
              ) : (
                <p className="text-xs text-center text-muted-foreground py-2">
                  Nessun fornitore trovato. Carica prima le fatture.
                </p>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type View = "agenda" | "calendario";

export function ScadenziarioClient({ initialDocumenti }: { initialDocumenti: Documento[] }) {
  const [documenti, setDocumenti] = useState<Documento[]>(initialDocumenti);
  const [view, setView] = useState<View>("agenda");
  const [selectedFileOrigini, setSelectedFileOrigini] = useState<Set<string>>(new Set());
  const [peekDoc, setPeekDoc] = useState<Documento | null>(null);
  const [regoleOpen, setRegoleOpen] = useState(false);
  const [bulkPaying, setBulkPaying] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const kpi = useMemo(() => computeKpi(documenti), [documenti]);
  const buckets = useMemo(() => bucketizeDocumenti(documenti), [documenti]);

  const loadData = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await fetch("/api/scadenziario");
      if (res.ok) {
        const data = await res.json();
        setDocumenti(data.documenti ?? []);
      }
    } finally {
      setRefreshing(false);
    }
  }, []);

  function toggleSelect(fo: string) {
    setSelectedFileOrigini(prev => {
      const next = new Set(prev);
      if (next.has(fo)) next.delete(fo); else next.add(fo);
      return next;
    });
  }

  async function handlePaga(doc: Documento, pagata = true) {
    try {
      const res = await fetch("/api/scadenziario/pagata", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_origini: [doc.file_origine], pagata }),
      });
      if (!res.ok) { toast.error("Errore nel salvataggio"); return; }
      toast.success(pagata ? "Fattura segnata come pagata" : "Pagamento annullato");
      await loadData();
    } catch {
      toast.error("Errore di connessione");
    }
  }

  async function handleBulkPaga() {
    if (selectedFileOrigini.size === 0) return;
    setBulkPaying(true);
    try {
      const res = await fetch("/api/scadenziario/pagata", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_origini: Array.from(selectedFileOrigini), pagata: true }),
      });
      const data = await res.json();
      if (!res.ok) { toast.error("Errore nel salvataggio"); return; }
      toast.success(`${data.aggiornate} fattur${data.aggiornate === 1 ? "a segnata" : "e segnate"} come pagate`);
      setSelectedFileOrigini(new Set());
      await loadData();
    } catch {
      toast.error("Errore di connessione");
    } finally {
      setBulkPaying(false);
    }
  }

  async function handleSetScadenza(doc: Documento, scadenza_override: string | null) {
    const res = await fetch("/api/scadenziario/scadenza", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_origine: doc.file_origine, scadenza_override }),
    });
    if (!res.ok) throw new Error("Errore salvataggio");
    await loadData();
  }

  const sharedProps = {
    selectedFileOrigini,
    onToggleSelect: toggleSelect,
    onPaga: (doc: Documento) => handlePaga(doc, true),
    onPeek: setPeekDoc,
  };

  return (
    <div className="space-y-5 pb-20">
      {/* KPI bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Scadute" count={kpi.scadute_count} totale={kpi.scadute_totale} tone="rose" />
        <KpiCard label="Questa settimana" count={kpi.settimana_count} totale={kpi.settimana_totale} tone="orange" />
        <KpiCard label="Da pagare" count={kpi.da_pagare_count} totale={kpi.da_pagare_totale} tone="sky" />
        <KpiCard label="Pagate (mese)" count={kpi.pagate_mese_count} totale={kpi.pagate_mese_totale} tone="emerald" />
      </div>

      {/* Alert senza scadenza */}
      {buckets.senzaScadenza.length > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-500/40 bg-amber-50 dark:bg-amber-900/10 px-4 py-3 text-sm">
          <AlertTriangle className="size-4 text-amber-600 flex-shrink-0" />
          <span className="text-amber-800 dark:text-amber-300 flex-1">
            <strong>{buckets.senzaScadenza.length}</strong> fattur{buckets.senzaScadenza.length === 1 ? "a senza" : "e senza"} scadenza (€{formatEuro(buckets.senzaScadenza.reduce((s, d) => s + (d.totale_documento || 0), 0))}).
            Apri una fattura e imposta la data manualmente.
          </span>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex rounded-md border overflow-hidden">
          <button
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${view === "agenda" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
            onClick={() => setView("agenda")}
          >
            <List className="size-3.5" /> Agenda
          </button>
          <button
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors border-l ${view === "calendario" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
            onClick={() => setView("calendario")}
          >
            <CalendarDays className="size-3.5" /> Calendario
          </button>
        </div>

        <Button
          variant="outline"
          size="sm"
          className="h-8 gap-1.5 text-xs"
          onClick={() => setRegoleOpen(true)}
        >
          <Settings2 className="size-3.5" /> Regole fornitore
        </Button>

        <Button
          variant="ghost"
          size="sm"
          className="h-8 text-xs ml-auto"
          onClick={loadData}
          disabled={refreshing}
        >
          {refreshing ? "..." : "Aggiorna"}
        </Button>
      </div>

      {/* Content */}
      {view === "agenda" ? (
        <div className="space-y-3">
          <AgendaSection
            title="Scadute"
            docs={buckets.scadute}
            accentClass="text-rose-600 dark:text-rose-400"
            {...sharedProps}
          />
          <AgendaSection
            title="Questa settimana"
            docs={buckets.settimana}
            accentClass="text-orange-600 dark:text-orange-400"
            {...sharedProps}
          />
          <AgendaSection
            title="Questo mese"
            docs={buckets.mese}
            {...sharedProps}
          />
          <AgendaSection
            title="Oltre il mese"
            docs={buckets.oltre}
            defaultOpen={false}
            {...sharedProps}
          />
          <AgendaSection
            title="Senza scadenza"
            docs={buckets.senzaScadenza}
            defaultOpen={false}
            accentClass="text-muted-foreground"
            {...sharedProps}
          />
          <AgendaSection
            title="Pagate"
            docs={buckets.pagate}
            defaultOpen={false}
            accentClass="text-emerald-600 dark:text-emerald-400"
            {...sharedProps}
          />

          {documenti.length === 0 && (
            <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
              <Calendar className="size-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Nessun documento trovato.</p>
              <p className="text-xs mt-1">Le fatture con dati di scadenza appariranno qui.</p>
            </div>
          )}
        </div>
      ) : (
        <CalendarView documenti={documenti} />
      )}

      {/* Floating bulk action bar */}
      {selectedFileOrigini.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-full border bg-card shadow-lg px-5 py-3">
          <span className="text-sm font-medium">
            {selectedFileOrigini.size} selezionat{selectedFileOrigini.size === 1 ? "a" : "e"}
          </span>
          <Button size="sm" className="h-8 gap-1.5 rounded-full" onClick={handleBulkPaga} disabled={bulkPaying}>
            <Check className="size-3.5" />
            {bulkPaying ? "Salvataggio..." : "Segna pagate"}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="size-8 rounded-full"
            onClick={() => setSelectedFileOrigini(new Set())}
          >
            <X className="size-4" />
          </Button>
        </div>
      )}

      <PeekDialog
        doc={peekDoc}
        onClose={() => setPeekDoc(null)}
        onPaga={(doc, pagata) => handlePaga(doc, pagata)}
        onSetScadenza={handleSetScadenza}
      />

      <RegoleDialog open={regoleOpen} onClose={() => setRegoleOpen(false)} />
    </div>
  );
}
