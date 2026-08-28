"""Test guardia: la COMPLETEZZA dati onora ricavi_modalita_mensile.

Difetto trovato in audit il 28/08/2026, attivo sui dati veri: la RPC
gruppo_salute_componenti legge solo margini_mensili, dove una sede in modalità
mensile ha fatturato a 0 (i ricavi veri stanno in ricavi_modalita_mensile).
Risultato: OFFSIDE SPORTS PUB, con 437.898 € di ricavi 2026, veniva dichiarata
"senza fatturato" → entrambe le sedi del gruppo marcate "dati incompleti",
MOL del gruppo nascosto in pagina Catena.

È lo stesso difetto già corretto in _aggrega_sedi_mensili (vedi
test_gruppo_aggrega_sedi.py, "Bug 1: override vince sullo snapshot"): la
correzione non era mai stata propagata al percorso della completezza.
"""
from unittest.mock import MagicMock, patch

from services.routers.gruppo import (
    _applica_override_netto,
    _completezza_dati_pv,
    _salute_componenti_raw,
)


def _sb_vuoto():
    """sb con rpc/table che tornano vuoto: gli override si iniettano via patch."""
    sb = MagicMock()
    rpc_res = MagicMock()
    rpc_res.execute.return_value = MagicMock(data=[])
    sb.rpc.return_value = rpc_res
    tbl = MagicMock()
    for m in ("select", "in_", "eq", "gte", "lte"):
        getattr(tbl, m).return_value = tbl
    tbl.execute.return_value = MagicMock(data=[], count=0)
    sb.table.return_value = tbl
    return sb


class TestApplicaOverrideNetto:
    def test_override_sostituisce_netto_a_zero(self):
        """Il caso OFFSIDE: snapshot a 0, override con i ricavi veri."""
        rows = [{"ristorante_id": "a", "netto": 0, "n_fatture": 125, "personale": 10787}]
        with patch(
            "services.routers.gruppo._overrides_mese_sede",
            return_value={7: {"iva10": 53897.0, "iva22": 0.0, "altri": 0.0}},
        ):
            out = _applica_override_netto(_sb_vuoto(), rows, 2026, 7)
        assert out[0]["netto"] == 53897.0

    def test_senza_override_il_netto_resta_quello_della_rpc(self):
        rows = [{"ristorante_id": "a", "netto": 1234.5, "n_fatture": 3, "personale": 900}]
        with patch("services.routers.gruppo._overrides_mese_sede", return_value={}):
            out = _applica_override_netto(_sb_vuoto(), rows, 2026, 7)
        assert out[0]["netto"] == 1234.5

    def test_override_di_un_altro_mese_non_conta(self):
        """L'override esiste ma su un mese diverso da quello valutato."""
        rows = [{"ristorante_id": "a", "netto": 0, "n_fatture": 5, "personale": 800}]
        with patch(
            "services.routers.gruppo._overrides_mese_sede",
            return_value={3: {"iva10": 50000.0, "iva22": 0.0, "altri": 0.0}},
        ):
            out = _applica_override_netto(_sb_vuoto(), rows, 2026, 7)
        assert out[0]["netto"] == 0

    def test_override_a_zero_non_cancella_il_netto_della_rpc(self):
        """Un override tutto a zero non è un fatturato: non deve SOVRASCRIVERE.

        Il netto di partenza è > 0 di proposito: partendo da 0 il test non
        distinguerebbe "non ha sovrascritto" da "ha sovrascritto con 0" (è il
        mutante che toglie la guardia `lordo > 0`).
        """
        rows = [{"ristorante_id": "a", "netto": 4200.0, "n_fatture": 5, "personale": 800}]
        with patch(
            "services.routers.gruppo._overrides_mese_sede",
            return_value={7: {"iva10": 0.0, "iva22": 0.0, "altri": 0.0}},
        ):
            out = _applica_override_netto(_sb_vuoto(), rows, 2026, 7)
        assert out[0]["netto"] == 4200.0

    def test_somma_le_tre_componenti(self):
        rows = [{"ristorante_id": "a", "netto": 0, "n_fatture": 5, "personale": 800}]
        with patch(
            "services.routers.gruppo._overrides_mese_sede",
            return_value={7: {"iva10": 100.0, "iva22": 20.0, "altri": 5.0}},
        ):
            out = _applica_override_netto(_sb_vuoto(), rows, 2026, 7)
        assert out[0]["netto"] == 125.0

    def test_override_per_sede_non_contagia_le_altre(self):
        """Due sedi, override solo sulla prima: la seconda resta com'era."""
        rows = [
            {"ristorante_id": "a", "netto": 0, "n_fatture": 5, "personale": 800},
            {"ristorante_id": "b", "netto": 0, "n_fatture": 5, "personale": 800},
        ]

        def _per_sede(sb, rid, anno):
            return {7: {"iva10": 9000.0, "iva22": 0.0, "altri": 0.0}} if rid == "a" else {}

        with patch("services.routers.gruppo._overrides_mese_sede", side_effect=_per_sede):
            out = _applica_override_netto(_sb_vuoto(), rows, 2026, 7)
        assert out[0]["netto"] == 9000.0
        assert out[1]["netto"] == 0

    def test_lettura_fallita_tiene_i_valori_rpc(self):
        """Best-effort: un errore sugli override non azzera il dato della RPC."""
        rows = [{"ristorante_id": "a", "netto": 500.0, "n_fatture": 5, "personale": 800}]
        with patch(
            "services.routers.gruppo._overrides_mese_sede", side_effect=RuntimeError("giù")
        ):
            out = _applica_override_netto(_sb_vuoto(), rows, 2026, 7)
        assert out[0]["netto"] == 500.0


