"use client";

import { CopyButton } from "@/components/ui/copy-button";
import { sottotitoloBozza, type BozzaFornitore } from "@/lib/home-chat";

// La bozza al fornitore, sotto la risposta dell'assistente (fase 3, step 4): lo
// stesso testo di Prezzi → Score, da copiare. Nessun invio.
export function CardBozzaFornitore({ bozza }: { bozza: BozzaFornitore }) {
  return (
    <div className="mr-auto w-full space-y-2 rounded-xl border border-border bg-card px-3 py-2.5 text-sm sm:max-w-[85%]">
      <div>
        <p className="font-medium text-foreground">Bozza per {bozza.fornitore}</p>
        <p className="text-xs text-muted-foreground">{sottotitoloBozza(bozza)}</p>
      </div>
      <pre className="whitespace-pre-wrap break-words rounded-lg bg-muted/40 p-3 font-sans text-sm leading-relaxed text-foreground">
        {bozza.testo}
      </pre>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">Non la invio a nessuno: copiala e usala dove preferisci.</p>
        <CopyButton testo={bozza.testo} />
      </div>
    </div>
  );
}
