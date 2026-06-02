"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Info,
  XCircle,
  CheckCircle,
  Check,
  Sparkles,
} from "lucide-react";
import { type Briefing, type BriefingAzione } from "@/lib/home";
import { cn } from "@/lib/utils";

// Effetto typewriter sulla narrativa, come la Home desktop: solo al primo load
// del giorno, durata ~costante.
const TYPEWRITER_ENABLED = true;

function SeverityIcon({ severity }: { severity: BriefingAzione["severity"] }) {
  if (severity === "error") return <XCircle className="size-5 shrink-0 text-destructive" />;
  if (severity === "warning") return <AlertTriangle className="size-5 shrink-0 text-amber-500" />;
  if (severity === "success") return <CheckCircle className="size-5 shrink-0 text-emerald-500" />;
  return <Info className="size-5 shrink-0 text-sky-500" />;
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

export function MobileBriefing({ briefing }: { briefing: Briefing }) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<Set<string>>(new Set());

  // Typewriter solo al primo load del giorno (chiave = data del briefing).
  const [animate, setAnimate] = useState(false);
  const decided = useRef(false);
  useEffect(() => {
    if (decided.current) return;
    decided.current = true;
    if (!TYPEWRITER_ENABLED) return;
    try {
      const key = `oneflux:briefing-seen-m:${briefing.data}`;
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
    <div className="space-y-5">
      {/* Hero briefing con typewriter */}
      <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-sky-500/10 via-violet-500/[0.04] to-background p-5">
        <div className="pointer-events-none absolute -right-12 -top-12 size-40 rounded-full bg-sky-400/15 blur-3xl" />
        <div className="flex items-center gap-1.5 text-xs font-medium text-primary/80">
          <Sparkles className="size-3.5" />
          <span>Il tuo assistente</span>
        </div>
        <h1 className="mt-2 text-xl font-bold tracking-tight">{briefing.saluto}</h1>
        <p className="mt-3 whitespace-pre-line text-[15px] leading-relaxed text-foreground/90">
          {narrativa}
          {animate && narrativa.length < briefing.narrativa.length && (
            <span className="ml-0.5 inline-block h-5 w-0.5 animate-pulse bg-primary align-middle" />
          )}
        </p>
      </div>

      {/* Azioni da fare: solo informative + "Ignora". Nessun link verso la
          vista desktop (la Home mobile resta dentro la PWA). */}
      {tuttoOk ? (
        <div className="flex flex-col items-center gap-2.5 rounded-2xl border border-emerald-500/20 bg-gradient-to-br from-emerald-500/[0.07] to-transparent py-10 text-center">
          <div className="rounded-full bg-emerald-500/15 p-2.5 ring-1 ring-emerald-500/20">
            <Check className="size-6 text-emerald-500" />
          </div>
          <p className="text-[15px] font-semibold text-emerald-600 dark:text-emerald-400">
            Tutto in ordine
          </p>
          <p className="text-sm text-muted-foreground">Nessuna azione da fare oggi.</p>
        </div>
      ) : (
        <div className="space-y-2.5">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Da fare oggi
            <span className="ml-1.5 text-muted-foreground/60">({visibili.length})</span>
          </h2>
          {visibili.map((a) => (
            <div
              key={a.id}
              className={cn(
                "flex items-start gap-3 rounded-xl border bg-card p-4 transition-all",
                loading.has(a.id) && "pointer-events-none opacity-50",
              )}
            >
              <SeverityIcon severity={a.severity} />
              <p className="flex-1 text-sm leading-snug">{a.testo}</p>
              <button
                type="button"
                disabled={loading.has(a.id)}
                onClick={() => dismiss(a.id)}
                className="shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium text-muted-foreground active:scale-[0.98]"
              >
                Ignora
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
