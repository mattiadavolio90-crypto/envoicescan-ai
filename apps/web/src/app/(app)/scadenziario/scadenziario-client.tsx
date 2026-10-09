"use client";

import { useState, useEffect, useCallback, useMemo, useRef, type RefObject } from "react";
import { toast } from "sonner";
import {
  ArchiveRestore, ArrowUpDown, Calendar, CalendarDays, Check, ChevronDown,
  CalendarRange, ChevronRight, Download, Eye, EyeOff, Filter, List, Loader2, MapPin, Pencil, Search, Settings2,
  Split, Trash2, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { FilterChip } from "@/components/ui/filter-chip";
import { UnderlineTabs } from "@/components/ui/underline-tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MESI_LUNGHI as MESI } from "@/lib/mesi";
import { messaggioListaVuota } from "@/lib/esito-caricamento";
import { Separator } from "@/components/ui/separator";
import { RipartisciDialog } from "@/components/fatture/ripartisci-dialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/select";
import { InfoPopover } from "@/components/ui/info-popover";
import {
  type Documento, type RegolaPagamento, type SedeCatena,
  type Periodo, type Ordine, type OrdineArchivio, type FornitoreEntry,
  computeKpi, bucketizeDocumenti, raggruppaPerMeseFattura, formatEuro, formatEuroCompact, formatDate, parseLocalDate, todayLocalIso, MODALITA_LABELS,
  ordinaDocumenti, ordinaScadute, elencaFornitori, statoDocumento,
  scaduteFuoriDalMese,
  filtraDocumenti, aggregaPerSede, contaDaPagare, documentiSelezionabili,
  chiaviSelezionaTutte, statoSelezioneSezione, pianoAzioneDiMassa, applicaPagataAVideo,
  messaggioConfermaAzioneDiMassa, messaggioEsitoAzioneDiMassa, motivoAzioneSpenta,
  aperturaSezione, type AperturaSezione, ricercaAttiva,
  inPuntiVendita, alternaPuntoVendita, etichettaPuntiVendita,
} from "@/lib/scadenziario";
import { visteFattureOrdinate, vistaFattureIniziale } from "@/lib/tab-flags";

// ── KPI Bar ──────────────────────────────────────────────────────────────────

function useCountUp(target: number, duration = 600) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || target === 0) { el.textContent = formatEuro(target); return; }
    const start = performance.now();
    const raf = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      el.textContent = formatEuro(ease * target);
      if (t < 1) requestAnimationFrame(raf);
    };
    requestAnimationFrame(raf);
  }, [target, duration]);
  return ref;
}

type KpiCardProps = {
  /** Riga di dettaglio sotto il conteggio (es. la quota senza scadenza). */
  sub?: string;
  label: string;
  count: number;
  totale: number;
  tone: "negativo" | "incerto" | "neutro";
  active?: boolean;
  onClick?: () => void;
};

// Stesso linguaggio delle tessere di Margini e Analisi Fatture (Mattia, 28/9):
// bordo neutro, colore solo sul numero che giudica — scadute e in scadenza, e
// solo se non sono zero. Prima ogni tessera aveva bordo e cifra di un colore
// suo (rosso, giallo, blu, verde): il blu e il verde non giudicavano niente.
// La tessera attiva e' una selezione, non un giudizio: anello del colore primario.
const TONE_VALUE = {
  negativo: "text-negativo",
  incerto:  "text-incerto",
  neutro:   "text-foreground",
};
const BORDO_NEUTRO = "border-border hover:border-muted-foreground/40";
const BORDO_ATTIVO = "border-primary ring-2 ring-primary/30";

function KpiCard({ label, count, totale, tone, sub, active = false, onClick }: KpiCardProps) {
  const valRef = useCountUp(totale);
  const clickable = !!onClick;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!clickable}
      aria-pressed={clickable ? active : undefined}
      className={`text-left rounded-xl border bg-card px-4 pt-3 pb-3 transition-all flex flex-col gap-1
        ${active ? BORDO_ATTIVO : BORDO_NEUTRO}
        ${clickable ? "cursor-pointer hover:-translate-y-0.5" : "cursor-default"}`}
    >
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <p className={`text-2xl font-bold tracking-tight tabular-nums ${TONE_VALUE[totale > 0 ? tone : "neutro"]}`}>
        <span ref={valRef as RefObject<HTMLSpanElement>}>{formatEuro(totale)}</span>
      </p>
      <p className="text-[11px] text-muted-foreground">{count} fattur{count === 1 ? "a" : "e"}</p>
      {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
    </button>
  );
}

// ── Source badge ─────────────────────────────────────────────────────────────

