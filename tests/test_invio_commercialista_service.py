"""L'invio al commercialista senza database (fase C): calendario, email, ZIP,
esito di Brevo, il thread del queue-worker.

Le date si scelgono dove Roma e UTC danno giorni diversi (31/12 alle 22:30Z, i
due cambi d'ora): e' li' che un calcolo in UTC sposterebbe un periodo di un
giorno, e un periodo spostato e' una fattura saltata o spedita due volte.
"""
from __future__ import annotations

import io
import logging
import threading
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from services import invio_commercialista_service as s
from services.invio_commercialista_guardia import DocumentoVerificato

ROMA = ZoneInfo("Europe/Rome")
UTC = timezone.utc


# ─── Calendario ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("frequenza,oggi,attesa", [
    ("settimanale", date(2026, 9, 23), date(2026, 9, 21)),
    ("settimanale", date(2026, 9, 21), date(2026, 9, 21)),
    ("settimanale", date(2026, 9, 20), date(2026, 9, 14)),
    ("quindicinale", date(2026, 9, 15), date(2026, 9, 1)),
    ("quindicinale", date(2026, 9, 16), date(2026, 9, 16)),
    ("quindicinale", date(2026, 8, 31), date(2026, 8, 16)),
    ("quindicinale", date(2026, 9, 1), date(2026, 9, 1)),
    ("mensile", date(2026, 9, 1), date(2026, 9, 1)),
    ("mensile", date(2026, 9, 30), date(2026, 9, 1)),
])
def test_ultima_scadenza(frequenza, oggi, attesa):
    assert s.ultima_scadenza(frequenza, oggi) == attesa


def test_frequenza_sconosciuta_solleva():
    with pytest.raises(ValueError):
        s.ultima_scadenza("annuale", date(2026, 9, 1))


def test_limite_due_anni_come_postgres():
    assert s.limite_due_anni(date(2026, 9, 25)) == date(2024, 9, 25)
    assert s.limite_due_anni(date(2028, 2, 29)) == date(2026, 2, 28)


@pytest.mark.parametrize("frequenza,ultimo,oggi,atteso", [
    ("mensile", None, date(2026, 9, 1), None),
    ("mensile", date(2026, 8, 31), date(2026, 9, 1), None),
    ("mensile", date(2026, 7, 31), date(2026, 9, 1), (date(2026, 8, 1), date(2026, 8, 31))),
    # l'invio del 1/9 e' fallito: il 2/9 si riprova e il periodo si allarga da solo
    ("mensile", date(2026, 7, 31), date(2026, 9, 2), (date(2026, 8, 1), date(2026, 9, 1))),
    ("mensile", date(2026, 9, 1), date(2026, 9, 2), None),
    ("settimanale", date(2026, 9, 13), date(2026, 9, 21), (date(2026, 9, 14), date(2026, 9, 20))),
    ("settimanale", date(2026, 9, 20), date(2026, 9, 21), None),
    ("settimanale", date(2026, 9, 20), date(2026, 9, 27), None),
    ("quindicinale", date(2026, 8, 31), date(2026, 9, 16), (date(2026, 9, 1), date(2026, 9, 15))),
    ("quindicinale", date(2026, 9, 15), date(2026, 9, 16), None),
    # l'ultimo invio riuscito e' di tre anni fa: si riparte dal limite dei 2 anni
    ("mensile", date(2023, 6, 10), date(2026, 9, 1), (date(2024, 9, 1), date(2026, 8, 31))),
])
def test_periodo_dovuto(frequenza, ultimo, oggi, atteso):
    assert s.periodo_dovuto(frequenza, ultimo, oggi) == atteso


@pytest.mark.parametrize("istante,dentro", [
    (datetime(2026, 12, 31, 22, 30, tzinfo=UTC), False),   # a Roma 23:30
    (datetime(2027, 1, 1, 0, 59, tzinfo=UTC), False),      # 01:59
    (datetime(2027, 1, 1, 1, 0, tzinfo=UTC), True),        # 02:00
    (datetime(2027, 1, 1, 3, 59, tzinfo=UTC), True),       # 04:59
    (datetime(2027, 1, 1, 4, 0, tzinfo=UTC), False),       # 05:00
    (datetime(2026, 7, 1, 0, 0, tzinfo=UTC), True),        # 02:00 d'estate
    (datetime(2026, 7, 1, 3, 0, tzinfo=UTC), False),       # 05:00 d'estate
    (datetime(2026, 3, 29, 0, 59, tzinfo=UTC), False),     # 01:59, poi si salta alle 03:00
    (datetime(2026, 3, 29, 1, 0, tzinfo=UTC), True),       # 03:00 ora legale
    (datetime(2026, 10, 25, 2, 30, tzinfo=UTC), True),     # 03:30 ora solare, dopo il ritorno
    (datetime(2026, 10, 25, 3, 30, tzinfo=UTC), True),     # 04:30
    (datetime(2026, 10, 25, 4, 0, tzinfo=UTC), False),     # 05:00
])
def test_finestra_notturna_a_roma(istante, dentro):
    assert s.e_finestra_notturna(s.a_roma(istante)) is dentro


