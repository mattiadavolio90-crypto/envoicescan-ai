import { Suspense } from "react";
import { redirect } from "next/navigation";
import { PageHeader } from "@/components/ui/page-header";
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

  if (requested in LAYER_REDIRECT) {
    redirect(`/agenda?layer=${LAYER_REDIRECT[requested]}`);
  }

  const tab = requested === "inventario" ? "inventario" : "foodcost";

  return (
    <div className="space-y-4">
      <PageHeader
        icon="wrench"
        title="Strumenti"
        hint="Gli strumenti di analisi del tuo locale: ricette e foodcost, inventario di magazzino."
      />

      <Suspense>
        <TabsSwitcher active={tab} />
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
