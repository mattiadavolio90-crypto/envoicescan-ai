"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

// Dialog di conferma coerente col design mobile, in sostituzione del confirm()
// nativo (brutto e fuori stile). Controllato dal genitore via `open`.
export function ConfirmDialog({
  open,
  titolo,
  messaggio,
  confermaLabel = "Elimina",
  onConferma,
  onClose,
}: {
  open: boolean;
  titolo: string;
  messaggio?: string;
  confermaLabel?: string;
  onConferma: () => void;
  onClose: () => void;
}) {
  // Durante l'animazione di chiusura il dialog resta a video per un attimo: se
  // il genitore ha gia' cambiato titolo e messaggio (verso azzerato, selezione
  // svuotata) comparirebbero quelli nuovi, per esempio «0 fatture per 0 €».
  // Da chiuso si mostra l'ultimo contenuto visto da aperto.
  const [ultimo, setUltimo] = useState({ titolo, messaggio, confermaLabel });
  useEffect(() => {
    if (open) setUltimo({ titolo, messaggio, confermaLabel });
  }, [open, titolo, messaggio, confermaLabel]);
  const mostrato = open ? { titolo, messaggio, confermaLabel } : ultimo;

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-[calc(100vw-2rem)] rounded-2xl">
        <DialogHeader>
          <DialogTitle>{mostrato.titolo}</DialogTitle>
        </DialogHeader>
        {mostrato.messaggio && <p className="text-sm text-muted-foreground">{mostrato.messaggio}</p>}
        <div className="mt-2 flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 rounded-lg border border-border py-2.5 text-sm font-medium active:scale-[0.98]"
          >
            Annulla
          </button>
          <button
            onClick={() => { onConferma(); onClose(); }}
            className="flex-1 rounded-lg bg-destructive py-2.5 text-sm font-semibold text-white active:scale-[0.98]"
          >
            {mostrato.confermaLabel}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
