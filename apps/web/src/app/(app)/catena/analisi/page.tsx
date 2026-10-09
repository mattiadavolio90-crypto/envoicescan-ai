import { Suspense } from "react";
import { notFound, redirect } from "next/navigation";
import { getCurrentSession } from "@/lib/auth";
import { fetchGruppoOverview } from "@/lib/gruppo";
import { deveRedirigereAPuntoVendita } from "@/lib/catena-confronti";
import { copertiCatenaAccesi, risolviScheda, schedeAnalisiCatena } from "@/lib/catena-schede";
import { PageHeader } from "@/components/ui/page-header";
import { BlockRetry } from "../../dashboard/block-retry";
import { TabsSwitcher } from "../../analisi-fatture/tabs-switcher";
import { SchedaSpesaPV } from "./scheda-spesa-pv";
import { SchedaMarginiCoperti } from "./scheda-margini-coperti";
import { SchedaTagCatena } from "./scheda-tag-catena";

// Analisi catena (Mattia, 28/9): le tre analisi che stavano come finestre nella
// Home di catena, ora schede di pagina. Come /catena non c'e' un interruttore
// di pagina: le sedi le risolve il worker (`_resolve_gruppo`). Le schede si
// spengono dall'admin (`tab_off_catena_*`, fase H3): spente tutte, 404.

function AnalisiSkeleton() {
  return (
    <div className="space-y-5">
      <div className="h-10 border-b" />
      <div className="h-96 animate-pulse rounded-xl border bg-muted/40" />
    </div>
  );
}

async function AnalisiBlock({ richiesta }: { richiesta: string | undefined }) {
  const [overview, sessione] = await Promise.all([fetchGruppoOverview(), getCurrentSession()]);
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
  const pagine = sessione.status === "ok" ? sessione.user.pagine_abilitate : null;
  const schede = schedeAnalisiCatena(pagine);
  if (schede.length === 0) notFound();
  const tab = risolviScheda(schede, richiesta);

  return (
    <>
      <TabsSwitcher active={tab} disponibili={schede} />
      {tab === "spesa" && <SchedaSpesaPV />}
      {tab === "margini" && <SchedaMarginiCoperti coperti={copertiCatenaAccesi(pagine)} />}
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
        <AnalisiBlock richiesta={tab} />
      </Suspense>
    </div>
  );
}
