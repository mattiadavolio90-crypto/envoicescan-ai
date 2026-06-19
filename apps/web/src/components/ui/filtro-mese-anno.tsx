"use client";

import { MESI_LUNGHI } from "@/lib/mesi";

// Filtro periodo standard "anno + mese" usato nelle sotto-pagine di Prezzi.
// Sostituisce i 12 chip-mese in riga orizzontale con due <select> compatti,
// allineando lo stile a Margini/Analisi Fatture (lo standard scelto). mese=null
// significa "tutto l'anno". Componente unico → niente piu' copie da mantenere.

type Props = {
  anno: number;
  mese: number | null; // 1-12, oppure null = tutto l'anno
  anni: number[];
  onAnnoChange: (anno: number) => void;
  onMeseChange: (mese: number | null) => void;
  /** Limita i mesi selezionabili (es. fino al mese corrente per l'anno corrente). */
  maxMese?: number;
};

export function FiltroMeseAnno({
  anno, mese, anni, onAnnoChange, onMeseChange, maxMese = 12,
}: Props) {
  const selectClass =
    "h-8 rounded-md border border-input bg-background px-2 text-xs";

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted-foreground">Periodo:</span>
      <select
        value={anno}
        onChange={(e) => onAnnoChange(Number(e.target.value))}
        className={selectClass}
        aria-label="Anno"
      >
        {anni.map((y) => <option key={y} value={y}>{y}</option>)}
      </select>
      <select
        value={mese ?? ""}
        onChange={(e) => onMeseChange(e.target.value === "" ? null : Number(e.target.value))}
        className={selectClass}
        aria-label="Mese"
      >
        <option value="">Tutto l&apos;anno</option>
        {MESI_LUNGHI.slice(0, maxMese).map((label, i) => (
          <option key={i + 1} value={i + 1}>{label}</option>
        ))}
      </select>
    </div>
  );
}
