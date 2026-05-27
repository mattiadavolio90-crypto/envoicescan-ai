"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Calendar, Settings2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { calcolaPeriodo, calcolaMese, type PeriodoPreset } from "./periodi";
import type { MeseDisponibile } from "@/lib/fatture";

type Props = {
  presetCorrente: PeriodoPreset | null;
  dataDa?: string;
  dataA?: string;
  meseSelezionato?: string; // formato "YYYY-MM"
  mesiDisponibili: MeseDisponibile[];
};

const PRESETS: { key: PeriodoPreset; label: string }[] = [
  { key: "mese_corrente", label: "Mese" },
  { key: "trimestre_corrente", label: "Trimestre" },
  { key: "semestre_corrente", label: "Semestre" },
  { key: "anno_corrente", label: "Anno" },
];

export function FiltriPeriodo({
  presetCorrente,
  dataDa,
  dataA,
  meseSelezionato,
  mesiDisponibili,
}: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [showCustom, setShowCustom] = useState(presetCorrente === "personalizzato");
  const [showMese, setShowMese] = useState(presetCorrente === "mese_specifico");

  function navigate(updates: Record<string, string | undefined>) {
    const params = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v === undefined || v === "") params.delete(k);
      else params.set(k, v);
    }
    router.push(`${pathname}?${params.toString()}`);
  }

  function applyPreset(preset: PeriodoPreset) {
    const p = calcolaPeriodo(preset);
    setShowCustom(false);
    setShowMese(false);
    navigate({
      preset,
      data_da: p.data_da,
      data_a: p.data_a,
      mese: undefined,
    });
  }

  function applyMese(yearMonth: string) {
    if (!yearMonth) return;
    const [y, m] = yearMonth.split("-").map((s) => parseInt(s, 10));
    const p = calcolaMese(y, m);
    navigate({
      preset: "mese_specifico",
      data_da: p.data_da,
      data_a: p.data_a,
      mese: yearMonth,
    });
  }

  function showCustomPanel() {
    setShowCustom(true);
    setShowMese(false);
    navigate({ preset: "personalizzato" });
  }

  function showMesePanel() {
    setShowMese(true);
    setShowCustom(false);
  }

  const activePreset = presetCorrente ?? "anno_corrente";

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {PRESETS.map((p) => (
          <button
            key={p.key}
            onClick={() => applyPreset(p.key)}
            className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
              activePreset === p.key
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-background border-input hover:bg-muted"
            }`}
          >
            {p.label}
          </button>
        ))}
        <button
          onClick={showMesePanel}
          className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors inline-flex items-center gap-1.5 ${
            activePreset === "mese_specifico"
              ? "bg-primary text-primary-foreground border-primary"
              : "bg-background border-input hover:bg-muted"
          }`}
        >
          <Calendar className="size-3" />
          Mese specifico
        </button>
        <button
          onClick={showCustomPanel}
          className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors inline-flex items-center gap-1.5 ${
            activePreset === "personalizzato"
              ? "bg-primary text-primary-foreground border-primary"
              : "bg-background border-input hover:bg-muted"
          }`}
        >
          <Settings2 className="size-3" />
          Personalizzato
        </button>
        {dataDa && dataA && (
          <span className="ml-2 text-xs text-muted-foreground">
            {fmtIt(dataDa)} → {fmtIt(dataA)}
          </span>
        )}
      </div>

      {showMese && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Mese:</span>
          <select
            value={meseSelezionato ?? ""}
            onChange={(e) => applyMese(e.target.value)}
            className="h-7 text-xs rounded-md border border-input bg-background px-2"
          >
            <option value="" disabled>
              Seleziona un mese
            </option>
            {mesiDisponibili.map((m) => (
              <option key={`${m.year}-${m.month}`} value={`${m.year}-${String(m.month).padStart(2, "0")}`}>
                {m.label} ({m.count} fatture)
              </option>
            ))}
          </select>
        </div>
      )}

      {showCustom && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Dal</span>
          <Input
            type="date"
            value={dataDa ?? ""}
            onChange={(e) =>
              navigate({ preset: "personalizzato", data_da: e.target.value || undefined })
            }
            className="h-7 text-xs w-36"
          />
          <span className="text-xs text-muted-foreground">al</span>
          <Input
            type="date"
            value={dataA ?? ""}
            onChange={(e) =>
              navigate({ preset: "personalizzato", data_a: e.target.value || undefined })
            }
            className="h-7 text-xs w-36"
          />
        </div>
      )}
    </div>
  );
}

function fmtIt(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y.slice(2)}`;
}
