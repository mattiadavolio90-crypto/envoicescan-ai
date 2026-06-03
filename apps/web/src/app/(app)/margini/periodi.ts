export type PeriodoPreset =
  | "mese_corrente"
  | "trimestre_corrente"
  | "semestre_corrente"
  | "anno_corrente"
  | "anno_precedente"
  | "q1" | "q2" | "q3" | "q4"
  | "h1" | "h2"
  | "mese_specifico"
  | "personalizzato";

export type PeriodoCalcolato = {
  data_da: string;
  data_a: string;
  label: string;
};

function fmt(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function lastDay(year: number, month1Based: number): Date {
  return new Date(year, month1Based, 0);
}

export function calcolaPeriodo(preset: PeriodoPreset, oggi: Date = new Date()): PeriodoCalcolato {
  const y = oggi.getFullYear();
  const m = oggi.getMonth(); // 0-indexed

  switch (preset) {
    case "mese_corrente": {
      const inizio = new Date(y, m, 1);
      return { data_da: fmt(inizio), data_a: fmt(oggi), label: "Mese in corso" };
    }
    case "trimestre_corrente": {
      const trim = Math.floor(m / 3) * 3;
      const inizio = new Date(y, trim, 1);
      return { data_da: fmt(inizio), data_a: fmt(oggi), label: "Trimestre" };
    }
    case "semestre_corrente": {
      const sem = m < 6 ? 0 : 6;
      const inizio = new Date(y, sem, 1);
      return { data_da: fmt(inizio), data_a: fmt(oggi), label: "Semestre" };
    }
    case "anno_corrente": {
      const inizio = new Date(y, 0, 1);
      return { data_da: fmt(inizio), data_a: fmt(oggi), label: "Anno in corso" };
    }
    case "anno_precedente": {
      const inizio = new Date(y - 1, 0, 1);
      const fine = new Date(y - 1, 11, 31);
      return { data_da: fmt(inizio), data_a: fmt(fine), label: `Anno ${y - 1}` };
    }
    case "q1": return { data_da: fmt(new Date(y, 0, 1)), data_a: fmt(lastDay(y, 3)), label: `Q1 ${y}` };
    case "q2": return { data_da: fmt(new Date(y, 3, 1)), data_a: fmt(lastDay(y, 6)), label: `Q2 ${y}` };
    case "q3": return { data_da: fmt(new Date(y, 6, 1)), data_a: fmt(lastDay(y, 9)), label: `Q3 ${y}` };
    case "q4": return { data_da: fmt(new Date(y, 9, 1)), data_a: fmt(lastDay(y, 12)), label: `Q4 ${y}` };
    case "h1": return { data_da: fmt(new Date(y, 0, 1)), data_a: fmt(lastDay(y, 6)), label: `H1 ${y}` };
    case "h2": return { data_da: fmt(new Date(y, 6, 1)), data_a: fmt(lastDay(y, 12)), label: `H2 ${y}` };
    default: {
      const inizio = new Date(y, 0, 1);
      return { data_da: fmt(inizio), data_a: fmt(oggi), label: "Anno in corso" };
    }
  }
}

export function calcolaMese(year: number, month1Based: number): PeriodoCalcolato {
  const inizio = new Date(year, month1Based - 1, 1);
  const fine = lastDay(year, month1Based);
  return {
    data_da: fmt(inizio),
    data_a: fmt(fine),
    label: meseLabel(year, month1Based),
  };
}

// Genera gli ultimi N mesi (default 24) terminando con il mese corrente.
export function mesiSelezionabili(n = 24, oggi: Date = new Date()): { year: number; month: number; label: string }[] {
  const out: { year: number; month: number; label: string }[] = [];
  let y = oggi.getFullYear();
  let m = oggi.getMonth() + 1; // 1-based
  for (let i = 0; i < n; i++) {
    out.push({ year: y, month: m, label: meseLabel(y, m) });
    m -= 1;
    if (m < 1) { m = 12; y -= 1; }
  }
  return out;
}

// Scorporo IVA: i ricavi sono salvati lordi, il netto si ottiene dividendo per
// l'aliquota. Tenuto qui in un solo punto per evitare divergenze tra UI e worker.
export const IVA_DIVISORE_10 = 1.10;
export const IVA_DIVISORE_22 = 1.22;

export function scorporoNetto(iva10: number, iva22: number, altri: number): number {
  return iva10 / IVA_DIVISORE_10 + iva22 / IVA_DIVISORE_22 + altri;
}

// Formatter centralizzati in lib/format.ts (re-export per i consumer esistenti).
export { formatEuro, formatEuroCompact, formatPct, formatData } from "@/lib/format";

export const MESI_NOMI_LUNGHI = [
  "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
];

export const MESI_NOMI_SHORT = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

export function meseLabel(year: number, month1Based: number, short = false): string {
  const arr = short ? MESI_NOMI_SHORT : MESI_NOMI_LUNGHI;
  return `${arr[month1Based - 1]} ${year}`;
}
