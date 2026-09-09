"""Fase 6 (9/9/2026): il periodo della catena si dichiara, le soglie sono condivise.

Due divergenze PV↔catena, entrambe silenziose:

  6a. Il PV mostra UN mese e lo etichetta "· in corso" se parziale; la catena
      somma da gennaio al mese corrente (parziale) e scriveva solo "Anno 2026".
      Negli screenshot del 9/9 il gruppo segnava 710.885 EUR e il PV 0 EUR:
      due periodi diversi, affiancati senza che nulla lo dicesse.
  6b. Le soglie verde/giallo (80/50) erano consolidate in daily_briefing_service
      dal 2/9 — e gruppo.py le riscriveva come letterali in tre punti. I valori
      coincidevano; una soglia cambiata nel PV non sarebbe stata seguita qui.

I test passano dagli ENDPOINT veri (gruppo_overview e i due dialog): la riga da
presidiare vive li', non in un helper, e una copia del letterale nell'endpoint
sarebbe invisibile a un test sul solo helper.
"""
from unittest.mock import MagicMock, patch

import pytest

import services.daily_briefing_service as dbs
from services.routers import gruppo
from services.routers.gruppo import (
    RankingPV, SalutePV, _build_briefing, _colore_salute_o_grigio,
    _label_anno_parziale,
)


# ── 6a: l'etichetta dice l'arco e il mese in corso ───────────────────────────

def test_etichetta_dichiara_arco_e_mese_in_corso():
    assert _label_anno_parziale(2026, 9) == "Anno 2026 · gen–set, settembre in corso"
    assert _label_anno_parziale(2026, 12) == "Anno 2026 · gen–dic, dicembre in corso"


def test_etichetta_a_gennaio_non_scrive_gen_gen():
    assert _label_anno_parziale(2027, 1) == "Anno 2027 · gennaio in corso"


def test_etichetta_non_mente_mai_su_un_anno_chiuso():
    """Qualunque mese: mai la sola scritta "Anno N", che si legge come chiuso."""
    for m in range(1, 13):
        label = _label_anno_parziale(2026, m)
        assert label != "Anno 2026"
        assert "in corso" in label


RIGA = {
    "ristorante_id": "a", "mese": 6, "fatturato_iva10": 11_000,
    "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
    "altri_costi_fb": 0, "altri_costi_spese": 0,
    "quote_riparto_fb": 0, "quote_riparto_spese": 0,
    "costo_dipendenti": 1_000, "costo_personale_extra": 0,
}


def _sb():
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "in_", "eq", "lte", "order", "limit"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[RIGA])
    sb.table.return_value = q
    rpc_res = MagicMock()
    rpc_res.execute.return_value = MagicMock(data=[])
    sb.rpc.return_value = rpc_res
    return sb


def _patch_gruppo(indici=None):
    """Le patch comuni ai tre endpoint. `indici` forza gli indici di Salute per
    sede (None = lascia fare a _salute_indici_batch)."""
    patches = [
        patch.object(gruppo, "_resolve_gruppo",
                     return_value=(_sb(), "u1", [{"id": "a"}], "Gruppo",
                                   {"a": "PV a"}, ["a"])),
        patch.object(gruppo, "_anno_mese_corrente", return_value=(2026, 6)),
        patch.object(gruppo, "_completezza_dati_pv", return_value={}),
        patch.object(gruppo, "_costi_mese_per_sede", return_value={"a": 4_000.0}),
        patch.object(gruppo, "_overrides_mese_sede", return_value={}),
        patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
              return_value={"a": ({6: 4_000.0}, {})}),
        patch.object(gruppo, "_calcola_segnali", return_value=[]),
    ]
    if indici is not None:
        patches.append(patch.object(gruppo, "_salute_indici_batch", return_value=indici))
    return patches


def _con_patch(patches, fn):
    for p in patches:
        p.start()
    try:
        return fn()
    finally:
        for p in patches:
            p.stop()


def test_overview_dichiara_il_mese_in_corso():
    resp = _con_patch(_patch_gruppo(indici={"a": 90}),
                      lambda: gruppo.gruppo_overview(authorization="Bearer t"))
    assert resp.periodo_label == "Anno 2026 · gen–giu, giugno in corso"


@pytest.mark.parametrize("endpoint", [
    gruppo.gruppo_margini_coperti, gruppo.gruppo_spreco_categorie,
])
def test_i_dialog_sulla_vista_anno_dichiarano_il_mese_in_corso(endpoint):
    """Stessa finestra dell'overview (anno fino al mese corrente), stessa etichetta:
    correggere solo l'overview lascerebbe i dialog a dire "Anno 2026"."""
    resp = _con_patch(_patch_gruppo(), lambda: endpoint(mese=None, authorization="Bearer t"))
    assert resp.periodo_label == "Anno 2026 · gen–giu, giugno in corso"


