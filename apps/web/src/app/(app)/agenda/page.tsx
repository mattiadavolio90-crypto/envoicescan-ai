import { Suspense } from "react";
import { PageHeader } from "@/components/ui/page-header";
import { requirePaginaConTab } from "@/lib/page-guard";
import { getCurrentUser } from "@/lib/auth";
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
  // getCurrentUser e' avvolto in cache() di React: il layout l'ha gia' chiamato
  // in questo render, quindi il settore non costa una chiamata in piu'.
  const settore = (await getCurrentUser())?.tipo_attivita;

  return (
    <div className="space-y-4">
      <PageHeader
        icon="calendar"
        title="Agenda"
        hint={`Tutto ciò che succede nel tuo ${settore === "retail" ? "negozio" : "locale"}, giorno per giorno: appuntamenti, spese e turni del personale.`}
      />

      <Suspense>
        <LayerSwitcher active={layer} disponibili={disponibili} />
      </Suspense>

      <div className="mt-2">
        {layer === "tutto" && (
          <Suspense>
            <AgendaOverview settore={settore} />
          </Suspense>
        )}
        {layer === "appuntamenti" && (
          <Suspense>
            <AgendaView />
          </Suspense>
        )}
        {layer === "spese" && (
          <Suspense>
            <SpeseView settore={settore} />
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
