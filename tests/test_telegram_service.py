"""Test per services.telegram_service. Nessuna chiamata di rete reale: httpx.post
è mockato. Il contratto da proteggere è il fail-safe: un alert Telegram che non
parte (config assente, errore rete, 4xx/5xx) non deve MAI sollevare — l'agent
notturno e i check di salute che lo chiamano non devono rompersi per questo.
"""
from unittest.mock import MagicMock, patch

from services import telegram_service as ts


def test_non_configurato_ritorna_false_senza_sollevare(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert ts.telegram_configurato() is False
    assert ts.invia_messaggio("qualsiasi") is False


def test_configurato_true_con_entrambe_le_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    assert ts.telegram_configurato() is True


def test_invio_riuscito_chiama_api_corretta(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOKEN123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    mock_resp = MagicMock(status_code=200)
    with patch.object(ts.httpx, "post", return_value=mock_resp) as m_post:
        ok = ts.invia_messaggio("ciao", silenzioso=True)
    assert ok is True
    args, kwargs = m_post.call_args
    assert "TOKEN123" in args[0]
    assert kwargs["json"]["chat_id"] == "999"
    assert kwargs["json"]["text"] == "ciao"
    assert kwargs["json"]["disable_notification"] is True
    assert "parse_mode" not in kwargs["json"]  # niente Markdown: fragile, vedi modulo


def test_http_4xx_ritorna_false_non_solleva(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    mock_resp = MagicMock(status_code=400, text="Bad Request")
    with patch.object(ts.httpx, "post", return_value=mock_resp):
        assert ts.invia_messaggio("x") is False


def test_eccezione_di_rete_ritorna_false_non_solleva(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    with patch.object(ts.httpx, "post", side_effect=ConnectionError("no network")):
        assert ts.invia_messaggio("x") is False


def test_testo_troncato_al_limite_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    mock_resp = MagicMock(status_code=200)
    testo_lungo = "x" * 5000
    with patch.object(ts.httpx, "post", return_value=mock_resp) as m_post:
        ts.invia_messaggio(testo_lungo)
    assert len(m_post.call_args.kwargs["json"]["text"]) == 4096