class TestSaluteComponentiApplicaGliOverride:
    """_salute_componenti_raw DEVE passare per l'override, non solo restituire la RPC.

    Senza questi test un mutante che rimuove la chiamata (`return rows` al posto
    di `return _applica_override_netto(...)`) sopravvive: gli altri test esercitano
    l'helper direttamente e non vedrebbero mai il collegamento spezzato.
    """

    def _sb_con_rpc(self, rows):
        sb = MagicMock()
        rpc_res = MagicMock()
        rpc_res.execute.return_value = MagicMock(data=rows)
        sb.rpc.return_value = rpc_res
        tbl = MagicMock()
        for m in ("select", "in_", "eq", "gte", "lte"):
            getattr(tbl, m).return_value = tbl
        tbl.execute.return_value = MagicMock(data=[], count=0)
        sb.table.return_value = tbl
        return sb

    def test_il_netto_uscito_e_quello_dell_override(self):
        sb = self._sb_con_rpc(
            [{"ristorante_id": "a", "netto": 0, "n_fatture": 125, "personale": 10787}]
        )
        with patch(
            "services.routers.gruppo._overrides_mese_sede",
            return_value={7: {"iva10": 53897.0, "iva22": 0.0, "altri": 0.0}},
        ):
            out = _salute_componenti_raw(sb, ["a"], anno=2026, mese=7)
        assert out[0]["netto"] == 53897.0

    def test_gli_override_sono_letti_sul_mese_valutato(self):
        """L'anno/mese passati all'helper sono quelli su cui gira la RPC."""
        sb = self._sb_con_rpc(
            [{"ristorante_id": "a", "netto": 0, "n_fatture": 5, "personale": 800}]
        )
        with patch("services.routers.gruppo._overrides_mese_sede") as m:
            m.return_value = {}
            _salute_componenti_raw(sb, ["a"], anno=2026, mese=3)
        assert m.call_args.args[2] == 2026


