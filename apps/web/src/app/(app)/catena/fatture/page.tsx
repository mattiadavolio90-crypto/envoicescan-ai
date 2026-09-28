import { Suspense } from "react";
import { redirect } from "next/navigation";
import { getCurrentSession, getCurrentUser } from "@/lib/auth";
import { fetchGruppoOverview } from "@/lib/gruppo";
import { PageHeader } from "@/components/ui/page-header";
import { CodaDaAssegnare } from "@/components/fatture/coda-da-assegnare";
import { ScadenziarioClient } from "../../scadenziario/scadenziario-client";
import { BlockRetry } from "../../dashboard/block-retry";
import { TabsSwitcher } from "../../analisi-fatture/tabs-switcher";
import { SchedaCostiGruppo } from "./scheda-costi-gruppo";
import type { Documento, SedeCatena } from "@/lib/scadenziario";
import { workerGet } from "@/lib/worker";
import { esitoLista } from "@/lib/esito-caricamento";
import {
  SCHEDA_FATTURE_PREDEFINITA,
  risolviScheda,
  schedeFattureCatena,
} from "@/lib/catena-schede";

type GruppoScadenziarioResponse = {
  nome_gruppo: string;
  sedi: SedeCatena[];
  documenti: Documento[];
};

function FattureSkeleton() {
  return (
    <div className="space-y-5">
      {/* Riga delle schede. */}
      <div className="h-10 border-b" />
      {/* La barra di ricerca sta in cima alla pagina vera: senza il suo posto
          qui, al caricamento il contenuto scatta in giu' di una riga. */}
      <div className="h-10 animate-pulse rounded-md bg-muted/40" />
      {/* Filtri sopra i KPI, come nella pagina vera. */}
      <div className="flex flex-wrap gap-2">
        {[28, 28, 36].map((w, i) => (
          <div key={i} className="h-7 animate-pulse rounded-full bg-muted/40" style={{ width: `${w * 4}px` }} />
        ))}
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl border bg-muted/40" />
        ))}
      </div>
      <div className="h-96 animate-pulse rounded-lg border bg-muted/40" />
    </div>
  );
}

async function FattureBlock({ richiesta }: { richiesta: string | undefined }) {
  const [overview, sessione] = await Promise.all([fetchGruppoOverview(), getCurrentSession()]);
  // Worker giù/lento (null) → BlockRetry ripinga e fa refresh da solo appena
  // risponde. Mandare a /dashboard anche in questo caso sbatteva fuori dalla
  // pagina chi ha davvero un gruppo, per un guasto temporaneo.
  if (overview === null) {
    return (
      <BlockRetry endpoint="/api/account/sedi">
        <FattureSkeleton />
      </BlockRetry>
    );
  }
  // Account mono-sede: niente vista di gruppo da mostrare, torna alla Home del PV
  // (stesso comportamento di /catena — vedi catena/page.tsx).
  if (overview.num_pv < 2) {
    redirect("/dashboard");
  }

  const pagine = sessione.status === "ok" ? sessione.user.pagine_abilitate : null;
  const schede = schedeFattureCatena(overview.briefing?.n_fatture_da_collocare, pagine);
  const tab = risolviScheda(schede, richiesta, SCHEDA_FATTURE_PREDEFINITA);
  // Il menu delle categorie dei costi di gruppo deve offrire solo quelle che il
  // worker accetta per questo settore. Costa un /api/auth/me: solo su quella scheda.
  const settore = tab === "costi" ? (await getCurrentUser())?.tipo_attivita : undefined;
  // La preferenza di vista dello scadenziario segue l'account, quindi vale anche qui.
  const vistaFatture = sessione.status === "ok" ? sessione.user.vista_fatture : undefined;

  return (
    <>
      <TabsSwitcher active={tab} disponibili={schede} />
      {tab === "collocare" && <CodaDaAssegnare />}
      {tab === "costi" && <SchedaCostiGruppo settore={settore} />}
      {tab === "scadenze" && <ScadenzeGruppo vistaIniziale={vistaFatture} />}
    </>
  );
}

async function ScadenzeGruppo({ vistaIniziale }: { vistaIniziale: string | undefined }) {
  const data = await workerGet<GruppoScadenziarioResponse>(
    "/api/gruppo/scadenziario",
    "catena/fatture",
  );

  // `data === null` = worker giu'/timeout, non "zero scadenze": senza la
  // distinzione la pagina scriveva «Nessun documento trovato» su un guasto.
  const esito = esitoLista<Documento>(data, "documenti");

  return (
    <ScadenziarioClient
      initialDocumenti={esito.righe}
      caricamentoFallito={esito.stato === "non_disponibile"}
      vistaIniziale={vistaIniziale}
      modalitaCatena
      sedi={esitoLista<SedeCatena>(data, "sedi").righe}
    />
  );
}

// Tre schede (Mattia, 28/9): la coda delle fatture di gruppo e i costi di
// gruppo erano finestre della Home di catena, che ora e' solo recap e
// assistenza. Il flag `scadenziario` non chiude piu' la pagina intera: spegne la
// sola scheda «Scadenze» (vedi schedeFattureCatena).
export default async function CatenaFatturePage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab } = await searchParams;

  return (
    <div className="space-y-5">
      <PageHeader
        icon="calendar"
        title="Gestione Fatture — Gruppo"
        hint="Scadenze di tutti i punti vendita, fatture da collocare, costi divisi fra le sedi"
      />
      <Suspense fallback={<FattureSkeleton />}>
        <FattureBlock richiesta={tab} />
      </Suspense>
    </div>
  );
}
