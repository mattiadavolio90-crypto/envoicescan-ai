"""La catena dice quale punto vendita aspetta le fatture di fine mese.

La Home del PV, dal 16/10/2026, dice «In attesa delle fatture di fine mese: i
conti di settembre possono ancora cambiare» quando il mese appena chiuso ha la
merce ma nessuna fattura di merce negli ultimi giorni (`_mese_in_attesa`). La
catena non lo sapeva: confrontava quel PV con gli altri su un margine gonfiato e
poteva dire «tutto in ordine». Decisione di Mattia del 17/10: la catena mostra il
problema del punto vendita. Stessa regola e stessi numeri del PV
(`in_attesa_fine_mese` su netto e merce di `_merce_ok_per_sede`).
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from services import fastapi_worker as fw
from services.routers import gruppo


def _rank(rid, margine):
    return gruppo.RankingPV(ristorante_id=rid, nome=f"PV {rid}", margine_perc=margine,
                            fatturato=1000.0, colore="verde", dati_incompleti=False)


def _briefing(ranking, in_attesa, mese="settembre"):
    return gruppo._build_briefing(
        "G", ranking, salute_indice=90, salute_colore="verde", n_segnali=0, sev_max="info",
        incompleti_ids=set(), fatture_in_attesa_ids=in_attesa, mese_fatture=mese,
    ).narrativa


# ── La frase ────────────────────────────────────────────────────────────────

def test_il_pv_in_attesa_e_nominato_e_il_tutto_in_ordine_si_spegne():
    testo = _briefing([_rank("a", 40.0), _rank("b", 30.0)], {"a"})
    assert "PV a è in attesa delle fatture di fine settembre: lì i conti possono ancora cambiare." in testo, testo
    assert "tutto in ordine" not in testo.lower(), testo


def test_controllo_senza_attesa_il_tutto_in_ordine_resta():
    testo = _briefing([_rank("a", 40.0), _rank("b", 30.0)], set())
    assert "tutto in ordine" in testo.lower(), testo
    assert "fine settembre" not in testo


def test_il_pv_in_attesa_esce_dal_confronto_dei_margini():
    """Il suo margine e' piu' alto del reale: non puo' essere «il migliore»."""
    testo = _briefing([_rank("a", 40.0), _rank("b", 30.0), _rank("c", 20.0)], {"a"})
    assert "Va meglio PV b (30% di margine), più indietro PV c (20%)." in testo, testo


@pytest.mark.parametrize("ids, atteso", [
    ({"a", "b"}, "PV a e PV b sono in attesa"),
    ({"a", "b", "c"}, "PV a, PV b e PV c sono in attesa"),
    ({"a", "b", "c", "d"}, "4 punti vendita sono in attesa"),
])
def test_piu_punti_vendita(ids, atteso):
    ranking = [_rank(r, m) for r, m in (("a", 40.0), ("b", 30.0), ("c", 20.0), ("d", 10.0))]
    assert atteso in _briefing(ranking, ids)


def test_senza_mese_non_si_dice_nulla():
    testo = _briefing([_rank("a", 40.0), _rank("b", 30.0)], {"a"}, mese=None)
    assert "in attesa" not in testo and "Va meglio PV a" in testo, testo


# ── Chi e' in attesa: la regola del PV, per sede ───────────────────────────

def _sb(righe):
    q = MagicMock()
    q.table.return_value = q
    for m in ("select", "eq", "in_", "limit", "is_"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=righe)
    return q


def _in_attesa(auto, righe, coperta, oggi=date(2026, 10, 5), mese=9):
    out = set()
    with patch.object(gruppo, "_costi_mese_per_sede", return_value=auto), \
         patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
         patch.object(gruppo, "_oggi_rome", return_value=oggi), \
         patch.object(fw, "_fine_mese_coperta", side_effect=lambda sb, rid, a, m: coperta[rid]):
        gruppo._merce_ok_per_sede(_sb(righe), "u", list(auto), 2026, mese, in_attesa_out=out)
    return out


def _riga(rid, mese=9, **extra):
    return {"ristorante_id": rid, "mese": mese, "fatturato_iva10": 110000.0, **extra}


