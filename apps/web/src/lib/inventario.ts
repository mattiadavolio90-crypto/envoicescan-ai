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

export interface ConfrontoRiga {
  nome: string;
  categoria: string;
  um: string;
  qta_a: number;
  qta_b: number;
  delta_qta: number;
  valore_a: number;
  valore_b: number;
  delta_valore: number;
  stato: "variato" | "invariato" | "nuovo" | "uscito";
}

export interface ConfrontoInventari {
  valore_a: number;
  valore_b: number;
  delta_valore: number;
  righe: ConfrontoRiga[];
}

/**
 * Confronta due inventari (liste di voci) abbinando i prodotti per nome.
 * A = inventario sorgente (più vecchio), B = inventario destinazione.
 */
export function confrontaInventari(vociA: VoceInventario[], vociB: VoceInventario[]): ConfrontoInventari {
  const key = (n: string) => n.trim().toLowerCase();
  const mapA = new Map(vociA.map(v => [key(v.nome), v]));
  const mapB = new Map(vociB.map(v => [key(v.nome), v]));
  const chiavi = new Set([...mapA.keys(), ...mapB.keys()]);

  const righe: ConfrontoRiga[] = [];
  let valore_a = 0;
  let valore_b = 0;

  for (const k of chiavi) {
    const a = mapA.get(k);
    const b = mapB.get(k);
    const va = a?.valore_totale ?? 0;
    const vb = b?.valore_totale ?? 0;
    valore_a += va;
    valore_b += vb;
    const qa = a?.quantita ?? 0;
    const qb = b?.quantita ?? 0;

    let stato: ConfrontoRiga["stato"];
    if (!a) stato = "nuovo";
    else if (!b) stato = "uscito";
    else if (qa === qb && va === vb) stato = "invariato";
    else stato = "variato";

    righe.push({
      nome: (b ?? a)!.nome,
      categoria: (b ?? a)!.categoria,
      um: (b ?? a)!.um,
      qta_a: qa,
      qta_b: qb,
      delta_qta: qb - qa,
      valore_a: va,
      valore_b: vb,
      delta_valore: vb - va,
      stato,
    });
  }

  // Ordine: prima le righe con variazione di valore più rilevante (per modulo)
  righe.sort((x, y) => Math.abs(y.delta_valore) - Math.abs(x.delta_valore) || x.nome.localeCompare(y.nome));

  return {
    valore_a: Math.round(valore_a * 100) / 100,
    valore_b: Math.round(valore_b * 100) / 100,
    delta_valore: Math.round((valore_b - valore_a) * 100) / 100,
    righe,
  };
}

export const UM_INVENTARIO = ["G", "KG", "ML", "CL", "LT", "PZ", "BOTT", "CF"] as const;

export function fmtData(iso: string | null | undefined): string {
  if (!iso || !iso.includes("-")) return iso ?? "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}
