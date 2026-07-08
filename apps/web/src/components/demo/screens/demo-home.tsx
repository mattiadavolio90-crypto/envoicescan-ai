"use client";

import { HomeBriefing } from "@/app/(app)/dashboard/home-briefing";
import { ConfigAssistente } from "@/app/(app)/dashboard/config-assistente";
import { SaluteCard } from "@/app/(app)/dashboard/salute-card";
import { KpiBlock } from "@/app/(app)/dashboard/kpi-block";
import { demoBriefing, demoConfig, demoKpi, demoSalute } from "@/lib/demo-data";
import { DemoAnchor } from "../demo-anchor";

// Home del Demo Tour: RIUSA i componenti presentazionali reali della Home
// (stessa identica UI del prodotto), alimentati con i dati finti "Marea".
// Questi componenti prendono tutto via props e non fanno fetch al render — le
// uniche azioni interne (CTA con <Link>, "Ignora" con fetch) sono neutralizzate
// da DemoAnchor, che cattura i click così nessuna interazione esce dal tour.

export function DemoHome({ openConfig = false }: { openConfig?: boolean }) {
  return (
    <div className="space-y-8">
      {/* Nello step "config" il pannello si apre da solo (defaultOpen) e si
          posiziona SOTTO la barra-guida (top fisso invece del centro-schermo),
          con altezza limitata così il contenuto scorre senza finire sotto la
          barra. Uscendo dallo step si richiude da solo. */}
      <DemoAnchor id="config" className="flex justify-end">
        <ConfigAssistente
          config={demoConfig}
          defaultOpen={openConfig}
          dialogClassName="top-[11rem] translate-y-0 max-h-[calc(100dvh-12.5rem)]"
        />
      </DemoAnchor>

      <DemoAnchor id="briefing">
        <HomeBriefing briefing={demoBriefing} />
      </DemoAnchor>

      <DemoAnchor className="grid gap-4 lg:grid-cols-2 lg:items-stretch">
        <SaluteCard salute={demoSalute} hideLinks />
        <KpiBlock kpi={demoKpi} />
      </DemoAnchor>
    </div>
  );
}
