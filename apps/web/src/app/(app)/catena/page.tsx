import { Suspense } from "react";
import { redirect } from "next/navigation";
import { fetchGruppoOverview, fetchGruppoChatConfig } from "@/lib/gruppo";
import { chatCatenaAttiva, deveRedirigereAPuntoVendita } from "@/lib/catena-confronti";
import { SintesiCatena } from "./sintesi-catena";
import { getCurrentSession } from "@/lib/auth";
import { caricaFattureInHome } from "@/lib/home-kpi";
import { ChatWidget } from "../dashboard/chat-widget";
import { BlockRetry } from "../dashboard/block-retry";

// Home della catena: recap e assistenza (28/9/2026). Le funzioni di lavoro
// stanno in /catena/fatture (coda, costi di gruppo, scadenze) e le analisi in
// /catena/analisi; l'inserimento dei dati vive nel punto vendita.

function SintesiSkeleton() {
  // Rispecchia il layout reale: testata + briefing + 2 card grandi + segnali.
  return (
    <div className="space-y-6">
      <div className="h-8 w-64 animate-pulse rounded-xl bg-muted/40" />
      <div className="h-32 animate-pulse rounded-2xl border bg-muted/40" />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="h-72 animate-pulse rounded-2xl border bg-muted/40" />
        <div className="h-72 animate-pulse rounded-2xl border bg-muted/40" />
      </div>
      <div className="h-56 animate-pulse rounded-2xl border bg-muted/40" />
    </div>
  );
}

async function SintesiBlock() {
  const overview = await fetchGruppoOverview();
  // Account mono-sede (o worker che risponde 400): non c'è un gruppo da mostrare,
  // si torna alla Home del PV. Worker giù/lento (null) → BlockRetry ripinga e fa
  // refresh da solo appena risponde (niente più vicolo cieco "ricarica a mano").
  if (overview === null) {
    return (
      <BlockRetry endpoint="/api/account/sedi">
        <SintesiSkeleton />
      </BlockRetry>
    );
  }
  if (deveRedirigereAPuntoVendita(overview)) {
    redirect("/dashboard");
  }
  // Stessa regola della Home del punto vendita: il caricamento vive in Analisi
  // Fatture, e se l'admin la spegne la Home non lo riapre.
  const sessione = await getCurrentSession();
  const pagine = sessione.status === "ok" ? sessione.user.pagine_abilitate : null;
  return <SintesiCatena overview={overview} caricaFatture={caricaFattureInHome(pagine)} />;
}

// Chat di catena: pool AI unico (limite = somma dei limiti delle sedi). Compare
// solo se il pool è > 0 (almeno una sede con piano a pagamento). Suspense a parte
// per non ritardare la Sintesi.
async function ChatBlockCatena() {
  const config = await fetchGruppoChatConfig();
  if (!chatCatenaAttiva(config)) return null;
  return (
    <ChatWidget
      contesto="catena"
      limiteGiorno={config.limite_giorno}
      domandeOggiIniziali={config.domande_oggi}
    />
  );
}

export default async function CatenaPage() {
  return (
    <>
      <Suspense fallback={<SintesiSkeleton />}>
        <SintesiBlock />
      </Suspense>
      <Suspense fallback={null}>
        <ChatBlockCatena />
      </Suspense>
    </>
  );
}
