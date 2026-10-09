"use client";

import { useState, useEffect } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
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

// I colori che il cliente puo' dare a un appunto sono i token dell'app, cosi'
// reggono nei due temi. "Viola" (chiave `purple`) non ha un token ed e' uscito
// dal selettore il 18/09/2026: gli appunti salvati con quella chiave cadono sul
// primo colore, via `coloreInfo`.
const COLORI: { key: string; label: string; dot: string; badge: string }[] = [
  { key: "sky",   label: "Blu",     dot: "bg-primary",  badge: "bg-accent text-primary-text" },
  { key: "green", label: "Verde",   dot: "bg-positivo", badge: "bg-positivo/10 text-positivo" },
  { key: "amber", label: "Arancio", dot: "bg-incerto",  badge: "bg-incerto/10 text-incerto" },
  { key: "red",   label: "Rosso",   dot: "bg-negativo", badge: "bg-negativo/10 text-negativo" },
  { key: "gray",  label: "Grigio",  dot: "bg-muted-foreground/60", badge: "bg-muted text-muted-foreground" },
];

export function coloreInfo(key: string) {
  return COLORI.find(c => c.key === key) ?? COLORI[0];
}

// ─── Utilità ──────────────────────────────────────────────────────────────────

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
  // Salvataggio ed eliminazione: il chiamante ricarica il calendario.
  onSaved: () => void;
}

// Dal 09/10/2026 (Mattia, fase H2) e' l'unico posto dove un appuntamento si
// crea, si modifica, si colora e si elimina: la scheda «Appuntamenti»
// dell'Agenda e' confluita nel «Calendario» (agenda-overview.tsx).
export function EventoDialog({ open, evento, dataDefault, onClose, onSaved }: EventoDialogProps) {
  const [titolo, setTitolo] = useState("");
  const [descrizione, setDescrizione] = useState("");
  const [data, setData] = useState(dataDefault);
  const [oraInizio, setOraInizio] = useState("");
  const [oraFine, setOraFine] = useState("");
  const [colore, setColore] = useState("sky");
  const [saving, setSaving] = useState(false);
  const [confermaElimina, setConfermaElimina] = useState(false);

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

  async function elimina() {
    if (!evento) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/workspace/diario/${evento.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Evento eliminato");
      onSaved();
      onClose();
    } catch {
      toast.error("Errore eliminazione evento");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
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
            {evento && (
              <Button
                variant="ghost"
                className="mr-auto text-muted-foreground hover:text-negativo"
                onClick={() => setConfermaElimina(true)}
                disabled={saving}
              >
                <Trash2 /> Elimina
              </Button>
            )}
            <Button variant="outline" onClick={onClose} disabled={saving}>Annulla</Button>
            <Button onClick={salva} disabled={saving}>{saving ? "Salvo…" : "Salva"}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>

    <ConfirmDialog
      open={confermaElimina}
      titolo={evento ? `Eliminare "${evento.titolo}"?` : ""}
      onConferma={elimina}
      onClose={() => setConfermaElimina(false)}
    />
    </>
  );
}