def test_inizio_del_giorno_di_roma_in_utc():
    assert s.inizio_giorno_utc(date(2026, 7, 1)) == datetime(2026, 6, 30, 22, 0, tzinfo=UTC)
    assert s.inizio_giorno_utc(date(2027, 1, 1)) == datetime(2026, 12, 31, 23, 0, tzinfo=UTC)


@pytest.mark.parametrize("valore,atteso", [
    ("1", True), (" 1 ", True), ("", False), ("0", False), ("true", False), (None, False),
])
def test_interruttore(monkeypatch, valore, atteso):
    if valore is None:
        monkeypatch.delenv(s.ENV_ATTIVO, raising=False)
    else:
        monkeypatch.setenv(s.ENV_ATTIVO, valore)
    assert s.invio_attivo() is atteso


# ─── Email ───────────────────────────────────────────────────────────────────

DAL, AL, SCADE = date(2026, 8, 1), date(2026, 8, 31), date(2026, 10, 1)


def test_email_con_i_file():
    oggetto, corpo, testo = s.componi_email(
        "OFFSIDE SRL", "07863990961", DAL, AL, 12,
        [("Scarica le fatture", "https://x.supabase.co/object/sign/a.zip?token=abc&t=1")], SCADE,
    )
    assert oggetto == "Fatture ricevute dal 01/08/2026 al 31/08/2026 — OFFSIDE SRL"
    for parte in (corpo, testo):
        assert "12 file" in parte and "01/10/2026" in parte
        assert "Cassetto fiscale" in parte and "altri canali" in parte
    assert "https://x.supabase.co/object/sign/a.zip?token=abc&t=1" in testo
    assert 'href="https://x.supabase.co/object/sign/a.zip?token=abc&amp;t=1"' in corpo


def test_email_del_periodo_vuoto_senza_link():
    oggetto, corpo, testo = s.componi_email("OFFSIDE SRL", "07863990961", DAL, AL, 0, [], SCADE)
    assert "Dal 01/08/2026 al 31/08/2026 non sono arrivate" in testo
    assert "href" not in corpo and "http" not in testo
    assert "01/10/2026" not in testo


def test_email_ripulisce_il_nome():
    oggetto, corpo, testo = s.componi_email(
        "<b>Rossi</b>\r\nBcc: x@y.test", "07863990961", DAL, AL, 1, [("L", "https://x.test/a")], SCADE,
    )
    assert "\n" not in oggetto and "\r" not in oggetto
    assert "<b>" not in corpo and "&lt;b&gt;Rossi&lt;/b&gt;" in corpo


def test_email_senza_nome_usa_la_piva():
    oggetto, *_ = s.componi_email(None, "07863990961", DAL, AL, 0, [], SCADE)
    assert oggetto.endswith("— P.IVA 07863990961")


def test_nell_email_nessun_importo_ne_fornitore():
    """Il contenuto sta solo nei file: l'email non sa nulla delle fatture."""
    import inspect
    parametri = set(inspect.signature(s.componi_email).parameters)
    assert parametri == {"nome", "piva", "dal", "al", "n_file", "link", "scade"}


# ─── ZIP ─────────────────────────────────────────────────────────────────────

def _doc(n: int, nome: str | None = None) -> DocumentoVerificato:
    return DocumentoVerificato(receive_id=n, nome=nome or f"IT01234567890_{n:05d}.xml",
                               contenuto=f"<fattura n='{n}'/>".encode() * 50, identificativo=f"sdi{n}")


def _contenuto(percorso: Path) -> dict:
    with zipfile.ZipFile(percorso) as z:
        return {i.filename: (z.read(i.filename), i.date_time) for i in z.infolist()}


