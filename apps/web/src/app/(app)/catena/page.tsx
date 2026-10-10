import { Suspense } from "react";
import { redirect } from "next/navigation";
import { fetchGruppoOverview, fetchGruppoChatConfig } from "@/lib/gruppo";
import { chatCatenaAttiva, deveRedirigereAPuntoVendita } from "@/lib/catena-confronti";
import { quotaDaGruppo } from "@/lib/home-chat";
import { segnaliBoost, triggerAbilitati, valutaTrigger } from "@/lib/trigger-servizi";
import { TriggerHint } from "@/components/trigger-hint";
import { SintesiCatena } from "./sintesi-catena";
import { BlockRetry } from "../dashboard/block-retry";
import { linkAnalisiCatena, linkMarginiIncompleti, schedaCatenaAccesa } from "@/lib/catena-schede";
import { getCurrentUser } from "@/lib/auth";

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
  // La quota della chat di catena (pool AI: somma dei limiti delle sedi) si
  // legge insieme alla sintesi: la conversazione vive nel riquadro del briefing.
  const [overview, chatConfig, utente] = await Promise.all([
    fetchGruppoOverview(),
    fetchGruppoChatConfig(),
    getCurrentUser(),
  ]);
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
  // Boost AI (fase J): al 75% dei crediti del mese dell'account, in fondo.
  const boost =
    chatCatenaAttiva(chatConfig) && triggerAbilitati(utente?.pagine_abilitate)
      ? valutaTrigger("home", segnaliBoost(quotaDaGruppo(chatConfig), !utente?.sotto_utente))
      : null;
  return (
    <>
      <SintesiCatena
        overview={overview}
        chat={
          chatCatenaAttiva(chatConfig)
            ? {
                quota: quotaDaGruppo(chatConfig),
                lettoAlle: Date.now(),
                settore: utente?.tipo_attivita ?? null,
              }
            : null
        }
        linkSpesa={linkAnalisiCatena(utente?.pagine_abilitate, "spesa")}
        linkMargini={linkAnalisiCatena(utente?.pagine_abilitate, "margini")}
        linkIncompleti={linkMarginiIncompleti(utente?.pagine_abilitate)}
        codaAccesa={schedaCatenaAccesa(utente?.pagine_abilitate, "collocare")}
      />
      <TriggerHint trigger={boost} className="mt-6" />
    </>
  );
}

export default async function CatenaPage() {
  return (
    <>
      <Suspense fallback={<SintesiSkeleton />}>
        <SintesiBlock />
      </Suspense>
    </>
  );
}
