"""Saldo crediti Invoicetronic: lettura, soglia, avvisi (passo 0, 25/09/2026).

A saldo zero Invoicetronic rifiuta ogni download con 403 `usage_limit_exceeded`
e in circa 2 ore le fatture in arrivo di TUTTI i clienti finiscono `dead`, senza
avviso. Qui si verifica che:
  - il 403 del saldo si riconosca dal `code`, non dal solo status;
  - GET /status venga letto solo verso l'host Invoicetronic, con la chiave;
  - gli avvisi partano quando servono e non a ogni controllo;
  - un controllo che non sa (saldo illeggibile) non taccia.
Nessuna rete: httpx e Telegram sono sostituiti.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from services import invoicetronic_saldo as its


ORA = 1_000_000.0
GIORNO = 24 * 3600


class _Orologio:
    def __init__(self, t: float = ORA) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _sorveglianza(soglia: int = 100, esito_invio: bool = True):
    inviati: list[str] = []

    def invia(testo: str) -> bool:
        inviati.append(testo)
        return esito_invio

    orologio = _Orologio()
    return its.SorveglianzaSaldo(soglia, invia=invia, orologio=orologio), inviati, orologio


# ─── Riconoscere il 403 del saldo ────────────────────────────────────────────

@pytest.mark.parametrize("corpo", [
    b'{"status": 403, "code": "usage_limit_exceeded", "detail": "Operazioni esaurite"}',
    '{"code": "usage_limit_exceeded"}',
    {"code": "usage_limit_exceeded"},
])
def test_403_con_codice_del_saldo_e_saldo_esaurito(corpo):
    assert its.e_saldo_esaurito(403, corpo)


@pytest.mark.parametrize("status,corpo", [
    (403, '{"code": "signature_limit_exceeded"}'),
    (403, '{"code": "subkey_not_allowed"}'),
    (403, '{"detail": "usage_limit_exceeded"}'),
    (403, '{"code": 403}'),
    (403, "Forbidden"),
    (403, b""),
    (403, None),
    (429, '{"code": "usage_limit_exceeded"}'),
    (402, '{"code": "usage_limit_exceeded"}'),
])
def test_altri_rifiuti_non_sono_saldo_esaurito(status, corpo):
    assert not its.e_saldo_esaurito(status, corpo)


def test_codice_problema_non_solleva_su_corpo_illeggibile():
    assert its.codice_problema(b"\xff\xfe non json") is None
    assert its.codice_problema("[1, 2]") is None
    assert its.codice_problema(12) is None


# ─── Soglia ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valore,atteso", [(None, 100), ("250", 250), ("abc", 100), ("0", 100), ("-5", 100), ("  ", 100)])
def test_soglia_configurata(monkeypatch, valore, atteso):
    if valore is None:
        monkeypatch.delenv(its.ENV_SOGLIA, raising=False)
    else:
        monkeypatch.setenv(its.ENV_SOGLIA, valore)
    assert its.soglia_configurata() == atteso


# ─── Lettura di GET /status ──────────────────────────────────────────────────

def _risposta(status: int, json_body=None, content: bytes = b""):
    r = mock.MagicMock()
    r.status_code = status
    r.content = content
    r.json.return_value = json_body
    return r


@pytest.fixture
def chiave(monkeypatch):
    monkeypatch.setenv("INVOICETRONIC_API_KEY", "chiave-di-test")
    monkeypatch.delenv("INVOICETRONIC_API_BASE", raising=False)


def test_leggi_saldo_chiama_status_con_la_chiave(chiave):
    with mock.patch("httpx.get", return_value=_risposta(200, {"operation_left": 87, "signature_left": 0})) as get:
        assert its.leggi_saldo() == 87
    args, kwargs = get.call_args
    assert args[0] == "https://api.invoicetronic.com/v1/status"
    assert kwargs["auth"] == ("chiave-di-test", "")


def test_leggi_saldo_senza_chiave_non_chiama_nulla(monkeypatch):
    monkeypatch.delenv("INVOICETRONIC_API_KEY", raising=False)
    with mock.patch("httpx.get") as get, pytest.raises(its.SaldoIllegibile, match="INVOICETRONIC_API_KEY assente"):
        its.leggi_saldo()
    get.assert_not_called()


@pytest.mark.parametrize("base", ["https://evil.example.com/v1", "http://api.invoicetronic.com/v1", "https://invoicetronic.com.evil.io/v1"])
def test_leggi_saldo_rifiuta_host_non_invoicetronic(chiave, monkeypatch, base):
    monkeypatch.setenv("INVOICETRONIC_API_BASE", base)
    with mock.patch("httpx.get") as get, pytest.raises(its.SaldoIllegibile, match="host"):
        its.leggi_saldo()
    get.assert_not_called()


@pytest.mark.parametrize("risposta,motivo", [
    (_risposta(401, content=b'{"code": "unauthorized"}'), "HTTP 401 unauthorized"),
    (_risposta(500), "HTTP 500"),
    (_risposta(200, {"signature_left": 3}), "operation_left"),
    (_risposta(200, {"operation_left": "87"}), "operation_left"),
    (_risposta(200, {"operation_left": True}), "operation_left"),
    (_risposta(200, [87]), "operation_left"),
])
def test_leggi_saldo_risposte_inservibili(chiave, risposta, motivo):
    with mock.patch("httpx.get", return_value=risposta), pytest.raises(its.SaldoIllegibile) as exc:
        its.leggi_saldo()
    assert motivo in str(exc.value)


def test_leggi_saldo_status_rifiutato_per_saldo_vale_zero(chiave):
    r = _risposta(403, content=b'{"status": 403, "code": "usage_limit_exceeded"}')
    with mock.patch("httpx.get", return_value=r):
        assert its.leggi_saldo() == 0


def test_leggi_saldo_altro_403_resta_illeggibile(chiave):
    r = _risposta(403, content=b'{"code": "subkey_not_allowed"}')
    with mock.patch("httpx.get", return_value=r), pytest.raises(its.SaldoIllegibile, match="HTTP 403 subkey_not_allowed"):
        its.leggi_saldo()


def test_leggi_saldo_errore_di_rete_non_espone_dettagli(chiave):
    with mock.patch("httpx.get", side_effect=ConnectionError("https://api.invoicetronic.com/v1/status chiave-di-test")):
        with pytest.raises(its.SaldoIllegibile) as exc:
            its.leggi_saldo()
    assert str(exc.value) == "chiamata fallita (ConnectionError)"


def test_leggi_saldo_risposta_non_json(chiave):
    r = _risposta(200)
    r.json.side_effect = ValueError("no json")
    with mock.patch("httpx.get", return_value=r), pytest.raises(its.SaldoIllegibile, match="non JSON"):
        its.leggi_saldo()


# ─── Quando avvisare ─────────────────────────────────────────────────────────

def test_saldo_sopra_soglia_nessun_avviso():
    s, inviati, _ = _sorveglianza()
    assert s.registra_lettura(100) is None
    assert s.registra_lettura(5000) is None
    assert inviati == []


@pytest.mark.parametrize("rimaste,atteso", [(100, None), (99, "basso"), (1, "basso"), (0, "ESAURITO"), (-3, "ESAURITO")])
def test_confini_della_soglia(rimaste, atteso):
    s, inviati, _ = _sorveglianza(soglia=100)
    s.registra_lettura(rimaste)
    if atteso is None:
        assert inviati == []
    else:
        assert len(inviati) == 1 and atteso in inviati[0]


def test_sotto_soglia_avvisa_una_volta_ogni_24_ore():
    s, inviati, orologio = _sorveglianza()
    assert s.registra_lettura(80) is not None
    orologio.t += 6 * 3600
    assert s.registra_lettura(75) is None
    orologio.t += GIORNO - 6 * 3600 - 1
    assert s.registra_lettura(70) is None
    orologio.t += 1
    assert s.registra_lettura(70) is not None
    assert len(inviati) == 2


def test_da_basso_a_esaurito_avvisa_subito():
    s, inviati, orologio = _sorveglianza()
    s.registra_lettura(80)
    orologio.t += 6 * 3600
    testo = s.registra_lettura(0)
    assert testo is not None and "ESAURITO" in testo
    assert len(inviati) == 2


def test_l_avviso_di_saldo_esaurito_non_promette_un_recupero_che_non_esiste():
    testo = its.testo_saldo_esaurito(0)
    assert "non ripartono da sole" in testo and "§4bis" in testo
    assert "riprova" not in testo.lower()


def test_da_esaurito_a_basso_non_riavvisa_prima_di_24_ore():
    s, inviati, orologio = _sorveglianza()
    s.registra_lettura(0)
    orologio.t += 6 * 3600
    assert s.registra_lettura(40) is None
    orologio.t += GIORNO
    assert "basso" in s.registra_lettura(40)
    assert len(inviati) == 2


def test_rientro_sopra_soglia_detto_una_volta_e_solo_dopo_un_avviso():
    s, inviati, orologio = _sorveglianza()
    s.registra_lettura(20)
    orologio.t += 3600
    testo = s.registra_lettura(5000)
    assert testo is not None and "sopra soglia" in testo
    assert s.registra_lettura(5000) is None
    assert len(inviati) == 2
    s.registra_lettura(20)
    assert len(inviati) == 3, "dopo il rientro un nuovo calo va avvisato subito"


def test_avviso_non_consegnato_si_ritenta_al_controllo_dopo():
    s, inviati, orologio = _sorveglianza(esito_invio=False)
    assert s.registra_lettura(50) is None
    orologio.t += 6 * 3600
    s.registra_lettura(50)
    assert len(inviati) == 2, "un avviso che Telegram non consegna non conta come dato"


def test_stima_dei_giorni_rimasti():
    s, inviati, _ = _sorveglianza()
    s.registra_lettura(87, consumo_30gg=70)
    assert "70 fatture" in inviati[0]
    assert "circa 37 giorni" in inviati[0]


@pytest.mark.parametrize("consumo", [None, 0])
def test_senza_consumo_niente_stima(consumo):
    s, inviati, _ = _sorveglianza()
    s.registra_lettura(87, consumo_30gg=consumo)
    assert "giorni" not in inviati[0]


def test_saldo_illeggibile_avvisa_al_secondo_fallimento_poi_una_volta_al_giorno():
    s, inviati, _ = _sorveglianza()
    esiti = [s.registra_fallimento("HTTP 401") for _ in range(10)]
    avvisati = [i + 1 for i, e in enumerate(esiti) if e is not None]
    assert avvisati == [2, 6, 10]
    assert "2 controlli" in inviati[0] and "HTTP 401" in inviati[0]


def test_una_lettura_riuscita_azzera_i_fallimenti():
    s, inviati, _ = _sorveglianza()
    s.registra_fallimento("timeout")
    s.registra_lettura(5000)
    assert s.registra_fallimento("timeout") is None
    assert inviati == []


def test_gli_avvisi_non_portano_dati_di_clienti():
    s, inviati, orologio = _sorveglianza()
    s.registra_lettura(50, consumo_30gg=70)
    orologio.t += GIORNO
    s.registra_lettura(0)
    s.registra_fallimento("x")
    s.registra_fallimento("x")
    for testo in inviati:
        assert "@" not in testo
        assert "07863990961" not in testo


# ─── Un giro del controllo ───────────────────────────────────────────────────

def test_controlla_saldo_illeggibile_conta_un_fallimento():
    s, inviati, _ = _sorveglianza()
    with mock.patch.object(its, "leggi_saldo", side_effect=its.SaldoIllegibile("HTTP 500")):
        its.controlla_saldo(s, mock.MagicMock())
        its.controlla_saldo(s, mock.MagicMock())
    assert len(inviati) == 1 and "HTTP 500" in inviati[0]


def test_controlla_saldo_sotto_soglia_usa_il_consumo():
    s, inviati, _ = _sorveglianza()
    with mock.patch.object(its, "leggi_saldo", return_value=60), \
         mock.patch.object(its, "consumo_ultimi_30_giorni", return_value=30) as consumo:
        its.controlla_saldo(s, mock.MagicMock())
    consumo.assert_called_once()
    assert "circa 60 giorni" in inviati[0]


def test_controlla_saldo_sopra_soglia_non_interroga_il_db():
    s, _, _ = _sorveglianza()
    with mock.patch.object(its, "leggi_saldo", return_value=500), \
         mock.patch.object(its, "consumo_ultimi_30_giorni") as consumo:
        its.controlla_saldo(s, mock.MagicMock())
    consumo.assert_not_called()


def test_controlla_saldo_con_consumo_rotto_avvisa_lo_stesso():
    s, inviati, _ = _sorveglianza()
    with mock.patch.object(its, "leggi_saldo", return_value=10), \
         mock.patch.object(its, "consumo_ultimi_30_giorni", side_effect=RuntimeError("db giù")):
        its.controlla_saldo(s, mock.MagicMock())
    assert len(inviati) == 1 and "giorni" not in inviati[0]


def test_consumo_ultimi_30_giorni_conta_le_fatture_sdi():
    sb = mock.MagicMock()
    catena = sb.table.return_value.select.return_value.eq.return_value.gte.return_value
    catena.execute.return_value = mock.MagicMock(count=70)
    prima = datetime.now(timezone.utc)
    assert its.consumo_ultimi_30_giorni(sb) == 70
    sb.table.assert_called_once_with("fatture_queue")
    sb.table.return_value.select.assert_called_once_with("id", count="exact", head=True)
    sb.table.return_value.select.return_value.eq.assert_called_once_with("source", "invoicetronic")
    colonna, da = sb.table.return_value.select.return_value.eq.return_value.gte.call_args.args
    assert colonna == "created_at"
    assert abs(datetime.fromisoformat(da) - (prima - timedelta(days=30))) < timedelta(seconds=5)


def test_consumo_senza_conteggio_e_none():
    sb = mock.MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock.MagicMock(count=None)
    assert its.consumo_ultimi_30_giorni(sb) is None


# ─── Avviso immediato su un 403 del saldo ────────────────────────────────────

@pytest.fixture
def senza_avvisi_403_precedenti(monkeypatch):
    monkeypatch.setattr(its, "_ultimo_avviso_403", None)


def test_avviso_403_al_massimo_ogni_6_ore(senza_avvisi_403_precedenti):
    orologio = _Orologio()
    with mock.patch.object(its, "_invia_telegram", return_value=True) as invia:
        assert its.avvisa_saldo_esaurito("worker", orologio=orologio) is True
        orologio.t += 6 * 3600 - 1
        assert its.avvisa_saldo_esaurito("worker", orologio=orologio) is False
        orologio.t += 1
        assert its.avvisa_saldo_esaurito("worker", orologio=orologio) is True
    assert invia.call_count == 2
    testo = invia.call_args.args[0]
    assert "usage_limit_exceeded" in testo and "§4bis" in testo and "worker" in testo
    assert "non ripartono da sole" in testo
    assert "riprova" not in testo.lower(), "Riprova non recupera le fatture fermate al webhook: non va consigliato"


def test_avviso_403_non_consegnato_si_ritenta(senza_avvisi_403_precedenti):
    orologio = _Orologio()
    with mock.patch.object(its, "_invia_telegram", side_effect=[False, True]) as invia:
        assert its.avvisa_saldo_esaurito("worker", orologio=orologio) is False
        assert its.avvisa_saldo_esaurito("worker", orologio=orologio) is True
    assert invia.call_count == 2
