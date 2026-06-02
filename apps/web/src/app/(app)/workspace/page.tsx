import { Suspense } from "react";
import { PageHeader } from "@/components/ui/page-header";
import { TabsSwitcher } from "./tabs-switcher";
import { FoodcostTab } from "./foodcost-tab";
import { InventarioTab } from "./inventario-tab";
import { DiarioTab } from "./diario-tab";
import { PersonaleTab } from "./personale-tab";

export default async function WorkspacePage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const sp = await searchParams;
  const tab = sp.tab ?? "foodcost";

  return (
    <div className="space-y-4">
      <PageHeader
        icon="wrench"
        title="Strumenti"
        hint="Gli strumenti operativi del tuo locale: ricette e foodcost, diario, turni, inventario."
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
        {tab === "diario" && (
          <Suspense>
            <DiarioTab />
          </Suspense>
        )}
        {tab === "personale" && (
          <Suspense>
            <PersonaleTab />
          </Suspense>
        )}
      </div>
    </div>
  );
}
