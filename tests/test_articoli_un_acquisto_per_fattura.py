"""Analisi Fatture -> Articoli: un acquisto e' una fattura.

Il GINSENG della TORREFAZIONE SEMPIONE contava 5 acquisti su 4 fatture (due
righe nella 1755/CV, screenshot di Mattia del 14/10/2026). «N°», prezzo medio,
fornitore principale e sotto-tabella contano ora i documenti, con la regola
dell'Osservatorio dei prezzi; quantita' e totale restano somme.
"""
import random
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import services.routers.fatture as fatture
from utils.voci_prezzo import prezzo_documento, una_riga_per_documento


def _riga(id_, file, prezzo, quantita=10, data="2026-05-30", fornitore="TORREFAZIONE SEMPIONE SRL", **altro):
    return {
        "id": id_, "descrizione": "GINSENG SOLUBILE", "categoria": "CAFFE E THE", "fornitore": fornitore,
        "totale_riga": round(prezzo * quantita, 2), "quantita": quantita, "prezzo_unitario": prezzo,
        "data_documento": data, "created_at": "2026-06-01T10:00:00+00:00", "needs_review": False,
        "ripartita_su_gruppo": False, "file_origine": file, "unita_misura": "PZ", "numero_riga": 1,
        "tipo_documento": "TD01", "data_competenza": None, "piva_cedente": None, **altro,
    }


GINSENG = [
    _riga(1, "1755.xml", 15.0, data="2026-05-30"),
    _riga(2, "1755.xml", 15.0, data="2026-05-30"),
    _riga(3, "1400.xml", 15.0, data="2026-04-30"),
    _riga(4, "1038.xml", 15.0, data="2026-03-31"),
    _riga(5, "1037.xml", 15.0, data="2026-03-31"),
]


def _con_finti(rows, chiamata):
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
        MagicMock(data={"nuovi_da": "2026-01-01T00:00:00+00:00"})
    )
    with patch.multiple(
        fatture,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _resolve_ristorante_id=MagicMock(return_value="pv-1"),
        _get_supabase_client=MagicMock(return_value=sb),
        _fetch_fatture_rows=MagicMock(return_value=rows),
        _load_num_documento_map=MagicMock(return_value={"1755.xml": "1755/CV"}),
    ):
        return chiamata()


def _articolo(rows):
    return _con_finti(rows, lambda: fatture.get_articoli_aggregati(authorization="Bearer x").articoli)[0]


def _sotto_tabella(rows):
    return _con_finti(rows, lambda: fatture.get_righe_articolo(descrizione="GINSENG SOLUBILE", authorization="Bearer x"))


def test_due_righe_della_stessa_fattura_sono_un_acquisto():
    art = _articolo(GINSENG)
    assert art.num_acquisti == 4
    assert art.quantita_totale == 50, "la quantita' resta la somma delle righe"
    assert art.totale_speso == 750


def test_il_prezzo_medio_e_la_media_per_fattura():
    """Ogni fattura pesa uguale (decisione di Mattia): 10 a 1 € e 1 a 4 € nella
    stessa fattura fanno 1,27 € quella fattura; con un'altra a 2 € la media e'
    (1,27 + 2) / 2, non la media delle tre righe (2,33)."""
    rows = [
        _riga(1, "a.xml", 1.0, quantita=10),
        _riga(2, "a.xml", 4.0, quantita=1),
        _riga(3, "b.xml", 2.0, quantita=1, data="2026-06-10"),
    ]
    art = _articolo(rows)
    assert art.prezzo_unit_medio == round(((10 * 1.0 + 4.0) / 11 + 2.0) / 2, 2)


def test_il_fornitore_principale_conta_le_fatture():
    rows = [
        _riga(1, "a.xml", 1.0, fornitore="A"), _riga(2, "a.xml", 1.0, fornitore="A"), _riga(3, "a.xml", 1.0, fornitore="A"),
        _riga(4, "b.xml", 1.0, fornitore="B"), _riga(5, "c.xml", 1.0, fornitore="B"),
    ]
    art = _articolo(rows)
    assert art.fornitore_principale == "B", "B ha 2 fatture, A una sola (con 3 righe)"


