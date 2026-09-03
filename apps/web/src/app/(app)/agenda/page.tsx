import { Suspense } from "react";
import { PageHeader } from "@/components/ui/page-header";
import { requirePaginaConTab } from "@/lib/page-guard";
import { LayerSwitcher } from "./layer-switcher";
import { AgendaOverview } from "./agenda-overview";
import { AgendaView } from "../workspace/diario-tab";
import { SpeseView } from "../workspace/spese-view";
import { PersonaleTab } from "../workspace/personale-tab";

export default async function AgendaPage({
  searchParams,
}: {
  searchParams: Promise<{ layer?: string }>;
}) {
  const sp = await searchParams;
  // Il param qui si chiama `layer`, non `tab`: il guard lo riceve come nome, cosi'
  // un redirect ricostruisce /agenda?layer=... e non un ?tab= che nessuno legge.
  const { tab: layer, disponibili } = await requirePaginaConTab(
    "agenda", "agenda", sp.layer, "/agenda", "layer",
  );

  return (
    <div className="space-y-4">
      <PageHeader
        icon="calendar"
        title="Agenda"
        hint="Tutto ciò che succede nel tuo locale, giorno per giorno: appuntamenti, spese e turni del personale."
      />

      <Suspense>
        <LayerSwitcher active={layer} disponibili={disponibili} />
      </Suspense>

      <div className="mt-2">
        {layer === "tutto" && (
          <Suspense>
            <AgendaOverview />
          </Suspense>
        )}
        {layer === "appuntamenti" && (
          <Suspense>
            <AgendaView />
          </Suspense>
        )}
        {layer === "spese" && (
          <Suspense>
            <SpeseView />
          </Suspense>
        )}
        {layer === "personale" && (
          <Suspense>
            <PersonaleTab />
          </Suspense>
        )}
      </div>
    </div>
  );
}
