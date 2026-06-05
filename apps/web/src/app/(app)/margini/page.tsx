import { Suspense } from "react";
import { cookies } from "next/headers";
import { PageHeader } from "@/components/ui/page-header";
import { SESSION_COOKIE } from "@/lib/auth";
import { TabsSwitcher } from "./tabs-switcher";
import { FiltriPeriodo } from "./filtri-periodo";
import { KpiBar, type KpiData } from "./kpi-bar";
import { CalcoloTab } from "./calcolo-tab";
import { AnalisiTab } from "./analisi-tab";
import { calcolaPeriodo, type PeriodoPreset } from "./periodi";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

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
  const calc = calcolaPeriodo(preset);
  return { data_da: calc.data_da, data_a: calc.data_a, preset };
}

async function fetchKpiData(data_da: string, data_a: string): Promise<KpiData> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  const fallback: KpiData = {
    fatturato_lordo: 0, fatturato_netto: 0, costi_fb: 0, primo_margine: 0,
    spese_generali: 0, costo_personale: 0, mol: 0,
    food_cost_perc: 0, primo_margine_perc: 0, spese_perc: 0,
    personale_perc: 0, mol_perc: 0,
    delta_lordo_pct: null, delta_fb_pct: null, delta_margine_pct: null,
    delta_spese_pct: null, delta_personale_pct: null, delta_mol_pct: null,
    confronto_label: "periodo prec.",
  };
  if (!token) return fallback;

  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const qs = new URLSearchParams({ data_da, data_a });
    const res = await fetch(`${WORKER_URL}/api/margini/kpi?${qs}`, {
      headers: h,
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return fallback;
    const raw = await res.json();
    // Merge col fallback: garantisce che ogni campo numerico sia sempre definito
    // anche se il worker ritorna un oggetto parziale.
    return { ...fallback, ...raw } as KpiData;
  } catch {
    return fallback;
  }
}

export default async function MarginiPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const tab = sp.tab ?? "calcolo";
  const { data_da, data_a, preset, mese } = resolvePeriodo(sp);

  const kpi = await fetchKpiData(data_da, data_a);

  return (
    <div className="space-y-5">
      <PageHeader
        icon="bar-chart"
        title="Ricavi e Margini"
        hint="La salute economica del tuo locale"
      />

      <Suspense>
        <FiltriPeriodo presetCorrente={preset} dataDa={data_da} dataA={data_a} meseSelezionato={mese} />
      </Suspense>

      <KpiBar kpi={kpi} />

      <div className="pb-4" />

      <Suspense>
        <TabsSwitcher active={tab} />
      </Suspense>

      <div>
        {tab === "calcolo" && (
          <ErrorBoundary>
            <Suspense>
              <CalcoloTab dataDa={data_da} dataA={data_a} />
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
    </div>
  );
}