def test_la_sotto_tabella_ha_una_riga_per_fattura():
    righe = _sotto_tabella(GINSENG)
    assert [r.file_origine for r in righe] == ["1755.xml", "1400.xml", "1038.xml", "1037.xml"]
    prima = righe[0]
    assert prima.quantita == 20 and prima.totale_riga == 300 and prima.prezzo_unitario == 15.0
    assert prima.numero_documento == "1755/CV"


def test_una_quota_di_gruppo_resta_a_se_e_non_si_apre():
    rows = [
        _riga(1, "pv.xml", 10.0),
        _riga(-7, "struttura.xml", 12.0, ripartita_su_gruppo=True),
        _riga(-8, "struttura.xml", 12.0, ripartita_su_gruppo=True),
    ]
    righe = _sotto_tabella(rows)
    assert len(righe) == 2
    quota = next(r for r in righe if r.file_origine == "struttura.xml")
    assert quota.id < 0 and quota.ripartita_su_gruppo is True
    assert _articolo(rows).num_acquisti == 2


def test_unita_diverse_nella_stessa_fattura_restano_due_acquisti():
    rows = [_riga(1, "a.xml", 1.0), _riga(2, "a.xml", 12.0, quantita=1, unita_misura="CT")]
    assert _articolo(rows).num_acquisti == 2


def test_la_gemella_su_dizionari_da_lo_stesso_prezzo_della_regola_pandas():
    """`prezzo_documento` (righe come dizionari) e `una_riga_per_documento`
    (pandas) sono due scritture della stessa regola: su 300 fatture casuali
    devono dare lo stesso prezzo."""
    rnd = random.Random(20261014)
    righe = []
    for doc in range(300):
        for _ in range(rnd.choice([1, 1, 2, 3, 5])):
            righe.append({
                "doc": f"{doc}.xml", "data": "2026-05-01",
                "prezzo_unitario": rnd.choice([0.0, round(rnd.uniform(0.1, 90), 2), round(rnd.uniform(0.1, 90), 4)]),
                "quantita": rnd.choice([None, 0, 1, 2.5, 16, -2, 40]),
            })
    df = pd.DataFrame(righe)
    df["k"] = "X"
    attese = una_riga_per_documento(
        df[df["prezzo_unitario"] > 0], chiavi=["k"], file="doc", data="data",
        prezzo="prezzo_unitario", quantita="quantita",
    ).set_index("doc")["prezzo_unitario"].to_dict()
    per_doc = {}
    for r in righe:
        per_doc.setdefault(r["doc"], []).append(r)
    for doc, gruppo in per_doc.items():
        ottenuto = prezzo_documento(gruppo)
        if doc not in attese:
            assert ottenuto is None, doc
        else:
            assert ottenuto == pytest.approx(attese[doc], abs=1e-9), (doc, gruppo)


def test_il_trend_confronta_due_medie_per_fattura():
    """Il trend sul periodo precedente usa la stessa media: altrimenti
    confronterebbe una media per fattura con una media per riga."""
    ora = [_riga(1, "n.xml", 2.0, data="2026-05-10")]
    prima = [
        _riga(10, "p.xml", 1.0, quantita=10, data="2026-04-10"),
        _riga(11, "p.xml", 4.0, quantita=1, data="2026-04-10"),
    ]
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
        MagicMock(data={"nuovi_da": "2026-01-01T00:00:00+00:00"})
    )
    with patch.multiple(
        fatture,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _resolve_ristorante_id=MagicMock(return_value="pv-1"),
        _get_supabase_client=MagicMock(return_value=sb),
        _fetch_fatture_rows=MagicMock(side_effect=[ora, prima]),
    ):
        art = fatture.get_articoli_aggregati(data_da="2026-05-01", data_a="2026-05-31", authorization="Bearer x").articoli[0]
    precedente = (10 * 1.0 + 4.0) / 11
    assert art.prezzo_unit_trend_pct == round((2.0 - precedente) / precedente * 100, 1)
