"""Pianificatore ed esecutore dell'invio al commercialista su un Postgres vero
(fase C).

Il DB e' quello della migration: trigger, vincoli e indici unici decidono davvero.
Finti solo i confini: Invoicetronic, Storage, Brevo, saldo e Telegram. Le date si
calcolano da oggi (a Roma), perche' i vincoli del registro si misurano sul
`now()` del database: un test con date fisse scadrebbe fra due anni.
"""
from __future__ import annotations

import base64
import io
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from services import invio_commercialista_service as s
from services.email_service import EsitoBrevo
from services.invoicetronic_saldo import SaldoInvoicetronicEsaurito
from tests.test_invio_commercialista_guardia import _fattura

pytestmark = pytest.mark.sql

ROMA = ZoneInfo("Europe/Rome")
UTC = timezone.utc
U1 = "3e0e0000-0000-4000-8000-000000000001"
U2 = "3e0e0000-0000-4000-8000-000000000002"
SEDE_1 = "3e0e0000-0000-4000-8000-0000000000a1"
SEDE_2 = "3e0e0000-0000-4000-8000-0000000000a2"
PIVA = "07863990961"
AZIENDA = 1756
EMAIL = "studio@commercialista.test"


def _oggi() -> date:
    return datetime.now(ROMA).date()


def _alle(giorno: date, ora: int = 10, minuti: int = 0) -> datetime:
    return datetime.combine(giorno, time(ora, minuti), tzinfo=ROMA)


def _cur(db_sql, sql, *params):
    with db_sql.cursor() as cur:
        cur.execute(sql, params or None)
        return cur.fetchall() if cur.description else []


def _uno(db_sql, sql, *params):
    return _cur(db_sql, sql, *params)[0][0]


def _semina(db_sql, sdi=True):
    for uid, email in ((U1, "e1@ic.test"), (U2, "e2@ic.test")):
        _cur(db_sql, "INSERT INTO public.users (id, email, password_hash, nome_ristorante) VALUES (%s, %s, 'x', 'T')", uid, email)
    _cur(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo, sdi_attivo) "
                 "VALUES (%s, %s, 'OFFSIDE', %s, TRUE, %s)", SEDE_1, U1, PIVA, sdi)


def _config(db_sql, frequenza="mensile", attiva=True):
    return str(_uno(
        db_sql,
        "INSERT INTO public.invio_commercialista_config (user_id, piva, invoicetronic_company_id, invoicetronic_nome, "
        "email_destinatario, frequenza, data_partenza, attivo, consenso_ricevuto, consenso_data, consenso_email) "
        "VALUES (%s, %s, %s, 'OFFSIDE SRL', %s, %s, '2026-07-01', %s, %s, %s, %s) RETURNING id",
        U1, PIVA, AZIENDA, EMAIL, frequenza, attiva, attiva, date(2026, 9, 20) if attiva else None,
        EMAIL if attiva else None,
    ))


def _invio(db_sql, cid, tipo, dal, al, da="admin", creata=None):
    colonne = "config_id, user_id, piva, invoicetronic_company_id, destinatario, tipo, periodo_dal, periodo_al, richiesto_da"
    valori = [cid, U1, PIVA, AZIENDA, EMAIL, tipo, dal, al, da]
    if creata is not None:
        colonne += ", creata_at"
        valori.append(creata)
    return str(_uno(db_sql, f"INSERT INTO public.invio_commercialista_invii ({colonne}) VALUES "
                            f"({', '.join(['%s'] * len(valori))}) RETURNING id", *valori))


def _inviato(db_sql, cid, tipo, dal, al, creata=None):
    iid = _invio(db_sql, cid, tipo, dal, al, creata=creata)
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', email_tentata_at = now() WHERE id = %s", iid)
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'inviato' WHERE id = %s", iid)
    return iid


def _riga(db_sql, iid):
    with db_sql.cursor() as cur:
        cur.execute("SELECT * FROM public.invio_commercialista_invii WHERE id = %s", (iid,))
        nomi = [d.name for d in cur.description]
        return dict(zip(nomi, cur.fetchone()))


def _sb(db_sql):
    from tests.helpers_supabase_sql import ClientSQL
    return ClientSQL(db_sql)


def _documento(id_, arrivo: datetime, committente=PIVA, company=AZIENDA):
    xml = _fattura(body=f"<DatiGenerali><Numero>{id_}</Numero></DatiGenerali>").encode("utf-8")
    return {
        "id": id_, "company_id": company, "committente": committente,
        "created": arrivo.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "date_sent": (arrivo - timedelta(hours=6)).astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "encoding": "Base64", "payload": base64.b64encode(xml).decode(),
        "file_name": f"IT01234567890_{id_:05d}.xml", "identifier": f"sdi-{id_}",
    }


class _Client:
    def __init__(self, documenti):
        self.documenti = {d["id"]: d for d in documenti}
        self.azienda_restituita = {"id": AZIENDA, "vat": f"IT{PIVA}"}
        self.scaricati = []
        self.al_download = None
        self.chiuso = False

    def chiudi(self):
        self.chiuso = True

    def azienda(self, company_id):
        return self.azienda_restituita

    def elenco_ricevute(self, company_id):
        voci = sorted(self.documenti.values(), key=lambda d: d["created"], reverse=True)
        return [{k: v for k, v in d.items() if k not in ("payload", "encoding")} for d in voci]

    def documento(self, receive_id):
        self.scaricati.append(receive_id)
        if self.al_download:
            self.al_download(receive_id)
        return dict(self.documenti[receive_id])