def test_un_mese_un_zip_con_gli_originali(tmp_path):
    pacchi = s._Pacchi(tmp_path, DAL, AL)
    arrivo = datetime(2026, 8, 3, 9, 15, tzinfo=ROMA)
    pacchi.aggiungi(arrivo, _doc(1))
    pacchi.aggiungi(arrivo, _doc(2))
    [parte] = pacchi.chiudi()
    assert parte.nome == "fatture_2026-08-01_2026-08-31.zip"
    assert parte.n_file == 2 and parte.byte == parte.percorso.stat().st_size
    contenuto = _contenuto(parte.percorso)
    assert contenuto["IT01234567890_00001.xml"] == (_doc(1).contenuto, (2026, 8, 3, 9, 15, 0))


def test_piu_mesi_sotto_soglia_un_solo_zip(tmp_path):
    pacchi = s._Pacchi(tmp_path, date(2026, 7, 1), AL)
    pacchi.aggiungi(datetime(2026, 7, 31, 23, 0, tzinfo=ROMA), _doc(1))
    pacchi.aggiungi(datetime(2026, 8, 1, 1, 0, tzinfo=ROMA), _doc(2))
    [parte] = pacchi.chiudi()
    assert parte.nome == "fatture_2026-07-01_2026-08-31.zip"
    assert set(_contenuto(parte.percorso)) == {"IT01234567890_00001.xml", "IT01234567890_00002.xml"}
    assert parte.n_file == 2


def test_oltre_la_soglia_uno_zip_per_mese(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "SOGLIA_DIVISIONE", 10)
    pacchi = s._Pacchi(tmp_path, date(2026, 7, 1), AL)
    pacchi.aggiungi(datetime(2026, 7, 31, 23, 0, tzinfo=ROMA), _doc(1))
    pacchi.aggiungi(datetime(2026, 8, 1, 1, 0, tzinfo=ROMA), _doc(2))
    parti = pacchi.chiudi()
    assert [(p.nome, p.etichetta, p.n_file) for p in parti] == [
        ("fatture_2026-07.zip", "Fatture arrivate a luglio 2026", 1),
        ("fatture_2026-08.zip", "Fatture arrivate a agosto 2026", 1),
    ]
    assert set(_contenuto(parti[1].percorso)) == {"IT01234567890_00002.xml"}


def test_un_mese_oltre_la_soglia_si_spezza(tmp_path, monkeypatch):
    """Prima un mese sopra i 50 MB falliva ogni notte: ora lo ZIP corrente si chiude
    appena supera la soglia, e il resto del mese va nel successivo."""
    monkeypatch.setattr(s, "SOGLIA_DIVISIONE", 10)
    pacchi = s._Pacchi(tmp_path, DAL, AL)
    for n in (1, 2, 3):
        pacchi.aggiungi(datetime(2026, 8, n, 9, 0, tzinfo=ROMA), _doc(n))
    parti = pacchi.chiudi()
    assert [(p.nome, p.etichetta, p.n_file) for p in parti] == [
        ("fatture_2026-08_1.zip", "Fatture arrivate a agosto 2026 (1 di 3)", 1),
        ("fatture_2026-08_2.zip", "Fatture arrivate a agosto 2026 (2 di 3)", 1),
        ("fatture_2026-08_3.zip", "Fatture arrivate a agosto 2026 (3 di 3)", 1),
    ]
    assert set(_contenuto(parti[2].percorso)) == {"IT01234567890_00003.xml"}


def test_sotto_la_soglia_il_mese_resta_intero(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "SOGLIA_DIVISIONE", 10 ** 6)
    pacchi = s._Pacchi(tmp_path, DAL, AL)
    for n in (1, 2, 3):
        pacchi.aggiungi(datetime(2026, 8, n, 9, 0, tzinfo=ROMA), _doc(n))
    [parte] = pacchi.chiudi()
    assert parte.n_file == 3 and len(_contenuto(parte.percorso)) == 3


def test_zip_oltre_il_limite_del_bucket_non_parte(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "LIMITE_FILE", 10)
    pacchi = s._Pacchi(tmp_path, DAL, AL)
    pacchi.aggiungi(datetime(2026, 8, 3, tzinfo=ROMA), _doc(1))
    with pytest.raises(s._Rinuncia) as exc:
        pacchi.chiudi()
    assert exc.value.avviso is True


def test_nessun_documento_nessuno_zip(tmp_path):
    assert s._Pacchi(tmp_path, DAL, AL).chiudi() == []


