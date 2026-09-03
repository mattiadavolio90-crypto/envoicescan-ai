import { Suspense } from "react";
import { fetchBriefing, fetchSalute, fetchConfig, fetchKpi } from "@/lib/home";
import { fetchNotifiche } from "@/lib/notifiche";
import { chatVisibile, statoBlocchi } from "@/lib/home-kpi";
import { statoCardDaClassificare, vociSenzaClassificate } from "@/lib/home-da-classificare";
import { DaClassificareCard } from "./da-classificare-card";
import { HomeBriefing } from "./home-briefing";
import { NotificheWidget } from "./notifiche-widget";
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
  //   - dati ricevuti ma kpi.has_data === false => cliente davvero senza fatture
  //     per il mese/periodo mostrato. Indipendente da salute: un account puo'
  //     avere un indice di salute (calcolato su altre componenti) e ZERO dati di
  //     margine allo stesso tempo (es. cliente nuovo appena partito) — prima
  //     questo caso lasciava un buco silenzioso a destra, perche' KpiBlock si
  //     autonullifica su has_data=false (component-level) MA vuotoReale
  //     richiedeva anche !salute per scattare, quindi non mostrava mai il
  //     messaggio quando salute era presente. Ora i due stati sono indipendenti.
  const stato = statoBlocchi(kpi, salute);
  const kpiVuoto = stato === "vuoto";

  if (stato === "worker-giu") {
    return (
      <BlockRetry endpoint="/api/home/kpi">
        <div className="grid gap-4 lg:grid-cols-2">
          <CardSkeleton />
          <CardSkeleton />
        </div>
      </BlockRetry>
    );
  }

  // Promozione (Fase 4bis, decisione Mattia 1/9): la voce "Righe classificate"
  // esce dall'elenco della card Salute — il dato vive nella card grande sotto la
  // griglia. Solo qui sul desktop: il mobile non ha la card grande e tiene la voce.
  const saluteDesktop = salute
    ? { ...salute, voci: vociSenzaClassificate(salute.voci) }
    : null;

  return (
    <div className="grid gap-4 lg:grid-cols-2 lg:items-stretch">
      {saluteDesktop && <SaluteCard salute={saluteDesktop} />}
      {kpi && !kpiVuoto && <KpiBlock kpi={kpi} />}
      {kpiVuoto && (
        <Card>
          <CardContent className="flex h-full flex-col items-center justify-center py-16 text-center">
            <Receipt className="mx-auto size-12 text-muted-foreground/40" />
            <p className="mt-4 text-base font-medium">Nessun dato di margine per questo mese</p>
            <p className="text-sm text-muted-foreground mt-1">
              Carica le fatture e inserisci il fatturato per vedere qui food cost e MOL.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// Card grande "Righe da classificare" (Fase 4bis): a larghezza piena, subito
// sotto la griglia Salute+KPI — dopo i numeri a cui si riferisce, prima del
// resto. fetchSalute è cache(): stesso round-trip di KpiSaluteBlock, non uno in
// più. Con worker giù o dato assente: stato di errore dentro BlockRetry (che
// ripinga e ri-renderizza da solo), MAI il verde.
async function DaClassificareBlock() {
  const salute = await fetchSalute();
  const card = statoCardDaClassificare(salute);
  if (card.stato === "errore") {
    return (
      <BlockRetry endpoint="/api/home/salute">
        <DaClassificareCard card={card} />
      </BlockRetry>
    );
  }
  return <DaClassificareCard card={card} />;
}

// La chat compare solo se abilitata e con limite > 0 (piani free = 0). Caricata
// nel suo Suspense per non ritardare il resto.
async function ChatBlock() {
  const config = await fetchConfig();
  if (!chatVisibile(config)) return null;
  return (
    <ChatWidget
      limiteGiorno={config?.chat_limite_giorno ?? 0}
      domandeOggiIniziali={config?.chat_domande_oggi ?? 0}
    />
  );
}

export default async function DashboardPage() {
  // /dashboard è la Home del PUNTO VENDITA (sede attiva), anche per i clienti
  // catena: ci si arriva scendendo in un PV dalla plancia /catena. L'atterraggio
  // dei clienti catena su /catena avviene al login (vista di gruppo = il loro
  // punto di vista naturale), non con un redirect qui — che altrimenti renderebbe
  // la Home del PV irraggiungibile nel drill-down.
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

        {/* La coda fatture "da assegnare" NON vive più qui: è un fenomeno di gruppo
            (catene same-P.IVA) e si gestisce solo in modalità catena, dove non si
            duplica per ogni PV. Vedi CodaDaAssegnare contesto="catena" in sintesi-catena. */}

        <Suspense fallback={<div className="grid gap-4 lg:grid-cols-2"><CardSkeleton /><CardSkeleton /></div>}>
          <KpiSaluteBlock />
        </Suspense>

        <Suspense fallback={<div className="h-24 animate-pulse rounded-2xl border bg-muted/40" />}>
          <DaClassificareBlock />
        </Suspense>

        {/* Spazio riservato in fondo: il FAB "Chiedi a ONEFLUX" (fixed bottom-right)
            altrimenti resta sovrapposto all'ultimo contenuto durante lo scroll. */}
        <div aria-hidden className="h-20" />
      </div>

      <Suspense fallback={null}>
        <ChatBlock />
      </Suspense>
    </>
  );
}
