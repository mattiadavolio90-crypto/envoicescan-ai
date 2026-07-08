"use client";

import { ArrowRight } from "lucide-react";
import { Logo, Wordmark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { DEMO_STEPS } from "@/lib/demo-steps";

// Schermata "0": copertina d'ingresso, PRIMA dello step 1. Chi arriva dal link
// diretto (WhatsApp/email) o dal tasto in landing non deve trovarsi già dentro
// il tour senza sapere cos'è: qui si dice in una riga cos'è ("Marea", dati di
// esempio), quanto dura (N passi) e si dà il via col bottone — niente scroll o
// spotlight in questa schermata, stessa impaginazione della chiusura per
// coerenza visiva apertura/chiusura del tour.
export function DemoCover({ onStart }: { onStart: () => void }) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center bg-gradient-to-br from-sky-500/10 via-background to-background px-6 py-12">
      <div className="w-full max-w-md text-center">
        <div className="flex items-center justify-center gap-2.5">
          <Logo variant="icon" size={36} glow />
          <Wordmark className="text-2xl" />
        </div>

        <h1 className="mt-8 text-2xl font-bold leading-snug tracking-tight sm:text-3xl">
          Benvenuto nella demo di ONEFLUX
        </h1>

        <p className="mt-3 text-base text-muted-foreground">
          Ti mostro in {DEMO_STEPS.length} passi (circa 1 minuto) come lavora il
          tuo assistente, su un ristorante di esempio — &quot;Marea&quot;.
        </p>

        <div className="mt-8 flex flex-col items-center gap-3">
          <Button
            size="lg"
            onClick={onStart}
            className="h-12 w-full max-w-sm gap-2 bg-emerald-600 text-base text-white shadow-lg shadow-emerald-600/30 hover:bg-emerald-700"
          >
            Inizia il tour
            <ArrowRight className="size-5" />
          </Button>
          <p className="text-xs text-muted-foreground">
            Dati di esempio, nessun dato reale
          </p>
        </div>
      </div>
    </div>
  );
}
