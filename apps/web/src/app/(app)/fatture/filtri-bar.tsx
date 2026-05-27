"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

type Props = {
  tab: string;
  dataDa?: string;
  dataA?: string;
  fornitore?: string;
  categoria?: string;
  needsReview?: boolean;
  categorie: string[];
};

const TABS = [
  { key: "dettaglio", label: "Dettaglio Articoli" },
  { key: "categorie", label: "Categorie" },
  { key: "fornitori", label: "Fornitori" },
];

export function FiltriBar({
  tab,
  dataDa,
  dataA,
  fornitore,
  categoria,
  needsReview,
  categorie,
}: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();

  const navigate = useCallback(
    (updates: Record<string, string | undefined>) => {
      const params = new URLSearchParams(sp.toString());
      for (const [k, v] of Object.entries(updates)) {
        if (v === undefined || v === "") params.delete(k);
        else params.set(k, v);
      }
      params.delete("page");
      router.push(`${pathname}?${params.toString()}`);
    },
    [router, pathname, sp]
  );

  return (
    <div className="space-y-4">
      {/* Tab switcher */}
      <div className="flex gap-2 border-b border-border pb-0">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => navigate({ tab: t.key })}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === t.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Filtri (solo per tab dettaglio) */}
      {tab === "dettaglio" && (
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Da</label>
            <Input
              type="date"
              className="w-36 h-8 text-sm"
              defaultValue={dataDa ?? ""}
              onChange={(e) => navigate({ data_da: e.target.value || undefined })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">A</label>
            <Input
              type="date"
              className="w-36 h-8 text-sm"
              defaultValue={dataA ?? ""}
              onChange={(e) => navigate({ data_a: e.target.value || undefined })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Fornitore</label>
            <Input
              type="text"
              placeholder="Cerca..."
              className="w-44 h-8 text-sm"
              defaultValue={fornitore ?? ""}
              onBlur={(e) => navigate({ fornitore: e.target.value || undefined })}
              onKeyDown={(e) => {
                if (e.key === "Enter") navigate({ fornitore: (e.target as HTMLInputElement).value || undefined });
              }}
            />
          </div>
          {categorie.length > 0 && (
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Categoria</label>
              <select
                value={categoria ?? ""}
                onChange={(e) => navigate({ categoria: e.target.value === "" ? undefined : e.target.value })}
                className="h-8 w-48 rounded-md border border-input bg-background px-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="">Tutte</option>
                {categorie.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Da verificare</label>
            <Button
              size="sm"
              variant={needsReview ? "default" : "outline"}
              className="h-8"
              onClick={() => navigate({ needs_review: needsReview ? undefined : "true" })}
            >
              {needsReview ? "Solo da verificare" : "Tutte"}
            </Button>
          </div>
        </div>
      )}

      {/* Filtri periodo per pivot */}
      {(tab === "categorie" || tab === "fornitori") && (
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Da</label>
            <Input
              type="date"
              className="w-36 h-8 text-sm"
              defaultValue={dataDa ?? ""}
              onChange={(e) => navigate({ data_da: e.target.value || undefined })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">A</label>
            <Input
              type="date"
              className="w-36 h-8 text-sm"
              defaultValue={dataA ?? ""}
              onChange={(e) => navigate({ data_a: e.target.value || undefined })}
            />
          </div>
        </div>
      )}
    </div>
  );
}
