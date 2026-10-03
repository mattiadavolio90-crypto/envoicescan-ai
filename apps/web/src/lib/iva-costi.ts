// Un costo inserito a mano IVA inclusa si salva al netto, come le fatture
// (Mattia, 3/10/2026). Lo scorporo vero lo fa il worker (utils/iva.py); qui c'e'
// lo stesso conto per l'anteprima nel modulo, in centesimi interi perche' i due
// diano lo stesso netto al centesimo (tests/test_iva_costi.py).
export const ALIQUOTE_IVA_COSTI = [4, 5, 10, 22] as const;
export type AliquotaIvaCosti = (typeof ALIQUOTE_IVA_COSTI)[number];

export function nettoDaLordo(lordo: number, aliquota: AliquotaIvaCosti): number {
  const centesimi = Math.round(lordo * 100);
  return Math.floor((centesimi * 100) / (100 + aliquota) + 0.5) / 100;
}

export function aliquotaDaScelta(valore: string): AliquotaIvaCosti | null {
  const n = Number(valore);
  return (ALIQUOTE_IVA_COSTI as readonly number[]).includes(n) ? (n as AliquotaIvaCosti) : null;
}
