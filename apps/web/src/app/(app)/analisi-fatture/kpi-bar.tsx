"use client";

import { useEffect, useRef, useState } from "react";
import type { KpiResponse } from "@/lib/fatture";
import { formatEuro } from "./periodi";

type Props = {
  kpi: KpiResponse | null;
};

type Tone = "blu" | "neutro";

// Quattro riquadri, quattro colori, nessuna gerarchia (AF1 del piano): "Spesa
// totale" e "Voci in fattura" pesavano uguale. Nessuno dei quattro e' un
// giudizio, quindi nessuno e' verde o rosso: il dato che conta e' in blu, gli
// altri tre neutri.
const TONE: Record<Tone, { border: string; hover: string; value: string }> = {
  blu:    { border: "border-primary/40", hover: "hover:border-primary/70", value: "text-primary-text" },
  neutro: { border: "border-border", hover: "hover:border-muted-foreground/40", value: "text-foreground" },
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
    // Erano quattro. «Voci in fattura» e «Prodotti diversi» sono uscite il
    // 22/09/2026: entrambe erano gia' scritte piu' sotto nella stessa pagina
    // (articoli-tab.tsx: «N prodotti» e «N acquisti»), e la prima portava
    // anche una contraddizione muta — la card contava 1347 righe escludendo
    // quelle a importo zero, la riga sotto ne diceva 1348 includendole, e la
    // differenza era un omaggio a 0 EUR che nulla spiegava. Con un solo
    // conteggio in pagina la contraddizione non puo' piu' esistere.
    <div className="grid grid-cols-2 gap-3">
      <KpiCard tone="blu"    label="Spesa totale"  numeric={kpi.totale}        format={formatEuro} animate={animate} />
      <KpiCard tone="neutro" label="Media al mese" numeric={kpi.media_mensile} format={formatEuro} animate={animate} />
    </div>
  );
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
