"use client";

import { ArrowLeft, ArrowRight, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/brand/logo";
import type { DemoStep } from "@/lib/demo-steps";

// Barra-guida unica in alto. È l'UNICO elemento del tour: niente tooltip
// flottanti, niente faretto sull'elemento. Contiene:
//   riga 1 → "DEMO ONEFLUX · Guida X di 6" + puntini avanzamento + ← Avanti → ✕
//   riga 2 → descrizione del passo corrente
// La schermata sotto resta completamente pulita e nitida.

type Props = {
  step: DemoStep;
  index: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
  onSkipToEnd: () => void;
};

// Dallo step MOL in poi il prospect ha già visto i soldi (chat + rincari in
// euro): gli offriamo una scorciatoia diretta al finale invece di obbligarlo
// a passare per tutti gli step rimanenti.
const SKIP_DA_INDICE = 3;

export function DemoTopBar({ step, index, total, onPrev, onNext, onClose, onSkipToEnd }: Props) {
  const isFirst = index === 0;
  const isLast = index === total - 1;
  const showSkip = index >= SKIP_DA_INDICE && !isLast;

  return (
    // relative z-[70]: la barra deve restare cliccabile SOPRA anche il Dialog
    // "Configura assistente" aperto nello step 2 (backdrop/content a z-50).
    // Sfondo OPACO (bg-background + velo ambra come background-image): niente
    // trasparenze — quello che passa sotto la barra non deve intravedersi mai.
    <div className="relative z-[70] shrink-0 border-b-2 border-amber-400/60 bg-background bg-[linear-gradient(rgba(245,158,11,0.14),rgba(245,158,11,0.14))] px-4 py-2.5 sm:px-6">
      {/* riga 1: identità demo + avanzamento + controlli, SEMPRE su una riga
          sola (niente wrap): su mobile l'etichetta si accorcia a "2/6" invece
          di "Demo ONEFLUX · Passo 2 di 6", che è troppo lunga e costringeva i
          bottoni ad andare a capo in modo disallineato. */}
      <div className="flex items-center gap-2">
        <span className="inline-flex min-w-0 shrink items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400">
          <Logo variant="icon" size={16} className="shrink-0" />
          <span className="hidden sm:inline">Demo ONEFLUX</span>
          <span className="hidden text-amber-500/60 sm:inline">·</span>
          <span className="font-semibold">
            <span className="sm:hidden">{index + 1}/{total}</span>
            <span className="hidden sm:inline">Passo {index + 1} di {total}</span>
          </span>
        </span>

        {/* puntini avanzamento */}
        <div className="hidden items-center gap-1.5 sm:flex">
          {Array.from({ length: total }).map((_, i) => (
            <span
              key={i}
              className={cn(
                "h-1.5 rounded-full transition-all",
                i === index ? "w-5 bg-amber-400" : "w-1.5 bg-amber-400/30",
              )}
            />
          ))}
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <button
            onClick={onPrev}
            disabled={isFirst}
            aria-label="Passo precedente"
            className="inline-flex size-8 items-center justify-center rounded-lg text-amber-700 transition-colors hover:bg-amber-500/20 disabled:pointer-events-none disabled:opacity-30 dark:text-amber-400"
          >
            <ArrowLeft className="size-4" />
          </button>
          <button
            onClick={onNext}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-amber-500 px-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-amber-600 sm:px-4"
          >
            <span className="hidden sm:inline">{isLast ? "Voglio provarlo" : "Avanti"}</span>
            <span className="sm:hidden">{isLast ? "Provalo" : "Avanti"}</span>
            <ArrowRight className="size-4" />
          </button>
          <button
            onClick={onClose}
            aria-label="Chiudi la demo"
            className="inline-flex size-8 items-center justify-center rounded-lg text-amber-700 transition-colors hover:bg-amber-500/20 dark:text-amber-400"
          >
            <X className="size-4" />
          </button>
        </div>
      </div>

      {/* riga 2: titolo + descrizione del passo */}
      <div className="mt-1.5 flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-2">
        <span className="text-sm font-bold leading-snug text-foreground sm:text-[15px]">
          {step.title}
        </span>
        <span className="text-xs leading-snug text-muted-foreground sm:text-sm">
          {step.body}
        </span>
      </div>

      {/* micro-CTA: scorciatoia al finale per chi è già convinto (dallo step
          "rincari" in poi). Discreta, non compete con "Avanti". */}
      {showSkip && (
        <button
          onClick={onSkipToEnd}
          className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-emerald-700 underline-offset-2 transition-colors hover:underline dark:text-emerald-400"
        >
          <Sparkles className="size-3" />
          Ho visto abbastanza, voglio provarlo sul mio locale →
        </button>
      )}
    </div>
  );
}
