export interface ArticoloInventario {
  nome: string;
  categoria: string;
  prezzo_unitario: number;
  um: string;
}

export interface VoceInventario {
  id: string;
  data_inventario: string;
  nome: string;
  categoria: string;
  quantita: number;
  um: string;
  prezzo_unitario: number;
  valore_totale: number;
  note?: string | null;
}

export interface KpiInventario {
  n_articoli: number;
  n_categorie: number;
  valore_totale: number;
}

export interface CategoriaInventarioStats {
  categoria: string;
  n_articoli: number;
  valore_totale: number;
  pct_totale: number;
}

export interface InventarioResponse {
  voci: VoceInventario[];
  kpi: KpiInventario;
  categorie: CategoriaInventarioStats[];
}

export interface SnapshotDate {
  data_inventario: string;
  n_articoli: number;
  valore_totale: number;
}

export const UM_INVENTARIO = ["G", "KG", "ML", "CL", "LT", "PZ", "BOTT", "CF"] as const;

export function fmtData(iso: string | null | undefined): string {
  if (!iso || !iso.includes("-")) return iso ?? "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}
