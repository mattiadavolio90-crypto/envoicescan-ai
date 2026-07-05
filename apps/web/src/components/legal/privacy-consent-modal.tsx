"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

interface Props {
  needsConsent: boolean;
}

// Modale bloccante per gli account creati prima dell'introduzione del consenso
// esplicito (2/6/2026, rev.25): quei clienti non hanno mai avuto occasione di
// accettare Privacy/Termini con una checkbox reale. Mostrato una sola volta,
// al primo accesso dopo il deploy, finche' non registra un consenso vero
// (GDPR Art. 7.1) — non e' dismissibile senza accettare, ma non blocca il
// resto dell'app (nessun redirect, resta sopra il contenuto).
export function PrivacyConsentModal({ needsConsent }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(needsConsent);
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);

  if (!open) return null;

  async function handleAccetta() {
    setSaving(true);
    try {
      const res = await fetch("/api/auth/accetta-privacy", { method: "POST" });
      if (!res.ok) throw new Error();
      setOpen(false);
      router.refresh();
    } catch {
      toast.error("Errore nel salvataggio, riprova.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={() => {}} disablePointerDismissal>
      <DialogContent className="w-full sm:max-w-md gap-5" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Aggiornamento Informativa Privacy</DialogTitle>
        </DialogHeader>

        <p className="text-sm text-muted-foreground">
          Per continuare a usare ONEFLUX ti chiediamo di confermare di aver letto
          l&apos;Informativa Privacy e i Termini di Servizio, aggiornati per il
          trattamento dei tuoi dati (GDPR UE 2016/679, art. 6.1.b).
        </p>

        <label className="flex items-start gap-2.5 text-sm cursor-pointer">
          <input
            type="checkbox"
            className="mt-0.5 size-4 shrink-0 accent-primary cursor-pointer"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
            disabled={saving}
          />
          <span>
            Ho letto e accetto l&apos;
            <Link href="/privacy" target="_blank" className="text-primary hover:underline">
              Informativa Privacy
            </Link>{" "}
            e i{" "}
            <Link href="/termini" target="_blank" className="text-primary hover:underline">
              Termini di Servizio
            </Link>
            . Acconsento al trattamento dei miei dati per l&apos;erogazione del servizio.
          </span>
        </label>

        <DialogFooter>
          <Button onClick={handleAccetta} disabled={!checked || saving} className="w-full">
            {saving ? "Salvataggio..." : "Conferma e continua"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
