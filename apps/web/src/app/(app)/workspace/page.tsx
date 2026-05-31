import { Suspense } from "react";
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
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Strumenti</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Gli strumenti operativi del tuo locale: ricette e foodcost, diario, turni, inventario.
        </p>
      </div>

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
