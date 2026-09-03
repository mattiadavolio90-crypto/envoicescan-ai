import { Suspense } from "react";
import { redirect } from "next/navigation";
import { PageHeader } from "@/components/ui/page-header";
import { requirePaginaConTab } from "@/lib/page-guard";
import { TabsSwitcher } from "./tabs-switcher";
import { FoodcostTab } from "./foodcost-tab";
import { InventarioTab } from "./inventario-tab";

// I tab Agenda/Spese/Personale sono migrati nella pagina dedicata /agenda.
// Vecchi link a ?tab=agenda|spese|personale vengono rediretti per non rompersi.
const LAYER_REDIRECT: Record<string, string> = {
  agenda: "appuntamenti",
  spese: "spese",
  personale: "personale",
};

export default async function WorkspacePage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const sp = await searchParams;
  const requested = sp.tab ?? "foodcost";

  // Redirect dei vecchi layer PRIMA del guard: un utente con solo 'agenda' (non
  // 'workspace') che apre un vecchio link ?tab=spese deve atterrare su /agenda,
  // non prendere un 404 dal guard workspace.
  if (requested in LAYER_REDIRECT) {
    redirect(`/agenda?layer=${LAYER_REDIRECT[requested]}`);
  }

  // Risolve permessi pagina E tab in un colpo: la normalizzazione difensiva del
  // param (che qui era gia' presente) vive ora in risolviTab, insieme al
  // filtro delle tab spente dal pannello admin.
  const { tab, disponibili } = await requirePaginaConTab(
    "workspace", "workspace", sp.tab, "/workspace",
  );

  return (
    <div className="space-y-4">
      <PageHeader
        icon="wrench"
        title="Strumenti"
        hint="Gli strumenti di analisi del tuo locale: ricette e foodcost, inventario di magazzino."
      />

      <Suspense>
        <TabsSwitcher active={tab} disponibili={disponibili} />
      </Suspense>

      <div className="mt-2">
        {tab === "foodcost" && (
          <Suspense>
            <FoodcostTab />
          </Suspense>
        )}
        {tab === "inventario" && (
          <Suspense>
            <InventarioTab />
          </Suspense>
        )}
      </div>
    </div>
  );
}