# ─── Misure della prova ──────────────────────────────────────────────────────

def test_misure_della_prova():
    documenti = [
        {"created": "2026-08-02T10:00:00Z", "date_sent": "2026-08-02T04:00:00Z"},
        {"created": "2026-08-10T10:00:00Z", "date_sent": "2026-08-01T10:00:00Z"},
        {"created": "2026-08-11T10:00:00Z", "date_sent": None},
    ]
    parte = s.Parte("a.zip", "x", Path("a.zip"), 2, 1234)
    assert s.misure_prova(documenti, 500, 497, [parte]) == (
        "prova: documenti 3; saldo prima 500, dopo 497; arrivo meno date_sent da 0.25 a 9.00 giorni; "
        "senza date_sent 1; zip 1, 1234 byte"
    )
    assert s.misure_prova([], None, None, []) == "prova: documenti 0; zip 0, 0 byte"


# ─── Brevo: tre esiti ────────────────────────────────────────────────────────

class _Risposta:
    def __init__(self, status, corpo=None):
        self.status_code = status
        self._corpo = corpo

    def json(self):
        if isinstance(self._corpo, Exception):
            raise self._corpo
        return self._corpo


@pytest.fixture
def brevo(monkeypatch):
    import requests

    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    chiamate = []
    timeouts = []

    def imposta(risposta):
        def post(url, json=None, headers=None, timeout=None):
            chiamate.append(json)
            timeouts.append(timeout)
            if isinstance(risposta, Exception):
                raise risposta
            return risposta
        monkeypatch.setattr(requests, "post", post)
        return chiamate
    imposta.timeouts = timeouts
    return imposta


def test_brevo_201_e_inviata(brevo):
    from services.email_service import brevo_invia_con_esito
    chiamate = brevo(_Risposta(201, {"messageId": "<abc@smtp-relay>"}))
    esito = brevo_invia_con_esito("studio@x.test", "", "Oggetto", "<p>ciao</p>", text_body="ciao")
    assert (esito.stato, esito.http_status, esito.message_id) == ("inviata", 201, "<abc@smtp-relay>")
    assert chiamate[0]["to"] == [{"email": "studio@x.test"}]
    assert chiamate[0]["textContent"] == "ciao"
    assert chiamate[0]["replyTo"]["email"] == "md@oneflux.it"


def test_brevo_201_senza_json_resta_inviata(brevo):
    from services.email_service import brevo_invia_con_esito
    brevo(_Risposta(201, ValueError("vuoto")))
    esito = brevo_invia_con_esito("studio@x.test", "Studio", "O", "<p/>")
    assert (esito.stato, esito.message_id) == ("inviata", None)


@pytest.mark.parametrize("status", [400, 401, 422, 499])
def test_brevo_4xx_e_rifiutata(brevo, status):
    from services.email_service import brevo_invia_con_esito
    brevo(_Risposta(status, {"code": "invalid_parameter"}))
    esito = brevo_invia_con_esito("studio@x.test", "", "O", "<p/>")
    assert (esito.stato, esito.http_status) == ("rifiutata", status)


@pytest.mark.parametrize("risposta", [_Risposta(500), _Risposta(503), _Risposta(302), _Risposta(200),
                                      TimeoutError("lento")])
def test_brevo_5xx_timeout_e_altro_sono_incerti(brevo, risposta):
    """Un timeout non dice che l'email non e' partita: rispedire sarebbe un doppione."""
    from services.email_service import brevo_invia_con_esito
    brevo(risposta)
    assert brevo_invia_con_esito("studio@x.test", "", "O", "<p/>").stato == "incerta"


def test_brevo_senza_chiave_non_chiama(monkeypatch):
    import requests
    from services.email_service import brevo_invia_con_esito
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.setattr(requests, "post", MagicMock(side_effect=AssertionError("chiamata")))
    esito = brevo_invia_con_esito("studio@x.test", "", "O", "<p/>")
    assert (esito.stato, esito.http_status) == ("rifiutata", None)


# ─── Storage ─────────────────────────────────────────────────────────────────

