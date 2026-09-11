export type PeriodoPreset =
  | "mese_corrente"
  | "trimestre_corrente"
  | "semestre_corrente"
  | "anno_corrente"
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
    default: {
      const inizio = new Date(y, 0, 1);
      return { data_da: fmt(inizio), data_a: fmt(oggi), label: "Anno in corso" };
    }
  }
}

export function calcolaMese(anno: number, mese: number): PeriodoCalcolato {
  const inizio = new Date(anno, mese - 1, 1);
  const fine = new Date(anno, mese, 0);
  const mesi = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];
  return {
    data_da: fmt(inizio),
    data_a: fmt(fine),
    label: `${mesi[mese - 1]} ${anno}`,
  };
}

// Formatter centralizzati in lib/format.ts (re-export per i consumer esistenti).
// NB: formatEuroCompact ora gestisce anche i milioni (M), prima qui no.
export { formatEuro, formatEuroCompact, formatData } from "@/lib/format";

export const CATEGORIA_ICONS: Record<string, string> = {
  CARNE: "🥩",
  PESCE: "🐠",
  LATTICINI: "🧀",
  SALUMI: "🥓",
  UOVA: "🥚",
  "SCATOLAME E CONSERVE": "🥫",
  "OLIO E CONDIMENTI": "🫙",
  "PASTA E CEREALI": "🌾",
  VERDURE: "🥦",
  FRUTTA: "🍓",
  "SALSE E CREME": "🥣",
  "PRODOTTI DA FORNO": "🍞",
  "SPEZIE E AROMI": "🌿",
  PASTICCERIA: "🍰",
  "GELATI E DESSERT": "🍦",
  "SUSHI VARIE": "🍣",
  SHOP: "🛍️",
  ACQUA: "💧",
  BEVANDE: "🥤",
  "CAFFE E THE": "☕",
  BIRRE: "🍺",
  VINI: "🍷",
  DISTILLATI: "🥃",
  "AMARI/LIQUORI": "🍸",
  "VARIE BAR": "🍹",
  "MATERIALE DI CONSUMO": "📦",
  "SERVIZI E CONSULENZE": "📋",
  "UTENZE E LOCALI": "🔌",
  "MANUTENZIONE E ATTREZZATURE": "🔧",
  // Retail: l'unica categoria merce di un negozio. Qui e' sicuro — questa e' una
  // mappa per nome con fallback, non una partizione: nessun menu dei ristoranti
  // la legge come elenco (a differenza di CATEGORIE_TUTTE in lib/admin.ts, dove
  // aggiungerla sarebbe la violazione del vincolo). Senza voce il negozio
  // vedrebbe la sua unica categoria col segnaposto generico.
  "ARTICOLO DI VENDITA": "🏪",
};

export function categoriaIcon(cat: string | null | undefined): string {
  if (!cat) return "🏷️";
  return CATEGORIA_ICONS[cat.trim().toUpperCase()] ?? "🏷️";
}
