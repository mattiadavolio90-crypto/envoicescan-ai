"use client";

// Il filtro del periodo dell'Osservatorio prezzi, condiviso con la scheda
// «Prezzi» di catena (Mattia, 13/10/2026: «ci vuole un filtro temporale come nel
// punto vendita»). Solo disegno: lo stato e il caricamento restano alla pagina.

import type { ReactNode } from "react";
import { Calendar, Settings2 } from "lucide-react";
import { FilterChip } from "@/components/ui/filter-chip";
import { Input } from "@/components/ui/input";
import { MESI_LUNGHI } from "@/lib/mesi";

export type ModoPeriodo = "anno" | "mese" | "custom";

export const ANNO_CORRENTE = new Date().getFullYear();

export function fmtRangeIt(da: string, a: string): string {
  const f = (iso: string) => {
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y.slice(2)}`;
  };
  return `${f(da)} → ${f(a)}`;
}

export function FiltroPeriodoPrezzi({
  anno,
  modo,
  mese,
  customDa,
  customA,
  range,
  loading,
  onAnno,
  onModoMese,
  onMese,
  onModoCustom,
  onCustom,
  destra,
}: {
  anno: number;
  modo: ModoPeriodo;
  mese: number | null;
  customDa: string;
  customA: string;
  range: { data_da: string; data_a: string };
  loading: boolean;
  onAnno: (anno: number) => void;
  onModoMese: () => void;
  onMese: (mese: number) => void;
  onModoCustom: () => void;
  onCustom: (da: string, a: string) => void;
  /** Spiegazione e «Aggiorna», allineati a destra sulla stessa riga. */
  destra?: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className={`flex flex-wrap items-center gap-1.5 ${loading ? "opacity-70" : ""}`}>
        <select
          value={anno}
          disabled={loading}
          onChange={(e) => onAnno(Number(e.target.value))}
          aria-label="Anno"
          className="h-7 rounded-full border border-input bg-background px-3 text-xs font-medium"
        >
          {Array.from({ length: 5 }, (_, i) => ANNO_CORRENTE - i).map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
        <FilterChip active={modo === "anno"} disabled={loading} onClick={() => onAnno(anno)}>
          {anno === ANNO_CORRENTE ? "Anno in corso" : "Tutto l'anno"}
        </FilterChip>
        <FilterChip active={modo === "mese"} disabled={loading} onClick={onModoMese}>
          <Calendar className="size-3" />
          Seleziona mese
        </FilterChip>
        <FilterChip active={modo === "custom"} disabled={loading} onClick={onModoCustom}>
          <Settings2 className="size-3" />
          Personalizzato
        </FilterChip>
        {range.data_da && range.data_a && (
          <span className="ml-2 text-xs font-medium text-primary-text">{fmtRangeIt(range.data_da, range.data_a)}</span>
        )}
        {destra && <div className="ml-auto flex items-center gap-1">{destra}</div>}
      </div>

      {modo === "mese" && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Mese:</span>
          <select
            value={mese ?? ""}
            onChange={(e) => onMese(Number(e.target.value))}
            aria-label="Mese"
            className="h-7 rounded-md border border-input bg-background px-2 text-xs"
          >
            <option value="" disabled>Seleziona un mese</option>
            {MESI_LUNGHI.map((label, i) => (
              <option key={i + 1} value={i + 1}>{label} {anno}</option>
            ))}
          </select>
        </div>
      )}

      {modo === "custom" && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Dal</span>
          <Input type="date" value={customDa} onChange={(e) => onCustom(e.target.value, customA)} className="h-7 w-36 text-xs" />
          <span className="text-xs text-muted-foreground">al</span>
          <Input type="date" value={customA} onChange={(e) => onCustom(customDa, e.target.value)} className="h-7 w-36 text-xs" />
        </div>
      )}
    </div>
  );
}
