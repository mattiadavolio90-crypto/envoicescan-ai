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

export function formatEuro(v: number, decimali = 0): string {
  return v.toLocaleString("it-IT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: decimali,
    maximumFractionDigits: decimali,
  });
}

export function formatEuroCompact(v: number): string {
  if (Math.abs(v) >= 1000) {
    return `€ ${(v / 1000).toFixed(1)}k`;
  }
  return formatEuro(v);
}

export function formatData(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y.slice(2)}`;
}

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
};

export function categoriaIcon(cat: string | null | undefined): string {
  if (!cat) return "🏷️";
  return CATEGORIA_ICONS[cat.trim().toUpperCase()] ?? "🏷️";
}
