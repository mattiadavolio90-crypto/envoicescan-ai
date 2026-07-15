"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/select";
import { Button } from "@/components/ui/button";

type Sede = { id: string; nome: string };

// Dialog per ripartire una fattura di struttura sul gruppo. Due modalità:
//  - da FATTURA (fileOrigine): il documento è già in `fatture`, usato dal dettaglio
//    fattura (Scadenziario) → POST /api/riparto/da-fattura.
//  - da CODA (queueId): la fattura è ancora in coda 'da_assegnare', si ripartisce
//    direttamente senza assegnarla a un locale → POST /api/riparto/da-coda. Il worker
//    la atterra sulla sede tecnica "Costi comuni di gruppo" in background.
// Passare esattamente uno tra fileOrigine e queueId.
export function RipartisciDialog({
  open,
  onOpenChange,
  fileOrigine,
  queueId,
  descrizioneDefault,
  sedi,
  onDone,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  fileOrigine?: string;
  queueId?: number;
  descrizioneDefault?: string;
  sedi: Sede[];
  onDone?: () => void;
}) {
  const [descrizione, setDescrizione] = useState(descrizioneDefault ?? "");
  const [tipo, setTipo] = useState<"generale" | "fb">("generale");
  const [regola, setRegola] = useState<"equa" | "percentuali">("equa");
  const [perc, setPerc] = useState<Record<string, string>>({});
  const [salvaRegola, setSalvaRegola] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setDescrizione(descrizioneDefault ?? "");
      // Percentuali iniziali: parti uguali come suggerimento editabile.
      const eq = sedi.length > 0 ? (100 / sedi.length).toFixed(1) : "0";
      setPerc(Object.fromEntries(sedi.map((s) => [s.id, eq])));
    }
  }, [open, descrizioneDefault, sedi]);

  const sommaPerc = Object.values(perc).reduce((a, v) => a + (Number(v.replace(",", ".")) || 0), 0);

  async function salva() {
    if (!descrizione.trim()) {
      toast.error("Inserisci una descrizione");
      return;
    }
    if (regola === "percentuali" && Math.abs(sommaPerc - 100) > 0.5) {
      toast.error(`Le percentuali devono sommare 100 (ora: ${sommaPerc.toFixed(1)})`);
      return;
    }
    setSaving(true);
    try {
      const daCoda = queueId != null;
      const body: Record<string, unknown> = {
        descrizione: descrizione.trim(),
        tipo,
        regola,
        salva_regola_fornitore: salvaRegola,
        ...(daCoda ? { queue_id: queueId } : { file_origine: fileOrigine }),
      };
      if (regola === "percentuali") {
        body.percentuali = Object.fromEntries(
          Object.entries(perc).map(([id, v]) => [id, Number(v.replace(",", ".")) || 0]),
        );
      }
      const res = await fetch(daCoda ? "/api/riparto/da-coda" : "/api/riparto/da-fattura", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail || data?.error);
      toast.success("Fattura ripartita sul gruppo");
      onDone?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error && e.message ? e.message : "Impossibile ripartire la fattura");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Ripartisci sul gruppo</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Costo di struttura comune (es. commercialista, auto): la quota di ogni sede entra nel suo
            MOL. Il documento resta intero nell&apos;analisi fatture.
          </p>
          <div>
            <label className="mb-1 block text-xs font-medium">Descrizione</label>
            <input
              value={descrizione}
              onChange={(e) => setDescrizione(e.target.value)}
              placeholder="Es. Commercialista giugno"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium">Tipo di costo</label>
              <NativeSelect value={tipo} onValueChange={(v) => setTipo(v as "generale" | "fb")} className="h-[38px] text-sm">
                <option value="generale">Spese generali</option>
                <option value="fb">F&B</option>
              </NativeSelect>
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium">Ripartizione</label>
              <NativeSelect value={regola} onValueChange={(v) => setRegola(v as "equa" | "percentuali")} className="h-[38px] text-sm">
                <option value="equa">Parti uguali</option>
                <option value="percentuali">Percentuali</option>
              </NativeSelect>
            </div>
          </div>

          {regola === "percentuali" && (
            <div className="space-y-1.5 rounded-md border p-2.5">
              {sedi.map((s) => (
                <div key={s.id} className="flex items-center gap-2 text-sm">
                  <span className="flex-1 truncate">{s.nome}</span>
                  <input
                    value={perc[s.id] ?? ""}
                    onChange={(e) => setPerc((p) => ({ ...p, [s.id]: e.target.value }))}
                    inputMode="decimal"
                    className="w-16 rounded border bg-background px-2 py-1 text-right text-sm tabular-nums"
                  />
                  <span className="text-muted-foreground">%</span>
                </div>
              ))}
              <div className={`text-right text-xs ${Math.abs(sommaPerc - 100) > 0.5 ? "text-destructive" : "text-muted-foreground"}`}>
                Totale: {sommaPerc.toFixed(1)}%
              </div>
            </div>
          )}

          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={salvaRegola} onChange={(e) => setSalvaRegola(e.target.checked)} />
            Fai sempre così per questo fornitore (proposta automatica la prossima volta)
          </label>

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={saving}>
              Annulla
            </Button>
            <Button size="sm" onClick={salva} disabled={saving}>
              {saving ? "Ripartizione…" : "Ripartisci"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
