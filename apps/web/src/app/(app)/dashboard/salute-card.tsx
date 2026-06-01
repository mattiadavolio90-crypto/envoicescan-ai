import Link from "next/link";
import { Check, ArrowRight } from "lucide-react";
import { type Salute } from "@/lib/home";
import { cn } from "@/lib/utils";

// Palette per i 3 stati dell'indice. Verde >=80, Giallo 50-79, Rosso <50
// (soglie decise lato backend, qui solo i colori).
const COLORI = {
  verde: {
    ring: "text-emerald-500",
    text: "text-emerald-600",
    badge: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400",
    label: "In salute",
    card: "bg-gradient-to-br from-emerald-500/10 via-emerald-500/[0.03] to-background",
    orb1: "bg-emerald-400/15",
    orb2: "bg-emerald-400/8",
  },
  giallo: {
    ring: "text-amber-500",
    text: "text-amber-600",
    badge: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
    label: "Da completare",
    card: "bg-gradient-to-br from-amber-500/10 via-amber-500/[0.03] to-background",
    orb1: "bg-amber-400/15",
    orb2: "bg-amber-400/8",
  },
  rosso: {
    ring: "text-rose-500",
    text: "text-rose-600",
    badge: "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400",
    label: "Dati incompleti",
    card: "bg-gradient-to-br from-rose-500/10 via-rose-500/[0.03] to-background",
    orb1: "bg-rose-400/15",
    orb2: "bg-rose-400/8",
  },
} as const;

function Anello({ indice, colore }: { indice: number; colore: Salute["colore"] }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const offset = c - (Math.max(0, Math.min(100, indice)) / 100) * c;
  const tint = COLORI[colore];
  return (
    <div className="relative size-32 shrink-0">
      <svg viewBox="0 0 120 120" className="size-32 -rotate-90">
        <circle
          cx="60" cy="60" r={r}
          className="stroke-muted"
          strokeWidth="10"
          fill="none"
        />
        <circle
          cx="60" cy="60" r={r}
          className={cn("transition-all", tint.ring)}
          stroke="currentColor"
          strokeWidth="10"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn("text-3xl font-bold tabular-nums", tint.text)}>{indice}%</span>
      </div>
    </div>
  );
}

export function SaluteCard({ salute }: { salute: Salute }) {
  const tint = COLORI[salute.colore];

  return (
    <div className={cn("relative flex h-full flex-col overflow-hidden rounded-2xl border p-6 sm:p-7", tint.card)}>
      <div className={cn("pointer-events-none absolute -right-16 -top-16 size-56 rounded-full blur-3xl", tint.orb1)} />
      <div className={cn("pointer-events-none absolute -bottom-20 left-1/3 size-52 rounded-full blur-3xl", tint.orb2)} />
      <div className="mb-4 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Salute della gestione</h2>
        <span className="text-xs capitalize text-muted-foreground/70">{salute.mese_label}</span>
      </div>
      <div className="flex flex-1 flex-col items-center gap-6 sm:flex-row sm:items-center sm:gap-7">
        <Anello indice={salute.indice} colore={salute.colore} />

        <div className="flex-1 space-y-3">
          <span className={cn("inline-block rounded-full px-3 py-1 text-xs font-medium", tint.badge)}>
            {tint.label}
          </span>

          <ul className="space-y-2.5">
              {salute.voci.map((v) => (
                <li key={v.key} className="flex items-start gap-3 text-sm">
                  {v.ok ? (
                    <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/40">
                      <Check className="size-3.5 text-emerald-600" />
                    </span>
                  ) : (
                    <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/40">
                      <span className="size-2 rounded-full bg-amber-500" />
                    </span>
                  )}
                  <div className="flex flex-1 flex-col gap-0.5">
                    <span className={cn(v.ok ? "text-foreground" : "font-medium")}>
                      {v.label}
                    </span>
                    {/* Dettaglio come sottotitolo (niente piu' colonna duplicata
                        a destra), e CTA sotto solo se c'e' qualcosa da fare. */}
                    <span className="text-xs text-muted-foreground">{v.dettaglio}</span>
                    {!v.ok && v.cta_page && (
                      <Link
                        href={v.cta_page}
                        title="Vai alla pagina"
                        className="mt-0.5 inline-flex w-fit items-center gap-1 text-xs font-medium text-primary hover:underline"
                      >
                        Vai alla pagina
                        <ArrowRight className="size-3.5" />
                      </Link>
                    )}
                  </div>
                </li>
              ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