function ScadenzaBadge({ source }: { source: string | null }) {
  if (!source || source === "stored") return null;
  const map: Record<string, { label: string; className: string }> = {
    override: { label: "manuale", className: "bg-accent text-primary-text" },
    xml:      { label: "da fattura", className: "bg-accent text-primary-text" },
    fornitore: { label: "da regola", className: "bg-accent text-primary-text" },
    fornitore_rid: { label: "RID", className: "bg-accent text-primary-text" },
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

// Badge Sede — solo modalità catena. Stesso stile del badge "Ripartita" in
// articoli-tab.tsx per la sede tecnica (blu del brand + Split, "Gruppo").
function SedeBadge({ nome, isSedeTecnica }: { nome: string; isSedeTecnica: boolean }) {
  if (isSedeTecnica) {
    return (
      <span
        className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent text-primary-text font-semibold inline-flex items-center gap-0.5 whitespace-nowrap"
        title="Costo comune di gruppo, non attribuito a un singolo punto vendita"
      >
        <Split className="size-2.5" /> Gruppo
      </span>
    );
  }
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground font-medium inline-flex items-center gap-0.5 whitespace-nowrap">
      <MapPin className="size-2.5" /> {nome}
    </span>
  );
}

type DocumentoRowProps = {
  doc: Documento;
  selected: boolean;
  onToggleSelect: () => void;
  onPaga: (doc: Documento) => void;
  onPeek: (doc: Documento) => void;
  sedeTecnicaId?: string;
  /**
   * Nella vista "Per mese" sparisce tutto cio' che riguarda le scadenze: badge
   * della fonte, data di scadenza, selezione multipla e "Paga". Una prop su
   * questo componente e non un secondo componente copiato, che al primo fix
   * divergerebbe mostrando due elenchi diversi per le stesse fatture.
   */
  mostraScadenze?: boolean;
};

/**
 * Niente bordo rosso per riga.
 *
 * Fino al 17/09/2026 ogni riga scaduta portava un `border-l-2 border-rose-500/60`.
 * Su una sede reale le scadute sono 414 (1.685 in vista gruppo): l'audit visivo
 * del 16/09 ha letto la pagina come «un muro rosso senza fine», voto 8 su 10, la
 * piu' pesante dell'app.
 *
 * E non distingueva nulla: le sezioni sono gia' partizionate per stato, quindi
 * dentro "Scadute" TUTTE le righe erano rosse e nelle altre nessuna. Il segnale
 * lo danno il titolo di sezione (rose-600) e la data di scadenza qui sotto, che
 * restano.
 */
function DocumentoRow({ doc, selected, onToggleSelect, onPaga, onPeek, sedeTecnicaId, mostraScadenze = true }: DocumentoRowProps) {
  const isOverdue = statoDocumento(doc) === "Scaduta";

  return (
    <div
      className={`flex items-center gap-3 px-3 py-2.5 rounded-md transition-colors cursor-pointer group
        ${selected ? "bg-primary/8" : "hover:bg-muted/50"}`}
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
          <span className="font-medium text-sm truncate max-w-[200px]" title={doc.fornitore}>{doc.fornitore}</span>
          {doc.numero_documento && (
            <span className="text-xs text-muted-foreground">#{doc.numero_documento}</span>
          )}
          {doc.oscurata && (
            <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium bg-muted text-muted-foreground">
              esclusa da te
            </span>
          )}
          {mostraScadenze && <ScadenzaBadge source={doc.scadenza_source} />}
          {doc.sede_nome && (
            <SedeBadge nome={doc.sede_nome} isSedeTecnica={!!doc.ristorante_id && doc.ristorante_id === sedeTecnicaId} />
          )}
        </div>
        <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground flex-wrap">
          {doc.data_documento && <span>Fattura: {formatDate(doc.data_documento)}</span>}
          {mostraScadenze && doc.scadenza_effettiva && (
            <span className={isOverdue && !doc.pagata ? "text-negativo font-medium" : ""}>
              Scade: {formatDate(doc.scadenza_effettiva)}
            </span>
          )}
        </div>
      </div>

      <div className="text-right flex-shrink-0">
        <p className="font-semibold text-sm tabular-nums">{formatEuro(doc.totale_documento)}</p>
      </div>

      {mostraScadenze && !doc.pagata && (
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs flex-shrink-0 gap-1 opacity-60 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
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
  /** Ricerca attiva: la sezione si apre anche se chiusa di default. */
  forzaAperta?: boolean;
  selectedFileOrigini: Set<string>;
  onToggleSelect: (fo: string) => void;
  onToggleAll: (docs: Documento[], selectAll: boolean) => void;
  onPaga: (doc: Documento) => void;
  onPeek: (doc: Documento) => void;
  accentClass?: string;
  sedeTecnicaId?: string;
  /** Vedi DocumentoRow: nella vista "Per mese" le scadenze non esistono. */
  mostraScadenze?: boolean;
  /** Sottotitolo a destra del titolo (la vista "Per mese" ci mette il totale). */
  sommario?: string;
};

function AgendaSection({
  title, docs, defaultOpen = true, forzaAperta = false,
  selectedFileOrigini, onToggleSelect, onToggleAll, onPaga, onPeek, accentClass = "", sedeTecnicaId,
  mostraScadenze = true, sommario,
}: AgendaSectionProps) {
  const [apertura, setApertura] = useState<AperturaSezione>({ open: defaultOpen, primaDellaRicerca: null });
  const open = apertura.open;
  const checkboxRef = useRef<HTMLInputElement>(null);

  // La ricerca apre la sezione e, svuotata, la riporta com'era: aperturaSezione
  // in lib/scadenziario.ts.
  useEffect(() => {
    setApertura(s => aperturaSezione(s, forzaAperta));
  }, [forzaAperta]);

  const selectableDocs = documentiSelezionabili(docs);
  const { selezionati: selectedCount, tutte: allSelected } =
    statoSelezioneSezione(docs, selectedFileOrigini);
  const someSelected = selectedCount > 0 && !allSelected;

  useEffect(() => {
    if (checkboxRef.current) checkboxRef.current.indeterminate = someSelected;
  }, [someSelected]);

  if (docs.length === 0) return null;
  const totale = docs.reduce((s, d) => s + (d.totale_documento || 0), 0);

  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <div className="flex items-center px-3 py-3 hover:bg-muted/30 transition-colors">
        {mostraScadenze && selectableDocs.length > 0 && (
          <input
            ref={checkboxRef}
            type="checkbox"
            checked={allSelected}
            className="size-4 cursor-pointer accent-primary mr-2 flex-shrink-0"
            onChange={() => onToggleAll(selectableDocs, !allSelected)}
            onClick={e => e.stopPropagation()}
            title={allSelected ? "Deseleziona tutto" : "Seleziona tutto"}
          />
        )}
        <button
          className="flex-1 flex items-center justify-between"
          onClick={() => setApertura(s => ({ ...s, open: !s.open }))}
        >
          <div className="flex items-center gap-2">
            {open ? <ChevronDown className="size-4 text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}
            <span className={`font-semibold text-sm ${accentClass}`}>{title}</span>
            <span className="text-xs text-muted-foreground bg-muted rounded-full px-2 py-0.5">{docs.length}</span>
            {selectedCount > 0 && (
              <span className="text-xs text-primary font-medium">{selectedCount} sel.</span>
            )}
          </div>
          <span className="text-sm font-medium text-muted-foreground tabular-nums">{formatEuro(totale)}</span>
        </button>
      </div>

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
              sedeTecnicaId={sedeTecnicaId}
              mostraScadenze={mostraScadenze}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Note di credito section (read-only, non pagabili) ─────────────────────────

function OscurateSection({
  docs,
  onPeek,
  onOscura,
  sedeTecnicaId,
}: {
  docs: Documento[];
  onPeek: (doc: Documento) => void;
  onOscura: (doc: Documento, oscurata: boolean) => Promise<void>;
  sedeTecnicaId?: string;
}) {
  const [open, setOpen] = useState(false);
  if (docs.length === 0) return null;
  const totale = docs.reduce((s, d) => s + Math.abs(d.totale_documento || 0), 0);

  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <div className="flex items-center px-3 py-3 hover:bg-muted/30 transition-colors">
        <button className="flex-1 flex items-center justify-between" onClick={() => setOpen(o => !o)}>
          <div className="flex items-center gap-2">
            {open ? <ChevronDown className="size-4 text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}
            <span className="font-semibold text-sm text-muted-foreground">Escluse da te</span>
            <span className="text-xs text-muted-foreground bg-muted rounded-full px-2 py-0.5">{docs.length}</span>
            <span className="text-[10px] font-medium rounded-full px-2 py-0.5 bg-muted text-muted-foreground">
              non conteggiate
            </span>
          </div>
          <span className="text-sm font-medium text-muted-foreground tabular-nums">{formatEuro(totale)}</span>
        </button>
      </div>

      {open && (
        <div className="border-t divide-y divide-border/50">
          {docs.map((doc) => (
            <div
              key={`${doc.file_origine}::${doc.ristorante_id ?? ""}`}
              className="flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-muted/50"
            >
              <button className="flex-1 min-w-0 text-left cursor-pointer" onClick={() => onPeek(doc)}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-sm truncate max-w-[200px]" title={doc.fornitore}>{doc.fornitore}</span>
                  {doc.numero_documento && (
                    <span className="text-xs text-muted-foreground">#{doc.numero_documento}</span>
                  )}
                  {doc.sede_nome && (
                    <SedeBadge nome={doc.sede_nome} isSedeTecnica={!!doc.ristorante_id && doc.ristorante_id === sedeTecnicaId} />
                  )}
                </div>
                {doc.data_documento && (
                  <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
                    <span>Documento: {formatDate(doc.data_documento)}</span>
                  </div>
                )}
              </button>
              <span className="text-sm font-medium text-muted-foreground flex-shrink-0 tabular-nums">
                {formatEuro(doc.totale_documento)}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 gap-1.5 text-xs flex-shrink-0"
                onClick={() => { void onOscura(doc, false); }}
              >
                <Eye className="size-3.5" /> Rimetti nei conti
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function NoteCreditoSection({
  docs,
  onPeek,
  sedeTecnicaId,
}: {
  docs: Documento[];
  onPeek: (doc: Documento) => void;
  sedeTecnicaId?: string;
}) {
  const [open, setOpen] = useState(false);
  if (docs.length === 0) return null;
  const totale = docs.reduce((s, d) => s + Math.abs(d.totale_documento || 0), 0);

  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <div className="flex items-center px-3 py-3 hover:bg-muted/30 transition-colors">
        <button className="flex-1 flex items-center justify-between" onClick={() => setOpen(o => !o)}>
          <div className="flex items-center gap-2">
            {open ? <ChevronDown className="size-4 text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}
            <span className="font-semibold text-sm text-primary-text">Note di credito</span>
            <span className="text-xs text-muted-foreground bg-muted rounded-full px-2 py-0.5">{docs.length}</span>
            <span className="text-[10px] font-medium rounded-full px-2 py-0.5 bg-accent text-primary-text">
              non da pagare
            </span>
          </div>
          <span className="text-sm font-medium text-muted-foreground tabular-nums">{formatEuro(totale)}</span>
        </button>
      </div>

      {open && (
        <div className="border-t divide-y divide-border/50">
          {docs.map((doc) => (
            <div
              key={doc.file_origine}
              className="flex items-center gap-3 px-3 py-2.5 rounded-md transition-colors cursor-pointer hover:bg-muted/50"
              onClick={() => onPeek(doc)}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-sm truncate max-w-[200px]" title={doc.fornitore}>{doc.fornitore}</span>
                  {doc.numero_documento && (
                    <span className="text-xs text-muted-foreground">#{doc.numero_documento}</span>
                  )}
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium bg-accent text-primary-text">
                    nota di credito
                  </span>
                  {doc.sede_nome && (
                    <SedeBadge nome={doc.sede_nome} isSedeTecnica={!!doc.ristorante_id && doc.ristorante_id === sedeTecnicaId} />
                  )}
                </div>
                {doc.data_documento && (
                  <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
                    <span>Documento: {formatDate(doc.data_documento)}</span>
                  </div>
                )}
              </div>
              <div className="text-right flex-shrink-0">
                <p className="font-semibold text-sm text-primary-text tabular-nums">
                  {formatEuro(Math.abs(doc.totale_documento || 0))}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Calendar view ────────────────────────────────────────────────────────────

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
      if (doc.pagata) continue;
      if (doc.is_nota_credito) continue;
      const dt = parseLocalDate(doc.scadenza_effettiva);
      if (dt && dt.getFullYear() === anno && dt.getMonth() === mese) {
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
      if (d.pagata) return false;
      if (d.is_nota_credito) return false;
      const dt = parseLocalDate(d.scadenza_effettiva);
      return !!dt && dt.getFullYear() === anno && dt.getMonth() === mese && dt.getDate() === selectedDay;
    });
  }, [documenti, anno, mese, selectedDay]);

  // Le scadute degli altri mesi: il calendario mostra una finestra sola, e su
  // una sede reale sono sparse su piu' mesi. Senza questa riga la griglia vuota
  // sembra dire "non c'e' niente da pagare" mentre i riquadri sopra dicono il
  // contrario.
  const fuoriMese = useMemo(
    () => scaduteFuoriDalMese(documenti, anno, mese),
    [documenti, anno, mese],
  );

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

      {fuoriMese.count > 0 && (
        <p className="text-xs text-muted-foreground -mt-1">
          <span className="font-medium text-negativo">
            {fuoriMese.count} {fuoriMese.count === 1 ? "fattura scaduta" : "fatture scadute"}
          </span>
          {" "}({formatEuro(fuoriMese.totale)}) {fuoriMese.count === 1 ? "ha" : "hanno"} scadenza
          in altri mesi e non compare{fuoriMese.count === 1 ? "" : "no"} qui. Le trovi nella vista Lista.
        </p>
      )}

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
          // Opacità su sky-500: minimo 0.28 così anche l'importo più basso è
          // chiaramente visibile sia su card chiara (light) sia scura (dark).
          const bgOpacity = hasAmount ? Math.max(0.28, intensity * 0.92) : 0;
          const isSelected = selectedDay === day;
          // Testo leggibile in entrambi i temi: su intensità alta lo sfondo sky è
          // pieno → bianco; su intensità medio-bassa lo sfondo è semitrasparente →
          // sky scuro in light, sky chiaro in dark (segue il tema sotto la cella).
          const onBg = !isSelected && hasAmount
            ? (intensity > 0.55 ? "text-white" : "text-primary-text")
            : "";

          return (
            <button
              key={day}
              onClick={() => setSelectedDay(isSelected ? null : day)}
              className={`relative flex flex-col items-center justify-center rounded-md py-1.5 transition-colors text-xs gap-0
                ${isToday ? "ring-2 ring-primary ring-offset-1" : ""}
                ${isSelected ? "bg-primary text-primary-foreground" : hasAmount ? "" : "hover:bg-muted/50"}
              `}
              // Era `rgba(14,165,233, a)`: un azzurro fisso, identico nei due
              // temi, mentre il testo sopra si ribalta col tema (onBg, qui
              // sopra). Stessa correzione gia' fatta sulla heatmap della pivot
              // e in catena: color-mix su un token, cosi' fondo e testo
              // seguono lo stesso tema. L'intensita' resta quella di prima.
              style={hasAmount && !isSelected
                ? { backgroundColor: `color-mix(in oklab, var(--primary) ${Math.round(bgOpacity * 100)}%, transparent)` }
                : {}}
            >
              <span className={`font-semibold leading-none ${isToday && !isSelected ? "text-primary" : ""} ${onBg}`}>{day}</span>
              {hasAmount && (
                <>
                  <span className={`text-[9px] leading-none mt-0.5 font-medium ${isSelected ? "text-primary-foreground/90" : onBg}`}>
                    {formatEuroCompact(totale)}
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
              <span className="truncate max-w-[200px] text-muted-foreground" title={doc.fornitore}>{doc.fornitore}</span>
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

type SedeOpt = { id: string; nome: string; indirizzo: string | null; comune: string | null; attiva?: boolean };

type PeekDialogProps = {
  doc: Documento | null;
  onClose: () => void;
  onPaga: (doc: Documento, pagata: boolean) => void;
  onSetScadenza: (doc: Documento, data: string | null) => Promise<void>;
  onElimina: (doc: Documento) => Promise<void>;
  onOscura: (doc: Documento, oscurata: boolean) => Promise<void>;
  onSpostata: (doc: Documento) => void;
  // Modalità catena: "Sposta sede"/"Ripartisci sul gruppo" restano nascosti
  // (agiscono sulla sede ATTIVA del PV loggato, non su quella del documento —
  // fuori scope Fase 3, si riprende in una fase dedicata se serve).
  modalitaCatena?: boolean;
};

function PeekDialog({ doc, onClose, onPaga, onSetScadenza, onElimina, onOscura, onSpostata, modalitaCatena = false }: PeekDialogProps) {
  const [editingScadenza, setEditingScadenza] = useState(false);
  const [scadenzaInput, setScadenzaInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [anteprimaOpen, setAnteprimaOpen] = useState(false);
  const [righe, setRighe] = useState<RigaFattura[]>([]);
  const [loadingRighe, setLoadingRighe] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [oscuraConfirm, setOscuraConfirm] = useState(false);
  const [oscurando, setOscurando] = useState(false);
  // Sedi del cliente: la sezione "Sposta in altra sede" compare SOLO se l'account
  // ha più di una sede (clienti multi-sede con P.IVA condivisa). Per gli altri
  // resta invisibile: niente UI inutile.
  const [sedi, setSedi] = useState<SedeOpt[]>([]);
  const [spostandoVerso, setSpostandoVerso] = useState<string | null>(null);
  const [ripartisciOpen, setRipartisciOpen] = useState(false);
  // Solo un sotto-utente senza Catena riceve `catena: false`: per lui il riparto
  // (che scrive su tutte le sedi) e' negato dal worker.
  const [catenaNegata, setCatenaNegata] = useState(false);

  useEffect(() => {
    if (doc) { setScadenzaInput(doc.scadenza_effettiva ?? ""); }
    setEditingScadenza(false);
    setAnteprimaOpen(false);
    setRighe([]);
    setDeleteConfirm(false);
    setDeleting(false);
    setOscuraConfirm(false);
    setOscurando(false);
    setSpostandoVerso(null);
  }, [doc]);

  // Carica le sedi una sola volta all'apertura del primo dettaglio (lista breve,
  // stabile per l'account). Se la fetch fallisce o c'è una sola sede, la sezione
  // sposta semplicemente non compare.
  useEffect(() => {
    if (!doc || sedi.length > 0 || modalitaCatena) return;
    let alive = true;
    fetch("/api/account/sedi", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive && d?.sedi) {
          setSedi(d.sedi as SedeOpt[]);
          setCatenaNegata(d.catena === false);
        }
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [doc, sedi.length, modalitaCatena]);

  async function handleSposta(ristoranteId: string) {
    if (!doc || spostandoVerso) return;
    setSpostandoVerso(ristoranteId);
    try {
      const res = await fetch("/api/fatture/sposta-sede", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_origine: doc.file_origine, ristorante_id: ristoranteId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data?.ok) throw new Error(data?.detail || data?.error);
      toast.success("Fattura spostata nell'altra sede");
      // La fattura ora appartiene a un'altra sede: va tolta da questa lista, come
      // fa handleElimina. Senza, restava a video sotto la sede vecchia e un secondo
      // click rispondeva con un errore che contraddiceva il toast verde appena letto.
      onSpostata(doc);
      onClose();
    } catch {
      toast.error("Non sono riuscito a spostare la fattura. Riprova.");
      setSpostandoVerso(null);
    }
  }

  async function handleDelete() {
    if (!doc) return;
    setDeleting(true);
    try {
      await onElimina(doc);
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Errore durante l'eliminazione");
      setDeleting(false);
      setDeleteConfirm(false);
    }
  }

  async function handleOscura() {
    if (!doc) return;
    setOscurando(true);
    try {
      await onOscura(doc, !doc.oscurata);
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Operazione non riuscita");
      setOscurando(false);
      setOscuraConfirm(false);
    }
  }

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
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto">
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
                  <span>{doc.tipo_documento || "TD01"}{doc.is_nota_credito ? " · Nota di credito" : ""}</span>
                </div>
                <div className="flex justify-between text-sm items-center gap-2">
                  <span className="text-muted-foreground">Stato</span>
                  <span className={`font-medium ${doc.pagata ? "text-positivo" : ""}`}>
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
                                  {r.prezzo_unitario != null ? formatEuro(r.prezzo_unitario, 4) : "—"}
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
                {doc.is_nota_credito ? (
                  <div className="rounded-lg border border-primary/40 bg-accent px-4 py-3 text-sm text-primary-text">
                    Questa è una <strong>nota di credito</strong>: è un accredito del fornitore, non un importo da pagare. Per questo è esclusa da scadenze e totali.
                  </div>
                ) : doc.pagata ? (
                  <Button variant="outline" className="w-full" onClick={() => { onPaga(doc, false); onClose(); }}>
                    Segna come non pagata
                  </Button>
                ) : (
                  <Button className="w-full gap-2" onClick={() => { onPaga(doc, true); onClose(); }}>
                    <Check className="size-4" /> Segna come pagata
                  </Button>
                )}
              </div>

              {/* Sposta in altra sede — solo clienti multi-sede.
                  Corregge a posteriori un'assegnazione automatica sbagliata del
                  routing multi-sede (fattura finita nella sede sbagliata). */}
              {sedi.length > 1 && (
                <>
                  <Separator />
                  <div className="space-y-2">
                    <div className="flex items-center gap-1.5">
                      <MapPin className="size-4 text-muted-foreground" />
                      <Label className="text-sm font-medium">Sposta in un&apos;altra sede</Label>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Se questa fattura è finita nella sede sbagliata, spostala qui.
                    </p>
                    <div className="flex flex-wrap gap-2 pt-0.5">
                      {sedi.filter((s) => !s.attiva).map((s) => (
                        <Button
                          key={s.id}
                          variant="outline"
                          size="sm"
                          className="gap-1.5"
                          disabled={spostandoVerso !== null}
                          onClick={() => handleSposta(s.id)}
                        >
                          {spostandoVerso === s.id
                            ? <Loader2 className="size-3.5 animate-spin" />
                            : <MapPin className="size-3.5" />}
                          {s.nome}
                        </Button>
                      ))}
                    </div>
                  </div>

                  {!catenaNegata && (
                  <>
                  {/* Ripartisci sul gruppo — costi di struttura comuni (commercialista,
                      auto…) intestati alla sede legale, divisi fra i punti vendita.
                      La quota di ogni sede entra nel suo MOL; il documento resta intero. */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-1.5">
                      <Split className="size-4 text-muted-foreground" />
                      <Label className="text-sm font-medium">Costo comune del gruppo</Label>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Se questo costo va diviso fra i punti vendita (es. commercialista, auto
                      aziendale), ripartiscilo sul gruppo.
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => setRipartisciOpen(true)}
                    >
                      <Split className="size-3.5" />
                      Ripartisci sul gruppo
                    </Button>
                  </div>

                  <RipartisciDialog
                    open={ripartisciOpen}
                    onOpenChange={setRipartisciOpen}
                    fileOrigine={doc.file_origine}
                    descrizioneDefault={doc.fornitore ?? ""}
                    sedi={sedi.map((s) => ({ id: s.id, nome: s.nome }))}
                    onDone={() => onClose()}
                  />
                  </>
                  )}
                </>
              )}

              <Separator />

              {/* Escludi dai conti — l'alternativa NON distruttiva all'eliminazione,
                  messa prima apposta: chi arriva qui per "togliere una fattura dai
                  numeri" incontra questa e non il cestino. Etichetta in italiano
                  corrente: "oscurata" e' il nome tecnico della colonna, non una
                  parola che il cliente debba imparare. */}
              <div>
                {!oscuraConfirm ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full text-muted-foreground hover:text-foreground gap-1.5"
                    onClick={() => setOscuraConfirm(true)}
                  >
                    {doc.oscurata ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
                    {doc.oscurata ? "Rimetti nei conti" : "Escludi dai conti"}
                  </Button>
                ) : (
                  <div className="space-y-2">
                    <p className="text-xs text-center text-muted-foreground">
                      {doc.oscurata
                        ? "Tornerà a contare in margini, foodcost e analisi."
                        : "Resterà in elenco ma uscirà da margini, foodcost e analisi."}
                    </p>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" className="flex-1" onClick={() => setOscuraConfirm(false)} disabled={oscurando}>
                        Annulla
                      </Button>
                      <Button variant="default" size="sm" className="flex-1 gap-1.5" onClick={handleOscura} disabled={oscurando}>
                        {oscurando && <Loader2 className="size-3.5 animate-spin" />}
                        Conferma
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              {/* Elimina fattura */}
              <div>
                {!deleteConfirm ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full text-muted-foreground hover:text-destructive gap-1.5"
                    onClick={() => setDeleteConfirm(true)}
                  >
                    <Trash2 className="size-4" /> Elimina fattura
                  </Button>
                ) : (
                  <div className="space-y-2">
                    <p className="text-xs text-center text-muted-foreground">Sposta questa fattura nel cestino?</p>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" className="flex-1" onClick={() => setDeleteConfirm(false)} disabled={deleting}>
                        Annulla
                      </Button>
                      <Button variant="destructive" size="sm" className="flex-1 gap-1.5" onClick={handleDelete} disabled={deleting}>
                        {deleting && <Loader2 className="size-3.5 animate-spin" />}
                        Conferma
                      </Button>
                    </div>
                  </div>
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
  /** Chiamata dopo un salvataggio andato a buon fine. */
  onSalvato?: () => void;
  open: boolean;
  onClose: () => void;
};

function RegoleDialog({ open, onClose, onSalvato }: RegoleDialogProps) {
  const [regole, setRegole] = useState<RegolaPagamento[]>([]);
  const [fornitori, setFornitori] = useState<FornitoreOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedNomi, setSelectedNomi] = useState<Set<string>>(new Set());
  const [searchForn, setSearchForn] = useState("");
  const [modalitaInput, setModalitaInput] = useState("30gg");
  const [saving, setSaving] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [resRegole, resFornitori] = await Promise.all([
        fetch("/api/scadenziario/regole"),
        fetch("/api/scadenziario/fornitori"),
      ]);
      if (resRegole.ok) { const d = await resRegole.json(); setRegole(d.regole ?? []); }
      if (resFornitori.ok) { const d = await resFornitori.json(); setFornitori(d.fornitori ?? []); }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) { loadAll(); setSelectedNomi(new Set()); setSearchForn(""); setModalitaInput("30gg"); }
  }, [open, loadAll]);

  const fornitoriDisponibili = useMemo(() => {
    const giaCon = new Set(regole.map(r => r.piva_fornitore));
    return fornitori.filter(f => !f.piva_fornitore || !giaCon.has(f.piva_fornitore));
  }, [fornitori, regole]);

  const fornitoriFiltrati = useMemo(() => {
    const q = searchForn.trim().toLowerCase();
    return q ? fornitoriDisponibili.filter(f => f.fornitore.toLowerCase().includes(q)) : fornitoriDisponibili;
  }, [fornitoriDisponibili, searchForn]);

  const selectedItems = useMemo(
    () => fornitoriDisponibili.filter(f => selectedNomi.has(f.fornitore)),
    [fornitoriDisponibili, selectedNomi]
  );
  const conPiva = selectedItems.filter(f => f.piva_fornitore);
  const senzaPiva = selectedItems.filter(f => !f.piva_fornitore);
  const canSave = conPiva.length > 0;

  function toggleFornitore(nome: string) {
    setSelectedNomi(prev => {
      const next = new Set(prev);
      if (next.has(nome)) next.delete(nome); else next.add(nome);
      return next;
    });
  }

  function selectAll() { setSelectedNomi(new Set(fornitoriFiltrati.map(f => f.fornitore))); }
  function clearAll() { setSelectedNomi(new Set()); }
  const allChecked = fornitoriFiltrati.length > 0 && fornitoriFiltrati.every(f => selectedNomi.has(f.fornitore));
  const someChecked = !allChecked && fornitoriFiltrati.some(f => selectedNomi.has(f.fornitore));

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    let salvate = 0;
    try {
      for (const f of conPiva) {
        const res = await fetch("/api/scadenziario/regole", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ piva_fornitore: f.piva_fornitore, modalita: modalitaInput }),
        });
        if (res.ok) salvate++;
        else { const d = await res.json(); toast.error(`${f.fornitore}: ${d.detail || "Errore"}`); }
      }
      if (salvate > 0)
        toast.success(`${salvate} regol${salvate === 1 ? "a salvata" : "e salvate"}`);
      if (senzaPiva.length > 0)
        toast.warning(`${senzaPiva.length} fornitore/i senza P.IVA non salvat${senzaPiva.length === 1 ? "o" : "i"}`);
      setSelectedNomi(new Set());
      await loadAll();
      // La lista sta nel genitore: senza questo la regola veniva creata e le
      // scadenze a video restavano quelle di prima, fino a un "Aggiorna" a mano.
      if (salvate > 0) onSalvato?.();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      const res = await fetch(`/api/scadenziario/regole/${id}`, { method: "DELETE" });
      if (!res.ok) { toast.error("Errore eliminazione"); return; }
      setRegole(r => r.filter(x => x.id !== id));
      toast.success("Regola eliminata");
      // Togliere una regola ricalcola `scadenza_effettiva` delle sue fatture:
      // senza questo la lista resta quella di prima, lo stesso difetto corretto
      // per il salvataggio e lasciato sul verso opposto.
      onSalvato?.();
    } catch { toast.error("Errore eliminazione"); }
  }

  const pivaToNome = useMemo(() => {
    const m: Record<string, string> = {};
    for (const f of fornitori) if (f.piva_fornitore) m[f.piva_fornitore] = f.fornitore;
    return m;
  }, [fornitori]);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Regole Scadenza Fornitori</DialogTitle>
          <DialogDescription>
            Termini di pagamento per fornitore — sovrascrivono i dati della fattura XML.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 pt-1 max-h-[70vh] overflow-y-auto pr-1">
          {loading ? (
            <p className="text-sm text-muted-foreground text-center py-6">Caricamento...</p>
          ) : (
            <>
              {/* Regole esistenti */}
              {regole.length > 0 && (
                <div className="space-y-1.5">
                  {regole.map(reg => (
                    <div key={reg.id} className="flex items-center gap-3 rounded-lg border bg-muted/20 px-3 py-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate" title={pivaToNome[reg.piva_fornitore] || reg.piva_fornitore}>{pivaToNome[reg.piva_fornitore] || reg.piva_fornitore}</p>
                        <p className="text-xs text-muted-foreground">
                          {MODALITA_LABELS[reg.modalita] ?? reg.modalita}
                          <span className="mx-1.5 opacity-40">·</span>
                          <span className="font-mono text-[11px]">{reg.piva_fornitore}</span>
                        </p>
                      </div>
                      <Button variant="ghost" size="icon" className="size-7 text-muted-foreground hover:text-destructive flex-shrink-0"
                        onClick={() => handleDelete(reg.id)}>
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}

              {/* Form nuova regola */}
              {fornitoriDisponibili.length > 0 ? (
                <div className="rounded-lg border border-dashed p-3 space-y-3">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    Nuova regola{selectedNomi.size > 0 && ` — ${selectedNomi.size} fornitore/i selezionat${selectedNomi.size === 1 ? "o" : "i"}`}
                  </p>

                  {/* Modalità — prima del fornitore così l'utente imposta prima la regola */}
                  <div className="space-y-1">
                    <Label className="text-xs">Modalità di pagamento</Label>
                    <NativeSelect value={modalitaInput} onValueChange={setModalitaInput} className="h-9 text-sm">
                      {Object.entries(MODALITA_LABELS).map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                      ))}
                    </NativeSelect>
                  </div>

                  {/* Checklist fornitori */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs">Fornitori</Label>
                      <div className="flex gap-3 text-[11px]">
                        <button onClick={selectAll} className="text-primary hover:underline">Tutti</button>
                        {selectedNomi.size > 0 && (
                          <button onClick={clearAll} className="text-muted-foreground hover:underline">Deseleziona</button>
                        )}
                      </div>
                    </div>

                    {/* Ricerca */}
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
                      <Input
                        placeholder="Cerca..."
                        value={searchForn}
                        onChange={e => setSearchForn(e.target.value)}
                        className="pl-8 h-8 text-xs"
                      />
                    </div>

                    {/* Lista checkbox */}
                    <div className="rounded-md border divide-y max-h-44 overflow-y-auto">
                      {/* Header seleziona tutto filtrati */}
                      <label className="flex items-center gap-2.5 px-3 py-2 bg-muted/30 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={allChecked}
                          ref={(el) => { if (el) el.indeterminate = someChecked; }}
                          onChange={() => allChecked ? clearAll() : selectAll()}
                          className="size-3.5 accent-primary"
                        />
                        <span className="text-xs font-medium text-muted-foreground">
                          {searchForn ? `${fornitoriFiltrati.length} risultati` : `Tutti (${fornitoriFiltrati.length})`}
                        </span>
                      </label>

                      {fornitoriFiltrati.length === 0 ? (
                        <p className="text-xs text-muted-foreground text-center py-3">Nessun fornitore trovato</p>
                      ) : (
                        fornitoriFiltrati.map(f => (
                          <label key={f.fornitore} className="flex items-center gap-2.5 px-3 py-2 hover:bg-muted/30 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={selectedNomi.has(f.fornitore)}
                              onChange={() => toggleFornitore(f.fornitore)}
                              className="size-3.5 accent-primary flex-shrink-0"
                            />
                            <span className="min-w-0 text-xs truncate flex-1" title={f.fornitore}>{f.fornitore}</span>
                            {!f.piva_fornitore && (
                              <span className="text-[10px] text-muted-foreground italic flex-shrink-0">senza P.IVA</span>
                            )}
                          </label>
                        ))
                      )}
                    </div>

                    {senzaPiva.length > 0 && (
                      <p className="text-[11px] text-incerto">
                        {senzaPiva.length} fornitore/i senza P.IVA verranno ignorati al salvataggio.
                      </p>
                    )}
                  </div>

                  <Button
                    size="sm"
                    className="w-full h-9"
                    onClick={handleSave}
                    disabled={saving || !canSave}
                  >
                    {saving
                      ? "Salvataggio..."
                      : canSave
                        ? `Salva regola per ${conPiva.length} fornitore/i`
                        : "Seleziona almeno un fornitore"}
                  </Button>
                </div>
              ) : (
                <p className="text-xs text-center text-muted-foreground py-4">
                  {fornitori.length === 0
                    ? "Nessun fornitore trovato. Carica prima le fatture."
                    : "Tutti i fornitori hanno già una regola configurata."}
                </p>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Fornitore Multi-Select ────────────────────────────────────────────────────

type FornitoreMultiSelectProps = {
  fornitori: FornitoreEntry[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
};

function FornitoreMultiSelect({ fornitori, selected, onChange }: FornitoreMultiSelectProps) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? fornitori.filter(f => f.label.toLowerCase().includes(q)) : fornitori;
  }, [fornitori, search]);

  function toggle(key: string) {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key); else next.add(key);
    onChange(next);
  }

  function selectAll() { onChange(new Set(fornitori.map(f => f.key))); }
  function clearAll() { onChange(new Set()); }

  const label = selected.size === 0
    ? "Tutti i fornitori"
    : selected.size === 1
      ? (fornitori.find(f => f.key === Array.from(selected)[0])?.label ?? Array.from(selected)[0])
      : `${selected.size} fornitori`;

  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            className={`h-8 text-xs gap-1.5 max-w-[240px] justify-start ${selected.size > 0 ? "border-primary text-primary" : ""}`}
          >
            <Filter className="size-3.5 flex-shrink-0" />
            <span className="truncate" title={label}>{label}</span>
            {selected.size > 0 && (
              <span className="ml-auto flex-shrink-0 size-4 flex items-center justify-center rounded-full bg-primary text-primary-foreground text-[10px] font-semibold">
                {selected.size}
              </span>
            )}
          </Button>
        }
      />
      <PopoverContent className="w-64 p-0" align="start" sideOffset={6}>
        <div className="p-2 border-b">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
            <input
              className="w-full pl-7 pr-2 py-1.5 text-xs rounded-md border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="Cerca fornitore..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              autoFocus
            />
          </div>
        </div>

        <div className="flex items-center gap-3 px-3 py-1.5 border-b">
          <button onClick={selectAll} className="text-[11px] text-primary hover:underline">Seleziona tutti</button>
          <span className="text-muted-foreground text-[11px]">·</span>
          <button onClick={clearAll} className="text-[11px] text-muted-foreground hover:text-foreground hover:underline">Deseleziona</button>
          {selected.size > 0 && (
            <span className="ml-auto text-[11px] text-muted-foreground">{selected.size} sel.</span>
          )}
        </div>

        <div className="max-h-56 overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-3">Nessun fornitore trovato</p>
          ) : (
            filtered.map(f => (
              <label
                key={f.key}
                className="flex items-center gap-2.5 px-3 py-1.5 hover:bg-muted/50 cursor-pointer text-xs"
              >
                <input
                  type="checkbox"
                  checked={selected.has(f.key)}
                  onChange={() => toggle(f.key)}
                  className="size-3.5 accent-primary flex-shrink-0"
                />
                <span className="truncate" title={f.label}>{f.label}</span>
              </label>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ── Punti vendita multi-select (solo catena) ─────────────────────────────────

type PuntoVenditaOpt = { id: string; nome: string; is_sede_tecnica: boolean; totale: number };

type PuntoVenditaMultiSelectProps = {
  sedi: PuntoVenditaOpt[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
};

// Erano pillole a scelta singola, una riga intera sopra le card (Mattia, 29/9):
// ora una tendina come quella dei fornitori, con l'importo da pagare accanto a
// ogni punto vendita.
function PuntoVenditaMultiSelect({ sedi, selected, onChange }: PuntoVenditaMultiSelectProps) {
  const tutti = sedi.map(s => s.id);
  const label = etichettaPuntiVendita(selected, sedi);
  const attivo = selected.size > 0;

  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            className={`h-8 text-xs gap-1.5 max-w-[260px] justify-start ${attivo ? "border-primary text-primary" : ""}`}
          >
            <MapPin className="size-3.5 flex-shrink-0" />
            <span className="truncate" title={label}>{label}</span>
            {attivo && (
              <span className="ml-auto flex-shrink-0 size-4 flex items-center justify-center rounded-full bg-primary text-primary-foreground text-[10px] font-semibold">
                {selected.size}
              </span>
            )}
          </Button>
        }
      />
      <PopoverContent className="w-72 p-0" align="start" sideOffset={6}>
        <div className="flex items-center gap-3 px-3 py-1.5 border-b">
          <button onClick={() => onChange(new Set())} className="text-[11px] text-primary hover:underline">Tutti</button>
          {attivo && (
            <span className="ml-auto text-[11px] text-muted-foreground">{selected.size} sel.</span>
          )}
        </div>
        <div className="max-h-64 overflow-y-auto py-1">
          {sedi.map(s => (
            <label
              key={s.id}
              className="flex items-center gap-2.5 px-3 py-1.5 hover:bg-muted/50 cursor-pointer text-xs"
            >
              <input
                type="checkbox"
                checked={selected.has(s.id)}
                onChange={() => onChange(alternaPuntoVendita(selected, s.id, tutti))}
                className="size-3.5 accent-primary flex-shrink-0"
              />
              {s.is_sede_tecnica
                ? <Split className="size-3.5 flex-shrink-0 text-primary-text" />
                : <MapPin className="size-3.5 flex-shrink-0 text-muted-foreground" />}
              <span className="truncate" title={s.nome}>{s.nome}</span>
              <span className="ml-auto flex-shrink-0 tabular-nums text-muted-foreground">{formatEuro(s.totale)}</span>
            </label>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type View = "agenda" | "calendario" | "lista_mensile";

const ORDINE_ARCHIVIO_LABELS: Record<OrdineArchivio, string> = {
  data: "Data fattura",
  importo: "Importo",
  fornitore: "Fornitore",
};

const ORDINE_LABELS: Record<Ordine, string> = {
  scadenza: "Scadenza (prima le vicine)",
  importo: "Importo (prima i più alti)",
  fornitore: "Fornitore (A→Z)",
};

type CestinoItem = {
  file_origine: string;
  fornitore: string;
  num_righe: number;
  totale: number;
  deleted_at: string;
  data_documento: string;
  // Il backend lo manda solo in modalita' catena (db_service.py, ramo
  // `is_multi`): li' il cestino elenca le fatture di TUTTE le sedi, e senza
  // rispedirlo ripristina/elimina agirebbero sulla sede attiva invece che su
  // quella del documento.
  ristorante_id?: string;
  sede_nome?: string;
};

function formatDateCestino(iso: string | null) {
  if (!iso) return "—";
  try { return new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(iso)); }
  catch { return iso; }
}

function daysToCestino(deleted_at: string) {
  const expiry = new Date(deleted_at);
  expiry.setDate(expiry.getDate() + 30);
  return Math.max(0, Math.ceil((expiry.getTime() - Date.now()) / 86400000));
}

type ScadenziarioClientProps = {
  initialDocumenti: Documento[];
  // Modalità catena (Fase 3): assenti/false → comportamento identico a oggi.
  modalitaCatena?: boolean;
  sedi?: SedeCatena[];
  /**
   * Il caricamento server e' FALLITO (worker giu', timeout, non-2xx), che non e'
   * la stessa cosa di "zero documenti": senza questo flag la pagina scriveva
   * «Nessun documento trovato» su un guasto, rassicurando il cliente mentre
   * aveva scadenze aperte. Default false: i chiamanti che non lo passano si
   * comportano esattamente come prima.
   */
  caricamentoFallito?: boolean;
  /**
   * Viste consentite dal pannello admin ("agenda" = Scadenzario, "calendario").
   * Default = entrambe, quindi un chiamante che non la passa resta identico a
   * prima: e' il caso della vista di CATENA (catena/fatture/page.tsx), che monta
   * questo stesso componente in un contesto diverso dal punto vendita e NON deve
   * ereditarne i flag. Scelta deliberata, non una dimenticanza da "uniformare".
   */
  visteAttive?: string[];
  /**
   * Vista su cui atterrare, dalla preferenza salvata sull'account
   * (`users.vista_fatture`). Se non e' fra quelle consentite dall'admin si cade
   * sulla prima permessa: altrimenti spegnere una vista lascerebbe chi l'aveva
   * salvata su una pagina vuota, senza il bottone per uscirne.
   */
  vistaIniziale?: string;
  /** Vista chiesta dal link (`?vista=`): vince sulla salvata, non si salva. */
  vistaRichiesta?: string;
};

export function ScadenziarioClient({ initialDocumenti, modalitaCatena = false, sedi = [], caricamentoFallito = false, visteAttive = ["lista_mensile", "agenda", "calendario"], vistaIniziale, vistaRichiesta }: ScadenziarioClientProps) {
  const [documenti, setDocumenti] = useState<Documento[]>(initialDocumenti);
  const sedeTecnicaId = sedi.find(s => s.is_sede_tecnica)?.id;
  const [filtroSede, setFiltroSede] = useState<Set<string>>(new Set()); // vuoto = tutti i punti vendita
  // Ordine delle schede e vista d'apertura: lib/tab-flags (Archivio prima,
  // Mattia 09/10/2026).
  const visteConsentite = visteFattureOrdinate(visteAttive) as View[];
  const [view, setView] = useState<View>(
    (vistaFattureIniziale(visteAttive, vistaIniziale, vistaRichiesta) ?? "lista_mensile") as View,
  );

  // Il salvataggio e' best-effort e NON blocca il cambio vista: se il POST
  // fallisce la scelta resta attiva per questa sessione, invece di lampeggiare
  // tornando indietro sotto le dita del cliente (stesso trattamento del tema in
  // impostazioni/account-client.tsx).
  function cambiaVista(v: View) {
    setView(v);
    void fetch("/api/account/preferenze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vista_fatture: v }),
    }).catch(() => {});
  }
  const [selectedFileOrigini, setSelectedFileOrigini] = useState<Set<string>>(new Set());
  const [peekDoc, setPeekDoc] = useState<Documento | null>(null);
  const [regoleOpen, setRegoleOpen] = useState(false);
  const [bulkPaying, setBulkPaying] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // ── Cestino widget
  const [cestinoOpen, setCestinoOpen] = useState(false);
  const [cestinoItems, setCestinoItems] = useState<CestinoItem[]>([]);
  const [cestinoLoading, setCestinoLoading] = useState(false);
  const [cestinoConfirmElimina, setCestinoConfirmElimina] = useState<CestinoItem | null>(null);
  // «Svuota tutto» era l'unica azione del cestino senza conferma, ed e' un hard
  // delete: le due per-riga ce l'hanno da sempre.
  const [cestinoConfermaSvuota, setCestinoConfermaSvuota] = useState(false);
  const [cestinoActionLoading, setCestinoActionLoading] = useState(false);

  // ── Filtri
  const [filtroPeriodo, setFiltroPeriodo] = useState<Periodo>("tutti");
  const [filtroFornitori, setFiltroFornitori] = useState<Set<string>>(new Set());
  const [filtroDateDa, setFiltroDateDa] = useState("");
  const [filtroDateA, setFiltroDateA] = useState("");
  const [filtroSoloNuove, setFiltroSoloNuove] = useState(false);
  const [ricerca, setRicerca] = useState("");
  const ricercaRef = useRef<HTMLInputElement>(null);
  // `null` = nessuna conferma aperta; true/false = il verso dell'operazione.
  // Un'azione di massa irreversibile una-per-una va confermata: stornare 50
  // pagamenti segnati per sbaglio costava ~150 clic.
  const [confermaBulk, setConfermaBulk] = useState<boolean | null>(null);
  const [ordine, setOrdine] = useState<Ordine>("scadenza");
  const [ordineArchivio, setOrdineArchivio] = useState<OrdineArchivio>("data");

  const filtriAttivi = filtroPeriodo !== "tutti" || filtroFornitori.size > 0 || filtroDateDa !== "" || filtroDateA !== "" || filtroSoloNuove || filtroSede.size > 0 || ricerca.trim() !== "";

  function resetFiltri() {
    setFiltroPeriodo("tutti");
    setFiltroFornitori(new Set());
    setFiltroDateDa("");
    setFiltroDateA("");
    setFiltroSoloNuove(false);
    setFiltroSede(new Set());
    setRicerca("");
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || t?.isContentEditable) return;
      // Con una modale aperta il campo di ricerca e' dietro l'overlay: dargli il
      // fuoco sposterebbe il cursore su un elemento che non si vede.
      if (document.querySelector('[role="dialog"]')) return;
      e.preventDefault();
      ricercaRef.current?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function matchFiltroSede(d: Documento): boolean {
    return inPuntiVendita(d.ristorante_id, filtroSede);
  }

  // Lista fornitori unici raggruppati per P.IVA (fallback nome se assente): la
  // stessa P.IVA con ragione sociale scritta diversa non deve apparire come
  // voci multiple nel filtro. Mostra il nome più frequente per quella chiave.
  const fornitoriUnici = useMemo(() => elencaFornitori(documenti), [documenti]);

  // ── Documenti filtrati
  // I filtri stanno in `lib/scadenziario.ts`, coperti da
  // tests/test_scadenziario_filtri_frontend.py: qui dentro nessun test li
  // raggiungeva, e decidono quali fatture il cliente vede.
  const filtriComuni = useMemo(() => ({
    periodo: filtroPeriodo,
    fornitori: [...filtroFornitori],
    soloNuove: filtroSoloNuove,
    dataDa: filtroDateDa,
    dataA: filtroDateA,
    ricerca,
  }), [filtroPeriodo, filtroFornitori, filtroSoloNuove, filtroDateDa, filtroDateA, ricerca]);

  const documentiFiltrati = useMemo(
    () => filtraDocumenti(documenti, filtriComuni, matchFiltroSede),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [documenti, filtriComuni, filtroSede, sedeTecnicaId],
  );

  // Le due azioni della barra di selezione agiscono solo sulle fatture che
  // cambiano stato: un pulsante che non cambierebbe nulla resta spento.
  const pianoPagate = useMemo(
    () => pianoAzioneDiMassa(documenti, selectedFileOrigini, true),
    [documenti, selectedFileOrigini],
  );
  const pianoNonPagate = useMemo(
    () => pianoAzioneDiMassa(documenti, selectedFileOrigini, false),
    [documenti, selectedFileOrigini],
  );
  const motivoPagateSpento = motivoAzioneSpenta(pianoPagate, true);
  const motivoNonPagateSpento = motivoAzioneSpenta(pianoNonPagate, false);

  // KPI e bucket calcolati sui documenti filtrati
  const kpi = useMemo(() => computeKpi(documentiFiltrati), [documentiFiltrati]);

  // KPI per sede (striscia cliccabile, solo modalità catena): stessi filtri
  // comuni di documentiFiltrati ma SENZA il filtro sede, aggregati per
  // ristorante_id.
  const kpiPerSede = useMemo(() => {
    if (!modalitaCatena || sedi.length === 0) return [];
    const perSede = aggregaPerSede(documenti, filtriComuni);
    return sedi.map(s => ({
      id: s.id,
      nome: s.nome_ristorante,
      is_sede_tecnica: s.is_sede_tecnica,
      count: perSede.get(s.id)?.count ?? 0,
      totale: perSede.get(s.id)?.totale ?? 0,
    }));
  }, [documenti, modalitaCatena, sedi, filtriComuni]);
  const buckets = useMemo(() => {
    const b = bucketizeDocumenti(documentiFiltrati);
    return {
      scadute: ordinaScadute(b.scadute, ordine),
      settimana: ordinaDocumenti(b.settimana, ordine),
      mese: ordinaDocumenti(b.mese, ordine),
      oltre: ordinaDocumenti(b.oltre, ordine),
      senzaScadenza: ordinaDocumenti(b.senzaScadenza, ordine),
      pagate: ordinaDocumenti(b.pagate, ordine),
      noteCredito: ordinaDocumenti(b.noteCredito, ordine),
      oscurate: ordinaDocumenti(b.oscurate, ordine),
    };
  }, [documentiFiltrati, ordine]);

  // Il calendario ha già la propria navigazione mensile: applica solo il filtro
  // fornitore (i chip periodo sono specifici dell'agenda).
  const documentiCalendario = useMemo(() =>
    filtraDocumenti(
      documenti,
      { periodo: "tutti", fornitori: [...filtroFornitori], soloNuove: filtroSoloNuove, ricerca },
      matchFiltroSede,
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [documenti, filtroFornitori, filtroSoloNuove, ricerca, filtroSede, sedeTecnicaId]
  );

  const loadData = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await fetch(modalitaCatena ? "/api/gruppo/scadenziario" : "/api/scadenziario");
      if (res.ok) {
        const data = await res.json();
        setDocumenti(data.documenti ?? []);
      }
    } finally {
      setRefreshing(false);
    }
  }, [modalitaCatena]);

  function toggleSelect(fo: string) {
    setSelectedFileOrigini(prev => {
      const next = new Set(prev);
      if (next.has(fo)) next.delete(fo); else next.add(fo);
      return next;
    });
  }

  function toggleAll(docs: Documento[], selectAll: boolean) {
    setSelectedFileOrigini(prev => {
      const next = new Set(prev);
      for (const d of docs) {
        if (selectAll) next.add(d.file_origine);
        else next.delete(d.file_origine);
      }
      return next;
    });
  }

  function selectAllVisible() {
    setSelectedFileOrigini(new Set(chiaviSelezionaTutte(documentiFiltrati)));
  }

  function deselectAll() {
    setSelectedFileOrigini(new Set());
  }

  async function handlePaga(doc: Documento, pagata = true) {
    try {
      const res = await fetch("/api/scadenziario/pagata", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_origini: [doc.file_origine], pagata, ristorante_id: doc.ristorante_id }),
      });
      const data = await res.json().catch(() => ({}));
      // Il worker risponde 200 anche se la scrittura fallisce: lo dice `ok`.
      if (!res.ok || data.ok === false) { toast.error("Errore nel salvataggio"); await loadData(); return; }
      toast.success(pagata ? "Fattura segnata come pagata" : "Pagamento annullato");
      setDocumenti(prev => applicaPagataAVideo(prev, [doc], pagata, todayLocalIso()));
    } catch {
      toast.error("Errore di connessione");
      await loadData();
    }
  }

  async function handleBulkPaga(pagata: boolean) {
    const piano = pianoAzioneDiMassa(documenti, selectedFileOrigini, pagata);
    if (piano.gruppi.length === 0) return;
    setBulkPaying(true);
    try {
      let aggiornate = 0;
      let ok = true;
      for (const { ristorante_id, file_origini } of piano.gruppi) {
        const res = await fetch("/api/scadenziario/pagata", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file_origini, pagata, ristorante_id }),
        });
        const data = await res.json().catch(() => ({}));
        // Il worker risponde 200 anche se una parte fallisce: lo dice `ok`.
        if (!res.ok || data.ok === false) { ok = false; continue; }
        aggiornate += data.aggiornate ?? 0;
      }

      if (!ok) { toast.error("Errore nel salvataggio"); await loadData(); return; }
      toast.success(messaggioEsitoAzioneDiMassa(aggiornate, pagata));
      setDocumenti(prev => applicaPagataAVideo(prev, piano.cambiano, pagata, todayLocalIso()));
      setSelectedFileOrigini(new Set());
    } catch {
      toast.error("Errore di connessione");
      await loadData();
    } finally {
      setBulkPaying(false);
    }
  }

  async function handleSetScadenza(doc: Documento, scadenza_override: string | null) {
    const res = await fetch("/api/scadenziario/scadenza", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_origine: doc.file_origine, scadenza_override, ristorante_id: doc.ristorante_id }),
    });
    if (!res.ok) { await loadData(); throw new Error("Errore salvataggio"); }
    const data = await res.json();
    setDocumenti(prev => prev.map(d =>
      d.file_origine === doc.file_origine
        ? {
            ...d,
            scadenza_effettiva: data.scadenza_effettiva ?? null,
            scadenza_source: scadenza_override ? "override" : d.scadenza_source,
            stato_scadenza: data.stato_scadenza ?? d.stato_scadenza,
          }
        : d
    ));
  }

  async function handleElimina(doc: Documento) {
    const res = await fetch("/api/fatture/elimina", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_origine: doc.file_origine, ristorante_id: doc.ristorante_id }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const detail = data.detail ?? "";
      if (detail === "already_in_trash") throw new Error("La fattura è già nel cestino");
      throw new Error(detail || "Errore durante l'eliminazione");
    }
    toast.success("Fattura spostata nel cestino");
    setDocumenti(prev => prev.filter(d => d.file_origine !== doc.file_origine));
    setPeekDoc(null);
    // Ricarica il cestino se era già aperto
    if (cestinoOpen) loadCestino();
  }

  async function handleOscura(doc: Documento, oscurata: boolean) {
    const res = await fetch("/api/fatture/oscura", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_origine: doc.file_origine, oscurata, ristorante_id: doc.ristorante_id }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const detail = data.detail ?? "";
      if (detail === "already_in_trash") throw new Error("La fattura è nel cestino");
      if (detail === "ripartita_su_gruppo") throw new Error("È ripartita sul gruppo: rimuovi prima il riparto");
      throw new Error(detail || "Operazione non riuscita");
    }
    toast.success(oscurata ? "Fattura esclusa dai conti" : "Fattura rimessa nei conti");
    // `.map` e non `.filter` come handleElimina: la riga RESTA in elenco, cambia
    // solo sezione. Il match include ristorante_id perche' in catena lo stesso
    // file_origine puo' esistere su piu' sedi: senza, si marcherebbero a video
    // due fatture con un solo click (handleElimina e handleSetScadenza hanno
    // questo difetto — preesistente, non allargato qui).
    setDocumenti(prev => prev.map(d =>
      d.file_origine === doc.file_origine && d.ristorante_id === doc.ristorante_id
        ? { ...d, oscurata }
        : d
    ));
  }

  function handleSpostata(doc: Documento) {
    setDocumenti(prev => prev.filter(d => d.file_origine !== doc.file_origine));
    setPeekDoc(null);
  }

  async function loadCestino() {
    setCestinoLoading(true);
    try {
      const res = await fetch(modalitaCatena ? "/api/gruppo/cestino" : "/api/cestino");
      if (res.ok) { const d = await res.json(); setCestinoItems(d.cestino ?? []); }
    } finally { setCestinoLoading(false); }
  }

  function toggleCestino() {
    if (!cestinoOpen) loadCestino();
    setCestinoOpen(prev => !prev);
  }

  async function handleCestinoRipristina(item: CestinoItem) {
    setCestinoActionLoading(true);
    try {
      const res = await fetch("/api/cestino/ripristina", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_origine: item.file_origine, ristorante_id: item.ristorante_id }),
      });
      const data = await res.json();
      if (!res.ok) { toast.error(data.detail || "Errore ripristino"); return; }
      toast.success(`Fattura ripristinata (${data.righe_ripristinate} prodotti)`);
      await loadCestino();
      await loadData();
    } catch { toast.error("Errore di connessione"); }
    finally { setCestinoActionLoading(false); }
  }

  async function handleCestinoEliminaConferma() {
    if (!cestinoConfirmElimina) return;
    setCestinoActionLoading(true);
    try {
      const res = await fetch("/api/cestino/elimina", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_origine: cestinoConfirmElimina.file_origine,
          ristorante_id: cestinoConfirmElimina.ristorante_id,
        }),
      });
      const data = await res.json();
      if (!res.ok) { toast.error(data.detail || "Errore eliminazione"); return; }
      toast.success(`Fattura eliminata definitivamente`);
      setCestinoConfirmElimina(null);
      await loadCestino();
    } catch { toast.error("Errore di connessione"); }
    finally { setCestinoActionLoading(false); }
  }

  // L'endpoint svuota la sola sede ATTIVA (cestino.py: _resolve_ristorante_id),
  // per scelta: svuotare tutte le sedi di una catena con un click sarebbe piu'
  // pericoloso del difetto che risolve. Ma in catena la lista mostra le fatture
  // di TUTTE le sedi, e `setCestinoItems([])` le faceva sparire tutte a video:
  // quelle delle altre sedi sembravano cancellate e ricomparivano al primo
  // «Aggiorna». Si ricarica dal server, che dice la verita'.
  async function handleCestinoSvuota() {
    setCestinoActionLoading(true);
    try {
      const res = await fetch("/api/cestino/svuota", { method: "POST" });
      const data = await res.json();
      if (!res.ok) { toast.error(data.detail || "Errore svuotamento"); return; }
      toast.success("Cestino svuotato");
      await loadCestino();
    } catch { toast.error("Errore di connessione"); }
    finally { setCestinoActionLoading(false); }
  }

  // Export CSV dell'elenco visibile (rispetta i filtri attivi, ordinato come a
  // video). Formato Excel-IT: separatore ";", BOM UTF-8, importi con virgola.
  function exportCsv() {
    const righe = ordinaDocumenti(documentiFiltrati, ordine);
    if (righe.length === 0) { toast.error("Nessuna fattura da esportare"); return; }
    const headers = ["Fornitore", "N. documento", "Data fattura", "Scadenza", "Importo", "Stato"];
    const num = (n: number | null | undefined) =>
      (n ?? 0).toFixed(2).replace(".", ",");
    const body = righe.map(d => [
      d.fornitore || "",
      d.numero_documento || "",
      d.data_documento ? formatDate(d.data_documento) : "",
      d.scadenza_effettiva ? formatDate(d.scadenza_effettiva) : "",
      num(d.totale_documento),
      statoDocumento(d),
    ]);
    const csv = [headers, ...body]
      .map(r => r.map(c => `"${String(c ?? "").replace(/"/g, '""')}"`).join(";"))
      .join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "scadenziario.csv";
    a.click();
    URL.revokeObjectURL(url);
    toast.success("CSV scaricato — aprilo con Excel");
  }

  const totaleSelezionabiliFiltrate = chiaviSelezionaTutte(documentiFiltrati).length;

  // Vista "Per mese": stessi filtri della Lista (fornitore, sede, ricerca), ma
  // NON il periodo — quello filtra su `scadenza_effettiva`, che qui non esiste.
  const gruppiMensili = useMemo(
    () => raggruppaPerMeseFattura(documentiCalendario, ordineArchivio),
    [documentiCalendario, ordineArchivio],
  );

  const sharedProps = {
    selectedFileOrigini,
    onToggleSelect: toggleSelect,
    onToggleAll: toggleAll,
    onPaga: (doc: Documento) => handlePaga(doc, true),
    onPeek: setPeekDoc,
    sedeTecnicaId,
    forzaAperta: ricercaAttiva(ricerca),
  };

  return (
    <div className="space-y-5 pb-20">
      {/* KPI bar — le card sono cliccabili e applicano il filtro periodo
          corrispondente (toggle: riclicco la card attiva → torno a "tutti").
          "Pagate (mese)" è un consuntivo, non un filtro: resta informativa.
          Nascosta in "Per mese": scadute / questa settimana / da pagare sono
          tutte grandezze di scadenza, e questa e' la vista di chi non le usa. */}
      <div className={`grid grid-cols-2 lg:grid-cols-4 gap-3 ${view === "lista_mensile" ? "hidden" : ""}`}>
        <KpiCard
          label={filtriAttivi ? "Scadute (filtro)" : "Scadute"}
          count={kpi.scadute_count} totale={kpi.scadute_totale} tone="negativo"
          active={filtroPeriodo === "scadute"}
          onClick={() => setFiltroPeriodo(p => p === "scadute" ? "tutti" : "scadute")}
        />
        <KpiCard
          label={filtriAttivi ? "Settimana (filtro)" : "Questa settimana"}
          count={kpi.settimana_count} totale={kpi.settimana_totale} tone="incerto"
          active={filtroPeriodo === "settimana"}
          onClick={() => setFiltroPeriodo(p => p === "settimana" ? "tutti" : "settimana")}
        />
        {/* La quota senza scadenza sta QUI e non in una quinta tessera: quelle
            fatture sono gia' dentro "Da pagare" (sono debiti a tutti gli
            effetti), ma sfuggono a ogni fascia temporale e nessun numero in
            cima le nominava — in produzione un terzo del non pagato. Una
            quinta card sbilancerebbe la griglia grid-cols-2 lg:grid-cols-4. */}
        <KpiCard
          label={filtriAttivi ? "Da pagare (filtro)" : "Da pagare"}
          count={kpi.da_pagare_count} totale={kpi.da_pagare_totale} tone="neutro"
          sub={kpi.senza_scadenza_count > 0
            ? `di cui ${formatEuro(kpi.senza_scadenza_totale)} senza scadenza`
            : undefined}
          active={filtroPeriodo === "tutti" && !filtriAttivi}
          onClick={() => resetFiltri()}
        />
        <KpiCard label="Pagate (mese)" count={kpi.pagate_mese_count} totale={kpi.pagate_mese_totale} tone="neutro" />
      </div>

      {/* Niente riquadro giallo «N fatture senza scadenza» (Mattia, 28/9): il
          totale sta gia' sotto «Da pagare», le fatture nella sezione «Senza
          scadenza» dell'elenco, e i termini si impostano da «Regole fornitore». */}
      {/* Reso come `map` e non con una condizione per coppia: con tre viste
          un `mostraLista && mostraCalendario` avrebbe nascosto la scheda
          proprio quando le viste sono piu' di due. */}
      {visteConsentite.length > 1 && (
        <UnderlineTabs
          value={view}
          onChange={cambiaVista}
          tabs={visteConsentite.map((v) => {
            const Icona = v === "agenda" ? List : v === "calendario" ? CalendarDays : CalendarRange;
            // «Lista / Calendario / Per mese» descrivevano la FORMA della
            // pagina, non la domanda a cui risponde, e nessuna diceva che
            // "Per mese" e' l'unica che nasconde le scadenze — cioe' proprio
            // la funzione che serve per consultare le fatture senza scadenze.
            return {
              value: v,
              label: (
                <>
                  <Icona /> {v === "agenda" ? "Scadenzario" : v === "calendario" ? "Calendario" : "Archivio fatture"}
                </>
              ),
              title:
                v === "agenda"
                  ? "Cosa devi pagare e quando, raggruppato per scadenza"
                  : v === "calendario"
                    ? "Le scadenze sul calendario, giorno per giorno"
                    : "Tutte le fatture per mese di emissione, senza scadenze",
            };
          })}
        />
      )}

      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* L'unica pagina dell'app senza aiuto, ed e' quella con tre viste e
            quattro card che si contengono a vicenda. Sta nella toolbar del
            client — non accanto al titolo, che e' un Server Component senza
            slot per figli — cosi' arriva anche alla catena. */}
        <InfoPopover title="Come leggere Gestione Fatture">
          <div className="space-y-1.5 text-muted-foreground">
            <p><strong className="text-foreground">Archivio fatture</strong> = tutte le fatture per mese di emissione, <em>senza</em> scadenze: serve per consultarle, non per pagarle.</p>
            <p><strong className="text-foreground">Scadenzario</strong> = cosa devi pagare e quando, raggruppato per scadenza.</p>
            <p><strong className="text-foreground">Calendario</strong> = le stesse scadenze sul calendario, giorno per giorno.</p>
          </div>
          <div className="border-t border-border pt-2 space-y-1.5 text-muted-foreground">
            <p className="font-medium text-foreground">Le card in alto non si sommano</p>
            <p><strong className="text-foreground">Da pagare</strong> e&apos; il totale: <strong className="text-foreground">Scadute</strong> e <strong className="text-foreground">Questa settimana</strong> sono due sue parti, gia&apos; comprese dentro.</p>
          </div>
        </InfoPopover>

        <Button variant="outline" size="sm" onClick={() => setRegoleOpen(true)}>
          <Settings2 className="size-3.5" /> Regole fornitore
        </Button>

        <Button variant="outline" size="sm" onClick={exportCsv}>
          <Download className="size-3.5" /> Esporta CSV
        </Button>

        <div className="ml-auto flex items-center gap-2">
          <Button
            variant={cestinoOpen ? "secondary" : "outline"}
            size="sm"
            onClick={toggleCestino}
          >
            <ArchiveRestore className="size-3.5" />
            Cestino{cestinoItems.length > 0 && ` (${cestinoItems.length})`}
          </Button>
          <Button variant="outline" size="sm" onClick={loadData} disabled={refreshing}>
            {refreshing ? "..." : "Aggiorna"}
          </Button>
        </div>
      </div>

      {/* Cestino collassabile */}
      {cestinoOpen && (
        <div className="rounded-lg border bg-card p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-semibold flex items-center gap-1.5">
              <ArchiveRestore className="size-4 text-muted-foreground" />
              Cestino Fatture
            </p>
            <div className="flex items-center gap-2">
              {/* Conferma inline, come le due azioni per-riga qui sotto: questa
                  pagina non usa ConfirmDialog. In catena il bottone dice quale
                  sede svuota, perche' la lista ne mostra piu' di una e
                  l'endpoint agisce sulla sola sede attiva. */}
              {cestinoItems.length > 0 && (
                cestinoConfermaSvuota ? (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">
                      {modalitaCatena ? "Elimini il cestino di questa sede?" : "Elimini tutto il cestino?"}
                    </span>
                    <Button variant="outline" size="sm" onClick={() => setCestinoConfermaSvuota(false)} disabled={cestinoActionLoading}>
                      Annulla
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => { setCestinoConfermaSvuota(false); handleCestinoSvuota(); }}
                      disabled={cestinoActionLoading}
                    >
                      {cestinoActionLoading ? <Loader2 className="size-3.5 animate-spin" /> : "Elimina"}
                    </Button>
                  </div>
                ) : (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setCestinoConfermaSvuota(true)}
                    disabled={cestinoActionLoading}
                  >
                    <Trash2 className="size-3.5 mr-1" />
                    {modalitaCatena ? "Svuota questa sede" : "Svuota tutto"}
                  </Button>
                )
              )}
              <Button variant="outline" size="sm" onClick={loadCestino} disabled={cestinoLoading}>
                {cestinoLoading ? <Loader2 className="size-3.5 animate-spin" /> : "Aggiorna"}
              </Button>
            </div>
          </div>

          {cestinoLoading ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            </div>
          ) : cestinoItems.length === 0 ? (
            <p className="text-sm text-center text-muted-foreground py-4">Cestino vuoto</p>
          ) : (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                Le fatture eliminate vengono conservate per 30 giorni.
              </p>
              {cestinoItems.map(item => {
                const days = daysToCestino(item.deleted_at);
                const urgent = days <= 5;
                return (
                  <div key={`${item.file_origine}|${item.ristorante_id ?? ""}`} className="flex items-center gap-3 px-3 py-2.5 rounded-md border bg-background hover:bg-muted/30 transition-colors">
                    <div className="flex-1 min-w-0 space-y-0.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium truncate" title={item.fornitore || item.file_origine}>{item.fornitore || item.file_origine}</span>
                        <span className="text-xs text-muted-foreground">{item.num_righe} prodott{item.num_righe === 1 ? "o" : "i"}</span>
                        {item.sede_nome && (
                          <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
                            {item.sede_nome}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
                        {item.data_documento && <span>Data: {formatDateCestino(item.data_documento)}</span>}
                        <span>Eliminata: {formatDateCestino(item.deleted_at)}</span>
                        <span className={`font-medium ${urgent ? "text-negativo" : ""}`}>
                          {days === 0 ? "Eliminazione imminente" : `${days}g al 30°`}
                        </span>
                      </div>
                    </div>
                    <span className="text-sm font-semibold flex-shrink-0">{formatEuro(item.totale)}</span>
                    <div className="flex gap-1.5 flex-shrink-0">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 gap-1 text-xs"
                        onClick={() => handleCestinoRipristina(item)}
                        disabled={cestinoActionLoading}
                      >
                        <ArchiveRestore className="size-3.5" /> Ripristina
                      </Button>
                      {cestinoConfirmElimina?.file_origine === item.file_origine &&
                       cestinoConfirmElimina?.ristorante_id === item.ristorante_id ? (
                        <div className="flex gap-1">
                          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setCestinoConfirmElimina(null)} disabled={cestinoActionLoading}>
                            Annulla
                          </Button>
                          <Button variant="destructive" size="sm" className="h-7 text-xs" onClick={handleCestinoEliminaConferma} disabled={cestinoActionLoading}>
                            {cestinoActionLoading ? <Loader2 className="size-3.5 animate-spin" /> : "Elimina"}
                          </Button>
                        </div>
                      ) : (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-7 text-muted-foreground hover:text-destructive"
                          onClick={() => setCestinoConfirmElimina(item)}
                          disabled={cestinoActionLoading}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Filtri — sotto le card e la barra delle viste (Mattia, 29/9): prima
          stavano meta' sopra le card e meta' sotto, e sembravano due barre di
          filtri. Qui c'e' tutto cio' che restringe l'elenco, in un posto solo e
          in quest'ordine: ricerca, una riga di scelte, il conteggio. */}
      <div className="space-y-3">
        {/* Ricerca — il primo gesto di chi lavora qui: il fornitore chiama e
            chiede di una fattura. Cerca su fornitore, numero documento e importo
            (matchRicerca in lib/scadenziario.ts, presidio
            tests/test_scadenziario_ricerca_frontend.py). */}
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            ref={ricercaRef}
            type="search"
            value={ricerca}
            onChange={e => setRicerca(e.target.value)}
            placeholder="Cerca fattura: fornitore, numero o importo"
            aria-label="Cerca fattura per fornitore, numero documento o importo"
            className="h-10 pl-9 pr-9"
          />
          {ricerca !== "" && (
            <button
              type="button"
              onClick={() => { setRicerca(""); ricercaRef.current?.focus(); }}
              aria-label="Pulisci la ricerca"
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          )}
        </div>

        {/* Una riga: stato, finestra di scadenza, punti vendita (catena),
            fornitori, nuove; l'ordinamento in fondo a destra. */}
        <div className="flex items-center gap-2 flex-wrap">
          <Filter className="size-3.5 text-muted-foreground flex-shrink-0" />

          {/* Stato scadenza */}
          <div className="flex items-center gap-1.5">
            {(["tutti", "scadute"] as Periodo[]).map(p => {
              const labels: Partial<Record<Periodo, string>> = { tutti: "Tutti", scadute: "Solo scadute" };
              return (
                <FilterChip key={p} active={filtroPeriodo === p} onClick={() => setFiltroPeriodo(p)}>
                  {labels[p]}
                </FilterChip>
              );
            })}
          </div>

          {/* Finestra temporale — filtra su `scadenza_effettiva`, quindi in
              "Per mese" non avrebbe alcun effetto visibile: un chip che si
              accende e non cambia l'elenco e' peggio di un chip assente. */}
          <div className={`items-center gap-1.5 ${view === "lista_mensile" ? "hidden" : "flex"}`}>
            <Separator orientation="vertical" className="mr-0.5 h-5" />
            {(["settimana", "mese"] as Periodo[]).map(p => {
              const labels: Partial<Record<Periodo, string>> = { settimana: "Questa settimana", mese: "Questo mese" };
              return (
                <FilterChip key={p} active={filtroPeriodo === p} onClick={() => setFiltroPeriodo(f => f === p ? "tutti" : p)}>
                  {labels[p]}
                </FilterChip>
              );
            })}
            <FilterChip
              active={filtroPeriodo === "personalizzato"}
              onClick={() => setFiltroPeriodo(f => f === "personalizzato" ? "tutti" : "personalizzato")}
              title="Intervallo di date personalizzato"
              aria-label="Intervallo di date personalizzato"
              className="size-7 px-0"
            >
              <Calendar />
            </FilterChip>
          </div>

          <Separator orientation="vertical" className="h-5" />

          {/* Punti vendita — solo catena: una tendina a scelta multipla al
              posto della riga di pillole a scelta singola (Mattia, 29/9). */}
          {modalitaCatena && kpiPerSede.length > 0 && (
            <PuntoVenditaMultiSelect sedi={kpiPerSede} selected={filtroSede} onChange={setFiltroSede} />
          )}
          <FornitoreMultiSelect
            fornitori={fornitoriUnici}
            selected={filtroFornitori}
            onChange={setFiltroFornitori}
          />
          <button
            type="button"
            onClick={() => setFiltroSoloNuove(v => !v)}
            title="Mostra solo le fatture arrivate dall'ultimo caricamento"
            className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors
              ${filtroSoloNuove
                ? "bg-primary text-primary-foreground border-primary"
                : "border-primary/30 bg-primary/5 text-primary hover:bg-primary/10"}`}
          >
            Nuove
          </button>

          {/* Ordinamento — nelle due viste a lista. Nel calendario no: li'
              l'ordine e' la griglia dei giorni, e un selettore sarebbe un
              controllo che non muove niente. */}
          {view !== "calendario" && (
            <div className="ml-auto flex items-center gap-1.5">
              <ArrowUpDown className="size-3.5 text-muted-foreground flex-shrink-0" />
              {view === "agenda" ? (
                <NativeSelect
                  value={ordine}
                  onValueChange={(v) => setOrdine(v as Ordine)}
                  className="h-8 text-xs w-auto"
                  aria-label="Ordina fatture"
                >
                  {(Object.keys(ORDINE_LABELS) as Ordine[]).map(k => (
                    <option key={k} value={k}>{ORDINE_LABELS[k]}</option>
                  ))}
                </NativeSelect>
              ) : (
                <NativeSelect
                  value={ordineArchivio}
                  onValueChange={(v) => setOrdineArchivio(v as OrdineArchivio)}
                  className="h-8 text-xs w-auto"
                  aria-label="Ordina fatture"
                >
                  {(Object.keys(ORDINE_ARCHIVIO_LABELS) as OrdineArchivio[]).map(k => (
                    <option key={k} value={k}>{ORDINE_ARCHIVIO_LABELS[k]}</option>
                  ))}
                </NativeSelect>
              )}
            </div>
          )}
        </div>

        {/* Date personalizzate */}
        {filtroPeriodo === "personalizzato" && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-muted-foreground">Scadenza da</span>
            <Input type="date" value={filtroDateDa} onChange={e => setFiltroDateDa(e.target.value)} className="h-7 text-xs w-36" />
            <span className="text-xs text-muted-foreground">a</span>
            <Input type="date" value={filtroDateA} onChange={e => setFiltroDateA(e.target.value)} className="h-7 text-xs w-36" />
          </div>
        )}

        {/* Risultati, pulisci filtri, seleziona tutte */}
        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground pt-0.5">
          <div className="flex items-center gap-3">
            {view === "agenda" && (
              <span>
                {/* Conta le fatture DA PAGARE, la stessa popolazione dei bucket di
                    scadenza elencati sotto: non ogni documento filtrato (note di
                    credito ed escluse hanno le loro sezioni). */}
                {filtriAttivi
                  ? `${contaDaPagare(documentiFiltrati)} su ${contaDaPagare(documenti)} fatture da pagare`
                  : `${contaDaPagare(documenti)} fatture da pagare`}
              </span>
            )}
            {filtriAttivi && (
              <button
                onClick={resetFiltri}
                className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="size-3" /> Pulisci filtri
              </button>
            )}
          </div>
          {view === "agenda" && (
            <div className="flex gap-3">
              {totaleSelezionabiliFiltrate > 0 && (
                <button className="text-primary hover:underline" onClick={selectAllVisible}>
                  Seleziona tutte ({totaleSelezionabiliFiltrate})
                </button>
              )}
              {selectedFileOrigini.size > 0 && (
                <button className="hover:underline" onClick={deselectAll}>
                  Deseleziona tutto
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      {view === "agenda" ? (
        <div className="space-y-3">
          {/* Niente riquadro «Quando pagherai» (Mattia, 09/10/2026: «non ho
              capito a cosa serve»): le fasce ripetevano le card in alto. */}
          {/* Chiusa all'apertura dal 17/09/2026: su una sede reale sono 414
              righe (1.685 in vista gruppo), e montarle tutte spingeva "Questo
              mese" — cio' su cui si agisce — a ~38 schermate di distanza. Il
              totale resta leggibile nel riquadro in cima e nel titolo di
              sezione; chi ci lavora paga un clic. */}
          <AgendaSection title="Scadute" docs={buckets.scadute} defaultOpen={false} accentClass="text-negativo" {...sharedProps} />
          <AgendaSection title="Questa settimana" docs={buckets.settimana} accentClass="text-incerto" {...sharedProps} />
          <AgendaSection title="Questo mese" docs={buckets.mese} {...sharedProps} />
          <AgendaSection title="Oltre il mese" docs={buckets.oltre} defaultOpen={false} {...sharedProps} />
          <AgendaSection title="Senza scadenza" docs={buckets.senzaScadenza} defaultOpen={false} accentClass="text-muted-foreground" {...sharedProps} />
          <AgendaSection title="Pagate" docs={buckets.pagate} defaultOpen={false} accentClass="text-positivo" {...sharedProps} />
          <NoteCreditoSection docs={buckets.noteCredito} onPeek={setPeekDoc} sedeTecnicaId={sedeTecnicaId} />
          <OscurateSection docs={buckets.oscurate} onPeek={setPeekDoc} onOscura={handleOscura} sedeTecnicaId={sedeTecnicaId} />

          {documentiFiltrati.length === 0 && (
            <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
              <Calendar className="size-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">
                {messaggioListaVuota({
                  caricamentoFallito,
                  righeCaricate: documenti.length,
                  filtriAttivi,
                  guasto: "Non è stato possibile caricare le scadenze. Riprova fra un momento.",
                  conFiltri: "Nessuna fattura corrisponde ai filtri.",
                  vuoto: "Nessun documento trovato.",
                })}
              </p>
              {filtriAttivi && (
                <button className="text-xs text-primary mt-2 hover:underline" onClick={resetFiltri}>Pulisci filtri</button>
              )}
            </div>
          )}
        </div>
      ) : view === "lista_mensile" ? (
        <div className="space-y-3">
          {gruppiMensili.map((g) => (
            <AgendaSection
              key={g.chiave || "senza-data"}
              title={g.label}
              docs={g.docs}
              // Solo il mese piu' recente aperto: con anni di storico, aprirli
              // tutti riempirebbe la pagina di righe che nessuno ha chiesto.
              defaultOpen={g === gruppiMensili[0]}
              // Come nella vista Scadenzario: con una ricerca attiva i mesi si
              // aprono, o cercare una fattura di marzo in Archivio mostrerebbe
              // solo un elenco di mesi chiusi.
              forzaAperta={ricercaAttiva(ricerca)}
              mostraScadenze={false}
              selectedFileOrigini={selectedFileOrigini}
              onToggleSelect={() => {}}
              onToggleAll={() => {}}
              onPaga={(d: Documento) => handlePaga(d, true)}
              onPeek={setPeekDoc}
              sedeTecnicaId={sedeTecnicaId}
            />
          ))}

          {/* Si testa cio' che si RENDE: questo ramo costruisce l'elenco da
              `gruppiMensili` (che ignora il filtro periodo, qui nascosto), non da
              `documentiFiltrati`. Con "Solo scadute" attivo e zero scadute, il
              messaggio "nessuna fattura" compariva sotto un elenco pieno. */}
          {gruppiMensili.length === 0 && (
            <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
              <CalendarRange className="size-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">
                {messaggioListaVuota({
                  caricamentoFallito,
                  righeCaricate: documenti.length,
                  filtriAttivi,
                  guasto: "Non è stato possibile caricare le fatture. Riprova fra un momento.",
                  conFiltri: "Nessuna fattura corrisponde ai filtri.",
                  vuoto: "Nessun documento trovato.",
                })}
              </p>
              {filtriAttivi && (
                <button className="text-xs text-primary mt-2 hover:underline" onClick={resetFiltri}>Pulisci filtri</button>
              )}
            </div>
          )}
        </div>
      ) : (
        <CalendarView documenti={documentiCalendario} />
      )}

      {/* Floating bulk action bar */}
      {selectedFileOrigini.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-full border bg-card shadow-lg px-5 py-3">
          <span className="text-sm font-medium">
            {selectedFileOrigini.size} selezionat{selectedFileOrigini.size === 1 ? "a" : "e"}
          </span>
          {/* Il motivo sta sullo span (un Button disabilitato ha pointer-events-none
              e il suo title non comparirebbe mai) e, per gli screen reader, in
              aria-describedby verso uno span `hidden`: letto una volta sola, come
              descrizione del pulsante. */}
          <span title={motivoPagateSpento ?? undefined}>
            <Button
              size="sm"
              className="h-8 gap-1.5 rounded-full"
              onClick={() => setConfermaBulk(true)}
              disabled={bulkPaying || motivoPagateSpento !== null}
              aria-describedby={motivoPagateSpento ? "motivo-segna-pagate" : undefined}
            >
              <Check className="size-3.5" />
              {bulkPaying ? "Salvataggio…" : "Segna pagate"}
            </Button>
            {motivoPagateSpento && <span id="motivo-segna-pagate" hidden>{motivoPagateSpento}</span>}
          </span>
          <span title={motivoNonPagateSpento ?? "Riporta le fatture selezionate fra quelle da pagare"}>
            <Button
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 rounded-full"
              onClick={() => setConfermaBulk(false)}
              disabled={bulkPaying || motivoNonPagateSpento !== null}
              aria-describedby={motivoNonPagateSpento ? "motivo-segna-non-pagate" : undefined}
            >
              <X className="size-3.5" />
              Segna non pagate
            </Button>
            {motivoNonPagateSpento && <span id="motivo-segna-non-pagate" hidden>{motivoNonPagateSpento}</span>}
          </span>
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

      {/* La conferma dice QUANTE fatture e QUANTI euro: "12 fatture, 8.450,00 €"
          e' verificabile a colpo d'occhio, "12 selezionate" no. */}
      <ConfirmDialog
        open={confermaBulk !== null}
        titolo={confermaBulk ? "Segnare come pagate?" : "Riportare fra quelle da pagare?"}
        messaggio={confermaBulk
          ? messaggioConfermaAzioneDiMassa(pianoPagate, true)
          : messaggioConfermaAzioneDiMassa(pianoNonPagate, false)}
        confermaLabel={confermaBulk ? "Segna pagate" : "Segna non pagate"}
        onConferma={() => { if (confermaBulk !== null) handleBulkPaga(confermaBulk); }}
        onClose={() => setConfermaBulk(null)}
      />

      <PeekDialog
        doc={peekDoc}
        onClose={() => setPeekDoc(null)}
        onPaga={(doc, pagata) => handlePaga(doc, pagata)}
        onSetScadenza={handleSetScadenza}
        onElimina={handleElimina}
        onOscura={handleOscura}
        onSpostata={handleSpostata}
        modalitaCatena={modalitaCatena}
      />

      <RegoleDialog
        open={regoleOpen}
        onClose={() => setRegoleOpen(false)}
        onSalvato={loadData}
      />
    </div>
  );
}
