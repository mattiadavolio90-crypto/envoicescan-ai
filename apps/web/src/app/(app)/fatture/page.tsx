import Link from "next/link";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchFatture, fetchPivot, fetchCategorie } from "@/lib/fatture";
import { FattureTable } from "./fatture-table";
import { PivotTable } from "./pivot-table";
import { FiltriBar } from "./filtri-bar";

type SearchParams = {
  tab?: string;
  data_da?: string;
  data_a?: string;
  fornitore?: string;
  categoria?: string;
  needs_review?: string;
  page?: string;
};

export default async function FatturePage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const tab = sp.tab ?? "dettaglio";
  const page = parseInt(sp.page ?? "1", 10);
  const dataDa = sp.data_da;
  const dataA = sp.data_a;

  const [fattureData, categorie] = await Promise.all([
    tab === "dettaglio"
      ? fetchFatture({
          data_da: dataDa,
          data_a: dataA,
          fornitore: sp.fornitore,
          categoria: sp.categoria,
          needs_review: sp.needs_review === "true" ? true : undefined,
          page,
          page_size: 50,
        })
      : null,
    fetchCategorie(),
  ]);

  const pivotData =
    tab === "categorie" || tab === "fornitori"
      ? await fetchPivot(tab === "fornitori" ? "fornitore" : "categoria", dataDa, dataA)
      : null;

  const totalRighe = fattureData?.total ?? 0;
  const totalPages = Math.ceil(totalRighe / 50);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Fatture</h1>
          {tab === "dettaglio" && totalRighe > 0 && (
            <p className="text-sm text-muted-foreground mt-1">{totalRighe.toLocaleString("it-IT")} righe</p>
          )}
        </div>
        <Button size="sm" render={<Link href="/upload" />}>
          <Upload className="size-4" />
          Carica
        </Button>
      </div>

      {/* Filtri + Tab */}
      <FiltriBar
        tab={tab}
        dataDa={dataDa}
        dataA={dataA}
        fornitore={sp.fornitore}
        categoria={sp.categoria}
        needsReview={sp.needs_review === "true"}
        categorie={categorie}
      />

      {/* Contenuto tab */}
      {tab === "dettaglio" && (
        <FattureTable
          righe={fattureData?.righe ?? []}
          total={totalRighe}
          page={page}
          totalPages={totalPages}
          categorie={categorie}
        />
      )}

      {(tab === "categorie" || tab === "fornitori") && (
        <PivotTable
          rows={pivotData?.rows ?? []}
          mesi={pivotData?.mesi_disponibili ?? []}
          dimensioneLabel={tab === "categorie" ? "Categoria" : "Fornitore"}
        />
      )}
    </div>
  );
}
