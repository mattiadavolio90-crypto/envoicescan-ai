import { Suspense } from "react";
import { fetchBriefing, fetchSalute, fetchConfig, fetchKpi } from "@/lib/home";
import { fetchNotifiche } from "@/lib/notifiche";
import { chatVisibile, statoBlocchi } from "@/lib/home-kpi";
import { HomeBriefing } from "./home-briefing";
import { NotificheWidget } from "./notifiche-widget";
import { SaluteCard } from "./salute-card";
import { KpiBlock } from "./kpi-block";
import { ConfigAssistente } from "./config-assistente";
import { BlockRetry } from "./block-retry";
import { HomeAutoRefresh } from "./home-auto-refresh";
import { Card, CardContent } from "@/components/ui/card";
import { Receipt } from "lucide-react";
import { getCurrentSession, getCurrentUser } from "@/lib/auth";
import { requireHome } from "@/lib/page-guard";
import { TestataHome } from "@/components/home/testata-home";
import { ConversazioneAssistente } from "@/components/home/conversazione-assistente";
import { vistaSede } from "@/lib/home-chat";
import { costoMerceLabel } from "@/lib/categorie-spesa";

// Streaming con Suspense per blocco: ogni sezione carica i suoi dati in modo
// indipendente. Prima un unico Promise.all bloccante aspettava la chiamata piu'
// lenta (dashboard/stats su clienti con migliaia di righe, o il briefing) e, se
// quella andava in timeout, l'intera pagina rendeva il fallback (briefing/card
// "spariti"). Ora il pattern e' lo stesso della Home mobile: ogni blocco appare
// appena pronto, uno lento non affossa gli altri.

function CardSkeleton() {
  return <div className="h-56 animate-pulse rounded-2xl border bg-muted/40" />;
}

// Testata comune alle due Home (28/9/2026): nome della sede e «Configura
// assistente». «Carica fatture» sta solo in Analisi Fatture (Mattia, 28/9: la
// Home e' recap e assistenza). `getCurrentSession` e' in cache() per la
// richiesta: il nome costa zero chiamate in piu'.
async function TestataBlock() {
  const [config, sessione] = await Promise.all([fetchConfig(), getCurrentSession()]);
  const utente = sessione.status === "ok" ? sessione.user : null;
  return (
    <TestataHome
      vista="pv"
      nome={utente?.sede_attiva_nome ?? utente?.nome_ristorante}
      azioni={config && <ConfigAssistente config={config} />}
    />
  );
}

async function BriefingBlock() {
  // config e utente sono in cache() per la richiesta (li legge anche la testata):
  // la conversazione non costa chiamate in piu'.
  const [briefing, config, utente] = await Promise.all([fetchBriefing(), fetchConfig(), getCurrentUser()]);
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
  // La conversazione c'e' solo se la chat e' abilitata e con quota > 0 (i piani
  // free hanno 0): stessa regola del vecchio pulsante flottante.
  return (
    <HomeBriefing
      briefing={briefing}
      conversazione={
        chatVisibile(config) && (
          <ConversazioneAssistente
            vista={vistaSede(utente?.sede_attiva_id)}
            limiteGiorno={config?.chat_limite_giorno ?? 0}
            domandeOggiIniziali={config?.chat_domande_oggi ?? 0}
            lettoAlle={Date.now()}
            settore={utente?.tipo_attivita}
          />
        )
      }
    />
  );
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
  // NON e' gratis: il layout usa `getCurrentSession`, una entry cache() DIVERSA
  // sopra un `verifySession` non memoizzato, quindi questa e' una chiamata in
  // piu' al worker per render (stesso costo dichiarato in Fase 3 per le altre
  // pagine). Se un giorno pesa, il fix e' memoizzare `verifySession`, non
  // togliere il settore dalle pagine.
  const [kpi, salute, user] = await Promise.all([fetchKpi(), fetchSalute(), getCurrentUser()]);

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

  // La voce "Righe classificate" e' TORNATA nell'elenco (Fase 4, 9/9/2026).
  // Dall'1/9 usciva di qui perche' la promuoveva la card grande sotto la griglia:
  // eliminata quella, senza questo ripristino sul desktop sparirebbe senza
  // sostituto — il mobile la voce non l'aveva mai persa.
  return (
    // Conti a sinistra e completezza a destra, come nella Home di catena.
    <div className="grid gap-4 lg:grid-cols-2 lg:items-stretch">
      {kpi && !kpiVuoto && <KpiBlock kpi={kpi} settore={user?.tipo_attivita} />}
      {kpiVuoto && (
        <Card>
          <CardContent className="flex h-full flex-col items-center justify-center py-8 text-center">
            <Receipt className="mx-auto size-8 text-muted-foreground/40" />
            <p className="mt-3 text-sm font-medium">Nessun dato di margine per questo mese</p>
            <p className="text-sm text-muted-foreground mt-1">
              Carica le fatture e inserisci il fatturato per vedere qui{" "}
              {costoMerceLabel(user?.tipo_attivita).toLowerCase()} e MOL.
            </p>
          </CardContent>
        </Card>
      )}
      {salute && <SaluteCard salute={salute} />}
    </div>
  );
}

export default async function DashboardPage() {
  // Un sotto-utente senza la Home va alla prima pagina che ha.
  await requireHome();
  // /dashboard è la Home del PUNTO VENDITA (sede attiva), anche per i clienti
  // catena: ci si arriva scendendo in un PV dalla plancia /catena. L'atterraggio
  // dei clienti catena su /catena avviene al login (vista di gruppo = il loro
  // punto di vista naturale), non con un redirect qui — che altrimenti renderebbe
  // la Home del PV irraggiungibile nel drill-down.
  return (
    <>
      <HomeAutoRefresh />
      <div className="space-y-6">
        <Suspense fallback={<div className="h-9" />}>
          <TestataBlock />
        </Suspense>

        <Suspense fallback={<div className="h-40 animate-pulse rounded-2xl border bg-muted/40" />}>
          <BriefingBlock />
        </Suspense>

        <Suspense fallback={null}>
          <NotificheBlock />
        </Suspense>

        {/* La coda fatture "da assegnare" NON vive più qui: è un fenomeno di gruppo
            (catene same-P.IVA) e si gestisce solo in modalità catena, dove non si
            duplica per ogni PV: la scheda «Da collocare» di /catena/fatture. */}

        <Suspense fallback={<div className="grid gap-4 lg:grid-cols-2"><CardSkeleton /><CardSkeleton /></div>}>
          <KpiSaluteBlock />
        </Suspense>
      </div>
    </>
  );
}
