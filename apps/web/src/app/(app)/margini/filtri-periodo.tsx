"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";
import { Calendar, Settings2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { calcolaPeriodo, calcolaMese, mesiSelezionabili, formatData, type PeriodoPreset } from "./periodi";

type Props = {
  presetCorrente: PeriodoPreset;
  dataDa: string;
  dataA: string;
  meseSelezionato?: string; // "YYYY-MM"
};

export function FiltriPeriodo({ presetCorrente, dataDa, dataA, meseSelezionato }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [pending, startTransition] = useTransition();
  const [showCustom, setShowCustom] = useState(presetCorrente === "personalizzato");
  const [showMese, setShowMese] = useState(presetCorrente === "mese_specifico");

  const mesi = mesiSelezionabili(24);

  function navigate(updates: Record<string, string | undefined>) {
    const params = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v === undefined || v === "") params.delete(k);
      else params.set(k, v);
    }
    startTransition(() => router.push(`${pathname}?${params.toString()}`));
  }

  function applyPreset(preset: PeriodoPreset) {
    const p = calcolaPeriodo(preset);
    setShowCustom(false);
    setShowMese(false);
    navigate({ preset, data_da: p.data_da, data_a: p.data_a, mese: undefined });
  }

  function applyMese(ym: string) {
    if (!ym) return;
    const [y, m] = ym.split("-").map((s) => parseInt(s, 10));
    const p = calcolaMese(y, m);
    navigate({ preset: "mese_specifico", data_da: p.data_da, data_a: p.data_a, mese: ym });
  }

  function showMesePanel() {
    setShowMese(true);
    setShowCustom(false);
  }

  function showCustomPanel() {
    setShowCustom(true);
    setShowMese(false);
    navigate({ preset: "personalizzato" });
  }

  const chipBase =
    "px-3 py-1.5 text-xs font-medium rounded-full border transition-colors inline-flex items-center gap-1.5 disabled:opacity-60";
  const chipActive = "bg-primary text-primary-foreground border-primary";
  const chipIdle = "bg-background border-input hover:bg-muted";

  return (
    <div className={`space-y-2 ${pending ? "opacity-70" : ""}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          disabled={pending}
          onClick={() => applyPreset("anno_corrente")}
          className={`${chipBase} ${presetCorrente === "anno_corrente" ? chipActive : chipIdle}`}
        >
          Anno in corso
        </button>
        <button
          disabled={pending}
          onClick={showMesePanel}
          className={`${chipBase} ${presetCorrente === "mese_specifico" ? chipActive : chipIdle}`}
        >
          <Calendar className="size-3" />
          Seleziona mese
        </button>
        <button
          disabled={pending}
          onClick={showCustomPanel}
          className={`${chipBase} ${presetCorrente === "personalizzato" ? chipActive : chipIdle}`}
        >
          <Settings2 className="size-3" />
          Personalizzato
        </button>
        <span className="ml-auto text-xs text-muted-foreground">
          {formatData(dataDa)} → {formatData(dataA)}
        </span>
      </div>

      {showMese && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Mese:</span>
          <select
            value={meseSelezionato ?? ""}
            onChange={(e) => applyMese(e.target.value)}
            className="h-7 text-xs rounded-md border border-input bg-background px-2"
          >
            <option value="" disabled>Seleziona un mese</option>
            {mesi.map((m) => (
              <option key={`${m.year}-${m.month}`} value={`${m.year}-${String(m.month).padStart(2, "0")}`}>
                {m.label}
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
            value={dataDa}
            onChange={(e) => navigate({ preset: "personalizzato", data_da: e.target.value || undefined })}
            className="h-7 text-xs w-36"
          />
          <span className="text-xs text-muted-foreground">al</span>
          <Input
            type="date"
            value={dataA}
            onChange={(e) => navigate({ preset: "personalizzato", data_a: e.target.value || undefined })}
            className="h-7 text-xs w-36"
          />
        </div>
      )}
    </div>
  );
}
