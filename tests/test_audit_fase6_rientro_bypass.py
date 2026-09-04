"""Lo script che misura il rientro nel bypass deve riconoscere lo stato bloccato.

Il caso che conta e' lo stato reale del 4/9: 373 declassate ferme a 0 mentre il
gruppo di controllo distribuisce 720/128/16. Una prima stesura lo dichiarava
VERDE, perche' contava fra i "rientri" le 5 voci gia' a soglia — che sono un
residuo storico, non un movimento. Il segnale e' il movimento, non il totale.
"""
from unittest.mock import patch

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
    # Qui nemmeno il controllo si muove: e' INCONCLUSIVO, non ROSSO. Fermarsi a
    # "non VERDE" lascerebbe passare uno script che confonde i due, cioe' proprio
    # la distinzione per cui esiste.
    assert "INCONCLUSIVO" in out, "stato senza traffico riportato come diagnosi certa"


def test_usa_la_costante_non_un_tre_cablato():
    """Se la soglia viene ritarata, lo script deve seguirla."""
    from config.constants import CONFERME_PER_BYPASS
    righe = _voci(10, "alta", CONFERME_PER_BYPASS - 1)
    with patch.object(mod, "get_supabase_client", lambda: None), \
         patch.object(mod, "_fetch_all", lambda _sb: righe):
        d = mod._distribuzione(righe)
    assert d[CONFERME_PER_BYPASS - 1] == 10


def test_le_verificate_non_contano_come_movimento(capsys):
    """Il filtro `verified` deve reggere anche sotto mutazione.

    Una voce verificata da una persona e' gia' in bypass: il suo streak non e'
    un rientro. Se il filtro sparisse, una manciata di verificate con streak 1-2
    verrebbe contata come "movimento" e ribalterebbe il verdetto da ROSSO a
    VERDE — lo stesso modo di sbagliare che lo script esiste per impedire.
    Lo stato qui e' bloccato (declassate tutte a 0) e deve restare ROSSO.
    """
    righe = (_voci(30, "alta", 2, verified=True)      # gia' in bypass: non contano
             + _voci(373, "alta", 0)                   # declassate: ferme
             + _voci(720, "media", 0) + _voci(128, "media", 1))
    out = _esegui(righe, capsys)
    assert "ROSSO" in out, (
        "le voci verificate sono state contate come movimento delle declassate"
    )
    assert "VERDE" not in out


def test_streak_oltre_soglia_resta_nel_totale():
    """Il min() in _distribuzione accorpa tutto il sopra-soglia nell'ultima
    colonna: senza, quelle voci sparirebbero dalla riga E dal totale in
    silenzio. Oggi a DB nessuna supera la soglia, ma se venisse ritarata
    verso il basso il conteggio mentirebbe."""
    from config.constants import CONFERME_PER_BYPASS

    righe = _voci(7, "alta", CONFERME_PER_BYPASS + 5)
    d = mod._distribuzione(righe)
    assert d[CONFERME_PER_BYPASS] == 7, "le voci sopra soglia sono sparite dal conteggio"
    assert sum(d.values()) == 7, "il totale non torna: righe perse"


def test_il_controllo_esclude_le_declassate(capsys):
    """I due gruppi devono restare separati.

    Se il 'controllo' includesse anche le declassate, le loro 5 voci gia' a
    soglia lo farebbero sembrare in movimento e lo stato senza traffico
    diventerebbe un ROSSO — un allarme su una tabella ferma.
    """
    righe = _voci(370, "alta", 0) + _voci(5, "alta", 3) + _voci(720, "media", 0)
    out = _esegui(righe, capsys)
    assert "INCONCLUSIVO" in out, (
        "le declassate sono finite nel gruppo di controllo: nessuno dei due si muove"
    )
    assert "ROSSO" not in out


def test_controllo_che_si_muove_solo_a_soglia_conta(capsys):
    """Il gruppo di controllo si misura fino alla soglia INCLUSA.

    Se le sue voci fossero tutte gia' rientrate (streak >= soglia) e nessuna
    a 1-2, escluderle direbbe "nemmeno il controllo si muove" — INCONCLUSIVO —
    mentre il contatore ha dimostrato di funzionare, ed e' bloccato solo per
    le declassate: ROSSO.
    """
    from config.constants import CONFERME_PER_BYPASS

    righe = _voci(373, "alta", 0) + _voci(50, "media", CONFERME_PER_BYPASS)
    out = _esegui(righe, capsys)
    assert "ROSSO" in out, "il controllo si e' mosso ma non viene contato"
    assert "INCONCLUSIVO" not in out


def test_nessuna_declassata_non_e_un_allarme(capsys):
    """Senza voci declassate non c'e' niente da misurare: qualunque verdetto
    diagnostico sarebbe emesso su un insieme vuoto."""
    righe = _voci(500, "media", 1) + _voci(200, "altissima", 0, verified=True)
    out = _esegui(righe, capsys)
    assert "niente da misurare" in out
    for verdetto in ("ROSSO", "VERDE", "INCONCLUSIVO"):
        assert verdetto not in out, f"emesso {verdetto} senza voci declassate"
