"""Quale pulsante offrire su una fattura in coda senza cliente (`lib/coda-fatture.ts`).

Prima del passo 0-bis (25/09/2026) le righe senza cliente avevano solo
«Assegna a…», che aggiorna le righe unknown_tenant: su una riga failed/dead
(download fallito, per esempio con il saldo Invoicetronic esaurito) toccava 0
righe e la fattura restava ferma. Ora quelle righe hanno «Riprova»: il worker
riscarica l'XML e decide il cliente dalla fattura.
"""

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/coda-fatture"


def _azione(status):
    return esegui_ts(MODULO, "emit(m.azioneFatturaOrfana(input));", argomento=status, richiede=["azioneFatturaOrfana"])


@pytest.mark.parametrize("status", ["failed", "dead"])
def test_download_fallito_si_riprova(status):
    assert _azione(status) == "riprova"


def test_piva_di_nessuno_si_assegna():
    assert _azione("unknown_tenant") == "assegna"


@pytest.mark.parametrize("status", ["pending", "processing", "done", "da_assegnare", "scartata", "", None])
def test_negli_altri_stati_nessun_pulsante(status):
    assert _azione(status) is None
