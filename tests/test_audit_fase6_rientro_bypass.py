"""Lo script che misura il rientro nel bypass deve riconoscere lo stato bloccato.

Il caso che conta e' lo stato reale del 4/9: 373 declassate ferme a 0 mentre il
gruppo di controllo distribuisce 720/128/16. Una prima stesura lo dichiarava
VERDE, perche' contava fra i "rientri" le 5 voci gia' a soglia — che sono un
residuo storico, non un movimento. Il segnale e' il movimento, non il totale.
"""
from unittest.mock import patch

import pytest

import scripts.audit_fase6_rientro_bypass as mod


def _voci(n, conf, streak, verified=False):
    return [{
        "descrizione": f"D{i}-{conf}-{streak}", "categoria": "CARNE",
        "confidence": conf, "verified": verified,
        "consecutive_correct_classifications": streak,
    } for i in range(n)]


def _esegui(righe, capsys):
    with patch.object(mod, "get_supabase_client", lambda: None), \
         patch.object(mod, "_fetch_all", lambda _sb: righe):
        assert mod.main() == 0
    return capsys.readouterr().out


def test_stato_bloccato_del_4_9_e_rosso(capsys):
    """Declassate ferme a 0 + controllo che si muove = via di rientro chiusa."""
    righe = (_voci(1671, "altissima", 0, verified=True)
             + _voci(373, "alta", 0) + _voci(5, "alta", 3)
             + _voci(720, "media", 0) + _voci(128, "media", 1) + _voci(16, "media", 2))
    out = _esegui(righe, capsys)
    assert "ROSSO" in out, "lo stato bloccato del 4/9 non viene riconosciuto"
    assert "VERDE" not in out
    assert "aggiorna_streak_classificazione" in out, "non indica dove guardare"


def test_voci_in_salita_sono_verdi(capsys):
    """Anche poche voci fra 1 e 2 provano che il contatore si muove."""
    righe = (_voci(340, "alta", 0) + _voci(21, "alta", 1) + _voci(12, "alta", 2)
             + _voci(720, "media", 0))
    out = _esegui(righe, capsys)
    assert "VERDE" in out
    assert "ROSSO" not in out


def test_nessun_traffico_non_e_un_allarme(capsys):
    """Tutto a 0 anche nel controllo: non si distingue 'via chiusa' da 'nessuna
    fattura elaborata'. Gridare al bug qui sarebbe un falso positivo."""
    righe = _voci(373, "alta", 0) + _voci(720, "media", 0)
    out = _esegui(righe, capsys)
    assert "INCONCLUSIVO" in out
    assert "ROSSO" not in out


def test_le_gia_a_soglia_non_bastano_a_dire_verde(capsys):
    """Il difetto della prima stesura: le voci gia' in bypass sono un residuo
    storico e non provano che qualcosa si sia mosso."""
    righe = _voci(373, "alta", 0) + _voci(5, "alta", 3) + _voci(720, "media", 0)
    out = _esegui(righe, capsys)
    assert "VERDE" not in out, "le voci gia' a soglia sono state contate come rientri"


def test_usa_la_costante_non_un_tre_cablato():
    """Se la soglia viene ritarata, lo script deve seguirla."""
    from config.constants import CONFERME_PER_BYPASS
    righe = _voci(10, "alta", CONFERME_PER_BYPASS - 1)
    with patch.object(mod, "get_supabase_client", lambda: None), \
         patch.object(mod, "_fetch_all", lambda _sb: righe):
        d = mod._distribuzione(righe)
    assert d[CONFERME_PER_BYPASS - 1] == 10
