import { Suspense } from "react";
import { redirect } from "next/navigation";
import { fetchGruppoOverview, fetchGruppoChatConfig } from "@/lib/gruppo";
import { SintesiCatena } from "./sintesi-catena";
import { ChatWidget } from "../dashboard/chat-widget";
import { BlockRetry } from "../dashboard/block-retry";

// Modalità catena (Fase 1) — UNA pagina: la Sintesi (plancia di sola lettura).
// La catena è un layer superiore di analisi/visualizzazione sopra i PV;
// l'inserimento vive solo nel punto vendita.

function SintesiSkeleton() {
  // Rispecchia il layout reale: testata + briefing + 2 card grandi + 3 confronti + ranking.
  return (
    <div className="space-y-6">
      <div className="h-8 w-64 animate-pulse rounded-xl bg-muted/40" />
      <div className="h-32 animate-pulse rounded-2xl border bg-muted/40" />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="h-72 animate-pulse rounded-2xl border bg-muted/40" />
        <div className="h-72 animate-pulse rounded-2xl border bg-muted/40" />
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="h-20 animate-pulse rounded-2xl border bg-muted/40" />
        <div className="h-20 animate-pulse rounded-2xl border bg-muted/40" />
        <div className="h-20 animate-pulse rounded-2xl border bg-muted/40" />
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
  if (overview.num_pv < 2) {
    redirect("/dashboard");
  }
  return <SintesiCatena overview={overview} />;
}

// Chat di catena: pool AI unico (limite = somma dei limiti delle sedi). Compare
// solo se il pool è > 0 (almeno una sede con piano a pagamento). Suspense a parte
// per non ritardare la Sintesi.
async function ChatBlockCatena() {
  const config = await fetchGruppoChatConfig();
  if (!config || !config.enabled || config.limite_giorno <= 0) return null;
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