class TestCompletezzaConOverride:
    def test_sede_in_modalita_mensile_non_e_piu_incompleta(self):
        """Il difetto in forma end-to-end: con override, "il fatturato" non manca più."""
        rows = [{"ristorante_id": "a", "netto": 0, "n_fatture": 125, "personale": 10787}]
        with patch(
            "services.routers.gruppo._overrides_mese_sede",
            return_value={7: {"iva10": 53897.0, "iva22": 0.0, "altri": 0.0}},
        ):
            rows = _applica_override_netto(_sb_vuoto(), rows, 2026, 7)
        out = _completezza_dati_pv(_sb_vuoto(), ["a"], rows=rows)
        assert out == {}

    def test_senza_ricavi_da_nessuna_parte_resta_incompleta(self):
        """Il fix non deve dichiarare completo chi davvero non ha fatturato."""
        rows = [{"ristorante_id": "a", "netto": 0, "n_fatture": 125, "personale": 10787}]
        with patch("services.routers.gruppo._overrides_mese_sede", return_value={}):
            rows = _applica_override_netto(_sb_vuoto(), rows, 2026, 7)
        out = _completezza_dati_pv(_sb_vuoto(), ["a"], rows=rows)
        assert out == {"a": ["il fatturato"]}


class TestSaluteIndiciSecondoConsumatore:
    """L'override non tocca solo la completezza: alza anche l'INDICE di salute.

    `_salute_indici_batch` condivide `_salute_componenti_raw` e assegna 25 punti
    su 100 alla voce `netto > 0`. Una sede in modalità mensile li perdeva tutti
    pur avendo fatturato. È corretto che ora li prenda — ma è un secondo
    consumatore del fix, e senza questo test nessuno lo copre: chi domani vede
    l'indice salire di 25 punti non trova la ragione da nessuna parte.
    """

    def _sb_con_rpc(self, rows):
        sb = MagicMock()
        rpc_res = MagicMock()
        rpc_res.execute.return_value = MagicMock(data=rows)
        sb.rpc.return_value = rpc_res
        tbl = MagicMock()
        for m in ("select", "in_", "eq", "gte", "lte"):
            getattr(tbl, m).return_value = tbl
        tbl.execute.return_value = MagicMock(data=[], count=0)
        sb.table.return_value = tbl
        return sb

    def test_l_indice_sale_di_25_punti_con_l_override(self):
        from services.routers.gruppo import _salute_indici_batch

        rpc_rows = [{
            "ristorante_id": "a", "netto": 0, "n_fatture": 10,
            "n_needs_review": 0, "personale": 8000,
        }]

        with patch("services.routers.gruppo._overrides_mese_sede", return_value={}):
            rows_senza = _salute_componenti_raw(self._sb_con_rpc(rpc_rows), ["a"], anno=2026, mese=7)
            senza = _salute_indici_batch(_sb_vuoto(), ["a"], rows=rows_senza)

        with patch(
            "services.routers.gruppo._overrides_mese_sede",
            return_value={7: {"iva10": 53897.0, "iva22": 0.0, "altri": 0.0}},
        ):
            rows_con = _salute_componenti_raw(self._sb_con_rpc(rpc_rows), ["a"], anno=2026, mese=7)
            con = _salute_indici_batch(_sb_vuoto(), ["a"], rows=rows_con)

        assert senza["a"] == 75
        assert con["a"] == 100


class TestUnaLetturaPerSede:
    """Gli override si leggono una volta per sede, non una per riga.

    _overrides_mese_sede non è memoizzata e _applica_override_netto gira su 4
    chiamanti: senza la cache locale è una query per riga.
    """

    def test_due_righe_stessa_sede_una_sola_lettura(self):
        rows = [
            {"ristorante_id": "a", "netto": 0, "n_fatture": 5, "personale": 800},
            {"ristorante_id": "a", "netto": 0, "n_fatture": 5, "personale": 800},
            {"ristorante_id": "b", "netto": 0, "n_fatture": 5, "personale": 800},
        ]
        with patch("services.routers.gruppo._overrides_mese_sede") as m:
            m.return_value = {}
            _applica_override_netto(_sb_vuoto(), rows, 2026, 7)
        letture = [c.args[1] for c in m.call_args_list]
        assert letture == ["a", "b"]
