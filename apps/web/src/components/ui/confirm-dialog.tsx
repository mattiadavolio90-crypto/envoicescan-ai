"use client";

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
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-[calc(100vw-2rem)] rounded-2xl">
        <DialogHeader>
          <DialogTitle>{titolo}</DialogTitle>
        </DialogHeader>
        {messaggio && <p className="text-sm text-muted-foreground">{messaggio}</p>}
        <div className="mt-2 flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 rounded-lg border border-border py-2.5 text-sm font-medium active:scale-[0.98]"
          >
            Annulla
          </button>
          <button
            onClick={() => { onConferma(); onClose(); }}
            className="flex-1 rounded-lg bg-destructive py-2.5 text-sm font-semibold text-destructive-foreground active:scale-[0.98]"
          >
            {confermaLabel}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
