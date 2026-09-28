"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { AscoltaButton } from "@/components/ascolta-button";

// Il riquadro dell'assistente, uguale nella Home del punto vendita e in quella
// della catena (Mattia, 28/9: una Home sola, cambiano solo i dati). Fino ad
// allora erano due copie divergenti: misure, titolo e typewriter diversi.

// Effetto typewriter (spegnibile in 1 riga): solo al primo load del giorno,
// max ~600ms. Dietro flag perche' deve restare sobrio e veloce.
const TYPEWRITER_ENABLED = true;

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

export function RiquadroAssistente({
  etichetta,
  saluto,
  narrativa,
  testoAscolta,
  chiaveGiorno,
  children,
}: {
  etichetta: string;
  saluto: string;
  narrativa: string;
  testoAscolta: string;
  /** Chiave del giorno per animare la narrativa solo la prima volta. Assente =
   * niente animazione. */
  chiaveGiorno?: string | null;
  children?: React.ReactNode;
}) {
  const [animate, setAnimate] = useState(false);
  const decided = useRef(false);
  useEffect(() => {
    if (decided.current) return;
    decided.current = true;
    if (!TYPEWRITER_ENABLED || !chiaveGiorno) return;
    try {
      const key = `oneflux:briefing-seen:${chiaveGiorno}`;
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, "1");
        setAnimate(true);
      }
    } catch {
      /* sessionStorage non disponibile: nessuna animazione */
    }
  }, [chiaveGiorno]);

  const mostrata = useTypewriter(narrativa, animate);

  return (
    <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-primary/10 via-primary/[0.04] to-background p-5 sm:p-6">
      <div className="pointer-events-none absolute -right-16 -top-16 size-56 rounded-full bg-accent blur-3xl" />
      <div className="pointer-events-none absolute -bottom-20 left-1/3 size-52 rounded-full bg-primary/10 blur-3xl" />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-medium text-primary/80">
          <Sparkles className="size-4" />
          <span>{etichetta}</span>
        </div>
        <AscoltaButton testo={testoAscolta} />
      </div>
      <h1 className="mt-2 text-xl font-bold tracking-tight sm:text-2xl">{saluto}</h1>
      <p className="mt-3 max-w-none whitespace-pre-line text-base leading-relaxed text-foreground/90">
        {mostrata}
        {animate && mostrata.length < narrativa.length && (
          <span className="ml-0.5 inline-block h-5 w-0.5 animate-pulse bg-primary align-middle" />
        )}
      </p>
      {children}
    </div>
  );
}
