import { Suspense } from "react";
import dynamic from "next/dynamic";
import { cookies } from "next/headers";
import { PageHeader } from "@/components/ui/page-header";
import { requirePaginaConTab } from "@/lib/page-guard";
import { oggiARoma } from "@/lib/oggi-roma";
import { SESSION_COOKIE, getCurrentUser } from "@/lib/auth";
import { TriggerHint } from "@/components/trigger-hint";
import { triggerAbilitati, valutaTrigger } from "@/lib/trigger-servizi";
import { TabsSwitcher } from "./tabs-switcher";
import { FiltriPeriodo } from "./filtri-periodo";
import { KpiBar, type KpiData } from "./kpi-bar";
import { calcolaPeriodo, type PeriodoPreset } from "./periodi";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";
import { kpiValutabiliPerTrigger } from "@/lib/esito-caricamento";

// dynamic(): i 3 tab importano recharts. Solo la tab attiva monta il suo
// componente, ma senza dynamic() il bundle della pagina includeva comunque
// tutti e 3 (e quindi recharts) a prescindere da quale fosse selezionata.
// Niente ssr:false: in un Server Component non e' consentito da Next.
const CalcoloTab = dynamic(() => import("./calcolo-tab").then((m) => m.CalcoloTab), {
  loading: () => <div className="h-40 animate-pulse rounded-lg bg-muted/40" />,
});
const CopertiTab = dynamic(() => import("./coperti-tab").then((m) => m.CopertiTab), {
  loading: () => <div className="h-40 animate-pulse rounded-lg bg-muted/40" />,
});
const AnalisiTab = dynamic(() => import("./analisi-tab").then((m) => m.AnalisiTab), {
  loading: () => <div className="h-40 animate-pulse rounded-lg bg-muted/40" />,
});

type SearchParams = {
  tab?: string;
  preset?: string;
  data_da?: string;
  data_a?: string;
  anno?: string;
  mese?: string;
};

function resolvePeriodo(sp: SearchParams): {
  data_da: string;
  data_a: string;
  preset: PeriodoPreset;
  mese?: string;
} {
  const preset = (sp.preset ?? "anno_corrente") as PeriodoPreset;
  if ((preset === "personalizzato" || preset === "mese_specifico") && sp.data_da && sp.data_a) {
    return { data_da: sp.data_da, data_a: sp.data_a, preset, mese: sp.mese };
  }
  // oggiARoma(): questa funzione gira in un Server Component, e Vercel e' in UTC.
  // Senza, fra mezzanotte e le 02:00 italiane il preset chiude sul giorno prima —
  // il 1° del mese significa mostrare il mese precedente per intero.
  const calc = calcolaPeriodo(preset, oggiARoma());
  return { data_da: calc.data_da, data_a: calc.data_a, preset };
}

async function fetchKpiData(data_da: string, data_a: string): Promise<KpiData> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  // `zeri` e' la forma del dato, non un risultato: serve a garantire che ogni
  // campo numerico sia definito anche su risposta parziale del worker.
  const zeri: KpiData = {
    fatturato_lordo: 0, fatturato_netto: 0, costi_fb: 0, primo_margine: 0,
    spese_generali: 0, costo_personale: 0, mol: 0,
    food_cost_perc: 0, primo_margine_perc: 0, spese_perc: 0,
    personale_perc: 0, mol_perc: 0,
    delta_lordo_pct: null, delta_fb_pct: null, delta_margine_pct: null,
    delta_spese_pct: null, delta_personale_pct: null, delta_mol_pct: null,
    confronto_label: "periodo prec.",
  };
  // Il ripiego dichiara di esserlo. Prima era identico a un periodo davvero
  // vuoto: stessi sei zeri, nessun modo per il cliente di distinguerli.
  const nonDisponibile: KpiData = { ...zeri, non_disponibile: true };
  if (!token) return nonDisponibile;

  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const qs = new URLSearchParams({ data_da, data_a });
    const res = await fetch(`${WORKER_URL}/api/margini/kpi?${qs}`, {
      headers: h,
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return nonDisponibile;
    const raw = await res.json();
    // Merge col fallback: garantisce che ogni campo numerico sia sempre definito
    // anche se il worker ritorna un oggetto parziale.
    return { ...zeri, ...raw } as KpiData;
  } catch {
    return nonDisponibile;
  }
}

export default async function MarginiPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const { tab, disponibili } = await requirePaginaConTab(
    "margini", "margini", sp.tab, "/margini",
    "tab", {
      preset: sp.preset, data_da: sp.data_da, data_a: sp.data_a,
      mese: sp.mese, anno: sp.anno,
    },
  );
  const { data_da, data_a, preset, mese } = resolvePeriodo(sp);

  const [kpi, user] = await Promise.all([fetchKpiData(data_da, data_a), getCurrentUser()]);

  // Trigger contestuale Consulenza: scatta su MOL negativo o food cost oltre
  // soglia (dati gia' nel KPI di pagina, nessuna query nuova). Mostrato solo se
  // il toggle cliente e' attivo e c'e' un segnale reale.
  const triggerOn = triggerAbilitati(user?.pagine_abilitate);
  // Su KPI non disponibili i segnali restano ASSENTI, non zero: il contratto di
  // trigger-servizi dice "un campo assente = non lo so, il trigger non scatta".
  // Passare `molNegativo: false` e `foodCostPct: 0` sarebbe dichiarare di sapere
  // che il MOL e' sano — un giudizio su numeri che non sono arrivati.
  const trigger = triggerOn && kpiValutabiliPerTrigger(kpi)
    ? valutaTrigger("margini", {
        foodCostPct: kpi.food_cost_perc,
        molNegativo: kpi.mol < 0,
      })
    : null;

  return (
    <div className="space-y-5">
      <PageHeader
        icon="bar-chart"
        title="Ricavi e Margini"
        hint={
          user?.tipo_attivita === "retail"
            ? "La salute economica del tuo negozio"
            : "La salute economica del tuo locale"
        }
      />

      <Suspense>
        <FiltriPeriodo presetCorrente={preset} dataDa={data_da} dataA={data_a} meseSelezionato={mese} />
      </Suspense>

      <KpiBar kpi={kpi} />

      <div className="pb-4" />

      <Suspense>
        <TabsSwitcher active={tab} disponibili={disponibili} />
      </Suspense>

      <div>
        {tab === "calcolo" && (
          <ErrorBoundary>
            <Suspense>
              <CalcoloTab dataDa={data_da} dataA={data_a} settore={user?.tipo_attivita} />
            </Suspense>
          </ErrorBoundary>
        )}
        {tab === "coperti" && (
          <ErrorBoundary>
            <Suspense>
              <CopertiTab dataDa={data_da} dataA={data_a} />
            </Suspense>
          </ErrorBoundary>
        )}
        {tab === "analisi" && (
          <ErrorBoundary>
            <Suspense>
              <AnalisiTab dataDa={data_da} dataA={data_a} />
            </Suspense>
          </ErrorBoundary>
        )}
      </div>

      <TriggerHint trigger={trigger} />
    </div>
  );
}
