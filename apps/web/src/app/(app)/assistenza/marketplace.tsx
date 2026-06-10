"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  Stethoscope,
  LineChart,
  Headset,
  FileSearch,
  PiggyBank,
  Globe,
  MessageCircle,
  Send,
  Loader2,
  ExternalLink,
  type LucideIcon,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  SERVIZI,
  whatsappLink,
  type Servizio,
  type ServizioIconName,
} from "@/lib/assistenza";

const ICONS: Record<ServizioIconName, LucideIcon> = {
  Stethoscope,
  LineChart,
  Headset,
  FileSearch,
  PiggyBank,
  Globe,
};

// Stile WhatsApp (verde) condiviso tra card e dialog.
const WHATSAPP_CLS =
  "gap-1.5 border-emerald-500/40 text-emerald-600 hover:border-emerald-500/60 hover:bg-emerald-50 hover:text-emerald-700 dark:text-emerald-500 dark:hover:bg-emerald-950/30";

// Tre gruppi visivi, ciascuno con contorno spesso (border-2) e ombra colorata
// coordinata sullo stesso accento:
//  - featured (Check-up, servizio civetta): GIALLO/amber, card "sollevata" in 3D
//  - default  (2-3-4): AZZURRO ONEFLUX (primary), contorno + ombra azzurra
//  - partner  (5-6):   ROSSO, contorno + ombra rossa
// L'ombra colorata usa shadow-<color>-500/<alpha>: l'alone prende la tinta.
const CARD_VARIANT: Record<NonNullable<Servizio["variant"]>, string> = {
  default:
    "border-2 border-sky-500/40 bg-sky-500/[0.03] shadow-lg shadow-sky-500/10 " +
    "hover:border-sky-500/60 hover:shadow-sky-500/20",
  featured:
    "relative z-10 border-2 border-amber-400/70 bg-amber-400/[0.06] " +
    "scale-[1.04] -translate-y-2 shadow-2xl shadow-amber-500/30 " +
    "hover:scale-[1.06] hover:-translate-y-3 hover:border-amber-400 hover:shadow-amber-500/40",
  partner:
    "border-2 border-red-500/40 bg-red-500/[0.03] shadow-lg shadow-red-500/10 " +
    "hover:border-red-500/60 hover:shadow-red-500/20",
};

const ICON_TILE: Record<NonNullable<Servizio["variant"]>, string> = {
  default: "bg-sky-500/15 text-sky-500",
  featured: "bg-amber-400/20 text-amber-500",
  partner: "bg-red-500/15 text-red-500",
};

// Badge prezzo, in tinta col gruppo. Mostrato in alto a destra di ogni card.
const PRICE_BADGE: Record<NonNullable<Servizio["variant"]>, string> = {
  default: "bg-sky-500/10 text-sky-600 dark:text-sky-400",
  featured: "bg-amber-400/15 text-amber-600 dark:text-amber-400",
  partner: "bg-red-500/10 text-red-600 dark:text-red-400",
};

export function Marketplace() {
  const [attivo, setAttivo] = useState<Servizio | null>(null);
  const [messaggio, setMessaggio] = useState("");
  const [invio, setInvio] = useState(false);

  function apri(s: Servizio) {
    setAttivo(s);
    setMessaggio("");
  }

  async function invia() {
    if (!attivo) return;
    setInvio(true);
    try {
      const res = await fetch("/api/assistenza/lead", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Il worker accetta oggi servizio_key/servizio_label/messaggio: la coda
        // admin legge questi campi. TODO (fase 2): arricchire il payload con
        // partner label e aree quando worker + tabella marketplaceleads li
        // supporteranno, senza rompere la coda esistente.
        body: JSON.stringify({
          servizio_key: attivo.key,
          servizio_label: attivo.label,
          messaggio,
        }),
      });
      if (!res.ok) throw new Error();
      toast.success("Richiesta inviata. Ti ricontatto al più presto.");
      setAttivo(null);
    } catch {
      toast.error("Non sono riuscito a inviare. Riprova o scrivimi su WhatsApp.");
    } finally {
      setInvio(false);
    }
  }

  return (
    <>
      {/* py/px extra: la card featured e' scalata e sollevata, serve respiro
          perche' ombra ed estensione non vengano tagliate ai bordi della grid. */}
      <div className="grid gap-5 px-1 py-2 sm:grid-cols-2 lg:grid-cols-3">
        {SERVIZI.map((s) => {
          const variant = s.variant ?? "default";
          const Icon = ICONS[s.icon];
          return (
            <div
              key={s.key}
              className={cn(
                "flex h-full flex-col rounded-xl p-5 transition-all duration-200",
                CARD_VARIANT[variant],
              )}
            >
              {variant === "featured" && (
                <span className="mb-3 inline-flex w-fit items-center rounded-full bg-amber-400/15 px-2.5 py-0.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                  Punto di partenza
                </span>
              )}
              {s.partnerLabel && (
                <span className="mb-3 inline-flex w-fit items-center rounded-full bg-red-500/10 px-2.5 py-0.5 text-[11px] font-medium text-red-600 dark:text-red-400">
                  {s.partnerLabel}
                </span>
              )}

              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className={cn("rounded-lg p-2.5", ICON_TILE[variant])}>
                    <Icon className="size-5" />
                  </div>
                  <h3 className="font-semibold leading-tight">{s.label}</h3>
                </div>
                {s.priceValue && (
                  <span
                    className={cn(
                      "shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold",
                      PRICE_BADGE[variant],
                    )}
                  >
                    {s.priceValue}
                  </span>
                )}
              </div>

              <p className="mt-3 flex-1 text-sm leading-relaxed text-muted-foreground">
                {s.descrizione}
              </p>

              {s.partnerUrl && (
                <a
                  href={s.partnerUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-flex w-fit items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  Scopri Recoma System
                  <ExternalLink className="size-3" />
                </a>
              )}

              <div className="mt-4 flex items-center gap-2">
                <Button size="sm" onClick={() => apri(s)} className="gap-1.5">
                  <Send className="size-3.5" />
                  Richiedi info
                </Button>
                <a
                  href={whatsappLink(s.label)}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`Scrivi su WhatsApp per ${s.label}`}
                  className={cn(buttonVariants({ size: "sm", variant: "outline" }), WHATSAPP_CLS)}
                >
                  <MessageCircle className="size-3.5" />
                  WhatsApp
                </a>
              </div>
            </div>
          );
        })}
      </div>

      <Dialog open={attivo !== null} onOpenChange={(v) => !v && setAttivo(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{attivo?.label}</DialogTitle>
            <DialogDescription>
              Lasciami due righe su cosa ti serve: ti ricontatto io. In alternativa
              puoi scrivermi direttamente su WhatsApp.
            </DialogDescription>
          </DialogHeader>

          <textarea
            value={messaggio}
            onChange={(e) => setMessaggio(e.target.value)}
            rows={4}
            placeholder="Es. Vorrei capire se il mio food cost è in linea con la media…"
            className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />

          <DialogFooter className="gap-2 sm:justify-between">
            {attivo && (
              <a
                href={whatsappLink(attivo.label)}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Scrivi su WhatsApp per ${attivo.label}`}
                className={cn(buttonVariants({ variant: "outline" }), WHATSAPP_CLS)}
              >
                <MessageCircle className="size-4" />
                WhatsApp
              </a>
            )}
            <Button onClick={invia} disabled={invio} className="gap-1.5">
              {invio ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
              Invia richiesta
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