class _Archivio:
    def __init__(self):
        self.file = {}
        self.rimossi = []

    def carica(self, percorso, dati):
        assert percorso not in self.file
        self.file[percorso] = dati

    def link(self, percorso, secondi):
        return f"https://firmato.test/{percorso}?scade={secondi}"

    def rimuovi(self, percorsi):
        self.rimossi += list(percorsi)
        for p in percorsi:
            self.file.pop(p, None)

    def elenca(self, prefisso):
        return []


class _Mondo:
    def __init__(self, documenti=()):
        self.client = _Client(list(documenti))
        self.archivio = _Archivio()
        self.email = []
        self.esito = EsitoBrevo("inviata", 201, "<m1@smtp-relay>")
        self.saldi = [500, 497]
        self.avvisi = []
        self.saldo_esaurito = []
        self.adesso = None

    def _saldo(self):
        valore = self.saldi.pop(0) if len(self.saldi) > 1 else self.saldi[0]
        if isinstance(valore, Exception):
            raise valore
        return valore

    def _invia(self, a, nome, oggetto, html, text_body=None, contesto=""):
        self.email.append({"a": a, "oggetto": oggetto, "html": html, "testo": text_body})
        if isinstance(self.esito, Exception):
            raise self.esito
        return self.esito

    def dip(self):
        return s.Dipendenze(
            client=lambda: self.client,
            archivio=lambda sb: self.archivio,
            invia_email=self._invia,
            leggi_saldo=self._saldo,
            soglia_saldo=lambda: 100,
            avvisa=lambda testo: self.avvisi.append(testo) or True,
            avvisa_saldo_esaurito=lambda origine: self.saldo_esaurito.append(origine) or True,
            orologio=lambda: self.adesso or datetime.now(UTC),
        )


@pytest.fixture
def acceso(monkeypatch):
    monkeypatch.setenv(s.ENV_ATTIVO, "1")
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")


def _tre_documenti(dal):
    return [_documento(i, _alle(dal + timedelta(days=i))) for i in (1, 2, 3)]


def _esegui(db_sql, mondo):
    return s.esegui_richiesti(_sb(db_sql), mondo.dip())


def _senza_dati_personali(avvisi):
    """Telegram non e' un sub-responsabile dichiarato (piano A3.6): negli avvisi
    solo id e motivi."""
    for testo in avvisi:
        for dato in (EMAIL, "OFFSIDE", PIVA):
            assert dato not in testo, (dato, testo)


# ─── Esecutore: la strada buona ──────────────────────────────────────────────

def test_il_primo_invio_spedisce_gli_originali_con_un_link(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))
    iid = _invio(db_sql, cid, "primo", dal, al)

    assert _esegui(db_sql, mondo) == ["inviato"]

    riga = _riga(db_sql, iid)
    assert riga["stato"] == "inviato" and riga["n_file"] == 3 and riga["documenti_ids"] == [1, 2, 3]
    assert riga["documenti_visti"] == [1, 2, 3]
    assert riga["brevo_http_status"] == 201 and riga["brevo_message_id"] == "<m1@smtp-relay>"
    assert riga["email_tentata_at"] is not None and riga["conclusa_at"] is not None
    percorso = f"{cid}/{iid}/fatture_{dal:%Y-%m-%d}_{al:%Y-%m-%d}.zip"
    assert riga["storage_paths"] == [percorso]
    assert timedelta(days=29, hours=23) < riga["link_scade_il"] - riga["iniziata_at"] < timedelta(days=30, hours=1)
    with zipfile.ZipFile(io.BytesIO(mondo.archivio.file[percorso])) as z:
        assert sorted(z.namelist()) == ["IT01234567890_00001.xml", "IT01234567890_00002.xml", "IT01234567890_00003.xml"]
        assert z.read("IT01234567890_00002.xml") == base64.b64decode(mondo.client.documenti[2]["payload"])
    [email] = mondo.email
    assert email["a"] == EMAIL and "OFFSIDE SRL" in email["oggetto"]
    assert f"https://firmato.test/{percorso}?scade=2592000" in email["testo"]
    ultimo_giorno_pieno = (s.a_roma(riga["link_scade_il"]).date() - timedelta(days=1)).strftime("%d/%m/%Y")
    assert f"vale fino al {ultimo_giorno_pieno}" in email["testo"]
    assert mondo.client.chiuso
    assert _uno(db_sql, "SELECT count(*) FROM public.email_rate_log WHERE destinatario = %s", EMAIL) == 1
    assert _uno(db_sql, "SELECT public.invio_commercialista_ultimo_giorno(%s)", cid) == al
    assert mondo.avvisi == []


def test_il_periodo_si_decide_sul_giorno_di_arrivo_a_roma(db_sql, acceso):
    """00:30 di Roma del primo giorno e' ancora il giorno prima in UTC: dentro.
    00:30 di Roma del giorno dopo l'ultimo e' ancora l'ultimo in UTC: fuori."""
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=10), _oggi() - timedelta(days=3)
    mondo = _Mondo([
        _documento(1, _alle(dal, 0, 30)),
        _documento(2, _alle(al, 23, 50)),
        _documento(3, _alle(al + timedelta(days=1), 0, 30)),
        _documento(4, _alle(dal - timedelta(days=1), 23, 50)),
    ])
    iid = _invio(db_sql, cid, "primo", dal, al)
    _esegui(db_sql, mondo)
    assert _riga(db_sql, iid)["documenti_ids"] == [1, 2]
    assert sorted(mondo.client.scaricati) == [1, 2]


