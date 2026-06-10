"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

// ─── Tipi ────────────────────────────────────────────────────────────────────

export interface EventoDiario {
  id: string;
  data_evento: string;
  titolo: string;
  descrizione?: string | null;
  ora_inizio?: string | null;
  ora_fine?: string | null;
  colore: string;
}

// ─── Colori disponibili ───────────────────────────────────────────────────────

const COLORI: { key: string; label: string; dot: string; badge: string }[] = [
  { key: "sky",    label: "Blu",     dot: "bg-sky-500",    badge: "bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200" },
  { key: "green",  label: "Verde",   dot: "bg-green-500",  badge: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" },
  { key: "amber",  label: "Arancio", dot: "bg-amber-500",  badge: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200" },
  { key: "red",    label: "Rosso",   dot: "bg-red-500",    badge: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200" },
  { key: "purple", label: "Viola",   dot: "bg-purple-500", badge: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200" },
  { key: "gray",   label: "Grigio",  dot: "bg-gray-400",   badge: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300" },
];

function coloreInfo(key: string) {
  return COLORI.find(c => c.key === key) ?? COLORI[0];
}

// ─── Utilità date ─────────────────────────────────────────────────────────────

const MESI = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];
const GIORNI_BREVI = ["L","M","M","G","V","S","D"];

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
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const g = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${g}`;
}

function fmtOra(t: string | null | undefined) {
  if (!t) return "";
  return t.slice(0, 5);
}

// ─── Dialog evento ────────────────────────────────────────────────────────────

interface EventoDialogProps {
  open: boolean;
  evento: EventoDiario | null;
  dataDefault: string;
  onClose: () => void;
  onSaved: () => void;
}

export function EventoDialog({ open, evento, dataDefault, onClose, onSaved }: EventoDialogProps) {
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
    if (!titolo.trim()) { toast.error("Il titolo è obbligatorio"); return; }
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
      const method = evento ? "PATCH" : "POST";
      const res = await fetch(url, {
        method,
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
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{evento ? "Modifica evento" : "Nuovo evento"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Titolo *</label>
            <Input
              value={titolo}
              onChange={e => setTitolo(e.target.value)}
              placeholder="es. Riunione con chef, Manutenzione frigo…"
              autoFocus
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Data *</label>
            <Input type="date" value={data} onChange={e => setData(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Ora inizio</label>
              <Input type="time" value={oraInizio} onChange={e => setOraInizio(e.target.value)} />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Ora fine</label>
              <Input type="time" value={oraFine} onChange={e => setOraFine(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Note</label>
            <textarea
              value={descrizione}
              onChange={e => setDescrizione(e.target.value)}
              rows={3}
              placeholder="Dettagli aggiuntivi…"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-2 block">Colore</label>
            <div className="flex gap-2">
              {COLORI.map(c => (
                <button
                  key={c.key}
                  title={c.label}
                  onClick={() => setColore(c.key)}
                  className={`size-6 rounded-full ${c.dot} transition-transform ${colore === c.key ? "ring-2 ring-offset-2 ring-foreground/30 scale-110" : "opacity-60 hover:opacity-100"}`}
                />
              ))}
            </div>
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

// ─── Calendario mini ──────────────────────────────────────────────────────────

interface CalendarioProps {
  anno: number;
  mese: number;
  eventi: EventoDiario[];
  selezionato: string | null;
  onSelect: (d: string) => void;
}

function CalendarioMini({ anno, mese, eventi, selezionato, onSelect }: CalendarioProps) {
  const oggi = todayISO();
  const n = giorniNelMese(anno, mese);
  const offset = primoGiornoMese(anno, mese);
  const eventiPerGiorno: Record<string, EventoDiario[]> = {};
  for (const e of eventi) {
    if (!eventiPerGiorno[e.data_evento]) eventiPerGiorno[e.data_evento] = [];
    eventiPerGiorno[e.data_evento].push(e);
  }

  const celle: (number | null)[] = [
    ...Array(offset).fill(null),
    ...Array.from({ length: n }, (_, i) => i + 1),
  ];

  return (
    <div className="select-none">
      <div className="grid grid-cols-7 mb-1">
        {GIORNI_BREVI.map((g, i) => (
          <div key={i} className="text-center text-[10px] font-medium text-muted-foreground py-1">{g}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {celle.map((giorno, i) => {
          if (!giorno) return <div key={i} />;
          const iso = `${anno}-${String(mese + 1).padStart(2, "0")}-${String(giorno).padStart(2, "0")}`;
          const isOggi = iso === oggi;
          const isSel = iso === selezionato;
          const dots = (eventiPerGiorno[iso] ?? []).slice(0, 4);
          return (
            <button
              key={iso}
              onClick={() => onSelect(iso)}
              className={`flex flex-col items-center justify-start rounded-lg py-1.5 min-h-[44px] text-sm transition-colors
                ${isSel ? "bg-primary text-primary-foreground font-semibold" : isOggi ? "ring-1 ring-primary font-semibold" : "hover:bg-muted"}
              `}
            >
              <span>{giorno}</span>
              {dots.length > 0 && (
                <div className="flex gap-0.5 mt-1">
                  {dots.map((e, di) => (
                    <span key={di} className={`size-1.5 rounded-full ${coloreInfo(e.colore).dot} ${isSel ? "opacity-90" : ""}`} />
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

// ─── Vista Agenda (calendario eventi) ───────────────────────────────────────────

export function AgendaView() {
  const today = todayISO();
  const now = new Date();
  const [anno, setAnno] = useState(now.getFullYear());
  const [mese, setMese] = useState(now.getMonth());
  const [eventi, setEventi] = useState<EventoDiario[]>([]);
  const [loading, setLoading] = useState(false);
  const [giornoSel, setGiornoSel] = useState<string>(today);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editEvento, setEditEvento] = useState<EventoDiario | null>(null);

  const loadEventi = useCallback(async (a: number, m: number) => {
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

  useEffect(() => { loadEventi(anno, mese); }, [anno, mese, loadEventi]);

  function mesePrecedente() {
    if (mese === 0) { setAnno(a => a - 1); setMese(11); }
    else setMese(m => m - 1);
  }
  function meseSuccessivo() {
    if (mese === 11) { setAnno(a => a + 1); setMese(0); }
    else setMese(m => m + 1);
  }

  async function elimina(e: EventoDiario) {
    if (!confirm(`Eliminare "${e.titolo}"?`)) return;
    try {
      const res = await fetch(`/api/workspace/diario/${e.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Evento eliminato");
      loadEventi(anno, mese);
    } catch {
      toast.error("Errore eliminazione evento");
    }
  }

  const eventiGiorno = eventi.filter(e => e.data_evento === giornoSel)
    .sort((a, b) => (a.ora_inizio ?? "99:99").localeCompare(b.ora_inizio ?? "99:99"));

  const fmtGiornoLabel = (iso: string) => {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-[1fr_320px] gap-4 items-start">
      {/* Calendario largo */}
      <Card>
        <CardContent className="p-4">
          {/* Navigazione mese */}
          <div className="flex items-center justify-center gap-2 mb-3">
            <button onClick={mesePrecedente} className="p-1 rounded hover:bg-muted">
              <ChevronLeft className="size-4" />
            </button>
            <span className="text-sm font-semibold min-w-[140px] text-center">{MESI[mese]} {anno}</span>
            <button onClick={meseSuccessivo} className="p-1 rounded hover:bg-muted">
              <ChevronRight className="size-4" />
            </button>
          </div>
          <CalendarioMini
            anno={anno}
            mese={mese}
            eventi={eventi}
            selezionato={giornoSel}
            onSelect={setGiornoSel}
          />
        </CardContent>
      </Card>

      {/* Pannello giorno selezionato */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold capitalize">{fmtGiornoLabel(giornoSel)}</h2>
          <Button
            size="sm"
            onClick={() => { setEditEvento(null); setDialogOpen(true); }}
          >
            <Plus className="size-3.5 mr-1" />Aggiungi
          </Button>
        </div>

        {loading ? (
          <div className="py-12 text-center text-sm text-muted-foreground">Caricamento…</div>
        ) : eventiGiorno.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            Nessun evento per questo giorno.
          </div>
        ) : (
          <div className="space-y-2">
            {eventiGiorno.map(e => {
              const col = coloreInfo(e.colore);
              return (
                <div
                  key={e.id}
                  className="flex items-start gap-3 rounded-lg border border-border p-3 hover:bg-muted/40 group"
                >
                  <div className={`mt-1 size-2.5 rounded-full flex-shrink-0 ${col.dot}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm truncate">{e.titolo}</span>
                      {(e.ora_inizio || e.ora_fine) && (
                        <span className="text-xs text-muted-foreground flex-shrink-0">
                          {fmtOra(e.ora_inizio)}{e.ora_fine ? `–${fmtOra(e.ora_fine)}` : ""}
                        </span>
                      )}
                    </div>
                    {e.descrizione && (
                      <p className="text-xs text-muted-foreground mt-0.5 whitespace-pre-wrap">{e.descrizione}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      onClick={() => { setEditEvento(e); setDialogOpen(true); }}
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7 text-muted-foreground hover:text-destructive"
                      onClick={() => elimina(e)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <EventoDialog
        open={dialogOpen}
        evento={editEvento}
        dataDefault={giornoSel}
        onClose={() => { setDialogOpen(false); setEditEvento(null); }}
        onSaved={() => loadEventi(anno, mese)}
      />
    </div>
  );
}
