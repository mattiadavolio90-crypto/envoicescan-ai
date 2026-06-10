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

// Resa grafica per variante. featured = entry-point in risalto (accento primary);
// partner = area servizi partner, sfondo/ombra separati. La card Recoma (con
// partnerUrl) riceve in piu' l'accento rosso elegante, gestito inline sotto.
const CARD_VARIANT: Record<NonNullable<Servizio["variant"]>, string> = {
  default: "border bg-card hover:border-foreground/20",
  featured:
    "border-primary/30 bg-primary/[0.04] ring-1 ring-primary/20 hover:border-primary/50 hover:ring-primary/30",
  partner: "border-border/70 bg-muted/30 shadow-sm hover:border-foreground/20",
};

const ICON_TILE: Record<NonNullable<Servizio["variant"]>, string> = {
  default: "bg-primary/10 text-primary",
  featured: "bg-primary/15 text-primary",
  partner: "bg-foreground/8 text-foreground/70",
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
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SERVIZI.map((s) => {
          const variant = s.variant ?? "default";
          const Icon = ICONS[s.icon];
          const isRecoma = Boolean(s.partnerUrl);
          return (
            <div
              key={s.key}
              className={cn(
                "flex h-full flex-col rounded-xl p-5 transition-colors",
                CARD_VARIANT[variant],
                isRecoma &&
                  "border-red-500/25 ring-1 ring-red-500/15 hover:border-red-500/40 hover:ring-red-500/25",
              )}
            >
              {s.partnerLabel && (
                <span
                  className={cn(
                    "mb-3 inline-flex w-fit items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium",
                    isRecoma
                      ? "bg-red-500/10 text-red-600 dark:text-red-400"
                      : "bg-foreground/8 text-muted-foreground",
                  )}
                >
                  {s.partnerLabel}
                </span>
              )}
              {variant === "featured" && (
                <span className="mb-3 inline-flex w-fit items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-medium text-primary">
                  Punto di partenza
                </span>
              )}

              <div className="flex items-center gap-3">
                <div className={cn("rounded-lg p-2.5", ICON_TILE[variant])}>
                  <Icon className="size-5" />
                </div>
                <h3 className="font-semibold leading-tight">{s.label}</h3>
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
