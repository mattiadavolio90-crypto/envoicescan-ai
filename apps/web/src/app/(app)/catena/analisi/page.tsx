import { Suspense } from "react";
import { redirect } from "next/navigation";
import { fetchGruppoOverview } from "@/lib/gruppo";
import { deveRedirigereAPuntoVendita } from "@/lib/catena-confronti";
import { SCHEDE_ANALISI_CATENA, risolviScheda } from "@/lib/catena-schede";
import { PageHeader } from "@/components/ui/page-header";
import { BlockRetry } from "../../dashboard/block-retry";
import { TabsSwitcher } from "../../analisi-fatture/tabs-switcher";
import { SchedaSpesaPV } from "./scheda-spesa-pv";
import { SchedaMarginiCoperti } from "./scheda-margini-coperti";
import { SchedaTagCatena } from "./scheda-tag-catena";

// Analisi catena (Mattia, 28/9): le tre analisi che stavano come finestre nella
// Home di catena, ora schede di pagina. Come /catena non c'e' un interruttore
// di pagina: le sedi le risolve il worker (`_resolve_gruppo`).

function AnalisiSkeleton() {
  return (
    <div className="space-y-5">
      <div className="h-10 border-b" />
      <div className="h-96 animate-pulse rounded-xl border bg-muted/40" />
    </div>
  );
}

async function AnalisiBlock({ tab }: { tab: string }) {
  const overview = await fetchGruppoOverview();
  if (overview === null) {
    return (
      <BlockRetry endpoint="/api/account/sedi">
        <AnalisiSkeleton />
      </BlockRetry>
    );
  }
  if (deveRedirigereAPuntoVendita(overview)) {
    redirect("/dashboard");
  }

  return (
    <>
      <TabsSwitcher active={tab} disponibili={[...SCHEDE_ANALISI_CATENA]} />
      {tab === "spesa" && <SchedaSpesaPV />}
      {tab === "margini" && <SchedaMarginiCoperti />}
      {tab === "tag" && <SchedaTagCatena />}
    </>
  );
}

export default async function AnalisiCatenaPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab } = await searchParams;

  return (
    <div className="space-y-5">
      <PageHeader
        icon="bar-chart"
        title="Analisi catena"
        hint="I punti vendita a confronto: spesa, margini e coperti, prodotti"
      />
      <Suspense fallback={<AnalisiSkeleton />}>
        <AnalisiBlock tab={risolviScheda(SCHEDE_ANALISI_CATENA, tab)} />
      </Suspense>
    </div>
  );
}
