"""Regressione cert. SUSHILAND: le note di credito (TD04) NON devono essere
contate come sconti commerciali nel tab Sconti.

Bug originale: la maschera sconti catturava ogni riga con importo negativo,
incluse le righe negative delle NC → doppio conteggio (apparivano sia in Sconti
sia in Note di Credito) e "Risparmiato" gonfiato. Inoltre il vecchio pattern
"NC|NOTA DI CREDITO|CREDIT" non riconosceva il valore reale del DB ('TD04').
"""
import pandas as pd

from services.routers.prezzi import _mask_nota_credito


def _df(rows):
    return pd.DataFrame(rows)


class TestMaskNotaCredito:

    def test_td04_riconosciuta(self):
        df = _df([{"tipo_documento": "TD04"}, {"tipo_documento": "TD01"}])
        mask = _mask_nota_credito(df)
        assert mask.tolist() == [True, False]

    def test_varianti_testuali(self):
        df = _df([
            {"tipo_documento": "Nota di Credito"},
            {"tipo_documento": "NC"},
            {"tipo_documento": "credit note"},
            {"tipo_documento": "TD01"},
            {"tipo_documento": ""},
        ])
        assert _mask_nota_credito(df).tolist() == [True, True, True, False, False]

    def test_colonna_assente_non_crasha(self):
        df = _df([{"totale_riga": -10.0}])
        mask = _mask_nota_credito(df)
        assert mask.tolist() == [False]


class TestScontiEscludonoNotaCredito:
    """Riproduce la maschera sconti del router (riga negativa MA non NC)."""

    def test_riga_nc_negativa_non_e_sconto(self):
        df = _df([
            # sconto commerciale vero (TD01, importo negativo)
            {"tipo_documento": "TD01", "prezzo_unitario": -2.0, "totale_riga": -5.0},
            # storno di una nota di credito (TD04, importo negativo) → NON sconto
            {"tipo_documento": "TD04", "prezzo_unitario": -7.30, "totale_riga": -2072.47},
        ])
        nc_mask = _mask_nota_credito(df)
        mask_sconto = (~nc_mask) & (
            (df["prezzo_unitario"] < -1e-9) | (df["totale_riga"] < -1e-9)
        )
        assert mask_sconto.tolist() == [True, False]
        # il "risparmiato" deve contare solo lo sconto vero (5.0), non la NC
        risparmiato = round(df[mask_sconto]["totale_riga"].abs().sum(), 2)
        assert risparmiato == 5.0
