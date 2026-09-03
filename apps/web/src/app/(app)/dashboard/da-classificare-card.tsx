import Link from "next/link";
import { AlertTriangle, ArrowRight, Check } from "lucide-react";
import { type CardDaClassificare } from "@/lib/home-da-classificare";
import { cn } from "@/lib/utils";

// Card grande "Righe da classificare" (Fase 4bis). Sempre visibile sulla Home
// del punto vendita — anche a zero righe: è il verde che insegna al cliente che
// questo numero esiste, così quando diventa giallo lo nota. Mai in catena.
//
// Principio ereditato da catena/card-segnali.tsx: un errore qui NON può
// diventare "tutto sotto controllo" — su errore si mostra l'errore, mai il verde.
export function DaClassificareCard({ card }: { card: CardDaClassificare }) {
  if (card.stato === "errore") {
    return (
      <div className="rounded-2xl border border-dashed bg-muted/30 p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Righe da classificare
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          Non riesco a leggere le righe da classificare in questo momento.
        </p>
      </div>
    );
  }

  const verde = card.stato === "ok";
  return (
    <div
      className={cn(
        "rounded-2xl border p-5",
        verde
          ? "border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/50 dark:bg-emerald-950/20"
          : "border-amber-200 bg-amber-50/60 dark:border-amber-900/50 dark:bg-amber-950/20",
      )}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Righe da classificare
      </p>
      <div className="mt-2 flex items-start gap-3">
        {verde ? (
          <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/40">
            <Check className="size-4 text-emerald-600" />
          </span>
        ) : (
          <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/40">
            <AlertTriangle className="size-4 text-amber-600" />
          </span>
        )}
        <div className="flex flex-1 flex-col gap-0.5">
          <span className="text-sm font-medium">{card.titolo}</span>
          {card.stato === "righe" && (
            <>
              <span className="text-xs text-amber-700 dark:text-amber-400">
                {card.sottotitolo}
              </span>
              <Link
                href={card.href}
                className="mt-1 inline-flex w-fit items-center gap-1 text-xs font-medium text-primary hover:underline"
              >
                Vai a sistemarle
                <ArrowRight className="size-3.5" />
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
