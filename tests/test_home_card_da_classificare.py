"""La card «Righe da classificare» della Home (Fase 4bis) conta i soldi giusti.

La card promette «€ esclusi da margini e food cost»: deve contare le righe con
categoria 'Da Classificare' (le sole escluse oggi, regola di dominio 1) — NON
`needs_review`, che include anche righe classificate-ma-dubbie che nei margini
CI SONO (338 righe legacy misurate a DB il 3/9). Confondere le due popolazioni è
la stessa classe del difetto card-vs-campanella (2/9: 187 vs 112 sulla stessa
schermata).

E su errore la card NON può diventare verde: `_card_da_classificare` ritorna
None e il frontend mostra «Riprova» — un default a zero sarebbe il falso verde
già pagato da card-segnali.
"""
import pytest

from services.fastapi_worker import SaluteDaClassificare, SaluteResponse, _card_da_classificare


class _Query:
    """Finto builder PostgREST: registra i filtri, serve le righe a pagine."""

    def __init__(self, righe_per_filtri):
        self._righe_per_filtri = righe_per_filtri
        self.filtri = []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filtri.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self.filtri.append(("neq", col, val))
        return self

    def is_(self, col, val):
        self.filtri.append(("is", col, val))
        return self

    def range(self, offset, end):
        self._offset, self._end = offset, end
        return self

    def execute(self):
        righe = self._righe_per_filtri(self.filtri)

        class _R:
            data = righe[self._offset:self._end + 1]
        return _R()


class _SB:
    def __init__(self, righe_per_filtri):
        self._righe_per_filtri = righe_per_filtri
        self.query_fatte = []

    def table(self, nome):
        assert nome == "fatture"
        q = _Query(self._righe_per_filtri)
        self.query_fatte.append(q)
        return q


def _sb_con(dc_righe, dv_righe=()):
    """Serve `dc_righe` alle query su 'Da Classificare', `dv_righe` a quelle
    sulla fiducia. Qualunque altra combinazione di filtri è un errore del
    chiamante e fa fallire il test."""

    def righe_per_filtri(filtri):
        if ("eq", "categoria", "Da Classificare") in filtri:
            return list(dc_righe)
        if any(f[0] == "eq" and f[1] == "categoria_fiducia" for f in filtri):
            return list(dv_righe)
        raise AssertionError(f"query inattesa con filtri {filtri}")

    return _SB(righe_per_filtri)


def test_conta_le_righe_da_classificare_e_ne_somma_l_importo():
    sb = _sb_con([{"totale_riga": 100.5}, {"totale_riga": -20.25}, {"totale_riga": 0}])
    out = _card_da_classificare(sb, "rid")
    assert out == SaluteDaClassificare(righe=3, importo=80.25)


def test_zero_righe_e_un_verde_vero_non_un_default():
    out = _card_da_classificare(_sb_con([]), "rid")
    assert out == SaluteDaClassificare(righe=0, importo=0.0)


def test_su_errore_ritorna_none_mai_zero():
    """None = il frontend mostra l'errore. Uno zero qui direbbe al cliente
    «tutto classificato» proprio quando non lo sappiamo."""

    class _SBRotto:
        def table(self, _):
            raise RuntimeError("db giù")

    assert _card_da_classificare(_SBRotto(), "rid") is None


def test_flag_spento_non_interroga_la_fiducia():
    sb = _sb_con([{"totale_riga": 10}])
    _card_da_classificare(sb, "rid")
    assert len(sb.query_fatte) == 1, (
        "a flag Fase 4 spento la card conta SOLO le 'Da Classificare': le "
        "righe dubbie nei margini ci sono ancora, sommarle mentirebbe"
    )


def test_flag_acceso_somma_anche_le_da_verificare(monkeypatch):
    import config.constants as C
    monkeypatch.setattr(C, "ESCLUDI_DA_VERIFICARE_DAI_MARGINI", True)
    sb = _sb_con([{"totale_riga": 10}], dv_righe=[{"totale_riga": 5}, {"totale_riga": 2.5}])
    out = _card_da_classificare(sb, "rid")
    assert out == SaluteDaClassificare(righe=3, importo=17.5)


def test_il_campo_nella_risposta_ha_default_none():
    """Un backend vecchio (o la query fallita) produce None, e il tipo lo
    consente: i client di prima della Fase 4bis non si rompono."""
    campo = SaluteResponse.model_fields["da_classificare"]
    assert campo.default is None
