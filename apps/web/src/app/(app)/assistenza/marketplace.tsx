"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  ChefHat,
  BookOpen,
  Plug,
  Globe,
  Camera,
  TrendingDown,
  MessageCircle,
  Send,
  Loader2,
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
import { SERVIZI, whatsappLink, type Servizio } from "@/lib/assistenza";

const ICONS: Record<string, LucideIcon> = {
  ChefHat,
  BookOpen,
  Plug,
  Globe,
  Camera,
  TrendingDown,
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
          const Icon = ICONS[s.icon] ?? ChefHat;
          return (
            <div
              key={s.key}
              className="flex flex-col rounded-xl border bg-card p-5 transition-colors hover:border-foreground/20"
            >
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-primary/10 p-2.5 text-primary">
                  <Icon className="size-5" />
                </div>
                <h3 className="font-semibold leading-tight">{s.label}</h3>
              </div>
              <p className="mt-3 flex-1 text-sm leading-relaxed text-muted-foreground">
                {s.descrizione}
              </p>
              <div className="mt-4 flex items-center gap-2">
                <Button size="sm" onClick={() => apri(s)} className="gap-1.5">
                  <Send className="size-3.5" />
                  Richiedi info
                </Button>
                <a
                  href={whatsappLink(s.label)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={cn(
                    buttonVariants({ size: "sm", variant: "outline" }),
                    "gap-1.5 border-emerald-500/40 text-emerald-600 hover:border-emerald-500/60 hover:bg-emerald-50 hover:text-emerald-700 dark:text-emerald-500 dark:hover:bg-emerald-950/30",
                  )}
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
                className={cn(
                  buttonVariants({ variant: "outline" }),
                  "gap-1.5 border-emerald-500/40 text-emerald-600 hover:border-emerald-500/60 hover:bg-emerald-50 hover:text-emerald-700 dark:text-emerald-500 dark:hover:bg-emerald-950/30",
                )}
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
