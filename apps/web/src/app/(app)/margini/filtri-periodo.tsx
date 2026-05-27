"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";
import { Settings2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { calcolaPeriodo, type PeriodoPreset, formatData } from "./periodi";

type Props = {
  presetCorrente: PeriodoPreset;
  dataDa: string;
  dataA: string;
};

const PRESETS: { key: PeriodoPreset; label: string; group: "primary" | "trim" | "sem" | "extra" }[] = [
  { key: "mese_corrente", label: "Mese in corso", group: "primary" },
  { key: "trimestre_corrente", label: "Trim. in corso", group: "primary" },
  { key: "semestre_corrente", label: "Sem. in corso", group: "primary" },
  { key: "anno_corrente", label: "Anno in corso", group: "primary" },
  { key: "anno_precedente", label: "Anno scorso", group: "primary" },
  { key: "q1", label: "Q1", group: "trim" },
  { key: "q2", label: "Q2", group: "trim" },
  { key: "q3", label: "Q3", group: "trim" },
  { key: "q4", label: "Q4", group: "trim" },
  { key: "h1", label: "H1", group: "sem" },
  { key: "h2", label: "H2", group: "sem" },
];

export function FiltriPeriodo({ presetCorrente, dataDa, dataA }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [pending, startTransition] = useTransition();
  const [showCustom, setShowCustom] = useState(presetCorrente === "personalizzato");

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
    navigate({ preset, data_da: p.data_da, data_a: p.data_a });
  }

  function showCustomPanel() {
    setShowCustom(true);
    navigate({ preset: "personalizzato" });
  }

  const chipBase =
    "px-3 py-1 text-xs font-medium rounded-full border transition-colors disabled:opacity-60";
  const chipActive = "bg-primary text-primary-foreground border-primary";
  const chipIdle = "bg-background border-input hover:bg-muted";

  return (
    <div className={`space-y-2 ${pending ? "opacity-70" : ""}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        {PRESETS.filter((p) => p.group === "primary").map((p) => (
          <button
            key={p.key}
            disabled={pending}
            onClick={() => applyPreset(p.key)}
            className={`${chipBase} ${presetCorrente === p.key ? chipActive : chipIdle}`}
          >
            {p.label}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-border" />
        {PRESETS.filter((p) => p.group === "trim").map((p) => (
          <button
            key={p.key}
            disabled={pending}
            onClick={() => applyPreset(p.key)}
            className={`${chipBase} ${presetCorrente === p.key ? chipActive : chipIdle}`}
          >
            {p.label}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-border" />
        {PRESETS.filter((p) => p.group === "sem").map((p) => (
          <button
            key={p.key}
            disabled={pending}
            onClick={() => applyPreset(p.key)}
            className={`${chipBase} ${presetCorrente === p.key ? chipActive : chipIdle}`}
          >
            {p.label}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-border" />
        <button
          disabled={pending}
          onClick={showCustomPanel}
          className={`${chipBase} inline-flex items-center gap-1 ${presetCorrente === "personalizzato" ? chipActive : chipIdle}`}
        >
          <Settings2 className="size-3" />
          Personalizzato
        </button>
        <span className="ml-auto text-xs text-muted-foreground">
          {formatData(dataDa)} → {formatData(dataA)}
        </span>
      </div>

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
