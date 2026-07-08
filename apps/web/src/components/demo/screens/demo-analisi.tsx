"use client";

import { ArrowDown, ArrowUp, Calendar, ChevronRight, Search, Settings2, Upload } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { KpiBar } from "@/app/(app)/analisi-fatture/kpi-bar";
import { categoriaIcon } from "@/app/(app)/analisi-fatture/periodi";
import { formatData, formatEuro } from "@/lib/format";
import type { KpiResponse } from "@/lib/fatture";
import { demoAnalisiKpi, demoArticoli } from "@/lib/demo-data";
import { DemoAnchor } from "../demo-anchor";

// Analisi Fatture del Demo Tour: replica 1:1 della pagina reale.
// Testata (PageHeader + azione Upload) → FiltriPeriodo (chip periodo) → KpiBar
// reale (4 KPI) → TabsSwitcher (Articoli/Categorie/Fornitori) → tabella articoli
// con le categorie e le icone VERE dell'app. Tutti gli elementi sono inerti
// (la navigazione nella demo la guida il tour), ma visivamente identici.

const kpiReale: KpiResponse = {
  totale: demoAnalisiKpi.totale,
  num_righe: demoAnalisiKpi.num_righe,
  num_prodotti: demoAnalisiKpi.num_prodotti,
  media_mensile: demoAnalisiKpi.totale,
  delta_totale_pct: null,
  delta_righe_pct: null,
  delta_prodotti_pct: null,
  delta_media_pct: null,
};

const chipBase =
  "px-3 py-1.5 text-xs font-medium rounded-full border inline-flex items-center gap-1.5";
const chipActive = "bg-primary text-primary-foreground border-primary";
const chipIdle = "bg-background border-input";

const TABS = [
  { key: "articoli", label: "Articoli" },
  { key: "categorie", label: "Categorie" },
  { key: "fornitori", label: "Fornitori" },
];

export function DemoAnalisi() {
  return (
    <div className="space-y-5">
      <PageHeader
        icon="file"
        title="Analisi Fatture"
        hint="Cosa hai comprato, da chi e quanto incide"
        actions={
          <span className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
            <Upload className="size-4" />
            Carica fatture
          </span>
        }
      />

      {/* Filtri periodo (chip inerti, come FiltriPeriodo): mese di maggio, così
          spesa totale (25.600 €) e 24 fatture combaciano con Margini e briefing. */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className={`${chipBase} ${chipIdle}`}>Anno in corso</span>
        <span className={`${chipBase} ${chipActive}`}>
          <Calendar className="size-3" />
          Seleziona mese
        </span>
        <span className={`${chipBase} ${chipIdle}`}>
          <Settings2 className="size-3" />
          Personalizzato
        </span>
        <span className="ml-2 text-xs font-medium text-sky-500 dark:text-sky-400">
          01/05/26 → 31/05/26
        </span>
      </div>

      <KpiBar kpi={kpiReale} />

      {/* Tabs (inerti) */}
      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <span
            key={t.key}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              t.key === "articoli"
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground"
            }`}
          >
            {t.label}
          </span>
        ))}
      </div>

      <DemoAnchor id="articoli" className="space-y-3">
        {/* Sub-filtri (veste inerte, come articoli-tab) */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-1">
            <span className="px-2.5 py-1 text-xs font-medium rounded-md border bg-primary text-primary-foreground border-primary">
              Tutti
            </span>
            <span className="px-2.5 py-1 text-xs font-medium rounded-md border bg-background border-input">
              Food &amp; Beverage
            </span>
            <span className="px-2.5 py-1 text-xs font-medium rounded-md border bg-background border-input">
              Spese Generali
            </span>
          </div>
          <div className="relative w-56">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
            <div className="h-7 text-xs pl-7 pr-2 flex items-center rounded-md border border-input bg-background text-muted-foreground">
              Cerca prodotto...
            </div>
          </div>
          <span className="ml-auto text-xs px-2.5 py-1 rounded-md border border-input bg-background font-medium">
            Esporta Excel
          </span>
        </div>

        {/* Counter + totale filtrato */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border/50">
          <span className="text-xs text-muted-foreground">{demoAnalisiKpi.num_prodotti} prodotti</span>
          <span className="text-xs inline-flex items-center gap-1.5 text-sky-500">
            Totale filtrato:
            <span className="font-semibold tabular-nums">{formatEuro(demoAnalisiKpi.totale, 2)}</span>
          </span>
        </div>

        {/* Tabella articoli statica */}
        <div className="rounded-lg border overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b">
              <tr className="text-xs text-muted-foreground">
                <th className="w-6"></th>
                <th className="text-left px-3 py-2 font-medium">Descrizione</th>
                <th className="text-left px-3 py-2 font-medium">Categoria</th>
                <th className="text-left px-3 py-2 font-medium">Fornitore</th>
                <th className="text-left px-3 py-2 font-medium whitespace-nowrap">Ultimo acq.</th>
                <th className="text-right px-3 py-2 font-medium">Q.tà</th>
                <th className="text-right px-3 py-2 font-medium whitespace-nowrap">€ medio</th>
                <th className="text-right px-3 py-2 font-medium">Totale</th>
                <th className="text-right px-3 py-2 font-medium">N°</th>
              </tr>
            </thead>
            <tbody>
              {demoArticoli.map((a) => {
                const trendPct = a.prezzo_unit_trend_pct;
                return (
                  <tr key={a.descrizione} className="border-b hover:bg-sky-100/40 dark:hover:bg-sky-900/20 transition-colors">
                    <td className="px-1 align-top pt-2.5">
                      <ChevronRight className="size-3.5 text-muted-foreground" />
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <span className="font-medium truncate max-w-72" title={a.descrizione}>
                        {a.descrizione}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className="text-xs inline-flex items-center gap-1.5">
                        <span className="text-base leading-none">{categoriaIcon(a.categoria)}</span>
                        <span className="font-medium">{a.categoria}</span>
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <span className="truncate inline-block max-w-32">{a.fornitore_principale}</span>
                      {a.altri_fornitori.length > 0 && (
                        <span className="ml-1 text-[10px] text-muted-foreground bg-muted rounded px-1">
                          +{a.altri_fornitori.length}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                      {formatData(a.ultimo_acquisto)}
                    </td>
                    <td className="px-3 py-2 text-xs text-right tabular-nums">
                      {a.quantita_totale.toLocaleString("it-IT", { maximumFractionDigits: 1 })} {a.unita_misura ?? ""}
                    </td>
                    <td className="px-3 py-2 text-xs text-right tabular-nums whitespace-nowrap">
                      {a.prezzo_unit_medio != null ? (
                        <span className="inline-flex items-center gap-1">
                          {formatEuro(a.prezzo_unit_medio, 2)}
                          {trendPct !== null && Math.abs(trendPct) >= 1 && (
                            <span
                              className={`text-[10px] font-semibold inline-flex items-center ${
                                trendPct > 0 ? "text-rose-600" : "text-emerald-600"
                              }`}
                            >
                              {trendPct > 0 ? <ArrowUp className="size-2.5" /> : <ArrowDown className="size-2.5" />}
                              {Math.abs(trendPct).toFixed(0)}%
                            </span>
                          )}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-right font-semibold tabular-nums">
                      {formatEuro(a.totale_speso)}
                    </td>
                    <td className="px-3 py-2 text-xs text-right text-muted-foreground">{a.num_acquisti}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </DemoAnchor>
    </div>
  );
}
