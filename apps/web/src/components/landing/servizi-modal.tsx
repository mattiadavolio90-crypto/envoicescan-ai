"use client";

// Modale "I nostri servizi": i servizi NON sono elencati in pagina, si aprono
// cliccando il link giallo nel footer ("Guarda i nostri servizi"). Apertura
// immediata in overlay, niente scroll/ancora. Fonte unica = catalogo `SERVIZI`
// in lib/assistenza (stesso dell'app): un servizio modificato lì cambia in
// entrambe. Prezzi e note interne (fase 2) NON renderizzati.

import { useEffect, useState } from "react";
import {
  X,
  Stethoscope,
  LineChart,
  Headset,
  FileSearch,
  PiggyBank,
  Globe,
  ExternalLink,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { SERVIZI, WHATSAPP_NUMERO, type Servizio, type ServizioIconName } from "@/lib/assistenza";
import { LANDING } from "@/lib/landing-content";

const SERVIZIO_ICONS: Record<ServizioIconName, LucideIcon> = {
  Stethoscope,
  LineChart,
  Headset,
  FileSearch,
  PiggyBank,
  Globe,
};

// Stessi gruppi-colore della pagina servizi reale dell'app (marketplace.tsx),
// adattati al tema scuro della landing: featured=GIALLO/amber (civetta, sollevata),
// default=AZZURRO OneFlux, partner=ROSSO. Cosi' l'overlay "somiglia" alla pagina vera.
const CARD_VARIANT: Record<NonNullable<Servizio["variant"]>, string> = {
  default: "border-sky-500/40 bg-sky-500/[0.04] hover:border-sky-500/60",
  featured:
    "border-amber-400/60 bg-amber-400/[0.06] ring-1 ring-amber-400/20 sm:scale-[1.02] shadow-lg shadow-amber-500/15",
  partner: "border-red-500/40 bg-red-500/[0.04] hover:border-red-500/60",
};
const ICON_TILE: Record<NonNullable<Servizio["variant"]>, string> = {
  default: "bg-sky-500/15 text-sky-400",
  featured: "bg-amber-400/20 text-amber-400",
  partner: "bg-red-500/15 text-red-400",
};
const PARTNER_BADGE: Record<NonNullable<Servizio["variant"]>, string> = {
  default: "bg-sky-500/10 text-sky-400",
  featured: "bg-amber-400/15 text-amber-400",
  partner: "bg-red-500/10 text-red-400",
};

function waServizi(): string {
  const msg = "Ciao! Vorrei sapere di più sui vostri servizi.";
  return `https://wa.me/${WHATSAPP_NUMERO}?text=${encodeURIComponent(msg)}`;
}

// Trigger (link giallo) + overlay. Tutto client: gestisce lo stato di apertura.
export function ServiziModal({
  triggerLabel,
  triggerClassName,
}: {
  triggerLabel: string;
  triggerClassName?: string;
}) {
  const [aperto, setAperto] = useState(false);
  const t = LANDING.servizi;

  // chiudi con ESC; blocca lo scroll del body quando aperto
  useEffect(() => {
    if (!aperto) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAperto(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [aperto]);

  return (
    <>
      <button
        type="button"
        onClick={() => setAperto(true)}
        className={cn("font-semibold text-yellow-400 hover:underline", triggerClassName)}
      >
        {triggerLabel}
      </button>

      {aperto ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t.title}
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/80 p-4 backdrop-blur-sm sm:p-8"
          onClick={() => setAperto(false)}
        >
          <div
            className="relative my-auto w-full max-w-4xl rounded-3xl border border-border bg-card p-6 shadow-2xl sm:p-10"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setAperto(false)}
              aria-label="Chiudi"
              className="absolute right-4 top-4 flex size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="size-5" />
            </button>

            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-primary">{t.kicker}</p>
            <h2 className="mt-3 font-display text-2xl font-bold tracking-tight sm:text-3xl">
              {t.title}
            </h2>
            <p className="mt-3 max-w-2xl text-sm text-white/[0.72] sm:text-base">{t.sottotitolo}</p>

            <div className="mt-8 grid gap-4 sm:grid-cols-2">
              {SERVIZI.map((sv) => {
                const Icon = SERVIZIO_ICONS[sv.icon];
                const variant = sv.variant ?? "default";
                return (
                  <div
                    key={sv.key}
                    className={cn(
                      "flex h-full flex-col rounded-xl border-2 p-5 text-left transition-colors",
                      CARD_VARIANT[variant],
                    )}
                  >
                    {/* badge in cima, in tinta col gruppo: featured = "Punto di
                        partenza" (giallo), partner = label collaborazione (rosso) */}
                    {variant === "featured" ? (
                      <span className="mb-3 inline-flex w-fit items-center rounded-full bg-amber-400/15 px-2.5 py-0.5 text-[11px] font-medium text-amber-400">
                        Punto di partenza
                      </span>
                    ) : null}
                    {sv.partnerLabel ? (
                      <span
                        className={cn(
                          "mb-3 inline-flex w-fit items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium",
                          PARTNER_BADGE[variant],
                        )}
                      >
                        {sv.partnerLabel}
                      </span>
                    ) : null}

                    <div className="flex items-center gap-3">
                      <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-lg", ICON_TILE[variant])}>
                        <Icon className="size-5" />
                      </span>
                      <h3 className="font-semibold leading-tight">{sv.label}</h3>
                    </div>

                    <p className="mt-3 flex-1 text-sm leading-relaxed text-muted-foreground">
                      {sv.descrizione}
                    </p>

                    {sv.partnerUrl ? (
                      <a
                        href={sv.partnerUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-3 inline-flex w-fit items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                      >
                        Scopri Recoma System
                        <ExternalLink className="size-3" />
                      </a>
                    ) : null}
                  </div>
                );
              })}
            </div>

            <p className="mt-8 text-center text-sm text-muted-foreground">
              Ti interessa un servizio?{" "}
              <a
                href={waServizi()}
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold text-primary hover:underline"
              >
                Scrivici su WhatsApp
              </a>
            </p>
          </div>
        </div>
      ) : null}
    </>
  );
}
