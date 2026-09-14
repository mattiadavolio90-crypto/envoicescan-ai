"""`_load_mensile_overrides` non tace piu' quando la lettura fallisce.

Ritorna {} su errore DB, e {} e' letto da 20+ consumatori come "nessun mese in
modalita' mensile": una sede mensile esce a fatturato 0 e MOL -100%. Il valore
resta {} (ogni chiamante ha il suo ripiego), ma l'errore ora va nel log:
prima del 14/09/2026 nessuno poteva sapere che era successo.
Mutante: togliere `logger.exception` lascia il log vuoto.
"""
import logging

import services.fastapi_worker as fw


class _SBRotto:
    def table(self, *_a, **_k):
        raise RuntimeError("PostgREST 503")


def test_su_errore_db_ritorna_vuoto_ma_lo_dice_nel_log(caplog):
    with caplog.at_level(logging.ERROR, logger="fastapi_worker"):
        out = fw._load_mensile_overrides(_SBRotto(), "rist-1", [2026])
    assert out == {}
    messaggi = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("_load_mensile_overrides" in m and "rist-1" in m for m in messaggi), messaggi
