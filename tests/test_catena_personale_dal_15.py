"""La catena applica la regola del personale «dal 15» come il punto vendita.

Fase 1 del piano consulente (23/09/2026): il PV non chiede il costo del
personale del mese appena chiuso prima del 15 — la busta paga del consulente
del lavoro arriva a meta' mese (`_personale_gia_dovuto`). La regola era stata
portata ai 4 consumatori del PV ma non alla catena: dal 1° al 14 di ogni mese
`/catena` abbassava l'indice di salute della sede, emetteva «Mancano il costo
del personale» e la narrativa diceva «da completare», sulla stessa sede su cui
il PV taceva. Trovato dalla review pre-push del 24/09, visibile dal 1° ottobre.

Tre consumatori, ognuno provato il 14 (tace) e il 15 (parla):
- l'indice di salute per sede (`_salute_indici_batch`);
- il segnale `dati_mancanti` (`_calcola_segnali`);
- la frase della narrativa, attraverso l'endpoint vero (`gruppo_overview`).

Cosa NON cambia prima del 15: la sede resta fuori dal confronto dei margini e il
livello dati della card Conti resta "food". Il margine senza personale E'
gonfiato: e' un fatto sul numero, non una richiesta al cliente.
"""
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services.daily_briefing_service import calcola_indice_salute  # noqa: E402
from services.routers import gruppo  # noqa: E402

RID = "a"
IL_14 = date(2026, 10, 14)
IL_15 = date(2026, 10, 15)


def _oggi(monkeypatch, giorno):
    monkeypatch.setattr(gruppo, "_oggi_rome", lambda: giorno)


# ── Indice di salute ────────────────────────────────────────────────────────

def _indice(monkeypatch, giorno, personale=0.0):
    _oggi(monkeypatch, giorno)
    monkeypatch.setattr(gruppo, "_voci_spente_per_sede", lambda sb, ids: {r: set() for r in ids})
    row = {"ristorante_id": RID, "n_fatture": 100, "n_needs_review": 0,
           "netto": 1000.0, "personale": personale}
    return gruppo._salute_indici_batch(MagicMock(), [RID], rows=[row], costi_mese={RID: 500.0})[RID]


def _atteso(personale):
    return calcola_indice_salute(
        {"fatture": 100, "fatturato": 100, "personale": personale, "classificate": 100}, set(),
    )


def test_indice_il_14_il_personale_mancante_non_pesa(monkeypatch):
    assert _indice(monkeypatch, IL_14) == _atteso(100)


def test_indice_dal_15_il_personale_mancante_pesa(monkeypatch):
    assert _indice(monkeypatch, IL_15) == _atteso(0)
    assert _atteso(0) < _atteso(100), "il caso deve distinguere le due date"


def test_indice_a_gennaio_il_mese_chiuso_e_dicembre_dell_anno_prima(monkeypatch):
    """Il mese chiuso del 10 gennaio e' dicembre dell'ANNO PRIMA: un calcolo
    senza il giro d'anno cadrebbe su un mese «vecchio», quindi sempre dovuto."""
    assert _indice(monkeypatch, date(2027, 1, 10)) == _atteso(100)
    assert _indice(monkeypatch, date(2027, 1, 15)) == _atteso(0)


def test_indice_col_personale_presente_non_cambia_nulla(monkeypatch):
    assert _indice(monkeypatch, IL_14, personale=800.0) == _atteso(100)
    assert _indice(monkeypatch, IL_15, personale=800.0) == _atteso(100)


# ── Segnale dati_mancanti ───────────────────────────────────────────────────

_ALTRI_SEGNALI = {"margine_calo", "ricavi_mancanti", "prezzi_sopra",
                  "andamento_incasso", "food_cost_alto"}


def _segnali(monkeypatch, giorno, completezza):
    _oggi(monkeypatch, giorno)
    monkeypatch.setattr(gruppo, "_completezza_dati_pv", lambda *a, **k: completezza)
    monkeypatch.setattr(gruppo, "_costi_mese_per_sede", lambda *a, **k: {})
    out = gruppo._calcola_segnali(
        MagicMock(), ["a", "b"], {"a": "PV a", "b": "PV b"},
        segnali_off=_ALTRI_SEGNALI, user_id="u1",
    )
    return {s["ristorante_id"]: s["testo"] for s in out if s["tipo"] == "dati_mancanti"}


COMPLETEZZA = {
    "a": [gruppo._MANCA_PERSONALE],
    "b": ["il fatturato", gruppo._MANCA_PERSONALE],
}


def test_segnale_il_14_non_chiede_il_personale(monkeypatch):
    testi = _segnali(monkeypatch, IL_14, COMPLETEZZA)
    assert "a" not in testi, "alla sede manca solo il personale non ancora dovuto"
    assert testi["b"].startswith("Mancano il fatturato —"), testi["b"]
    assert "personale" not in testi["b"]


def test_segnale_dal_15_chiede_il_personale(monkeypatch):
    testi = _segnali(monkeypatch, IL_15, COMPLETEZZA)
    assert testi["a"].startswith("Mancano il costo del personale —"), testi["a"]
    assert testi["b"].startswith("Mancano il fatturato e il costo del personale —"), testi["b"]


