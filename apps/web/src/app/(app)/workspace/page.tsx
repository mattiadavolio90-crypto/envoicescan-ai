import { Suspense } from "react";
import { CalendarDays, Users, Package, type LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { TabsSwitcher } from "./tabs-switcher";
import { FoodcostTab } from "./foodcost-tab";

function Placeholder({
  icon: Icon,
  titolo,
  descrizione,
}: {
  icon: LucideIcon;
  titolo: string;
  descrizione: string;
}) {
  return (
    <Card>
      <CardContent className="py-16 text-center">
        <Icon className="mx-auto size-12 text-muted-foreground/40" />
        <p className="mt-4 text-base font-medium">{titolo}</p>
        <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">{descrizione}</p>
        <p className="mt-3 text-xs font-medium text-amber-600 dark:text-amber-500">In costruzione</p>
      </CardContent>
    </Card>
  );
}

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
        {tab === "diario" && (
          <Placeholder
            icon={CalendarDays}
            titolo="Diario"
            descrizione="Un calendario condiviso per annotare eventi, scadenze e note del locale."
          />
        )}
        {tab === "personale" && (
          <Placeholder
            icon={Users}
            titolo="Personale"
            descrizione="Inserisci i turni del personale e ottieni il monte ore settimanale e mensile da esportare per l'ufficio paghe."
          />
        )}
        {tab === "inventario" && (
          <Placeholder
            icon={Package}
            titolo="Inventario"
            descrizione="Conta le giacenze a fine mese e tieni traccia del valore di magazzino."
          />
        )}
      </div>
    </div>
  );
}
