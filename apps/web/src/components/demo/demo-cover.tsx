"use client";

import { ArrowRight } from "lucide-react";
import { Logo, Wordmark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { DEMO_STEPS } from "@/lib/demo-steps";

// Schermata "0": copertina d'ingresso, PRIMA dello step 1. Chi arriva dal link
// diretto (WhatsApp/email) o dal tasto in landing non deve trovarsi già dentro
// il tour senza sapere cos'è. Impianto (audit CRO 10/07):
//   - VOCE ASSISTENTE fin da qui ("Ciao, sono l'assistente"): la presentazione
//     avviene in copertina, non allo step 1 — narratore unico per tutto il tour.
//   - OPEN LOOP sui soldi ("quanti soldi trovo nelle fatture"): la promessa che
//     la chiusura incassa col bottino 220 €. Niente copy da manuale d'uso.
//   - Bottone BLU brand (primary): il verde è riservato al momento-soldi
//     (chiusura + skip), così in chiusura è un segnale, non una tinta ricorrente.
export function DemoCover({ onStart }: { onStart: () => void }) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center bg-gradient-to-br from-sky-500/10 via-background to-background px-6 py-12">
      <div className="w-full max-w-md text-center">
        <div className="flex items-center justify-center gap-2.5">
          <Logo variant="icon" size={36} glow />
          <Wordmark className="text-2xl" />
        </div>

        <h1 className="mt-8 text-2xl font-bold leading-snug tracking-tight sm:text-3xl">
          Ciao, sono l&apos;assistente di ONEFLUX
        </h1>

        {/* {" "} esplicito dopo l'espressione: il compilatore JSX (SWC) mangia
            lo spazio quando il testo che segue va a capo nel sorgente
            (verificato in prod locale: "in 6passi"). */}
        <p className="mt-3 text-base text-muted-foreground">
          Dammi 1 minuto: in {DEMO_STEPS.length}{" "}
          passi ti mostro quanti soldi trovo nelle fatture di &quot;Marea&quot;,
          un ristorante di esempio. Poi immagina le tue.
        </p>

        <div className="mt-8 flex flex-col items-center gap-3">
          <Button
            size="lg"
            onClick={onStart}
            className="h-12 w-full max-w-sm gap-2 text-base shadow-lg shadow-primary/30"
          >
            Fammi vedere
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
