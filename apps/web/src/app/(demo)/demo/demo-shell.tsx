"use client";

import { useState } from "react";
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { Wordmark } from "@/components/brand/logo";
import { DemoSidebar } from "@/components/demo/demo-sidebar";
import { DemoChat } from "@/components/demo/demo-chat";
import { SpotlightTour } from "@/components/demo/spotlight-tour";
import { DemoTopBar } from "@/components/demo/demo-topbar";
import { DemoClosing } from "@/components/demo/demo-closing";
import { DemoHome } from "@/components/demo/screens/demo-home";
import { DemoAnalisi } from "@/components/demo/screens/demo-analisi";
import { DemoPrezzi } from "@/components/demo/screens/demo-prezzi";
import { DemoMargini } from "@/components/demo/screens/demo-margini";
import { DEMO_STEPS, type DemoScreen } from "@/lib/demo-steps";

// Orchestratore del Demo Tour. Tiene l'indice dello step corrente:
//   0..N-1  → step di contenuto (chrome dell'app + schermata + spotlight)
//   N       → schermata di conversione (DemoClosing)
// Il chrome (sidebar + header) è identico al layout (app), ma inerte: sidebar
// disabilitata, header senza azioni. La schermata sotto dipende dallo step.

function Screen({ screen, openConfig }: { screen: DemoScreen; openConfig: boolean }) {
  switch (screen) {
    case "home":
      return <DemoHome openConfig={openConfig} />;
    case "analisi":
      return <DemoAnalisi />;
    case "prezzi":
      return <DemoPrezzi />;
    case "margini":
      return <DemoMargini />;
  }
}

export function DemoShell() {
  const [index, setIndex] = useState(0);
  const total = DEMO_STEPS.length;
  const inClosing = index >= total;

  if (inClosing) {
    return <DemoClosing onRestart={() => setIndex(0)} />;
  }

  const step = DEMO_STEPS[index];

  return (
    // h-svh + overflow-hidden sul guscio: la pagina NON scrolla col body (che
    // creava il "nero infinito" sotto l'overlay). Scrolla SOLO il <main> interno,
    // e solo il tour lo muove (scrollIntoView) — l'utente non scrolla a mano
    // durante la guida, così faretto e tooltip restano sempre allineati.
    <div className="h-svh overflow-hidden">
      <SidebarProvider>
        <DemoSidebar screen={step.screen} />
        <SidebarInset className="h-svh overflow-hidden">
          <header className="relative flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
            {/* Trigger disattivato: la sidebar reale (drawer a tutto schermo su
                mobile) aprirebbe una via d'uscita dal tour guidato. La demo si
                naviga SOLO con i controlli della topbar. */}
            <SidebarTrigger className="-ml-1 pointer-events-none opacity-40" tabIndex={-1} aria-hidden />
            <Separator orientation="vertical" className="h-4" />
            <Wordmark className="pointer-events-none absolute left-1/2 -translate-x-1/2 text-2xl" />
          </header>

          {/* Banner-guida fisso: avviso demo + testo del passo + controlli
              (indietro/avanti/chiudi). Sostituisce il tooltip flottante: la
              schermata sotto resta pulita, la guida non si sovrappone mai. */}
          <DemoTopBar
            step={step}
            index={index}
            total={total}
            onPrev={() => setIndex((i) => Math.max(0, i - 1))}
            onNext={() => setIndex((i) => i + 1)}
            onClose={() => setIndex(total)}
            onSkipToEnd={() => setIndex(total)}
          />

          {/* Il main scrolla internamente (per portare in vista l'ancora), ma lo
              scroll manuale dell'utente è disattivato durante il tour. */}
          <main className="flex-1 overflow-y-auto overscroll-contain p-6 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <Screen screen={step.screen} openConfig={step.anchorId === "config"} />
          </main>
        </SidebarInset>
      </SidebarProvider>

      {/* Chat AI: montata sempre, si "apre" solo nello step dedicato. */}
      <DemoChat open={Boolean(step.openChat)} />

      {/* Faretto: cerchia l'elemento del passo. key forza il remount a ogni step
          così la misura dell'ancora riparte pulita. */}
      <SpotlightTour key={step.id} step={step} />
    </div>
  );
}
