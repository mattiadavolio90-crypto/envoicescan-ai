import { Suspense } from "react";
import dynamic from "next/dynamic";
import { cookies } from "next/headers";
import { PageHeader } from "@/components/ui/page-header";
import { requirePaginaConTab } from "@/lib/page-guard";
import { SESSION_COOKIE, getCurrentUser } from "@/lib/auth";
import { contaTopicAttivo } from "@/lib/notifiche";
import { TriggerHint } from "@/components/trigger-hint";
import { triggerAbilitati, valutaTrigger } from "@/lib/trigger-servizi";
import { TabsSwitcher } from "./tabs-switcher";
import { ScontiTab } from "./sconti-tab";
import { NcTab } from "./nc-tab";
import { ScoreTab } from "./score-tab";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

// dynamic(): VariazioniTab importa recharts (libreria pesante) solo per il tab
// omonimo. Cosi' il chunk recharts non entra nel bundle iniziale di /prezzi
// quando l'utente apre sconti/nc/score, che non lo usano.
// Niente ssr:false: in un Server Component non e' consentito da Next.
const VariazioniTab = dynamic(() => import("./variazioni-tab").then((m) => m.VariazioniTab), {
  loading: () => <div className="h-40 animate-pulse rounded-lg bg-muted/40" />,
});

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
  const sp = await searchParams;
  const { tab, disponibili } = await requirePaginaConTab("prezzi", "prezzi", sp.tab, "/prezzi");
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
        title="Osservatorio"
        hint="Variazioni e anomalie sui tuoi fornitori"
        subtitle="Monitora l'andamento dei prezzi e la coerenza dei fornitori nel tempo."
      />
      <Suspense>
        <TabsSwitcher active={tab} disponibili={disponibili} />
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
        {tab === "score" && (
          <Suspense>
            <ScoreTab />
          </Suspense>
        )}
      </div>

      <TriggerHint trigger={trigger} />
    </div>
  );
}