def test_il_periodo_vuoto_si_comunica_senza_link(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo([_documento(9, _alle(dal - timedelta(days=5)))])
    mondo.saldi = [RuntimeError("il saldo non serve senza download")]
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["inviato"]
    riga = _riga(db_sql, iid)
    assert (riga["n_file"], riga["storage_paths"], riga["documenti_ids"]) == (0, None, [])
    assert mondo.archivio.file == {} and "non sono arrivate" in mondo.email[0]["testo"]


def test_la_prova_misura_e_non_spedisce_anche_a_invio_spento(db_sql, monkeypatch):
    monkeypatch.delenv(s.ENV_ATTIVO, raising=False)
    _semina(db_sql)
    cid = _config(db_sql, attiva=False)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))
    iid = _invio(db_sql, cid, "prova", dal, al)
    assert _esegui(db_sql, mondo) == ["prova_ok"]
    riga = _riga(db_sql, iid)
    assert riga["stato"] == "prova_ok" and riga["n_file"] == 3 and riga["byte_totali"] > 0
    assert riga["motivo"].startswith("prova: documenti 3; saldo prima 500, dopo 497; arrivo meno date_sent da 0.25 a 0.25")
    assert riga["storage_paths"] is None and riga["email_tentata_at"] is None
    assert mondo.email == [] and mondo.archivio.file == {}
    assert _uno(db_sql, "SELECT count(*) FROM public.email_rate_log") == 0


def test_a_invio_spento_parte_solo_la_prova(db_sql, monkeypatch):
    monkeypatch.delenv(s.ENV_ATTIVO, raising=False)
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    mondo = _Mondo()
    assert _esegui(db_sql, mondo) == ["errore"]
    assert _riga(db_sql, iid)["motivo"] == "invio_spento"
    assert mondo.email == [] and mondo.client.scaricati == []


def test_una_riga_gia_presa_non_si_riprende(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', iniziata_at = now() WHERE id = %s", iid)
    assert _esegui(db_sql, _Mondo()) == []


# ─── Esecutore: la guardia blocca e sospende ─────────────────────────────────

def test_un_documento_di_un_altro_destinatario_blocca_tutto_e_sospende(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    documenti = _tre_documenti(dal) + [_documento(7, _alle(dal - timedelta(days=90)), committente="12345678903")]
    mondo = _Mondo(documenti)
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["bloccato"]
    riga = _riga(db_sql, iid)
    assert (riga["stato"], riga["motivo"]) == ("bloccato", "documento_con_altro_destinatario")
    assert mondo.client.scaricati == [] and mondo.email == []
    sospesa = _cur(db_sql, "SELECT sospesa_at IS NOT NULL, sospesa_motivo FROM public.invio_commercialista_config WHERE id = %s", cid)[0]
    assert sospesa == (True, "documento_con_altro_destinatario")
    assert len(mondo.avvisi) == 1 and "BLOCCATO" in mondo.avvisi[0]
    _senza_dati_personali(mondo.avvisi)


def test_la_piva_passata_anche_a_un_altro_account_sospende_davvero(db_sql, acceso):
    """E' il caso in cui il trigger della configurazione rifiutava la sospensione."""
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    _cur(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) VALUES (%s, %s, 'B', %s, TRUE)", SEDE_2, U2, PIVA)
    assert _esegui(db_sql, _Mondo()) == ["bloccato"]
    assert _riga(db_sql, iid)["motivo"] == "piva_non_solo_del_cliente"
    assert _uno(db_sql, "SELECT sospesa_at IS NOT NULL FROM public.invio_commercialista_config WHERE id = %s", cid) is True


def test_un_file_che_non_e_del_cliente_blocca_dopo_il_download(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    documenti = _tre_documenti(dal)
    altro = _fattura(cessionario=(
        "<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>12345678903</IdCodice>"
        "</IdFiscaleIVA></DatiAnagrafici></CessionarioCommittente>"
    )).encode()
    documenti[1]["payload"] = base64.b64encode(altro).decode()
    mondo = _Mondo(documenti)
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["bloccato"]
    assert _riga(db_sql, iid)["stato"] == "bloccato"
    assert mondo.archivio.file == {} and mondo.email == []


# ─── Esecutore: errori che non consumano il periodo ──────────────────────────

def test_saldo_insufficiente_non_scarica_niente(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))
    mondo.saldi = [102]
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["errore"]
    assert _riga(db_sql, iid)["motivo"] == "saldo_insufficiente (102 operazioni, 3 documenti)"
    assert mondo.client.scaricati == [] and len(mondo.avvisi) == 1
    _senza_dati_personali(mondo.avvisi)


def test_saldo_giusto_alla_soglia_basta(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))
    mondo.saldi = [103]
    _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["inviato"]


def test_saldo_esaurito_durante_i_download(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))

    def esaurito(receive_id):
        if receive_id == 2:
            raise SaldoInvoicetronicEsaurito("usage_limit_exceeded")
    mondo.client.al_download = esaurito
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["errore"]
    assert _riga(db_sql, iid)["motivo"] == "saldo_invoicetronic_esaurito"
    assert mondo.saldo_esaurito == ["invio_commercialista"]
    assert _uno(db_sql, "SELECT public.invio_commercialista_ultimo_giorno(%s)", cid) is None
    _invio(db_sql, cid, "primo", dal, al)