def test_per_sede_si_applica_la_regola_del_pv():
    auto = {"a": 30000.0, "b": 30000.0, "c": 30000.0, "d": 5000.0, "e": 0.0}
    righe = [_riga("a"), _riga("b"), _riga("c"), _riga("d"), _riga("e", altri_costi_fb=30000.0)]
    coperta = {"a": False, "b": True, "c": None, "d": False, "e": False}
    # a: merce senza fatture di fine mese -> in attesa
    # b: fine mese coperta; c: data non letta (niente stato inventato)
    # d: merce insufficiente (e' «da completare», non «in attesa»)
    # e: merce solo a mano, nessuna fattura: non ha una data, non resta grigia
    assert _in_attesa(auto, righe, coperta) == {"a"}


def test_la_data_di_fine_mese_si_legge_solo_dove_serve():
    """Una query per sede a ogni apertura della catena: solo per le sedi che
    possono essere in attesa (fatture di merce, incasso, merce sufficiente),
    come `_mese_in_attesa` nel PV."""
    auto = {"a": 30000.0, "d": 5000.0, "e": 0.0, "f": 30000.0}
    righe = [_riga("a"), _riga("d"), _riga("e", altri_costi_fb=30000.0), {"ristorante_id": "f", "mese": 9}]
    lette = []
    with patch.object(gruppo, "_costi_mese_per_sede", return_value=auto), \
         patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
         patch.object(gruppo, "_oggi_rome", return_value=date(2026, 10, 5)), \
         patch.object(fw, "_fine_mese_coperta", side_effect=lambda sb, rid, a, m: lette.append(rid)):
        gruppo._merce_ok_per_sede(_sb(righe), "u", list(auto), 2026, 9, in_attesa_out=set())
    assert lette == ["a"]


def test_senza_incasso_non_e_in_attesa():
    assert _in_attesa({"a": 30000.0}, [{"ristorante_id": "a", "mese": 9}], {"a": False}) == set()


def test_mese_in_corso_non_e_in_attesa():
    assert _in_attesa({"a": 30000.0}, [_riga("a", mese=10)], {"a": False}, mese=10) == set()


# ── L'endpoint vero ─────────────────────────────────────────────────────────

RIGA = {
    "mese": 9, "fatturato_iva10": 11_000, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
    "altri_costi_fb": 0, "altri_costi_spese": 0, "quote_riparto_fb": 0,
    "quote_riparto_spese": 0, "costo_dipendenti": 2_000, "costo_personale_extra": 0,
}


def test_overview_nomina_il_pv_in_attesa_del_mese_chiuso(monkeypatch):
    monkeypatch.setattr(gruppo, "_oggi_rome", lambda: date(2026, 10, 5))
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "in_", "eq", "lte", "order", "limit", "gte"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(
        data=[dict(RIGA, ristorante_id="a"), dict(RIGA, ristorante_id="b")], count=0)
    sb.table.return_value = q
    rpc_res = MagicMock()
    rpc_res.execute.return_value = MagicMock(data=[])
    sb.rpc.return_value = rpc_res
    with patch.object(gruppo, "_resolve_gruppo",
                      return_value=(sb, "u1", [{"id": "a"}, {"id": "b"}], "Gruppo",
                                    {"a": "PV a", "b": "PV b"}, ["a", "b"])), \
         patch.object(gruppo, "_anno_mese_corrente", return_value=(2026, 10)), \
         patch.object(gruppo, "_completezza_dati_pv", return_value={}), \
         patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
         patch.object(gruppo, "_fatture_arrivate_ieri_gruppo",
                      return_value={"n_assegnate": 0, "n_in_coda": 0}), \
         patch.object(fw, "_fine_mese_coperta", side_effect=lambda sb, rid, a, m: rid != "a"), \
         patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
               return_value={"a": ({9: 4_000.0}, {}), "b": ({9: 4_000.0}, {})}):
        testo = gruppo.gruppo_overview(authorization="Bearer t").briefing.narrativa
    assert "PV a è in attesa delle fatture di fine settembre" in testo, testo
    assert "PV b è in attesa" not in testo and "PV a e PV b" not in testo, testo
