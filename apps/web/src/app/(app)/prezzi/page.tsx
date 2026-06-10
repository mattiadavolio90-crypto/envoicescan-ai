import { Suspense } from "react";
import { cookies } from "next/headers";
import { PageHeader } from "@/components/ui/page-header";
import { requirePagina } from "@/lib/page-guard";
import { SESSION_COOKIE, getCurrentUser } from "@/lib/auth";
import { contaTopicAttivo } from "@/lib/notifiche";
import { TriggerHint } from "@/components/trigger-hint";
import { triggerAbilitati, valutaTrigger } from "@/lib/trigger-servizi";
import { TabsSwitcher } from "./tabs-switcher";
import { VariazioniTab } from "./variazioni-tab";
import { ScontiTab } from "./sconti-tab";
import { NcTab } from "./nc-tab";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

async function fetchSogliaAlert(): Promise<number> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return 5;
  try {
    const h: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/prezzi/soglia-alert`, {
      headers: h,
      cache: "no-store",
    });
    if (!res.ok) return 5;
    const data = await res.json();
    return data.soglia ?? 5;
  } catch {
    return 5;
  }
}

export default async function PrezziPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  await requirePagina("prezzi");
  const sp = await searchParams;
  const tab = sp.tab ?? "variazioni";
  const [soglia, user, alertPrezzi] = await Promise.all([
    fetchSogliaAlert(),
    getCurrentUser(),
    contaTopicAttivo("price_alert"),
  ]);

  // Trigger contestuale Analisi su Richiesta: scatta se ci sono prezzi in
  // aumento (topic price_alert gia' calcolato dal worker, nessuna query nuova).
  const trigger = triggerAbilitati(user?.pagine_abilitate)
    ? valutaTrigger("prezzi", { alertPrezziAttivi: alertPrezzi })
    : null;

  return (
    <div className="space-y-4">
      <PageHeader
        icon="search"
        title="Controllo Prezzi"
        hint="Variazioni e anomalie sui tuoi fornitori"
      />
      <Suspense>
        <TabsSwitcher active={tab} />
      </Suspense>
      <div className="mt-2">
        {tab === "variazioni" && (
          <Suspense>
            <VariazioniTab initialSoglia={soglia} />
          </Suspense>
        )}
        {tab === "sconti" && (
          <Suspense>
            <ScontiTab />
          </Suspense>
        )}
        {tab === "nc" && (
          <Suspense>
            <NcTab />
          </Suspense>
        )}
      </div>

      <TriggerHint trigger={trigger} />
    </div>
  );
}
