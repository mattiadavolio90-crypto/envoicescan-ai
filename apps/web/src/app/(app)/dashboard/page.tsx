import { Suspense } from "react";
import { fetchDashboardStats } from "@/lib/dashboard";
import { fetchBriefing, fetchSalute, fetchConfig, fetchKpi } from "@/lib/home";
import { fetchNotifiche } from "@/lib/notifiche";
import { HomeBriefing } from "./home-briefing";
import { ChatWidget } from "./chat-widget";
import { SaluteCard } from "./salute-card";
import { KpiBlock } from "./kpi-block";
import { ConfigAssistente } from "./config-assistente";
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
  const [briefing, notifiche] = await Promise.all([fetchBriefing(), fetchNotifiche()]);
  if (!briefing) {
    return (
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Il riepilogo della tua gestione — aggiornato in tempo reale
        </p>
      </div>
    );
  }
  return <HomeBriefing briefing={briefing} notificheCount={notifiche?.unread ?? 0} />;
}

async function KpiSaluteBlock() {
  const [kpi, salute, stats] = await Promise.all([
    fetchKpi(),
    fetchSalute(),
    fetchDashboardStats(),
  ]);

  const isEmpty = !stats || stats.kpi.righe_totali === 0;

  return (
    <>
      {(salute || kpi) && (
        <div className="grid gap-4 lg:grid-cols-2 lg:items-stretch">
          {salute && <SaluteCard salute={salute} />}
          {kpi && <KpiBlock kpi={kpi} />}
        </div>
      )}

      {isEmpty && !salute && (
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
  return <ChatWidget />;
}

export default function DashboardPage() {
  return (
    <>
      <div className="space-y-8">
        <Suspense fallback={null}>
          <ConfigBlock />
        </Suspense>

        <Suspense fallback={<div className="h-40 animate-pulse rounded-2xl border bg-muted/40" />}>
          <BriefingBlock />
        </Suspense>

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
