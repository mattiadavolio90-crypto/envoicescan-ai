import { Suspense } from "react";
import { fetchBriefing, fetchSalute, fetchConfig, fetchKpi } from "@/lib/home";
import { fetchNotifiche } from "@/lib/notifiche";
import { HomeBriefing } from "./home-briefing";
import { NotificheWidget } from "./notifiche-widget";
import { CodaDaAssegnare } from "@/components/fatture/coda-da-assegnare";
import { ChatWidget } from "./chat-widget";
import { SaluteCard } from "./salute-card";
import { KpiBlock } from "./kpi-block";
import { ConfigAssistente } from "./config-assistente";
import { BlockRetry } from "./block-retry";
import { HomeAutoRefresh } from "./home-auto-refresh";
import { Card, CardContent } from "@/components/ui/card";
import { Receipt } from "lucide-react";

// Streaming con Suspense per blocco: ogni sezione carica i suoi dati in modo
// indipendente. Prima un unico Promise.all bloccante aspettava la chiamata piu'
// lenta (dashboard/stats su clienti con migliaia di righe, o il briefing) e, se
// quella andava in timeout, l'intera pagina rendeva il fallback (briefing/card
// "spariti"). Ora il pattern e' lo stesso della Home mobile: ogni blocco appare
// appena pronto, uno lento non affossa gli altri.

function CardSkeleton() {
  return <div className="h-56 animate-pulse rounded-2xl border bg-muted/40" />;
}

async function ConfigBlock() {
  const config = await fetchConfig();
  if (!config) return null;
  return (
    <div className="flex justify-end">
      <ConfigAssistente config={config} />
    </div>
  );
}

async function BriefingBlock() {
  const briefing = await fetchBriefing();
  if (!briefing) {
    // Briefing assente = worker non ha risposto (cold-start/timeout): NON il
    // fallback muto di prima (header "Dashboard" e nient'altro, che sembrava
    // "sparito"). Mostriamo uno skeleton vivo e ripinghiamo finche' il worker
    // si sveglia, poi router.refresh() fa apparire il briefing da solo.
    return (
      <BlockRetry endpoint="/api/home/briefing">
        <div className="space-y-4">
          <div className="h-40 animate-pulse rounded-2xl border bg-muted/40" />
          <p className="text-center text-sm text-muted-foreground">
            Sto preparando il tuo riepilogo…
          </p>
        </div>
      </BlockRetry>
    );
  }
  return <HomeBriefing briefing={briefing} />;
}

async function NotificheBlock() {
  const notifiche = await fetchNotifiche();
  const count = notifiche?.unread ?? 0;
  if (count === 0) return null;
  return (
    <div className="flex justify-center sm:justify-start">
      <NotificheWidget count={count} />
    </div>
  );
}

async function KpiSaluteBlock() {
  // Solo kpi + salute: prima si chiamava anche fetchDashboardStats() (endpoint
  // pesante su clienti con migliaia di righe) solo per ricavare isEmpty, ma lo
  // stato vuoto e' gia' deducibile da kpi/salute — niente round-trip in piu'.
  const [kpi, salute] = await Promise.all([fetchKpi(), fetchSalute()]);

  // Distinzione importante:
  //   - entrambi null  => il worker NON ha risposto (cold-start/timeout): retry,
  //     non lo stato "vuoto", altrimenti a un cliente con dati veri comparirebbe
  //     "Nessuna fattura" finche' non ricarica.
  //   - dati ricevuti ma kpi.has_data === false => cliente davvero senza fatture.
  const workerGiu = !salute && !kpi;
  const vuotoReale = kpi?.has_data === false && !salute;

  if (workerGiu) {
    return (
      <BlockRetry endpoint="/api/home/kpi">
        <div className="grid gap-4 lg:grid-cols-2">
          <CardSkeleton />
          <CardSkeleton />
        </div>
      </BlockRetry>
    );
  }

  return (
    <>
      {(salute || kpi) && (
        <div className="grid gap-4 lg:grid-cols-2 lg:items-stretch">
          {salute && <SaluteCard salute={salute} />}
          {kpi && <KpiBlock kpi={kpi} />}
        </div>
      )}

      {vuotoReale && (
        <Card>
          <CardContent className="py-16 text-center">
            <Receipt className="mx-auto size-12 text-muted-foreground/40" />
            <p className="mt-4 text-base font-medium">Nessuna fattura registrata</p>
            <p className="text-sm text-muted-foreground mt-1">
              Carica le tue prime fatture dalla sezione Upload per iniziare.
            </p>
          </CardContent>
        </Card>
      )}
    </>
  );
}

// La chat compare solo se abilitata e con limite > 0 (piani free = 0). Caricata
// nel suo Suspense per non ritardare il resto.
async function ChatBlock() {
  const config = await fetchConfig();
  const enabled = (config?.chat_ai_enabled ?? true) && (config?.chat_limite_giorno ?? 0) > 0;
  if (!enabled) return null;
  return (
    <ChatWidget
      limiteGiorno={config?.chat_limite_giorno ?? 0}
      domandeOggiIniziali={config?.chat_domande_oggi ?? 0}
    />
  );
}

export default async function DashboardPage() {
  return (
    <>
      <HomeAutoRefresh />
      <div className="space-y-8">
        <Suspense fallback={null}>
          <ConfigBlock />
        </Suspense>

        <Suspense fallback={<div className="h-40 animate-pulse rounded-2xl border bg-muted/40" />}>
          <BriefingBlock />
        </Suspense>

        <Suspense fallback={null}>
          <NotificheBlock />
        </Suspense>

        {/* Coda fatture multi-sede da assegnare: si auto-nasconde se vuota o
            account mono-sede. Posto naturale = qui, con le notifiche, perche'
            e' un avviso che richiede un'azione del cliente (scegliere la sede). */}
        <CodaDaAssegnare />

        <Suspense fallback={<div className="grid gap-4 lg:grid-cols-2"><CardSkeleton /><CardSkeleton /></div>}>
          <KpiSaluteBlock />
        </Suspense>
      </div>

      <Suspense fallback={null}>
        <ChatBlock />
      </Suspense>
    </>
  );
}
