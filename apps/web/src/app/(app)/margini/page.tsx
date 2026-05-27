import { Suspense } from "react";
import { fetchMarginiAnno } from "@/lib/margini";
import { TabsSwitcher } from "./tabs-switcher";
import { CalcoloTab } from "./calcolo-tab";
import { AnalisiTab } from "./analisi-tab";

export default async function MarginiPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; anno?: string }>;
}) {
  const sp = await searchParams;
  const tab = sp.tab ?? "calcolo";
  const anno = parseInt(sp.anno ?? String(new Date().getFullYear()), 10);

  const margini = tab === "calcolo" ? await fetchMarginiAnno(anno) : null;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Marginalità</h1>
      <Suspense>
        <TabsSwitcher active={tab} />
      </Suspense>
      <div className="mt-2">
        {tab === "calcolo" ? (
          <Suspense>
            <CalcoloTab anno={anno} mesi={margini?.mesi ?? []} />
          </Suspense>
        ) : (
          <Suspense>
            <AnalisiTab anno={anno} />
          </Suspense>
        )}
      </div>
    </div>
  );
}
