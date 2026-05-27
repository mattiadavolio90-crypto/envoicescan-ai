import {
  fetchArticoliAggregati,
  fetchCategorie,
  fetchKpi,
  fetchMesiDisponibili,
  fetchPivot,
  type TipoProdotti,
} from "@/lib/fatture";
import { ArticoliTab } from "./articoli-tab";
import { FiltriPeriodo } from "./filtri-periodo";
import { KpiBar } from "./kpi-bar";
import { PivotTab } from "./pivot-tab";
import { TabsSwitcher } from "./tabs-switcher";
import { UploadModal } from "./upload-modal";
import { calcolaPeriodo, type PeriodoPreset } from "./periodi";

type SearchParams = {
  tab?: string;
  preset?: string;
  data_da?: string;
  data_a?: string;
  mese?: string;
  tipo?: string;
  search?: string;
  fornitore?: string;
  cat?: string;
  nuovi?: string;
  verifica?: string;
};

function resolvePeriodo(sp: SearchParams): {
  data_da: string;
  data_a: string;
  preset: PeriodoPreset;
  mese?: string;
} {
  const preset = (sp.preset ?? "anno_corrente") as PeriodoPreset;
  if (preset === "personalizzato" && sp.data_da && sp.data_a) {
    return { data_da: sp.data_da, data_a: sp.data_a, preset };
  }
  if (preset === "mese_specifico" && sp.data_da && sp.data_a) {
    return { data_da: sp.data_da, data_a: sp.data_a, preset, mese: sp.mese };
  }
  const validPresets: PeriodoPreset[] = [
    "mese_corrente",
    "trimestre_corrente",
    "semestre_corrente",
    "anno_corrente",
  ];
  const safe = validPresets.includes(preset) ? preset : "anno_corrente";
  const calc = calcolaPeriodo(safe);
  return { data_da: calc.data_da, data_a: calc.data_a, preset: safe };
}

function normalizeTipo(t?: string): TipoProdotti | undefined {
  if (t === "food_beverage" || t === "spese_generali") return t;
  return undefined;
}

export default async function AnalisiFatturePage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const tab = sp.tab ?? "articoli";
  const { data_da, data_a, preset, mese } = resolvePeriodo(sp);
  const tipoProdotti = normalizeTipo(sp.tipo);
  const soloNuovi = sp.nuovi === "1";
  const soloVerifica = sp.verifica === "1";

  // Carico in parallelo i dati base sempre necessari
  const [kpi, mesi, categorieRes] = await Promise.all([
    fetchKpi(data_da, data_a, tipoProdotti),
    fetchMesiDisponibili(),
    fetchCategorie(),
  ]);

  // Tab Articoli: filtri categoria/fornitore/search/nuovi/verifica gestiti
  // CLIENT-SIDE. Server fetcha solo per periodo + tipo prodotti.
  const [articoliRes, pivotCategorie, pivotFornitori] = await Promise.all([
    tab === "articoli"
      ? fetchArticoliAggregati({
          data_da,
          data_a,
          tipo_prodotti: tipoProdotti,
        })
      : Promise.resolve(null),
    tab === "categorie"
      ? fetchPivot("categoria", { data_da, data_a, tipo_prodotti: tipoProdotti })
      : Promise.resolve(null),
    tab === "fornitori"
      ? fetchPivot("fornitore", { data_da, data_a, tipo_prodotti: tipoProdotti })
      : Promise.resolve(null),
  ]);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Analisi Fatture</h1>
        <UploadModal />
      </div>

      {/* Filtri temporali */}
      <FiltriPeriodo
        presetCorrente={preset}
        dataDa={data_da}
        dataA={data_a}
        meseSelezionato={mese}
        mesiDisponibili={mesi}
      />

      {/* KPI bar */}
      <KpiBar kpi={kpi} />

      {/* Tabs */}
      <TabsSwitcher active={tab} />

      {/* Contenuto tab */}
      {tab === "articoli" && (
        <ArticoliTab
          articoli={articoliRes?.articoli ?? []}
          categorie={categorieRes.categorie}
          soloNuovi={soloNuovi}
          soloVerifica={soloVerifica}
          filtri={{ data_da, data_a, tipo_prodotti: tipoProdotti }}
        />
      )}

      {tab === "categorie" && pivotCategorie && (
        <PivotTab
          pivot={pivotCategorie}
          dimensione="categoria"
          filtri={{ data_da, data_a, tipo_prodotti: tipoProdotti }}
        />
      )}

      {tab === "fornitori" && pivotFornitori && (
        <PivotTab
          pivot={pivotFornitori}
          dimensione="fornitore"
          filtri={{ data_da, data_a, tipo_prodotti: tipoProdotti }}
        />
      )}
    </div>
  );
}
