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
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { SERVIZI, WHATSAPP_NUMERO, type ServizioIconName } from "@/lib/assistenza";
import { LANDING } from "@/lib/landing-content";

const SERVIZIO_ICONS: Record<ServizioIconName, LucideIcon> = {
  Stethoscope,
  LineChart,
  Headset,
  FileSearch,
  PiggyBank,
  Globe,
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
                const isPartner = sv.variant === "partner";
                return (
                  <div
                    key={sv.key}
                    className={cn(
                      "flex h-full flex-col rounded-2xl border bg-background/40 p-5 text-left",
                      sv.variant === "featured"
                        ? "border-primary/50 ring-1 ring-primary/20"
                        : "border-border/70",
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className={cn(
                          "flex size-10 shrink-0 items-center justify-center rounded-xl",
                          sv.variant === "featured" ? "bg-primary/15" : "bg-muted",
                        )}
                      >
                        <Icon className="size-5 text-primary" />
                      </span>
                      <h3 className="font-display text-base font-semibold leading-tight">{sv.label}</h3>
                    </div>
                    {sv.partnerLabel ? (
                      <p
                        className={cn(
                          "mt-3 text-xs font-medium uppercase tracking-wide",
                          isPartner ? "text-yellow-400/90" : "text-muted-foreground",
                        )}
                      >
                        {sv.partnerLabel}
                      </p>
                    ) : null}
                    <p className="mt-3 text-sm leading-relaxed text-white/[0.7]">{sv.descrizione}</p>
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