def test_brevo_rifiuta_errore_e_file_tolti_subito(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))
    mondo.esito = EsitoBrevo("rifiutata", 400)
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["errore"]
    riga = _riga(db_sql, iid)
    assert (riga["stato"], riga["brevo_http_status"], riga["motivo"]) == ("errore", 400, "brevo_rifiutata_http_400")
    assert riga["file_rimossi_at"] is not None and mondo.archivio.file == {}
    assert mondo.archivio.rimossi == riga["storage_paths"] and len(mondo.avvisi) == 1
    _senza_dati_personali(mondo.avvisi)


@pytest.mark.parametrize("esito", [EsitoBrevo("incerta", 502), EsitoBrevo("incerta"), EsitoBrevo("rifiutata")])
def test_brevo_incerto_blocca_la_configurazione_e_avvisa_una_volta(db_sql, acceso, esito):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))
    mondo.esito = esito
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["esito_incerto"]
    riga = _riga(db_sql, iid)
    assert riga["stato"] == "esito_incerto" and riga["brevo_http_status"] == esito.http_status
    assert mondo.archivio.file, "i file restano: il commercialista potrebbe avere il link"
    sb = _sb(db_sql)
    s.gestisci_appese(sb, mondo.dip())
    s.gestisci_appese(sb, mondo.dip())
    assert len(mondo.avvisi) == 1 and "incerto" in mondo.avvisi[0]
    _senza_dati_personali(mondo.avvisi)
    assert _riga(db_sql, iid)["avviso_inviato_at"] is not None


