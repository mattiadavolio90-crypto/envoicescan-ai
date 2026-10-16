"""Il filtro periodo di Analisi Fatture elenca solo i mesi che hanno righe.

Perche' esiste
==============
Audit di ottobre 2026 (F1a-04): `/api/fatture/mesi-disponibili` contava le testate
di `fatture_documenti`. Diciannove testate di dicembre 2025 senza nessuna riga
facevano comparire «Dicembre 2025 (19 fatture)», e scegliendolo KPI e articoli,
che leggono le righe, restavano vuoti. Ora i mesi si contano dalle righe con i
filtri della pagina (non cestinate, non escluse), come documenti distinti.
"""
from unittest.mock import MagicMock, patch

from services.routers import fatture


class _Tabella:
    def __init__(self, righe):
        self.righe = righe
        self.chiamate = []

    @property
    def not_(self):
        self.chiamate.append(("not_", ()))
        return self

    def __getattr__(self, nome):
        def _passa(*a, **k):
            self.chiamate.append((nome, a))
            return self
        return _passa

    def execute(self):
        return MagicMock(data=self.righe)


def _chiama(righe_fatture, testate):
    tabelle = {"fatture": _Tabella(righe_fatture), "fatture_documenti": _Tabella(testate)}
    sb = MagicMock()
    sb.table.side_effect = lambda nome: tabelle[nome]
    with patch.object(fatture, "_resolve_user_from_token", return_value={"id": "u"}), \
         patch.object(fatture, "_get_supabase_client", return_value=sb), \
         patch.object(fatture, "_resolve_ristorante_id", return_value="r"):
        resp = fatture.get_mesi_disponibili(authorization="Bearer t")
    return resp, tabelle


def test_una_testata_senza_righe_non_fa_comparire_il_mese():
    righe = [
        {"file_origine": "a.xml", "data_documento": "2026-01-05"},
        {"file_origine": "a.xml", "data_documento": "2026-01-05"},
        {"file_origine": "b.xml", "data_documento": "2026-01-20"},
        {"file_origine": "c.xml", "data_documento": "2026-02-03"},
    ]
    testate = [{"data_documento": "2025-12-%02d" % g} for g in range(9, 28)]
    resp, _ = _chiama(righe, testate)
    assert [(m["year"], m["month"], m["count"]) for m in resp.mesi] == [(2026, 2, 1), (2026, 1, 2)]


def test_le_righe_escluse_e_cestinate_non_contano():
    _, tabelle = _chiama([], [])
    chiamate = tabelle["fatture"].chiamate
    assert ("is_", ("deleted_at", "null")) in chiamate
    assert ("eq", ("oscurata", False)) in chiamate
    assert ("eq", ("ristorante_id", "r")) in chiamate
