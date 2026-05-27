import { Suspense } from "react";
import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";
import { TabsSwitcher } from "./tabs-switcher";
import { FiltriPeriodo } from "./filtri-periodo";
import { KpiBar, type KpiData } from "./kpi-bar";
import { RicaviTab } from "./ricavi-tab";
import { CalcoloTab } from "./calcolo-tab";
import { AnalisiTab } from "./analisi-tab";
import { calcolaPeriodo, type PeriodoPreset } from "./periodi";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

type SearchParams = {
  tab?: string;
  preset?: string;
  data_da?: string;
  data_a?: string;
  anno?: string;
};

function resolvePeriodo(sp: SearchParams): {
  data_da: string;
  data_a: string;
  preset: PeriodoPreset;
} {
  const preset = (sp.preset ?? "anno_corrente") as PeriodoPreset;
  if (preset === "personalizzato" && sp.data_da && sp.data_a) {
    return { data_da: sp.data_da, data_a: sp.data_a, preset };
  }
  const calc = calcolaPeriodo(preset);
  return { data_da: calc.data_da, data_a: calc.data_a, preset };
}

async function fetchKpiData(data_da: string, data_a: string): Promise<KpiData> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  const fallback: KpiData = {
    fatturato_netto: 0, ricavi_iva10: 0, ricavi_iva22: 0, altri_ricavi: 0,
    giorni_con_dati: 0, giorni_periodo: 0, media_giornaliera: 0,
  };
  if (!token) return fallback;

  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const qs = new URLSearchParams({ data_da, data_a });
    const res = await fetch(`${WORKER_URL}/api/ricavi/giornalieri?${qs}`, {
      headers: h,
      cache: "no-store",
    });
    if (!res.ok) return fallback;
    const data = await res.json();

    const giorniPeriodo = Math.round(
      (new Date(data_a).getTime() - new Date(data_da).getTime()) / 86400000,
    ) + 1;

    return {
      fatturato_netto: data.totale_netto ?? 0,
      ricavi_iva10: data.totale_iva10 ?? 0,
      ricavi_iva22: data.totale_iva22 ?? 0,
      altri_ricavi: data.totale_altri ?? 0,
      giorni_con_dati: data.giorni_con_dati ?? 0,
      giorni_periodo: Math.max(1, giorniPeriodo),
      media_giornaliera: data.giorni_con_dati > 0
        ? (data.totale_netto ?? 0) / data.giorni_con_dati
        : 0,
    };
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
  const tab = sp.tab ?? "ricavi";
  const { data_da, data_a, preset } = resolvePeriodo(sp);

  const anno = parseInt(
    sp.anno ?? String(parseInt(data_da.slice(0, 4), 10)),
    10,
  );

  const kpi = await fetchKpiData(data_da, data_a);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Marginalità</h1>
      </div>

      <Suspense>
        <FiltriPeriodo presetCorrente={preset} dataDa={data_da} dataA={data_a} />
      </Suspense>

      <KpiBar kpi={kpi} />

      <Suspense>
        <TabsSwitcher active={tab} />
      </Suspense>

      <div>
        {tab === "ricavi" && <RicaviTab dataDa={data_da} dataA={data_a} />}
        {tab === "calcolo" && (
          <Suspense>
            <CalcoloTab dataDa={data_da} dataA={data_a} />
          </Suspense>
        )}
        {tab === "analisi" && (
          <Suspense>
            <AnalisiTab dataDa={data_da} dataA={data_a} />
          </Suspense>
        )}
      </div>
    </div>
  );
}
