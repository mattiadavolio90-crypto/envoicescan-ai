"""scripts/allarme_admin.py: l'allarme dei controlli GitHub che arriva una volta,
si ripete se critico e dice quando e' rientrato. La decisione sta nel DB
(test_sql_admin_allarmi.py); qui il messaggio e il comportamento quando la
memoria non risponde."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "allarme_admin", Path(__file__).resolve().parent.parent / "scripts" / "allarme_admin.py")
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)

ARGS = ["--chiave", "server_giu", "--testo", "Il server non risponde", "--link", "https://x", "--risolto", "Server di nuovo attivo"]


def _main(monkeypatch, problema, azione_db, telegram_ok=True, tg=True):
    inviati = []
    monkeypatch.setenv("SUPABASE_URL", "https://db")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    if tg:
        monkeypatch.setenv("TG_TOKEN", "t")
        monkeypatch.setenv("TG_CHAT_ID", "c")
    else:
        monkeypatch.delenv("TG_TOKEN", raising=False)
        monkeypatch.delenv("TG_CHAT_ID", raising=False)
    monkeypatch.setattr(script, "chiedi_azione", lambda *a, **k: azione_db)
    monkeypatch.setattr(script, "invia_telegram", lambda tok, chat, testo, sil: inviati.append((testo, sil)) or telegram_ok)
    codice = script.main([*ARGS, "--problema", problema])
    return codice, inviati


def test_problema_nuovo_critico_suona():
    testo, silenzioso = script.componi("invia", "critico", "Il server non risponde", "https://x", None)
    assert testo == "🔴 Il server non risponde\nhttps://x"
    assert silenzioso is False


def test_ripetizione_e_rientro():
    assert script.componi("ripeti", "critico", "Giu'", None, None)[0] == "🔴 Ancora: Giu'"
    assert script.componi("risolto", "critico", "Giu'", None, "Di nuovo su") == ("✅ Risolto: Di nuovo su", True)
    assert script.componi("risolto", "critico", "Giu'", None, None)[0] == "✅ Risolto: Giu'"


def test_un_allarme_da_oggi_non_suona():
    testo, silenzioso = script.componi("invia", "oggi", "Riepilogo", None, None)
    assert testo.startswith("🟠 ") and silenzioso is True


def test_zitto_e_niente_non_mandano_nulla():
    for azione in ("zitto", "niente", "sconosciuta"):
        assert script.componi(azione, "critico", "x", None, None)[0] is None


def test_memoria_giu_col_problema_avvisa_lo_stesso(monkeypatch):
    codice, inviati = _main(monkeypatch, "1", None)
    assert codice == 0
    assert len(inviati) == 1
    assert "Memoria allarmi non raggiungibile" in inviati[0][0]


def test_memoria_giu_senza_problema_tace(monkeypatch):
    codice, inviati = _main(monkeypatch, "0", None)
    assert (codice, inviati) == (0, [])


def test_la_memoria_dice_zitto(monkeypatch):
    assert _main(monkeypatch, "1", "zitto") == (0, [])


def test_rientro_manda_il_risolto(monkeypatch):
    codice, inviati = _main(monkeypatch, "0", "risolto")
    assert codice == 0 and inviati == [("✅ Risolto: Server di nuovo attivo", True)]


def test_un_messaggio_dovuto_che_non_parte_fa_rosso_il_run(monkeypatch):
    assert _main(monkeypatch, "1", "invia", telegram_ok=False)[0] == 1
    assert _main(monkeypatch, "1", "invia", tg=False)[0] == 1


def test_scrive_l_azione_per_i_passi_successivi(monkeypatch, tmp_path):
    out = tmp_path / "out"
    monkeypatch.setattr(script, "chiedi_azione", lambda *a, **k: "zitto")
    monkeypatch.setenv("SUPABASE_URL", "https://db")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    script.main([*ARGS, "--problema", "1"])
    assert out.read_text(encoding="utf-8") == "azione=zitto\n"
