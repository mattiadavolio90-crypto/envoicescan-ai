"""Il riquadro sotto la voce dell'assistente (`lib/briefing-azioni.ts`).

Dal 25/09/2026 un'osservazione negativa (food cost alto, incasso sceso) spegne
il verde anche senza card da fare. Senza lo stato "vuoto" la Home mostrava il
titolo «Da fare oggi (0)» sopra una lista vuota: il caso esisteva gia' con un
arretrato aperto, e con la regola nuova diventava di ogni martedi'.
"""
import pytest

from tests.helpers_ts import esegui_ts


def _stato(tutto_ok, n_visibili, n_mancanti):
    return esegui_ts(
        "lib/briefing-azioni",
        "emit(m.statoAzioni(...input));",
        argomento=[tutto_ok, n_visibili, n_mancanti],
        richiede=["statoAzioni"],
    )


@pytest.mark.parametrize("tutto_ok,n_visibili,n_mancanti,atteso", [
    (True, 0, 0, "verde"),
    # Il verde lo decide il backend, ma una card ancora visibile vince: l'ha
    # sempre deciso cosi' `tutto_ok && visibili.length === 0`.
    (True, 2, 0, "lista"),
    (False, 1, 0, "lista"),
    (False, 1, 3, "lista"),
    (False, 0, 2, "dati_mancanti"),
    # Il caso nuovo: niente da fare, niente da completare, ma non e' tutto a posto.
    (False, 0, 0, "vuoto"),
])
def test_stato_azioni(tutto_ok, n_visibili, n_mancanti, atteso):
    assert _stato(tutto_ok, n_visibili, n_mancanti) == atteso
