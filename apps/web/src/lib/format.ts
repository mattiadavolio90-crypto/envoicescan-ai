// Formatter di dominio (valuta/data/percentuale) — FONTE UNICA.
// Prima erano duplicati in margini/periodi.ts, analisi-fatture/periodi.ts e
// scadenziario.ts, con formatEuroCompact divergente (milioni gestiti solo in uno):
// rischio di output incoerente tra pagine. Qui una sola implementazione.

export function formatEuro(v: number, decimali = 0): string {
  return v.toLocaleString("it-IT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: decimali,
    maximumFractionDigits: decimali,
  });
}

export function formatEuroCompact(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1000) return `€ ${(v / 1000).toFixed(1)}k`;
  return formatEuro(v);
}

export function formatPct(v: number, decimali = 1): string {
  if (!isFinite(v)) return "—";
  return `${v.toFixed(decimali)}%`;
}

export function formatData(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y.slice(2)}`;
}
