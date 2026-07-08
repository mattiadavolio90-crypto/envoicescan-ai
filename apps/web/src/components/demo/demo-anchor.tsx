"use client";

import { cn } from "@/lib/utils";

// Involucro per gli elementi della demo. Fa due cose:
//   1. marca il nodo con data-demo-anchor="<id>" così lo SpotlightTour lo trova
//      e ci punta il faretto (id dagli step di lib/demo-steps.ts);
//   2. neutralizza le interazioni interne: i componenti reali riusati (KpiBlock,
//      HomeBriefing, …) contengono <Link> e onClick che, se attivati,
//      porterebbero fuori dal tour o farebbero fetch. Catturiamo click e submit
//      in fase di cattura e li fermiamo. La navigazione nella demo è SOLO il
//      tour; qui sotto tutto è "vetrina", non si tocca.

type Props = {
  id?: string;
  className?: string;
  // Se false, lascia passare i click (per contenitori demo già inerti).
  inert?: boolean;
  children: React.ReactNode;
};

export function DemoAnchor({ id, className, inert = true, children }: Props) {
  function swallow(e: React.SyntheticEvent) {
    if (!inert) return;
    e.preventDefault();
    e.stopPropagation();
  }

  return (
    <div
      data-demo-anchor={id}
      className={cn(className)}
      onClickCapture={swallow}
      onSubmitCapture={swallow}
    >
      {children}
    </div>
  );
}