def _sb_tag():
    """Come _sb, ma le righe hanno anche le colonne che gruppo_tag_analisi legge
    (tag e chiavi prodotto): le RPC rispondono vuote, il periodo non dipende da loro."""
    sb = _sb()
    sb.table.return_value.execute.return_value = MagicMock(
        data=[{**RIGA, "id": 1, "nome": "Vino", "emoji": None, "descrizione_key": "k"}],
    )
    return sb


def test_analisi_tag_sulla_vista_anno_dichiara_il_mese_in_corso():
    """Quarto consumatore della stessa finestra, non elencato dal piano: trovato
    verificando chi altro scriveva "Anno {anno}". Il suo commento diceva
    "coerente con le altre" — lo e' solo se anche l'etichetta lo e'."""
    patches = _patch_gruppo()
    patches[0] = patch.object(gruppo, "_resolve_gruppo",
                              return_value=(_sb_tag(), "u1", [{"id": "a"}], "Gruppo",
                                            {"a": "PV a"}, ["a"]))
    resp = _con_patch(patches, lambda: gruppo.gruppo_tag_analisi(
        tag_id=1, mese=None, authorization="Bearer t"))
    assert resp.periodo_label == "Anno 2026 · gen–giu, giugno in corso"


@pytest.mark.parametrize("endpoint", [
    gruppo.gruppo_margini_coperti, gruppo.gruppo_spreco_categorie,
])
def test_i_dialog_sul_mese_singolo_restano_al_mese(endpoint):
    """Il mese scelto dall'utente e' un mese intero: l'etichetta non cambia."""
    resp = _con_patch(_patch_gruppo(), lambda: endpoint(mese=3, authorization="Bearer t"))
    assert resp.periodo_label == "Marzo 2026"


# ── 6b: la catena segue le soglie del PV, non una copia ──────────────────────

def test_indice_non_noto_resta_grigio():
    """La semantica della Fase 2 ("non lo so" = grigio) sopravvive al refactor."""
    assert _colore_salute_o_grigio(None) == "grigio"


def test_colore_segue_le_soglie_del_pv(monkeypatch):
    assert _colore_salute_o_grigio(85) == "verde"
    monkeypatch.setattr(dbs, "SALUTE_SOGLIA_VERDE", 90)
    assert _colore_salute_o_grigio(85) == "giallo"


def test_soglia_verde_cambiata_nel_pv_la_catena_segue(monkeypatch):
    """Il test che mancava: a 85 la card PV e' verde con soglia 80 e gialla con
    soglia 90. La catena deve dire la stessa cosa dello stesso numero, sia sul
    colore del gruppo sia su quello del singolo PV."""
    def _overview():
        return _con_patch(_patch_gruppo(indici={"a": 85}),
                          lambda: gruppo.gruppo_overview(authorization="Bearer t"))

    prima = _overview()
    assert prima.salute_colore == "verde"
    assert prima.salute_pv[0].colore == "verde"

    monkeypatch.setattr(dbs, "SALUTE_SOGLIA_VERDE", 90)
    dopo = _overview()
    assert dopo.salute_indice == 85
    assert dopo.salute_colore == "giallo"
    assert dopo.salute_pv[0].colore == "giallo"


def _rank(rid, margine):
    return RankingPV(ristorante_id=rid, nome=rid.upper(), margine_perc=margine,
                     fatturato=1000.0, colore="verde", dati_incompleti=False)


def _sal(rid, indice):
    return SalutePV(ristorante_id=rid, nome=rid.upper(), indice=indice,
                    colore=_colore_salute_o_grigio(indice))


def _briefing_fallback_salute():
    """Ramo di ripiego di _build_briefing: senza incompleti_ids la completezza
    si stima dalla salute per-PV ("rossa" = da completare)."""
    return _build_briefing(
        "G", [_rank("a", 40.0), _rank("b", 20.0)],
        salute_indice=75, salute_colore="giallo", n_segnali=0, sev_max="info",
        salute_pv=[_sal("a", 60), _sal("b", 90)],
    )


def test_soglia_gialla_cambiata_nel_pv_il_briefing_di_gruppo_segue(monkeypatch):
    prima = _briefing_fallback_salute().narrativa
    assert "da completare" not in prima, "a 60 con soglia 50 la sede e' completa"
    assert "A è al 40%" in prima or "40%" in prima

    monkeypatch.setattr(dbs, "SALUTE_SOGLIA_GIALLO", 70)
    dopo = _briefing_fallback_salute().narrativa
    assert "1 punto vendita ha i dati di costo ancora da completare" in dopo
    # ...e la stessa sede esce dal confronto margini: il suo 40% non e' reale.
    assert "40%" not in dopo
