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


class TestTotaleCreditoSegniMisti:
    """Regressione: il totale credito di una NC a segni misti (riaddebito + /
    storno -) deve essere il NETTO per documento, non la somma dei valori
    assoluti riga-per-riga. Caso LODI: +2174.67 - 2072.47 = 102.20, non 4247.14."""

    def test_totale_credito_e_netto_per_documento(self):
        # Stessa aggregazione usata in get_note_credito dopo il fix
        df_nc = _df([
            {"file_origine": "NC_LODI.xml", "totale_riga": 2174.67},
            {"file_origine": "NC_LODI.xml", "totale_riga": -2072.47},
        ])
        totale = round(df_nc.groupby("file_origine")["totale_riga"].sum().abs().sum(), 2)
        assert totale == 102.20, f"Atteso netto 102.20, trovato {totale}"
        # la vecchia formula sbagliata avrebbe dato 4247.14
        assert totale != round(df_nc["totale_riga"].abs().sum(), 2)

    def test_due_documenti_distinti_non_si_compensano(self):
        # Due NC distinte: i loro netti NON devono compensarsi tra loro
        df_nc = _df([
            {"file_origine": "NC_A.xml", "totale_riga": 100.0},
            {"file_origine": "NC_B.xml", "totale_riga": -100.0},
        ])
        totale = round(df_nc.groupby("file_origine")["totale_riga"].sum().abs().sum(), 2)
        # |+100| + |-100| = 200, NON 0 (che sarebbe somma netta cieca)
        assert totale == 200.0

    def test_credito_per_fornitore_netto_per_documento(self):
        # Stessa aggregazione usata in _nc_credito_per_fornitore dopo il fix
        df_nc = _df([
            {"_forn_key": "LODI SRL", "file_origine": "NC1.xml", "totale_riga": 2174.67},
            {"_forn_key": "LODI SRL", "file_origine": "NC1.xml", "totale_riga": -2072.47},
            {"_forn_key": "METRO", "file_origine": "NC2.xml", "totale_riga": -50.0},
        ])
        netto_per_doc = df_nc.groupby(["_forn_key", "file_origine"])["totale_riga"].sum().abs()
        grouped = netto_per_doc.groupby("_forn_key").sum()
        res = {k: round(float(v), 2) for k, v in grouped.to_dict().items()}
        assert res == {"LODI SRL": 102.20, "METRO": 50.0}
