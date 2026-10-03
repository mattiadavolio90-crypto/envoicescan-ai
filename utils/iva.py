"""Scorporo dell'IVA da un costo inserito a mano IVA inclusa.

Il conto si fa in centesimi interi con arrotondamento al mezzo centesimo per
eccesso: e' esatto, e lo stesso conto in `apps/web/src/lib/iva-costi.ts` (anteprima
nel modulo Spese) da' lo stesso netto al centesimo — lo verifica
tests/test_iva_costi.py su una griglia di importi.
"""
from decimal import ROUND_HALF_UP, Decimal

from config.constants import ALIQUOTE_IVA_COSTI


def netto_da_lordo(lordo: float, aliquota: int) -> float:
    if aliquota not in ALIQUOTE_IVA_COSTI:
        raise ValueError(f"Aliquota IVA non ammessa: {aliquota}")
    centesimi = Decimal(str(lordo)).quantize(Decimal("0.01"), ROUND_HALF_UP) * 100
    netto = (centesimi * 100 / (100 + aliquota)).quantize(Decimal("1"), ROUND_HALF_UP)
    return float(netto / 100)