def test_archivio_carica_zip_privati_e_firma_i_link():
    bucket = MagicMock()
    bucket.create_signed_url.return_value = {"signedURL": "https://x/sign/a.zip?token=t"}
    sb = MagicMock()
    sb.storage.from_.return_value = bucket
    archivio = s.ArchivioSupabase(sb)
    sb.storage.from_.assert_called_once_with("invii-commercialista")
    archivio.carica("c/i/a.zip", b"PK")
    bucket.upload.assert_called_once_with("c/i/a.zip", b"PK", {"content-type": "application/zip", "upsert": "false"})
    assert archivio.link("c/i/a.zip", 2592000) == "https://x/sign/a.zip?token=t"
    bucket.create_signed_url.assert_called_once_with("c/i/a.zip", 2592000)


def test_archivio_senza_link_solleva():
    bucket = MagicMock()
    bucket.create_signed_url.return_value = {"error": "x"}
    sb = MagicMock()
    sb.storage.from_.return_value = bucket
    with pytest.raises(RuntimeError):
        s.ArchivioSupabase(sb).link("a.zip", 10)


def test_link_valido_trenta_giorni():
    assert int(s.VALIDITA_LINK.total_seconds()) == 30 * 86400


class _ArchivioFinto:
    def __init__(self, albero):
        self.albero = albero
        self.rimossi = []

    def elenca(self, prefisso):
        return self.albero.get(prefisso, [])

    def rimuovi(self, percorsi):
        self.rimossi += percorsi


def test_la_spazzata_toglie_solo_i_file_vecchi_a_ogni_livello():
    adesso = datetime(2026, 9, 25, 3, 0, tzinfo=UTC)
    vecchio = (adesso - timedelta(days=34)).isoformat()
    recente = (adesso - timedelta(days=32)).isoformat()
    archivio = _ArchivioFinto({
        "": [{"name": "cfg1", "id": None}, {"name": "sciolto.zip", "id": "f0", "created_at": vecchio}],
        "cfg1": [{"name": "inv1", "id": None}, {"name": "inv2", "id": None}],
        "cfg1/inv1": [{"name": "a.zip", "id": "f1", "created_at": vecchio}],
        "cfg1/inv2": [{"name": "b.zip", "id": "f2", "created_at": recente}, {"name": "", "id": "f3"}],
    })
    assert s.spazza_bucket(archivio, adesso) == 2
    assert sorted(archivio.rimossi) == ["cfg1/inv1/a.zip", "sciolto.zip"]


def test_la_spazzata_non_scende_oltre_due_cartelle():
    adesso = datetime(2026, 9, 25, tzinfo=UTC)
    archivio = _ArchivioFinto({
        "": [{"name": "a", "id": None}], "a": [{"name": "b", "id": None}], "a/b": [{"name": "c", "id": None}],
        "a/b/c": [{"name": "x.zip", "id": "f", "created_at": "2020-01-01T00:00:00Z"}],
    })
    assert s.spazza_bucket(archivio, adesso) == 0


# ─── Il thread ───────────────────────────────────────────────────────────────

def _thread(monkeypatch, esiti_ciclo, giri):
    fermo = threading.Event()
    attese = []
    pulizie = []

    def ciclo(sb, dip):
        esito = esiti_ciclo.pop(0) if esiti_ciclo else None
        if isinstance(esito, Exception):
            raise esito

    def dormi(secondi):
        attese.append(secondi)
        if len(attese) >= giri:
            fermo.set()

    monkeypatch.setattr(s, "ciclo", ciclo)
    monkeypatch.setattr(s, "pulizia", lambda sb, dip: pulizie.append(1))
    t = s.avvia_thread(lambda: object(), dip=MagicMock(), dormi=dormi, fermo=fermo)
    t.join(5)
    assert not t.is_alive()
    return attese, pulizie


def test_il_thread_non_muore_e_aspetta_di_piu_dopo_gli_errori(monkeypatch):
    attese, _ = _thread(monkeypatch, [RuntimeError("x"), RuntimeError("x"), None, RuntimeError("x")], giri=4)
    assert attese == [120, 240, 60, 120]


def test_il_thread_non_aspetta_oltre_un_ora(monkeypatch):
    attese, _ = _thread(monkeypatch, [RuntimeError("x")] * 8, giri=8)
    assert max(attese) == 3600


def test_la_pulizia_gira_al_primo_giro_poi_ogni_sei_ore(monkeypatch):
    _, pulizie = _thread(monkeypatch, [], giri=3)
    assert pulizie == [1]


def test_il_thread_e_un_demone():
    fermo = threading.Event()
    fermo.set()
    t = s.avvia_thread(lambda: object(), dip=MagicMock(), dormi=lambda x: None, fermo=fermo)
    t.join(5)
    assert t.daemon and t.name == "invio-commercialista"