def test_troppe_email_allo_stesso_indirizzo_blocca_senza_sospendere(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    for _ in range(3):
        _cur(db_sql, "INSERT INTO public.email_rate_log (destinatario, created_at) VALUES (%s, now() - interval '23 hours')", EMAIL)
    _cur(db_sql, "INSERT INTO public.email_rate_log (destinatario, created_at) VALUES ('altro@x.test', now())")
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["bloccato"]
    assert _riga(db_sql, iid)["motivo"] == "troppe_email_allo_stesso_destinatario_in_24_ore"
    assert mondo.email == [] and mondo.archivio.file == {}
    assert _uno(db_sql, "SELECT sospesa_at FROM public.invio_commercialista_config WHERE id = %s", cid) is None


def test_email_di_ieri_non_contano(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    for _ in range(3):
        _cur(db_sql, "INSERT INTO public.email_rate_log (destinatario, created_at) VALUES (%s, now() - interval '25 hours')", EMAIL)
    _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    assert _esegui(db_sql, _Mondo()) == ["inviato"]


def test_senza_chiave_brevo_non_si_tenta(db_sql, acceso, monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY")
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["errore"]
    riga = _riga(db_sql, iid)
    assert (riga["motivo"], riga["email_tentata_at"]) == ("brevo_non_configurato", None)
    assert mondo.archivio.file == {} and len(mondo.avvisi) == 1


# ─── Esecutore: la configurazione cambia mentre si lavora ────────────────────

def test_configurazione_spenta_dopo_la_richiesta(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    _cur(db_sql, "UPDATE public.invio_commercialista_config SET attivo = false WHERE id = %s", cid)
    mondo = _Mondo()
    assert _esegui(db_sql, mondo) == []
    assert (_riga(db_sql, iid)["stato"], _riga(db_sql, iid)["motivo"]) == ("errore", "non_piu_autorizzato")
    assert mondo.client.scaricati == []


def test_email_cambiata_durante_i_download(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))
    mondo.client.al_download = lambda rid: rid == 3 and _cur(
        db_sql, "UPDATE public.invio_commercialista_config SET email_destinatario = 'nuovo@studio.test' WHERE id = %s", cid)
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["errore"]
    riga = _riga(db_sql, iid)
    assert (riga["motivo"], riga["email_tentata_at"]) == ("configurazione_cambiata_durante_l_invio", None)
    assert mondo.email == [] and mondo.archivio.file == {} and riga["file_rimossi_at"] is not None


# ─── Righe appese ────────────────────────────────────────────────────────────

def test_appesa_senza_email_diventa_errore_e_perde_i_file(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', iniziata_at = now() - interval '3 hours', "
                 "storage_paths = ARRAY['c/i/a.zip'], link_scade_il = now() + interval '30 days' WHERE id = %s", iid)
    mondo = _Mondo()
    assert s.gestisci_appese(_sb(db_sql), mondo.dip()) == 1
    riga = _riga(db_sql, iid)
    assert (riga["stato"], riga["motivo"]) == ("errore", "interrotto") and riga["file_rimossi_at"] is not None
    assert mondo.archivio.rimossi == ["c/i/a.zip"] and mondo.avvisi == []


def test_appesa_dopo_l_email_diventa_incerta_e_si_segnala(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', iniziata_at = now() - interval '3 hours', "
                 "email_tentata_at = now() - interval '170 minutes' WHERE id = %s", iid)
    mondo = _Mondo()
    s.gestisci_appese(_sb(db_sql), mondo.dip())
    assert _riga(db_sql, iid)["stato"] == "esito_incerto" and len(mondo.avvisi) == 1


def test_in_corso_da_poco_non_si_tocca(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', iniziata_at = now() - interval '100 minutes' WHERE id = %s", iid)
    assert s.gestisci_appese(_sb(db_sql), _Mondo().dip()) == 0
    assert _riga(db_sql, iid)["stato"] == "in_corso"


# ─── Pulizia degli ZIP ───────────────────────────────────────────────────────

def test_i_file_si_tolgono_un_giorno_dopo_la_scadenza_del_link(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    scaduti = _inviato(db_sql, cid, "primo", _oggi() - timedelta(days=60), _oggi() - timedelta(days=40))
    freschi = _inviato(db_sql, cid, "ordinario", _oggi() - timedelta(days=39), _oggi() - timedelta(days=20))
    for iid, scade in ((scaduti, "now() - interval '25 hours'"), (freschi, "now() - interval '23 hours'")):
        _cur(db_sql, f"UPDATE public.invio_commercialista_invii SET storage_paths = ARRAY['{iid}/a.zip'], link_scade_il = {scade} WHERE id = %s", iid)
    archivio = _Archivio()
    assert s.rimuovi_file_scaduti(_sb(db_sql), archivio, datetime.now(UTC)) == 1
    assert archivio.rimossi == [f"{scaduti}/a.zip"]
    assert _riga(db_sql, scaduti)["file_rimossi_at"] is not None and _riga(db_sql, freschi)["file_rimossi_at"] is None
    assert s.rimuovi_file_scaduti(_sb(db_sql), archivio, datetime.now(UTC)) == 0


# ─── Pianificatore ───────────────────────────────────────────────────────────

def _scenario():
    """Le 00:30 di Roma del primo giorno del mese scorso: in UTC e' ancora il
    mese prima, e un pianificatore che guardasse la data UTC non vedrebbe la
    scadenza. Il mese scorso e non questo: tutto il periodo e' passato qualunque
    giorno giri la suite. Ritorna (adesso, fine del mese prima, ultimo inviato)."""
    primo = (_oggi().replace(day=1) - timedelta(days=1)).replace(day=1)
    fine_mese_prima = primo - timedelta(days=1)
    ultimo = fine_mese_prima.replace(day=1) - timedelta(days=1)
    return _alle(primo, 0, 30), fine_mese_prima, ultimo


def _pianifica(db_sql, adesso, avvisi=None):
    return s.pianifica(_sb(db_sql), adesso, (avvisi if avvisi is not None else []).append)


def _ordinari(db_sql, cid):
    return _cur(db_sql, "SELECT periodo_dal, periodo_al, richiesto_da, stato FROM public.invio_commercialista_invii "
                        "WHERE config_id = %s AND tipo = 'ordinario' ORDER BY creata_at", cid)


def test_il_pianificatore_crea_l_ordinario_dovuto(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    adesso, fine_mese_prima, ultimo = _scenario()
    _inviato(db_sql, cid, "primo", ultimo - timedelta(days=9), ultimo, creata=_alle(ultimo + timedelta(days=1)))
    assert _pianifica(db_sql, adesso) == 1
    assert _ordinari(db_sql, cid) == [(ultimo + timedelta(days=1), fine_mese_prima, "notturno", "richiesto")]
    assert _pianifica(db_sql, adesso) == 0, "una volta sola"


def test_nessun_ordinario_senza_un_primo_riuscito(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    assert _pianifica(db_sql, _scenario()[0]) == 0
    assert _ordinari(db_sql, cid) == []


def test_nessun_ordinario_prima_della_scadenza(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    adesso, fine_mese_prima, _ = _scenario()
    _inviato(db_sql, cid, "primo", fine_mese_prima - timedelta(days=9), fine_mese_prima, creata=adesso)
    assert _pianifica(db_sql, adesso) == 0


def test_nessun_ordinario_senza_sede_sdi_attiva(db_sql):
    _semina(db_sql, sdi=False)
    cid = _config(db_sql)
    adesso, _, ultimo = _scenario()
    _inviato(db_sql, cid, "primo", ultimo - timedelta(days=9), ultimo, creata=_alle(ultimo + timedelta(days=1)))
    assert _pianifica(db_sql, adesso) == 0
    _cur(db_sql, "UPDATE public.ristoranti SET sdi_attivo = true WHERE id = %s", SEDE_1)
    assert _pianifica(db_sql, adesso) == 1, "riparte dall'ultimo invio, senza buchi"


def test_nessun_ordinario_per_una_configurazione_sospesa_o_spenta(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    adesso, _, ultimo = _scenario()
    _inviato(db_sql, cid, "primo", ultimo - timedelta(days=9), ultimo, creata=_alle(ultimo + timedelta(days=1)))
    _cur(db_sql, "UPDATE public.invio_commercialista_config SET sospesa_at = now() WHERE id = %s", cid)
    assert _pianifica(db_sql, adesso) == 0
    _cur(db_sql, "UPDATE public.invio_commercialista_config SET sospesa_at = NULL, attivo = false WHERE id = %s", cid)
    assert _pianifica(db_sql, adesso) == 0


def test_dopo_un_errore_si_riprova_la_notte_dopo_non_subito(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    adesso, fine_mese_prima, ultimo = _scenario()
    _inviato(db_sql, cid, "primo", ultimo - timedelta(days=9), ultimo, creata=_alle(ultimo + timedelta(days=1)))
    assert _pianifica(db_sql, adesso) == 1
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'errore' WHERE tipo = 'ordinario'")
    assert _pianifica(db_sql, adesso) == 0, "stessa notte: niente secondo tentativo"


def test_un_esito_incerto_ferma_il_pianificatore(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    adesso, _, ultimo = _scenario()
    _inviato(db_sql, cid, "primo", ultimo - timedelta(days=9), ultimo, creata=_alle(ultimo + timedelta(days=1)))
    reinvio = _invio(db_sql, cid, "reinvio", ultimo - timedelta(days=9), ultimo)
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso' WHERE id = %s", reinvio)
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'esito_incerto', email_tentata_at = now() WHERE id = %s", reinvio)
    assert _pianifica(db_sql, adesso) == 0


def test_dopo_due_anni_si_riparte_dal_limite_e_si_avvisa(db_sql):
    """Qui `adesso` e' davvero adesso: il trigger calcola il limite dei 2 anni
    dall'orologio del DB, e i due devono coincidere al giorno."""
    _semina(db_sql)
    cid = _config(db_sql)
    adesso = datetime.now(ROMA)
    vecchio = adesso.date() - timedelta(days=3 * 365)
    _inviato(db_sql, cid, "primo", vecchio - timedelta(days=9), vecchio, creata=_alle(vecchio + timedelta(days=1)))
    avvisi = []
    assert _pianifica(db_sql, adesso, avvisi) == 1
    [(dal, al, *_)] = _ordinari(db_sql, cid)
    assert (dal, al) == (s.limite_due_anni(adesso.date()), adesso.date() - timedelta(days=1))
    assert len(avvisi) == 1 and "2 anni" in avvisi[0]
    _senza_dati_personali(avvisi)


def test_il_ciclo_di_notte_pianifica_ed_esegue(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    adesso, fine_mese_prima, ultimo = _scenario()
    _inviato(db_sql, cid, "primo", ultimo - timedelta(days=9), ultimo, creata=_alle(ultimo + timedelta(days=1)))
    mondo = _Mondo([_documento(5, _alle(ultimo + timedelta(days=3)))])
    mondo.adesso = adesso + timedelta(hours=2)
    assert s.ciclo(_sb(db_sql), mondo.dip()) == ["inviato"]
    assert _ordinari(db_sql, cid) == [(ultimo + timedelta(days=1), fine_mese_prima, "notturno", "inviato")]
    assert len(mondo.email) == 1


def test_seconda_notte_di_errore_si_avvisa(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    adesso, fine_mese_prima, ultimo = _scenario()
    _inviato(db_sql, cid, "primo", ultimo - timedelta(days=9), ultimo, creata=_alle(ultimo + timedelta(days=1)))
    mondo = _Mondo([_documento(5, _alle(ultimo + timedelta(days=3)))])
    mondo.saldi = [RuntimeError("giu'")]
    # La prima notte scritta a mano: il DB data le righe col suo orologio, e una
    # riga creata adesso conterebbe come «gia' tentato» anche la notte dopo.
    _invio(db_sql, cid, "ordinario", ultimo + timedelta(days=1), fine_mese_prima, da="notturno", creata=adesso)
    assert _esegui(db_sql, mondo) == ["errore"]
    assert mondo.avvisi == [], "la prima notte non si disturba"
    _pianifica(db_sql, adesso + timedelta(days=1))
    assert _esegui(db_sql, mondo) == ["errore"]
    assert len(mondo.avvisi) == 1 and "saldo_illeggibile" in mondo.avvisi[0]
    _senza_dati_personali(mondo.avvisi)


# ─── Casi aggiunti per la mutazione ──────────────────────────────────────────

def test_un_altro_processo_prende_la_riga_fra_lettura_e_update(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    sb = _sb(db_sql)

    class Concorrente:
        def __init__(self):
            self.fatto = False

        def table(self, nome):
            builder = sb.table(nome)
            originale = builder.update

            def update(campi, **k):
                if nome == s.INVII and campi.get("stato") == "in_corso" and not self.fatto:
                    self.fatto = True
                    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', iniziata_at = now() WHERE id = %s", iid)
                return originale(campi, **k)
            builder.update = update
            return builder

    concorrente = Concorrente()
    assert s.prendi_richiesto(concorrente, datetime.now(UTC)) is None
    assert concorrente.fatto


def test_la_sede_spenta_non_conta_come_sede_sdi(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    adesso, _, ultimo = _scenario()
    _inviato(db_sql, cid, "primo", ultimo - timedelta(days=9), ultimo, creata=_alle(ultimo + timedelta(days=1)))
    _cur(db_sql, "UPDATE public.ristoranti SET attivo = false WHERE id = %s", SEDE_1)
    assert _pianifica(db_sql, adesso) == 0


def test_sdi_spento_dopo_la_richiesta_ferma_l_invio(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    _cur(db_sql, "UPDATE public.ristoranti SET sdi_attivo = false WHERE id = %s", SEDE_1)
    mondo = _Mondo()
    assert _esegui(db_sql, mondo) == ["errore"]
    assert _riga(db_sql, iid)["motivo"] == "nessuna_sede_con_sdi_attivo"
    assert mondo.client.scaricati == [] and mondo.email == []


def test_azienda_diversa_su_invoicetronic_blocca(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    mondo = _Mondo()
    mondo.client.azienda_restituita = {"id": AZIENDA, "vat": "IT12345678903"}
    assert _esegui(db_sql, mondo) == ["bloccato"]
    assert _riga(db_sql, iid)["motivo"] == "azienda_diversa_su_invoicetronic"


def test_elenco_senza_una_fattura_gia_arrivata_blocca(db_sql, acceso):
    """Chiave o azienda sbagliata: la coda di OneFlux ha visto arrivare una
    fattura che l'elenco non contiene."""
    import json
    _semina(db_sql)
    cid = _config(db_sql)
    _cur(db_sql, "INSERT INTO public.fatture_queue (id, event_id, piva_raw, status, user_id, ristorante_id, source, payload_meta) "
                 "VALUES (1, 'evt-x', %s, 'done', %s, %s, 'invoicetronic', %s::jsonb)",
         PIVA, U1, SEDE_1, json.dumps({"resource_id": 999, "invoicetronic_company_id": AZIENDA}))
    iid = _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    assert _esegui(db_sql, _Mondo()) == ["bloccato"]
    assert _riga(db_sql, iid)["motivo"] == "elenco_senza_fatture_gia_arrivate"


def test_lo_stesso_file_sdi_due_volte_va_nello_zip_una_volta(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    primo = _documento(1, _alle(dal + timedelta(days=1)))
    doppio = dict(primo, id=2, created=_alle(dal + timedelta(days=2)).astimezone(UTC).isoformat())
    mondo = _Mondo([primo, doppio])
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["inviato"]
    riga = _riga(db_sql, iid)
    assert (riga["n_file"], riga["documenti_ids"], riga["documenti_visti"]) == (1, [1], [1, 2])


def test_un_errore_dopo_il_tentativo_d_email_e_incerto(db_sql, acceso):
    """Qualunque cosa succeda dopo email_tentata_at, il periodo non torna libero."""
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))
    mondo.esito = RuntimeError("connessione chiusa")
    iid = _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["esito_incerto"]
    assert _riga(db_sql, iid)["motivo"] == "errore_interno: RuntimeError"



def test_anti_loop_per_configurazione(db_sql, acceso):
    """Due clienti con lo stesso commercialista: sei email in 24 ore non sono un loop."""
    _semina(db_sql)
    cid = _config(db_sql)
    seconda = "98765432109"
    _cur(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
                 "VALUES ('3e0e0000-0000-4000-8000-0000000000a3', %s, 'B', %s, TRUE)", U1, seconda)
    _cur(db_sql, "INSERT INTO public.invio_commercialista_config (user_id, piva, invoicetronic_company_id, "
                 "email_destinatario, data_partenza, attivo, consenso_ricevuto, consenso_data, consenso_email) "
                 "VALUES (%s, %s, 3000, %s, '2026-07-01', true, true, '2026-09-20', %s)", U1, seconda, EMAIL, EMAIL)
    for _ in range(5):
        _cur(db_sql, "INSERT INTO public.email_rate_log (destinatario, created_at) VALUES (%s, now() - interval '1 hour')", EMAIL)
    _invio(db_sql, cid, "primo", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    assert _esegui(db_sql, _Mondo()) == ["inviato"]
    _cur(db_sql, "INSERT INTO public.email_rate_log (destinatario, created_at) VALUES (%s, now())", EMAIL)
    _invio(db_sql, cid, "reinvio", _oggi() - timedelta(days=5), _oggi() - timedelta(days=1))
    assert _esegui(db_sql, _Mondo()) == ["bloccato"]


def test_la_cartella_temporanea_non_resta_sul_disco(db_sql, acceso, tmp_path, monkeypatch):
    """Dentro ci sono le fatture: su un errore come su un invio riuscito, via."""
    cartelle = []

    def mkdtemp(prefix=""):
        cartella = tmp_path / f"lavoro{len(cartelle)}"
        cartella.mkdir()
        cartelle.append(cartella)
        return str(cartella)
    monkeypatch.setattr(s.tempfile, "mkdtemp", mkdtemp)
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    _invio(db_sql, cid, "primo", dal, al)
    mondo = _Mondo(_tre_documenti(dal))
    mondo.esito = EsitoBrevo("rifiutata", 400)
    assert _esegui(db_sql, mondo) == ["errore"]
    assert cartelle and not any(c.exists() for c in cartelle)


def test_una_configurazione_che_fallisce_non_ferma_le_altre(db_sql, monkeypatch):
    _semina(db_sql)
    prima = _config(db_sql)
    seconda_piva = "98765432109"
    _cur(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo, sdi_attivo) "
                 "VALUES ('3e0e0000-0000-4000-8000-0000000000a3', %s, 'B', %s, TRUE, TRUE)", U1, seconda_piva)
    seconda = str(_uno(db_sql, "INSERT INTO public.invio_commercialista_config (user_id, piva, invoicetronic_company_id, "
                               "email_destinatario, data_partenza, attivo, consenso_ricevuto, consenso_data, consenso_email) "
                               "VALUES (%s, %s, 3000, %s, '2026-07-01', true, true, '2026-09-20', %s) RETURNING id",
                               U1, seconda_piva, EMAIL, EMAIL))
    adesso, fine_mese_prima, ultimo = _scenario()
    for cid, piva, azienda in ((prima, PIVA, AZIENDA), (seconda, seconda_piva, 3000)):
        iid = str(_uno(db_sql, "INSERT INTO public.invio_commercialista_invii (config_id, user_id, piva, invoicetronic_company_id, "
                               "destinatario, tipo, periodo_dal, periodo_al, richiesto_da, creata_at) "
                               "VALUES (%s, %s, %s, %s, %s, 'primo', %s, %s, 'admin', %s) RETURNING id",
                               cid, U1, piva, azienda, EMAIL, ultimo - timedelta(days=9), ultimo, _alle(ultimo + timedelta(days=1))))
        _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', email_tentata_at = now() WHERE id = %s", iid)
        _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'inviato' WHERE id = %s", iid)
    vero = s.ultimo_giorno_inviato

    def rotto(sb, config_id):
        if config_id == min(prima, seconda):
            raise RuntimeError("giu'")
        return vero(sb, config_id)
    monkeypatch.setattr(s, "ultimo_giorno_inviato", rotto)
    assert _pianifica(db_sql, adesso) == 1


def test_l_errore_inatteso_non_scrive_l_email_nei_log(db_sql, acceso, caplog):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal))

    def rotto(receive_id):
        raise ValueError(f"Failing row contains (..., {EMAIL}, ...)")
    mondo.client.al_download = rotto
    _invio(db_sql, cid, "primo", dal, al)
    with caplog.at_level("ERROR"):
        assert _esegui(db_sql, mondo) == ["errore"]
    assert "ValueError" in caplog.text and EMAIL not in caplog.text


def test_cancellando_l_account_gli_zip_se_ne_vanno_subito(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _inviato(db_sql, cid, "primo", _oggi() - timedelta(days=20), _oggi() - timedelta(days=1))
    rimosso = _inviato(db_sql, cid, "reinvio", _oggi() - timedelta(days=20), _oggi() - timedelta(days=10))
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET storage_paths = ARRAY['c/a.zip', 'c/b.zip'], "
                 "link_scade_il = now() + interval '20 days' WHERE id = %s", iid)
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET storage_paths = ARRAY['c/vecchio.zip'], "
                 "file_rimossi_at = now() WHERE id = %s", rimosso)
    archivio = _Archivio()
    assert s.rimuovi_file_del_cliente(_sb(db_sql), U1, archivio=archivio) == 2
    assert archivio.rimossi == ["c/a.zip", "c/b.zip"]
    assert _riga(db_sql, iid)["file_rimossi_at"] is not None
    assert s.rimuovi_file_del_cliente(_sb(db_sql), U2, archivio=archivio) == 0



# ─── Fatture arrivate in un periodo gia' spedito ─────────────────────────────

def _primo_spedito(db_sql, cid, dal, al, visti):
    iid = _invio(db_sql, cid, "primo", dal, al)
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'in_corso', email_tentata_at = now(), "
                 "documenti_ids = %s, documenti_visti = %s WHERE id = %s", visti[:1], visti, iid)
    _cur(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'inviato' WHERE id = %s", iid)
    return iid


def test_una_fattura_comparsa_in_un_periodo_gia_spedito_si_segnala(db_sql, acceso):
    """Invoicetronic la rielabora con la data di prima: il periodo e' gia' partito e il
    commercialista non la ricevera' mai. Il doppione scartato (visto, non inviato)
    non conta."""
    _semina(db_sql)
    cid = _config(db_sql)
    primo_dal, primo_al = _oggi() - timedelta(days=40), _oggi() - timedelta(days=21)
    _primo_spedito(db_sql, cid, primo_dal, primo_al, [1, 2])
    mondo = _Mondo([
        _documento(1, _alle(primo_dal + timedelta(days=1))),
        _documento(2, _alle(primo_dal + timedelta(days=2))),
        _documento(3, _alle(primo_dal + timedelta(days=3))),
        _documento(4, _alle(primo_al + timedelta(days=2))),
    ])
    _invio(db_sql, cid, "ordinario", primo_al + timedelta(days=1), _oggi() - timedelta(days=1))
    assert _esegui(db_sql, mondo) == ["inviato"]
    avvisi = [a for a in mondo.avvisi if "periodi gia' spediti" in a]
    assert len(avvisi) == 1 and "1 documenti" in avvisi[0]
    _senza_dati_personali(mondo.avvisi)


def test_il_reinvio_recupera_e_l_avviso_tace(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    primo_dal, primo_al = _oggi() - timedelta(days=40), _oggi() - timedelta(days=21)
    _primo_spedito(db_sql, cid, primo_dal, primo_al, [1])
    documenti = [_documento(1, _alle(primo_dal + timedelta(days=1))), _documento(3, _alle(primo_dal + timedelta(days=3)))]
    _invio(db_sql, cid, "reinvio", primo_dal, primo_al)
    mondo = _Mondo(documenti)
    assert _esegui(db_sql, mondo) == ["inviato"]
    assert mondo.avvisi == [], "il reinvio che li recupera non suona"
    _invio(db_sql, cid, "ordinario", primo_al + timedelta(days=1), _oggi() - timedelta(days=1))
    dopo = _Mondo(documenti)
    assert _esegui(db_sql, dopo) == ["inviato"]
    assert dopo.avvisi == [], "recuperati dal reinvio: niente piu' da segnalare"


def test_senza_periodi_spediti_niente_avvisi(db_sql, acceso):
    _semina(db_sql)
    cid = _config(db_sql)
    dal, al = _oggi() - timedelta(days=20), _oggi() - timedelta(days=1)
    mondo = _Mondo(_tre_documenti(dal) + [_documento(9, _alle(dal - timedelta(days=30)))])
    _invio(db_sql, cid, "primo", dal, al)
    assert _esegui(db_sql, mondo) == ["inviato"]
    assert mondo.avvisi == []
