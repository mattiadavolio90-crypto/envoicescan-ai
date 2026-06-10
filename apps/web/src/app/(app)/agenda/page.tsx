import { Suspense } from "react";
import { PageHeader } from "@/components/ui/page-header";
import { requirePagina } from "@/lib/page-guard";
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
  await requirePagina("agenda");
  const sp = await searchParams;
  const layer = sp.layer ?? "tutto";

  return (
    <div className="space-y-4">
      <PageHeader
        icon="calendar"
        title="Agenda"
        hint="Tutto ciò che succede nel tuo locale, giorno per giorno: appuntamenti, spese e turni del personale."
      />

      <Suspense>
        <LayerSwitcher active={layer} />
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
