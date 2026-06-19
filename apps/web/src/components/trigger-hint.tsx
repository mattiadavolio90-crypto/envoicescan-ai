"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TriggerDef } from "@/lib/trigger-servizi";

// Giorni di silenzio dopo che l'utente chiude un trigger: se lo ignora non
// torna subito. Il segnale a monte e' gia' raro; questo evita la ripetizione
// visiva ravvicinata anche quando il segnale persiste (es. food cost resta
// alto per settimane). 14 giorni = "non insistere".
const COOLDOWN_GIORNI = 14;

// Versione del namespace localStorage: alzala se cambia la semantica del salvataggio.
const STORAGE_PREFIX = "oneflux_trigger_v1_";

function storageKey(key: string): string {
  return `${STORAGE_PREFIX}${key}`;
}

// True se il trigger e' in cooldown (chiuso di recente) e va tenuto nascosto.
function inCooldown(key: string): boolean {
  try {
    const raw = localStorage.getItem(storageKey(key));
    if (!raw) return false;
    const ts = Number(raw);
    if (!Number.isFinite(ts)) return false;
    const scadenza = ts + COOLDOWN_GIORNI * 24 * 60 * 60 * 1000;
    return Date.now() < scadenza;
  } catch {
    // localStorage non disponibile (modalita' privata): non bloccare, mostra.
    return false;
  }
}

type Props = {
  // Trigger da mostrare, gia' deciso dalla pagina (valutaTrigger). null/undefined
  // = niente segnale reale, niente banner.
  trigger: TriggerDef | null | undefined;
  // Se false, il banner non si mostra mai (toggle per-cliente spento lato admin).
  enabled?: boolean;
  className?: string;
};

/**
 * Hint contestuale dei Servizi: una riga discreta in fondo a una pagina che
 * rimanda alla card giusta di /assistenza. NON e' un popup, NON e' bloccante,
 * NON e' una card pesante: e' un banner leggero, dismissibile e ricordato.
 *
 * Si mostra solo se: (1) il toggle cliente e' attivo, (2) la pagina ha passato
 * un trigger (segnale reale), (3) non e' in cooldown. La regola "1 per pagina"
 * e' garantita a monte da valutaTrigger, che restituisce al massimo un trigger.
 */
export function TriggerHint({ trigger, enabled = true, className }: Props) {
  // Parte nascosto e si rivela in useEffect: evita mismatch SSR/idratazione
  // (localStorage non esiste lato server) e flash del banner.
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!enabled || !trigger) {
      setVisible(false);
      return;
    }
    setVisible(!inCooldown(trigger.key));
  }, [enabled, trigger]);

  if (!trigger || !visible) return null;

  function dismiss() {
    try {
      localStorage.setItem(storageKey(trigger!.key), String(Date.now()));
    } catch {
      /* ignore */
    }
    setVisible(false);
  }

  return (
    <div
      role="note"
      aria-label="Suggerimento servizi"
      className={cn(
        "flex items-center gap-3 rounded-xl border border-sky-500/30 bg-sky-500/[0.04] px-4 py-3",
        className,
      )}
    >
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sky-500/15 text-sky-600 dark:text-sky-400">
        <Sparkles className="size-4" />
      </div>
      <p className="min-w-0 flex-1 text-sm leading-snug text-foreground/90">
        {trigger.messaggio}
      </p>
      <Link
        href={`/assistenza?servizio=${trigger.servizioKey}`}
        className="shrink-0 whitespace-nowrap rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
      >
        {trigger.cta}
      </Link>
      <button
        onClick={dismiss}
        aria-label="Nascondi suggerimento"
        className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