def test_configurazione_segnalata_solo_se_acceso(monkeypatch, caplog):
    monkeypatch.delenv(s.ENV_ATTIVO, raising=False)
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    with caplog.at_level(logging.ERROR):
        s.segnala_configurazione()
    assert "mancano" not in caplog.text
    monkeypatch.setenv(s.ENV_ATTIVO, "1")
    monkeypatch.delenv("INVOICETRONIC_EXPORT_KEY", raising=False)
    monkeypatch.delenv("INVOICETRONIC_API_KEY", raising=False)
    with caplog.at_level(logging.ERROR):
        s.segnala_configurazione()
    assert "BREVO_API_KEY" in caplog.text and "INVOICETRONIC_API_KEY" in caplog.text


def test_ciclo_pianifica_solo_di_notte_e_con_l_interruttore(monkeypatch):
    chiamate = []
    monkeypatch.setattr(s, "gestisci_appese", lambda sb, dip: chiamate.append("appese"))
    monkeypatch.setattr(s, "pianifica", lambda sb, adesso, avvisa: chiamate.append("pianifica"))
    monkeypatch.setattr(s, "esegui_richiesti", lambda sb, dip: chiamate.append("esegui") or [])
    dip = MagicMock()
    for acceso, ora, attesa in [("1", 1, True), ("1", 12, False), ("0", 1, False)]:
        chiamate.clear()
        monkeypatch.setenv(s.ENV_ATTIVO, acceso)
        dip.orologio = lambda ora=ora: datetime(2027, 1, 1, ora, 30, tzinfo=UTC)
        s.ciclo(object(), dip)
        assert chiamate == (["appese", "pianifica", "esegui"] if attesa else ["appese", "esegui"])


def test_brevo_ha_sempre_un_timeout(brevo):
    """Senza, un Brevo bloccato congela il thread: niente piu' invii, righe appese
    e pulizie degli ZIP, e nessun avviso."""
    from services.email_service import brevo_invia_con_esito
    brevo(_Risposta(201, {"messageId": "x"}))
    brevo_invia_con_esito("studio@x.test", "", "O", "<p/>")
    assert brevo.timeouts == [(10, 30)]


def test_il_client_invoicetronic_si_chiude():
    from services.invoicetronic_client import ClientInvoicetronic
    http = MagicMock()
    ClientInvoicetronic("ik_live_x", http=http).chiudi()
    http.close.assert_called_once_with()



def test_la_spazzata_gira_anche_se_la_pulizia_del_registro_fallisce(monkeypatch):
    """La spazzata e' la rete sotto il registro: non deve dipendere da lui."""
    fatte = []
    monkeypatch.setattr(s, "rimuovi_file_scaduti", MagicMock(side_effect=RuntimeError("giu'")))
    monkeypatch.setattr(s, "spazza_bucket", lambda archivio, adesso: fatte.append(adesso))
    dip = MagicMock()
    dip.orologio = lambda: datetime(2026, 9, 25, tzinfo=UTC)
    s.pulizia(object(), dip)
    assert fatte == [datetime(2026, 9, 25, tzinfo=UTC)]



def test_l_elenco_del_bucket_va_a_pagine():
    """Oltre 1000 voci in una cartella la spazzata non deve fermarsi alla prima pagina."""
    bucket = MagicMock()
    pagine = {0: [{"name": f"f{i}"} for i in range(1000)], 1000: [{"name": "ultimo"}]}
    bucket.list.side_effect = lambda prefisso, opzioni: pagine.get(opzioni["offset"], [])
    sb = MagicMock()
    sb.storage.from_.return_value = bucket
    voci = s.ArchivioSupabase(sb).elenca("cfg")
    assert len(voci) == 1001 and voci[-1]["name"] == "ultimo"



def test_l_elenco_del_bucket_non_gira_all_infinito():
    """Se lo Storage ignorasse l'offset, ogni pagina sarebbe piena per sempre."""
    bucket = MagicMock()
    bucket.list.side_effect = lambda prefisso, opzioni: [{"name": f"f{i}"} for i in range(1000)]
    sb = MagicMock()
    sb.storage.from_.return_value = bucket
    with pytest.raises(RuntimeError, match="massimo di pagine"):
        s.ArchivioSupabase(sb).elenca("cfg")
    assert bucket.list.call_count == s.PAGINE_BUCKET