def test_la_regola_non_tocca_la_completezza_grezza(monkeypatch):
    """`_completezza_dati_pv` resta il fatto (cosa manca davvero): la usano anche
    i dialog col periodo scelto, dove il margine senza personale e' inaffidabile
    a qualunque data."""
    _oggi(monkeypatch, IL_14)
    sb = MagicMock()
    rpc = MagicMock()
    rpc.execute.return_value = MagicMock(data=[
        {"ristorante_id": "a", "netto": 1000, "n_fatture": 5, "personale": 0},
    ])
    sb.rpc.return_value = rpc
    with patch.object(gruppo, "_applica_override_netto", lambda sb, rows, a, m: rows):
        assert gruppo._completezza_dati_pv(sb, ["a"]) == {"a": [gruppo._MANCA_PERSONALE]}


# ── Narrativa, attraverso l'endpoint vero ───────────────────────────────────

RIGA = {
    "mese": 6, "fatturato_iva10": 11_000,
    "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
    "altri_costi_fb": 0, "altri_costi_spese": 0,
    "quote_riparto_fb": 0, "quote_riparto_spese": 0,
    "costo_dipendenti": 0, "costo_personale_extra": 0,
}


def _overview(monkeypatch, giorno, completezza):
    _oggi(monkeypatch, giorno)
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
         patch.object(gruppo, "_completezza_dati_pv", return_value=completezza), \
         patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
         patch.object(gruppo, "_fatture_arrivate_ieri_gruppo",
                      return_value={"n_assegnate": 0, "n_in_coda": 0}), \
         patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
               return_value={"a": ({6: 4_000.0}, {}), "b": ({6: 4_000.0}, {})}):
        return gruppo.gruppo_overview(authorization="Bearer t")


FRASE_ATTESA = "il costo del personale di settembre non è ancora inserito"


def test_narrativa_il_14_informa_senza_chiedere(monkeypatch):
    resp = _overview(monkeypatch, IL_14, {"a": [gruppo._MANCA_PERSONALE]})
    testo = resp.briefing.narrativa
    assert "In un punto vendita " + FRASE_ATTESA in testo, testo
    assert "margine è più alto del reale" in testo
    assert "da completare" not in testo, testo
    # Il fatto sul numero resta: fuori dal confronto, card Conti in ambra.
    per_id = {r.ristorante_id: r for r in resp.ranking}
    assert per_id["a"].dati_incompleti is True and per_id["a"].margine_perc is None
    assert resp.kpi.livello_dati == "food"
    assert resp.kpi.pv_da_completare == 1


def test_narrativa_dal_15_torna_da_completare(monkeypatch):
    resp = _overview(monkeypatch, IL_15, {"a": [gruppo._MANCA_PERSONALE]})
    testo = resp.briefing.narrativa
    assert "1 punto vendita ha i dati di costo ancora da completare" in testo, testo
    assert "non è ancora inserito" not in testo


def test_narrativa_il_14_separa_chi_aspetta_da_chi_e_incompleto(monkeypatch):
    """La sede a cui manca anche altro resta «da completare»: la regola toglie
    solo il personale non dovuto, non assolve la sede."""
    resp = _overview(monkeypatch, IL_14, {
        "a": [gruppo._MANCA_PERSONALE],
        "b": ["il fatturato", gruppo._MANCA_PERSONALE],
    })
    testo = resp.briefing.narrativa
    assert "1 punto vendita ha i dati di costo ancora da completare" in testo, testo
    assert "In un punto vendita " + FRASE_ATTESA in testo, testo


def test_narrativa_plurale(monkeypatch):
    resp = _overview(monkeypatch, IL_14, {
        "a": [gruppo._MANCA_PERSONALE], "b": [gruppo._MANCA_PERSONALE],
    })
    assert "In 2 punti vendita " + FRASE_ATTESA in resp.briefing.narrativa


# ── _build_briefing: il «tutto in ordine» segue il PV ───────────────────────

def _rank(rid, margine, incompleti=False):
    return gruppo.RankingPV(ristorante_id=rid, nome=f"PV {rid}", margine_perc=margine,
                            fatturato=1000.0, colore="verde", dati_incompleti=incompleti)


@pytest.mark.parametrize("mese, atteso", [("settembre", True), (None, False)])
def test_chi_aspetta_il_personale_non_spegne_il_tutto_in_ordine(mese, atteso):
    """Nel PV, prima del 15, il personale mancante non rende rossa la salute e
    non e' un sollecito: il «Tutto in ordine» resta. La catena fa lo stesso.
    Senza il mese (dal 15) la sede torna incompleta e il verde si spegne."""
    out = gruppo._build_briefing(
        "G", [_rank("b", 30.0), _rank("a", None, incompleti=True)],
        salute_indice=90, salute_colore="verde", n_segnali=0, sev_max="info",
        incompleti_ids={"a"}, personale_in_attesa_ids={"a"}, mese_personale=mese,
    )
    assert ("tutto in ordine" in out.narrativa.lower()) is atteso, out.narrativa


def test_il_14_con_la_completezza_illeggibile_non_si_inventa_nulla(monkeypatch):
    """Il gate sul mese in attesa si guarda solo se la completezza e' stata
    letta: con None (RPC in errore) non c'e' niente da dire sul personale, e la
    card resta «non determinabile». Dal 15 il gate non scatta comunque, quindi
    il caso vive solo fra il 1° e il 14 (trovato dalla review del 24/09)."""
    resp = _overview(monkeypatch, IL_14, None)
    assert resp.kpi.livello_dati == "non_determinabile"
    assert "non è ancora inserito" not in resp.briefing.narrativa
