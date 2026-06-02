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

export default async function DashboardPage() {
  const [stats, briefing, kpi, salute, config, notifiche] = await Promise.all([
    fetchDashboardStats(),
    fetchBriefing(),
    fetchKpi(),
    fetchSalute(),
    fetchConfig(),
    fetchNotifiche(),
  ]);

  const notificheCount = notifiche?.unread ?? 0;

  const isEmpty = !stats || stats.kpi.righe_totali === 0;

  return (
    <>
    <div className="space-y-8">
      {config && (
        <div className="flex justify-end">
          <ConfigAssistente config={config} />
        </div>
      )}

      {briefing ? (
        <HomeBriefing briefing={briefing} notificheCount={notificheCount} />
      ) : (
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Il riepilogo della tua gestione — aggiornato in tempo reale
          </p>
        </div>
      )}

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
    </div>

    {(config?.chat_ai_enabled ?? true) && (config?.chat_limite_giorno ?? 0) > 0 && <ChatWidget />}
    </>
  );
}
