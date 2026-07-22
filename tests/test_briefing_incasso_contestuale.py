"""Test Fase 1 — apertura incasso contestuale del briefing.

Verifica i due helper deterministici nuovi e la resa narrativa:
- `_incasso_confronto_giorno_settimana`: confronto con la media dello STESSO
  giorno-settimana (l'unico ammesso), con requisito minimo di occorrenze e
  soglia "in linea".
- `_coperti_scontrino_ieri`: coperti + scontrino medio SEMPRE se presenti
  (nessuna soglia), None se il dato manca.
- `_buona_notizia_bullet` / `_buona_notizia_frase`: compongono l'apertura senza
  inventare campi (degrado graduale: solo incasso se non c'e' altro).

Decisione Mattia 22/07: il briefing dev'essere contestuale (confronto robusto +
coperti se presenti), mai fuorviante (niente "vs ieri").
"""
import os
from datetime import date

os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

from services.fastapi_worker import (  # noqa: E402
    _incasso_confronto_giorno_settimana,
    _coperti_scontrino_ieri,
)
from services.daily_briefing_service import (  # noqa: E402
    _buona_notizia_bullet,
    _buona_notizia_frase,
)

RID = "rist-xyz"


class _FakeQuery:
    """Mini query-builder che ignora i filtri e restituisce righe fisse."""

    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def gte(self, *_a, **_k):
        return self

    def lte(self, *_a, **_k):
        return self

    def lt(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows})()


class _FakeSB:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _FakeQuery(self._rows)


def _riga(data_iso, lordo10=0.0, lordo22=0.0, noiva=0.0):
    return {
        "data": data_iso,
        "fatturato_iva10": lordo10,
        "fatturato_iva22": lordo22,
        "altri_ricavi_noiva": noiva,
    }


# ── _incasso_confronto_giorno_settimana ─────────────────────────────────────

def test_confronto_richiede_minimo_occorrenze():
    # 21/07/2026 e' un martedi'. Solo 3 martedi' precedenti -> baseline corta -> None.
    ieri = date(2026, 7, 21)
    martedi = ["2026-07-14", "2026-07-07", "2026-06-30"]
    rows = [_riga(d, lordo10=10000) for d in martedi]
    assert _incasso_confronto_giorno_settimana(RID, _FakeSB(rows), ieri, 13000) is None


def test_confronto_sopra_la_media():
    ieri = date(2026, 7, 21)  # martedi'
    martedi = ["2026-07-14", "2026-07-07", "2026-06-30", "2026-06-23"]
    rows = [_riga(d, lordo10=10000) for d in martedi]  # media = 10000
    out = _incasso_confronto_giorno_settimana(RID, _FakeSB(rows), ieri, 13000)
    assert out is not None
    assert out["cfr_verso"] == "sopra"
    assert out["cfr_media"] == 10000
    assert out["cfr_delta_pct"] == 30


def test_confronto_in_linea_sotto_soglia():
    ieri = date(2026, 7, 21)
    martedi = ["2026-07-14", "2026-07-07", "2026-06-30", "2026-06-23"]
    rows = [_riga(d, lordo10=10000) for d in martedi]  # media = 10000
    # +3% < soglia 8% -> "in linea", nessuna enfasi.
    out = _incasso_confronto_giorno_settimana(RID, _FakeSB(rows), ieri, 10300)
    assert out is not None
    assert out["cfr_verso"] == "in_linea"


def test_confronto_ignora_altri_giorni_settimana():
    ieri = date(2026, 7, 21)  # martedi'
    # 4 martedi' a 10000 + rumore di sabati altissimi che NON devono entrare.
    martedi = ["2026-07-14", "2026-07-07", "2026-06-30", "2026-06-23"]
    sabati = ["2026-07-18", "2026-07-11", "2026-07-04"]
    rows = [_riga(d, lordo10=10000) for d in martedi]
    rows += [_riga(d, lordo10=22000) for d in sabati]
    out = _incasso_confronto_giorno_settimana(RID, _FakeSB(rows), ieri, 13000)
    assert out["cfr_media"] == 10000  # i sabati non hanno spostato la media


# ── _coperti_scontrino_ieri ─────────────────────────────────────────────────

def test_coperti_presenti():
    out = _coperti_scontrino_ieri(400, 12000.0)
    assert out == {"coperti": 400, "scontrino_medio": 30.0}


def test_coperti_assenti_ritorna_none():
    assert _coperti_scontrino_ieri(None, 12000.0) is None
    assert _coperti_scontrino_ieri(0, 12000.0) is None
    assert _coperti_scontrino_ieri("", 12000.0) is None


def test_coperti_senza_netto_ritorna_none():
    assert _coperti_scontrino_ieri(400, 0.0) is None


# ── Narrazione (bullet + frase) ─────────────────────────────────────────────

def _payload_completo():
    return {
        "tipo": "incasso_ieri",
        "incasso": 13345,
        "giorno_settimana": "martedì",
        "cfr_media": 10600,
        "cfr_delta_pct": 26,
        "cfr_verso": "sopra",
        "coperti": 406,
        "scontrino_medio": 27.5,
    }


def test_bullet_completo_contiene_tutto():
    b = _buona_notizia_bullet(_payload_completo())
    assert "13.345" in b
    assert "martedì" in b
    assert "26%" in b and "sopra" in b
    assert "406 coperti" in b
    assert "27,50" in b


def test_frase_solo_incasso_se_niente_altro():
    # Degrado: nessun confronto, nessun coperto -> solo l'incasso (come oggi).
    p = {"tipo": "incasso_ieri", "incasso": 13345, "giorno_settimana": "martedì"}
    f = _buona_notizia_frase(p)
    assert "13.345" in f
    assert "coperti" not in f
    assert "media" not in f


def test_frase_in_linea_non_usa_percentuale():
    p = {
        "tipo": "incasso_ieri", "incasso": 10300, "giorno_settimana": "martedì",
        "cfr_media": 10000, "cfr_verso": "in_linea", "cfr_delta_pct": 3,
    }
    f = _buona_notizia_frase(p)
    assert "in linea" in f
    assert "3%" not in f  # niente enfasi percentuale quando e' in linea
