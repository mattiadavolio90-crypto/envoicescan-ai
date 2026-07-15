"""Test sparkline MOL in /api/home/kpi (services.fastapi_worker).

Miglioria: il blocco MOL della Home mostra un mini-grafico dell'andamento MOL
nei mesi dell'anno corrente. I dati arrivano nello stesso endpoint KPI
(mol_mensile[]), riusando i margini gia' caricati: nessuna query in piu'.

Regole verificate:
- solo i mesi CON dati entrano nello sparkline (un mese vuoto non e' uno zero
  reale, spezzerebbe la linea con un falso crollo);
- se resta < 2 punti, mol_mensile e' vuoto (niente linea da disegnare);
- l'anno di riferimento e' quello del mese mostrato.
"""
from unittest.mock import MagicMock, patch

import services.fastapi_worker as fw


_USER = {"id": "u-1", "piano": "base"}
_RID = "rist-spark"


def _patch_common(margini_per_anno, costi_fb_per_anno=None, costi_spese_per_anno=None):
    """Patcha le fonti dati anno: dict {anno: {mese: row_margini}} e costi."""
    costi_fb_per_anno = costi_fb_per_anno or {}
    costi_spese_per_anno = costi_spese_per_anno or {}

    def fake_carica(_uid, _rid, anno):
        return margini_per_anno.get(anno, {})

    def fake_costi(_uid, _rid, anno):
        return (costi_fb_per_anno.get(anno, {}), costi_spese_per_anno.get(anno, {}))

    return fake_carica, fake_costi


def _row(fatturato, mol=None):
    # Il MOL è ora RICALCOLATO da _kpi_periodo (netto − costi), il campo 'mol'
    # salvato non è più usato. Uso altri_ricavi_noiva (niente scorporo IVA) e
    # costi a zero -> MOL ricalcolato == fatturato, così i valori restano puliti.
    return {"altri_ricavi_noiva": fatturato}


def _call_kpi(margini_per_anno):
    fake_carica, fake_costi = _patch_common(margini_per_anno)
    sb = MagicMock()
    fw._HOME_KPI_CACHE.clear()
    with patch.object(fw, "_resolve_user_from_token", return_value=_USER), \
         patch.object(fw, "_get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value=_RID), \
         patch.object(fw, "_oggi_rome", return_value=__import__("datetime").date(2026, 5, 15)), \
         patch("services.margine_service.carica_margini_anno", side_effect=fake_carica), \
         patch("services.margine_service.calcola_costi_automatici_per_anno", side_effect=fake_costi):
        return fw.home_kpi(authorization="Bearer tok")


def test_sparkline_solo_mesi_con_dati():
    # oggi = maggio 2026 -> mese mostrato = aprile (ultimo completo).
    # Dati in gennaio, marzo, aprile (febbraio vuoto): lo sparkline salta febbraio.
    margini = {2026: {
        1: _row(1000, 100),
        3: _row(1200, 150),
        4: _row(1300, 200),
    }}
    resp = _call_kpi(margini)
    assert resp.has_data
    assert resp.periodo_label == "Aprile"
    mesi = [p.mese for p in resp.mol_mensile]
    assert mesi == [1, 3, 4]  # febbraio (vuoto) escluso, maggio non ancora completo
    assert resp.mol_mensile_anno == 2026
    # MOL ricalcolato == fatturato (costi 0, no scorporo su altri_ricavi_noiva).
    assert [p.mol for p in resp.mol_mensile] == [1000, 1200, 1300]


def test_sparkline_vuoto_se_un_solo_mese():
    # Solo aprile ha dati -> un solo punto -> niente sparkline.
    margini = {2026: {4: _row(1300, 200)}}
    resp = _call_kpi(margini)
    assert resp.has_data
    assert resp.mol_mensile == []
    assert resp.mol_mensile_anno is None


def test_fallback_mese_in_corso_se_nessun_mese_completo():
    # Cliente appena partito: dati SOLO nel mese in corso (maggio, oggi=15 mag),
    # nessun mese completo passato. La card deve mostrare maggio "in corso"
    # invece di restare vuota. Confronto soppresso (mese parziale).
    margini = {2026: {5: _row(2000)}}
    resp = _call_kpi(margini)
    assert resp.has_data
    assert resp.is_mese_in_corso is True
    assert "in corso" in resp.periodo_label.lower()
    assert resp.periodo_label.startswith("Maggio")
    assert resp.confronto_label is None
    assert resp.fatturato == 2000


def test_mese_completo_ha_priorita_sul_mese_in_corso():
    # Se esiste un mese completo con dati (aprile), NON si ripiega sul mese in
    # corso: si mostra aprile, con is_mese_in_corso False.
    margini = {2026: {4: _row(1300), 5: _row(2000)}}
    resp = _call_kpi(margini)
    assert resp.has_data
    assert resp.is_mese_in_corso is False
    assert resp.periodo_label == "Aprile"


def test_nessun_dato_da_nessuna_parte_resta_vuoto():
    # Nessun dato in nessun mese (nemmeno quello in corso): card vuota.
    resp = _call_kpi({2026: {}})
    assert resp.has_data is False
