"""La riga dei dati mancanti non parla di food cost ai negozi.

Residuo della fase 4 del piano consulente, chiuso il 25/09/2026: la riga unica
dei solleciti chiudeva sempre con «margini e food cost non sono completi», anche
per un negozio, dove il food cost non esiste (regola di dominio 7: ogni
deviazione per i negozi scatta sul settore, i ristoranti non vedono cambiare
nemmeno un'etichetta). Il settore arriva come argomento dalla generazione del
briefing, risolto una volta per sede.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

import services.daily_briefing_service as dbs

RISTORANTE = "margini e food cost non sono completi"
NEGOZIO = "i margini non sono completi"


def _incasso():
    return {"id": "i", "topic_key": "incasso_mancante", "severity": "warning",
            "title": "Manca l'incasso di ieri", "payload": {}, "source_type": "live"}


@pytest.mark.parametrize("settore, atteso, vietato", [
    ("ristorazione", RISTORANTE, NEGOZIO),
    ("retail", NEGOZIO, "food cost"),
])
def test_la_riga_dei_solleciti_segue_il_settore(settore, atteso, vietato):
    riga, _ = dbs._riga_solleciti([_incasso()], settore)
    assert riga.endswith(atteso + "."), riga
    assert vietato not in riga


def test_senza_settore_e_la_frase_dei_ristoranti():
    """Il default e' la ristorazione: i chiamanti che non passano il settore
    non cambiano di una virgola."""
    riga, _ = dbs._riga_solleciti([_incasso()])
    assert riga.endswith(RISTORANTE + ".")


@pytest.mark.parametrize("settore, atteso", [("ristorazione", RISTORANTE), ("retail", NEGOZIO)])
def test_il_settore_arriva_al_testo_del_briefing(settore, atteso):
    """Dal briefing intero, non dalla sola funzione: il settore deve
    attraversare _build_snapshot fino al testo."""
    snap = dbs._build_snapshot([_incasso()], use_ai=False, settore=settore)
    assert atteso in snap["narrative"], snap["narrative"]
    if settore == "retail":
        assert "food cost" not in snap["narrative"]


def test_la_generazione_risolve_il_settore_della_sede():
    """generate_and_save_briefing chiede il settore della SEDE e lo passa."""
    visti = []
    vero = dbs._build_snapshot

    def _spia(*a, **k):
        visti.append(k.get("settore"))
        return vero(*a, **k)

    class _SB:
        def table(self, _n):
            return self

        def upsert(self, *a, **k):
            return self

        def execute(self):
            return type("R", (), {"data": []})()

    with patch("services.settore_service.settore_sede", lambda rid, sb: "retail"), \
         patch.object(dbs, "_build_snapshot", _spia), \
         patch.object(dbs, "_ai_narrative", lambda *a, **k: None, create=True):
        dbs.generate_and_save_briefing("u1", "r1", [_incasso()], _SB())
    assert visti == ["retail"]


def test_anche_all_ai_la_riga_arriva_senza_food_cost():
    """Il percorso con l'AI riceve la stessa riga come bullet (🧩): se il
    settore non ci arrivasse, il modello riscriverebbe «food cost» a un negozio."""
    ricevuti = []

    def _finta_ai(bullets, template, numeri):
        ricevuti.extend(bullets)
        return template

    with patch.object(dbs, "_narrate_with_ai", _finta_ai):
        dbs._build_snapshot([_incasso()], use_ai=True, settore="retail")
    riga = [b for b in ricevuti if b.startswith("\U0001F9E9 ")]
    assert riga and NEGOZIO in riga[0] and "food cost" not in riga[0], ricevuti


@pytest.mark.parametrize("settore", ["retail", "ristorazione"])
def test_il_percorso_veloce_della_home_passa_il_settore(settore):
    """Il briefing istantaneo di /api/home/briefing (prima della rigenerazione
    in background) costruisce lo snapshot da solo: anche li' il settore della
    sede deve arrivare."""
    import services.fastapi_worker as fw
    from unittest.mock import MagicMock
    visti = []
    vero = dbs._build_snapshot

    def _spia(*a, **k):
        visti.append(k.get("settore"))
        return vero(*a, **k)

    sb = MagicMock()
    # home_briefing importa gli helper da daily_briefing_service al momento
    # della chiamata: si patchano li'.
    with patch.object(fw, "_resolve_user_from_token", return_value={"id": "u1"}), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_resolve_ristorante_id", return_value="r1"), \
         patch.object(fw, "_briefing_nome_referente", return_value=("Anna", [])), \
         patch.object(dbs, "get_today_briefing", return_value=None), \
         patch.object(dbs, "get_latest_briefing", return_value=None), \
         patch.object(fw, "_briefing_raccogli_notifiche", return_value=[_incasso()]), \
         patch("services.settore_service.settore_sede", lambda rid, s: settore), \
         patch.object(dbs, "_build_snapshot", _spia):
        fw.home_briefing(background_tasks=MagicMock(), authorization="Bearer t")
    assert visti == [settore], visti



# ── Il ripiego sul titolo nella riga dei solleciti (residuo della fase 4) ────

@pytest.mark.parametrize("topic, titolo, atteso", [
    ("fatturato_mancante", "Fatturato di Agosto 2026 non inserito", "il fatturato di agosto 2026"),
    ("costo_personale_mancante", "Costo del personale di Luglio 2026 mancante",
     "il costo del personale di luglio 2026"),
])
def test_senza_payload_il_mese_si_legge_dal_titolo_in_minuscolo(topic, titolo, atteso):
    """Le notifiche persistite possono arrivare senza mese/anno nel payload: la
    voce li ricava dal titolo, e a meta' frase il mese va minuscolo."""
    n = {"topic_key": topic, "title": titolo, "payload": {}}
    assert dbs._voce_sollecito(n) == (atteso, False)


def test_il_payload_vince_sul_titolo():
    n = {"topic_key": "fatturato_mancante", "title": "Fatturato di Maggio 2026",
         "payload": {"mese": "agosto", "anno": 2026}}
    assert dbs._voce_sollecito(n) == ("il fatturato di agosto 2026", False)


def test_senza_mese_da_nessuna_parte_la_voce_non_c_e():
    n = {"topic_key": "fatturato_mancante", "title": "Fatturato mancante", "payload": {}}
    assert dbs._voce_sollecito(n) is None
