"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Info,
  XCircle,
  CheckCircle,
  Check,
  Sparkles,
  ArrowRight,
} from "lucide-react";
import { type Briefing, type BriefingAzione } from "@/lib/home";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Effetto typewriter abilitato (spegnibile in 1 riga): solo al primo load del
// giorno, max ~600ms. Dietro flag perche' deve restare sobrio e veloce.
const TYPEWRITER_ENABLED = true;

function SeverityIcon({ severity }: { severity: BriefingAzione["severity"] }) {
  if (severity === "error") return <XCircle className="size-5 text-destructive shrink-0" />;
  if (severity === "warning") return <AlertTriangle className="size-5 text-amber-500 shrink-0" />;
  if (severity === "success") return <CheckCircle className="size-5 text-emerald-500 shrink-0" />;
  return <Info className="size-5 text-sky-500 shrink-0" />;
}

function useTypewriter(text: string, enabled: boolean) {
  const [shown, setShown] = useState(enabled ? "" : text);
  useEffect(() => {
    if (!enabled) {
      setShown(text);
      return;
    }
    let i = 0;
    setShown("");
    // durata totale ~ costante indipendente dalla lunghezza
    const step = Math.max(8, Math.min(28, Math.round(600 / Math.max(text.length, 1))));
    const id = setInterval(() => {
      i += 1;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, step);
    return () => clearInterval(id);
  }, [text, enabled]);
  return shown;
}

type Props = { briefing: Briefing };

export function HomeBriefing({ briefing }: Props) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<Set<string>>(new Set());

  // Typewriter solo al primo load del giorno (chiave = data del briefing)
  const [animate, setAnimate] = useState(false);
  const decided = useRef(false);
  useEffect(() => {
    if (decided.current) return;
    decided.current = true;
    if (!TYPEWRITER_ENABLED) return;
    try {
      const key = `oneflux:briefing-seen:${briefing.data}`;
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, "1");
        setAnimate(true);
      }
    } catch {
      /* sessionStorage non disponibile: nessuna animazione */
    }
  }, [briefing.data]);

  const narrativa = useTypewriter(briefing.narrativa, animate);

  async function dismiss(id: string) {
    setLoading((prev) => new Set(prev).add(id));
    try {
      await fetch("/api/notifiche/dismiss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
    } finally {
      // segna come archiviata anche in caso di errore di rete: la card sparisce,
      // verra' ricalcolata al prossimo refresh server
      setDismissed((prev) => new Set(prev).add(id));
      setLoading((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  const visibili = briefing.azioni.filter((a) => !dismissed.has(a.id));
  const tuttoOk = briefing.tutto_ok || visibili.length === 0;

  return (
    <section className="space-y-6">
      {/* HERO — la voce dell'assistente */}
      <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-primary/5 via-background to-background p-6 sm:p-8">
        <div className="flex items-center gap-2 text-xs font-medium text-primary/80">
          <Sparkles className="size-4" />
          <span>Il tuo assistente</span>
        </div>
        <h1 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
          {briefing.saluto}
        </h1>
        <p className="mt-3 max-w-2xl whitespace-pre-line text-base leading-relaxed text-muted-foreground">
          {narrativa}
          {animate && narrativa.length < briefing.narrativa.length && (
            <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-primary align-middle" />
          )}
        </p>
      </div>

      {/* AZIONI — le card da svuotare */}
      {tuttoOk ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border bg-emerald-50/50 py-12 text-center dark:bg-emerald-950/20">
          <div className="rounded-full bg-emerald-100 p-3 dark:bg-emerald-900/40">
            <Check className="size-7 text-emerald-600" />
          </div>
          <p className="text-base font-medium">Tutto in ordine per oggi</p>
          <p className="text-sm text-muted-foreground">
            Nessuna azione da fare. Buon lavoro!
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Da fare oggi
            <span className="ml-1.5 text-muted-foreground/60">({visibili.length})</span>
          </h2>
          {visibili.map((a) => (
            <div
              key={a.id}
              className={cn(
                "flex flex-col gap-3 rounded-xl border bg-card p-4 transition-all sm:flex-row sm:items-center sm:gap-4",
                loading.has(a.id) && "pointer-events-none opacity-50",
              )}
            >
              <SeverityIcon severity={a.severity} />
              <p className="flex-1 text-sm leading-snug">{a.testo}</p>
              <div className="flex shrink-0 items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground"
                  disabled={loading.has(a.id)}
                  onClick={() => dismiss(a.id)}
                >
                  Ignora
                </Button>
                <Link href={a.cta_page} className={cn(buttonVariants({ size: "sm" }))}>
                  {a.cta_label}
                  <ArrowRight className="size-4" />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
