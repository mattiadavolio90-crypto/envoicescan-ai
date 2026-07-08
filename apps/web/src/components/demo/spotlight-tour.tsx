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
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [step.anchorId]);

  return null;
}
