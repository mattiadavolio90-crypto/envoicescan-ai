"use client";

import { useEffect, useRef, useState } from "react";
import { formatEuro } from "./periodi";
import { puntiSparkline } from "@/lib/sparkline-punti";
import { kpiNonDisponibile } from "@/lib/esito-caricamento";
import { colonneGriglia, selezionaKpi } from "@/lib/kpi-margini-tab";

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

// M4 — la linea diceva «sale» o «scende», non di quanto.
//
// Nessun asse, nessun `<title>`, nessun hover: una polilinea sospesa. Peggio,
// `ancoraZero: true` include lo zero nella scala, quindi una serie stabile che
// finisce a zero (Costo Personale: sei mesi a 60.000 EUR e poi i mesi non
// caricati) disegna quasi solo il crollo — il dato piu' vistoso del grafico e'
// un buco nei dati.
//
// Non si aggiungono assi (24px di altezza non li reggono): si aggiunge la SCALA
// come testo accessibile e come tooltip nativo, piu' il punto finale marcato
// cosi' si vede da che parte si legge la linea.
// Diametro del punto finale, in PIXEL: non in unita' della viewBox.
//
// La prima correzione compensava la deformazione dividendo per una costante
// `ASPETTO = 2`. Misurata dopo: il fattore vero dipende dalla larghezza della
// card, che ora cambia col tab (A1). Su un'area da ~1550px viene 2,16 con sei
// tessere, 4,8 con tre e **15,2 con una sola** (Coperti) — una costante li'
// non puo' essere giusta, e il punto sarebbe uscito schiacciato 15 volte.
// Il punto vive quindi in un <span> posizionato in percentuale, fuori dall'SVG:
// i pixel non passano per `preserveAspectRatio` e restano tondi a ogni
// larghezza, senza sapere niente della scala.
const PUNTO_PX = 5;

function Sparkline({ values: rawValues, color, label }: {
  values: number[]; color: string; label: string;
}) {
  const w = 100;
  const h = 24;
  const points = puntiSparkline(rawValues, { w, h, ancoraZero: true, padY: 1 });
  if (!points) return null;

  const validi = rawValues.filter((v) => Number.isFinite(v));
  const min = Math.min(...validi);
  const max = Math.max(...validi);
  // L'ultimo punto della polilinea: `puntiSparkline` li emette "x,y" separati da
  // spazio, nell'ordine della serie.
  const ultimo = points.split(" ").pop()?.split(",") ?? [];
  const [cx, cy] = [Number(ultimo[0]), Number(ultimo[1])];

  const scala = `${label}: da ${formatEuro(min)} a ${formatEuro(max)} nei mesi del periodo`;

  return (
    <div className="relative" title={scala}>
    <svg
      width="100%"
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="block w-full"
      role="img"
      aria-label={scala}
    >
      <title>{scala}</title>
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
      {Number.isFinite(cx) && Number.isFinite(cy) && (
        // Il punto finale dice da che parte si legge la linea. Sta FUORI dall'SVG,
        // posizionato in percentuale: misurato in pixel non passa per
        // `preserveAspectRatio="none"` e resta tondo a ogni larghezza di card.
        <span
          aria-hidden
          className="absolute rounded-full"
          style={{
            left: `${cx}%`,
            top: `${(cy / h) * 100}%`,
            width: PUNTO_PX,
            height: PUNTO_PX,
            marginLeft: -PUNTO_PX / 2,
            marginTop: -PUNTO_PX / 2,
            backgroundColor: color,
          }}
        />
      )}
    </div>
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

export function KpiBar({ kpi, tab }: { kpi: KpiData; tab?: string | null }) {
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

  // Selezione e griglia stanno in lib/kpi-margini-tab.ts, non qui: con la
  // `.filter()` scritta in questo file un test non poteva eseguirla, e
  // disattivarla lasciava verdi tutti i presidi (mutante del 23/09).
  const mostrate = selezionaKpi(cards, tab);
  const colonne = colonneGriglia(mostrate.length);

  return (
    <div className={`grid gap-3 ${colonne}`}>
      {mostrate.map((c) => (
        <KpiCard key={c.label} card={c} animate={animate} nonDisponibile={kpiNonDisponibile(kpi)} />
      ))}
      {/* `col-span-full`, non `lg:col-span-6`: da quando le colonne seguono il
          numero di tessere (1, 2, 3, 4, 5 o 6), un 6 fisso sforerebbe la griglia
          su ogni tab tranne Marginalita' a sei. */}
      {kpiNonDisponibile(kpi) && (
        <p className="col-span-full text-[11px] text-muted-foreground">
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
          <Sparkline values={c.spark} color={TONE_COLOR[c.tone]} label={c.label} />
        </div>
      )}
    </div>
  );
}
