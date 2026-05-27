"use client";

import { TrendingUp, Calendar, BarChart3, Euro } from "lucide-react";
import { formatEuro, formatEuroCompact } from "./periodi";

export type KpiData = {
  fatturato_netto: number;
  ricavi_iva10: number;
  ricavi_iva22: number;
  altri_ricavi: number;
  giorni_con_dati: number;
  giorni_periodo: number;
  media_giornaliera: number;
};

export function KpiBar({ kpi }: { kpi: KpiData }) {
  const cards = [
    {
      label: "Fatturato Netto",
      value: formatEuro(kpi.fatturato_netto),
      hint: kpi.fatturato_netto === 0 ? "Nessun ricavo nel periodo" : `IVA scorporata`,
      icon: Euro,
      tone: "primary" as const,
    },
    {
      label: "Media Giornaliera",
      value: formatEuroCompact(kpi.media_giornaliera),
      hint: `${kpi.giorni_con_dati}/${kpi.giorni_periodo} giorni con dati`,
      icon: TrendingUp,
      tone: "default" as const,
    },
    {
      label: "Ricavi IVA 10%",
      value: formatEuroCompact(kpi.ricavi_iva10),
      hint: kpi.fatturato_netto > 0
        ? `${((kpi.ricavi_iva10 / 1.10 / kpi.fatturato_netto) * 100).toFixed(0)}% del netto`
        : "—",
      icon: BarChart3,
      tone: "default" as const,
    },
    {
      label: "Ricavi IVA 22%",
      value: formatEuroCompact(kpi.ricavi_iva22),
      hint: kpi.fatturato_netto > 0
        ? `${((kpi.ricavi_iva22 / 1.22 / kpi.fatturato_netto) * 100).toFixed(0)}% del netto`
        : "—",
      icon: BarChart3,
      tone: "default" as const,
    },
    {
      label: "Altri Ricavi",
      value: formatEuroCompact(kpi.altri_ricavi),
      hint: "no IVA",
      icon: BarChart3,
      tone: "default" as const,
    },
    {
      label: "Copertura periodo",
      value: kpi.giorni_periodo > 0
        ? `${Math.round((kpi.giorni_con_dati / kpi.giorni_periodo) * 100)}%`
        : "—",
      hint: `${kpi.giorni_con_dati} di ${kpi.giorni_periodo} gg`,
      icon: Calendar,
      tone: "muted" as const,
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <div
            key={c.label}
            className={`rounded-lg border p-3 transition-colors ${
              c.tone === "primary"
                ? "border-primary/30 bg-primary/5"
                : c.tone === "muted"
                ? "border-border/60 bg-muted/30"
                : "border-border bg-card"
            }`}
          >
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
                {c.label}
              </p>
              <Icon className={`size-3.5 ${c.tone === "primary" ? "text-primary" : "text-muted-foreground/60"}`} />
            </div>
            <p className={`text-lg font-bold leading-tight ${c.tone === "primary" ? "text-primary" : ""}`}>
              {c.value}
            </p>
            <p className="text-[10px] text-muted-foreground mt-1 truncate">{c.hint}</p>
          </div>
        );
      })}
    </div>
  );
}
