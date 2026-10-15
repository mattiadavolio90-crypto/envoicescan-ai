"use client";

import { useEffect } from "react";
import type { DemoStep } from "@/lib/demo-steps";

// Nessun faretto/overlay: la guida è la sola barra in alto e la schermata resta
// pulita. Questo componente non disegna nulla — porta solo in vista l'elemento
// del passo (se ne ha uno), così quando il tour ne parla è già sullo schermo.
export function SpotlightTour({ step }: { step: DemoStep }) {
  useEffect(() => {
    if (!step.anchorId) return;
    const el = document.querySelector<HTMLElement>(`[data-demo-anchor="${step.anchorId}"]`);
    if (!el) return;
    // Centrato se ci sta; se e' piu' alto dello schermo (il briefing col riquadro dell'assistente,
    // dal 15/10 ad altezza fissa) dall'alto, se no la sua parte di sopra finisce fuori vista.
    const alto = el.getBoundingClientRect().height > window.innerHeight * 0.7;
    el.scrollIntoView({ behavior: "smooth", block: alto ? "start" : "center" });
  }, [step.anchorId]);

  return null;
}
