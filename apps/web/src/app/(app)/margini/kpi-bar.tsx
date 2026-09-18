"use client";

import { useEffect, useRef, useState } from "react";
import { formatEuro } from "./periodi";
import { puntiSparkline } from "@/lib/sparkline-punti";
import { kpiNonDisponibile } from "@/lib/esito-caricamento";

export type KpiData = {
  fatturato_lordo: number;
  fatturato_netto: number;
  costi_fb: number;
  primo_margine: number;
  spese_generali: number;
  costo_personale: number;
  mol: number;
  food_cost_perc: number;
  primo_margine_perc: number;
  spese_perc: number;
  personale_perc: number;
  mol_perc: number;
  delta_lordo_pct: number | null;
  delta_fb_pct: number | null;
  delta_margine_pct: number | null;
  delta_spese_pct: number | null;
  delta_personale_pct: number | null;
  delta_mol_pct: number | null;
  confronto_label: string;
  /**
   * true quando i numeri NON arrivano dal worker: timeout, risposta non ok o
   * sessione assente. Senza questo flag il ripiego a zeri era indistinguibile
   * da un periodo davvero vuoto — il cliente leggeva sei riquadri a "0 €" per
   * decine di secondi credendoli un dato, mentre la tabella sotto (che usa un
   * altro endpoint) si popolava. Opzionale: i consumatori che non lo passano
   * si comportano come prima.
   */
  non_disponibile?: boolean;
  spark_lordo?: number[];
  spark_fb?: number[];
  spark_margine?: number[];
  spark_spese?: number[];
  spark_personale?: number[];
  spark_mol?: number[];
};

function Sparkline({ values: rawValues, color }: { values: number[]; color: string }) {
  const w = 100;
  const h = 24;
  const points = puntiSparkline(rawValues, { w, h, ancoraZero: true, padY: 1 });
  if (!points) return null;
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="block w-full">
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        opacity={0.85}
      />
    </svg>
  );
}

type Tone = "neutro" | "positivo" | "negativo";

/**
 * Cinque riquadri neutri, il colore solo sul MOL.
 *
 * Fino al 17/09/2026 i sei riquadri avevano sei tinte diverse (sky, orange,
 * emerald, violet, pink + il MOL): l'audit visivo del 16/09 li ha letti come
 * «un arcobaleno, non un sistema». Una regola c'era — il colore indicava la
 * famiglia di voci, e la tabella sotto la rispetta — ma non si capiva senza
 * leggere la legenda, e si rompeva in tre punti: l'azzurro valeva sia "ricavi"
 * sia "cliccabile"; Margine Lordo e MOL avevano lo STESSO verde, quindi
 * sembravano la stessa cosa; e il verde non voleva dire "va bene", visto che il
 * MOL restava verde anche coi costi a zero.
 *
 * Il legame coi colori della tabella (`calcolo-tab.tsx`) resta sui nomi delle
 * voci, che sono identici. La tabella non si tocca: li' il colore distingue
 * righe adiacenti, qui distingueva riquadri gia' separati da un bordo.
 *
 * I valori sono 16px/700: per WCAG NON sono "large text", quindi la soglia AA e'
 * 4.5:1, non 3:1. Misurato in tema chiaro il 9/9/2026, le tinte -600 di orange
 * (#f54a00 -> 3,58:1) ed emerald (#009966 -> 3,65:1) erano sotto. Dal 18/09
 * i colori sono i token `positivo`/`negativo`, misurati sui due temi in
 * tests/test_globals_css_contrasto.py.
 */
const TONE: Record<Tone, { border: string; hover: string; value: string }> = {
  neutro:  { border: "border-border",         hover: "hover:border-muted-foreground/40", value: "text-foreground" },
  positivo: { border: "border-positivo/40", hover: "hover:border-positivo/70", value: "text-positivo" },
  negativo: { border: "border-negativo/40", hover: "hover:border-negativo/70", value: "text-negativo" },
};

// Gli stessi token del TONE per i tratti SVG sparkline, come var(): l'SVG non
// eredita `currentColor` qui.
const TONE_COLOR: Record<Tone, string> = {
  neutro:   "var(--muted-foreground)",
  positivo: "var(--positivo)",
  negativo: "var(--negativo)",
};

type CardDef = {
  label: string;
  numeric: number;
  sub?: string;
  tone: Tone;
  spark?: number[];
};

// Count-up al primo render: anima la presentazione di un valore gia' calcolato
// (nessun dato aggiunto). Rispetta prefers-reduced-motion.
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

export function KpiBar({ kpi }: { kpi: KpiData }) {
  const molTone: Tone = kpi.mol >= 0 ? "positivo" : "negativo";

  const [animate, setAnimate] = useState(false);
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    setAnimate(!reduce);
  }, []);

  // "Margine Lordo" era emerald/rose come il MOL: due riquadri identici per due
  // grandezze diverse. Va a neutro con gli altri — il MOL resta l'unico colorato.
  const cards: CardDef[] = [
    { label: "Fatturato Netto",  numeric: kpi.fatturato_netto, sub: `lordo ${formatEuro(kpi.fatturato_lordo)}`, tone: "neutro", spark: kpi.spark_lordo },
    { label: "Costi F&B",        numeric: kpi.costi_fb,                                                          tone: "neutro", spark: kpi.spark_fb },
    { label: "Margine Lordo",    numeric: kpi.primo_margine,                                                     tone: "neutro", spark: kpi.spark_margine },
    { label: "Spese Generali",   numeric: kpi.spese_generali,                                                    tone: "neutro", spark: kpi.spark_spese },
    { label: "Costo Personale",  numeric: kpi.costo_personale,                                                   tone: "neutro", spark: kpi.spark_personale },
    { label: "MOL",              numeric: kpi.mol,                                                                tone: molTone,  spark: kpi.spark_mol },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map((c) => (
        <KpiCard key={c.label} card={c} animate={animate} nonDisponibile={kpiNonDisponibile(kpi)} />
      ))}
      {kpiNonDisponibile(kpi) && (
        <p className="col-span-2 md:col-span-3 lg:col-span-6 text-[11px] text-muted-foreground">
          Non sono riuscito a caricare questi totali. I dati ci sono: ricarica la
          pagina fra un momento. La tabella qui sotto non e' interessata.
        </p>
      )}
    </div>
  );
}

function KpiCard({ card: c, animate, nonDisponibile }: {
  card: CardDef; animate: boolean; nonDisponibile: boolean;
}) {
  const t = TONE[c.tone];
  const shown = useCountUp(c.numeric, animate && !nonDisponibile);
  return (
    <div
      className={`@container rounded-xl border ${t.border} ${t.hover} bg-card px-4 pt-3 pb-2 transition-colors flex flex-col gap-1`}
    >
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium leading-none">
        {c.label}
      </p>
      <p className={`text-[clamp(1rem,4cqw,1.5rem)] font-bold tracking-tight leading-tight tabular-nums whitespace-nowrap ${t.value}`}>
        {nonDisponibile ? "—" : formatEuro(shown)}
      </p>
      {c.sub && !nonDisponibile && (
        <p className="text-[11px] text-muted-foreground leading-none">{c.sub}</p>
      )}
      {!nonDisponibile && c.spark && c.spark.length >= 2 && (
        <div className="mt-1">
          <Sparkline values={c.spark} color={TONE_COLOR[c.tone]} />
        </div>
      )}
    </div>
  );
}
