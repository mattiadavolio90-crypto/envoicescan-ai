"use client";

import { useEffect, useRef, useState } from "react";
import type { KpiResponse } from "@/lib/fatture";
import { formatEuro } from "./periodi";

type Props = {
  kpi: KpiResponse | null;
};

type Tone = "sky" | "violet" | "emerald" | "orange";

const TONE: Record<Tone, { border: string; hover: string; value: string }> = {
  sky:     { border: "border-sky-500/40",     hover: "hover:border-sky-500/70",     value: "text-sky-600 dark:text-sky-400" },
  violet:  { border: "border-violet-500/40",  hover: "hover:border-violet-500/70",  value: "text-violet-600 dark:text-violet-400" },
  emerald: { border: "border-emerald-500/40", hover: "hover:border-emerald-500/70", value: "text-emerald-600 dark:text-emerald-400" },
  orange:  { border: "border-orange-500/40",  hover: "hover:border-orange-500/70",  value: "text-orange-600 dark:text-orange-400" },
};

// Count-up al primo render: il valore sale da 0 al target in ~500ms. Il dato
// esiste gia' (nessun calcolo aggiunto); animiamo solo la presentazione.
// Rispetta prefers-reduced-motion: in quel caso mostra subito il valore finale.
function useCountUp(target: number, enabled: boolean): number {
  const [val, setVal] = useState(enabled ? 0 : target);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled) {
      setVal(target);
      return;
    }
    const start = performance.now();
    const dur = 500;
    function frame(now: number) {
      const p = Math.min((now - start) / dur, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setVal(target * eased);
      if (p < 1) rafRef.current = requestAnimationFrame(frame);
    }
    rafRef.current = requestAnimationFrame(frame);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [target, enabled]);

  return val;
}

export function KpiBar({ kpi }: Props) {
  const [animate, setAnimate] = useState(false);

  // Decide una sola volta: anima solo se l'utente non ha chiesto meno movimento.
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    setAnimate(!reduce);
  }, []);

  if (!kpi) return null;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <KpiCard tone="sky"     label="Spesa totale"     numeric={kpi.totale}        format={formatEuro} animate={animate} />
      <KpiCard tone="violet"  label="Righe"            numeric={kpi.num_righe}     format={fmtInt}     animate={animate} />
      <KpiCard tone="emerald" label="Prodotti diversi" numeric={kpi.num_prodotti}  format={fmtInt}     animate={animate} />
      <KpiCard tone="orange"  label="Media al mese"    numeric={kpi.media_mensile} format={formatEuro} animate={animate} />
    </div>
  );
}

function fmtInt(v: number): string {
  return Math.round(v).toLocaleString("it-IT");
}

function KpiCard({
  tone,
  label,
  numeric,
  format,
  animate,
}: {
  tone: Tone;
  label: string;
  numeric: number;
  format: (v: number) => string;
  animate: boolean;
}) {
  const t = TONE[tone];
  const shown = useCountUp(numeric, animate);
  return (
    <div className={`rounded-xl border ${t.border} ${t.hover} bg-card p-3 transition-colors`}>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <p className={`text-xl font-bold tracking-tight mt-1 tabular-nums ${t.value}`}>
        {format(shown)}
      </p>
    </div>
  );
}
