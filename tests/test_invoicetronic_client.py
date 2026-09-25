"""Il client Invoicetronic dell'invio al commercialista (fase B).

Il rischio che questi test presidiano: una lista vuota o incompleta scambiata
per «periodo senza fatture», che consumerebbe il periodo per sempre. Per questo
ogni dubbio (chiave di test, totale che non torna, ordine non rispettato,
risposta strana) e' un errore, mai un elenco vuoto. Nessuna rete: HTTP finto.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from services import invoicetronic_client as ic
from services.invoicetronic_saldo import SaldoInvoicetronicEsaurito

CHIAVE = "ik_live_prova"


class R:
    def __init__(self, status=200, corpo=None, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._corpo = corpo
        self.content = json.dumps(corpo).encode() if corpo is not None and not isinstance(corpo, bytes) else (corpo or b"")

    def json(self):
        if isinstance(self._corpo, bytes):
            raise ValueError("non json")
        return self._corpo


class HTTP:
    def __init__(self, *risposte):
        self.risposte = list(risposte)
        self.chiamate = []

    def get(self, url, params=None):
        self.chiamate.append((url, dict(params or {})))
        r = self.risposte.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class Tempo:
    def __init__(self):
        self.t = 1000.0
        self.dormito = []

    def orologio(self):
        return self.t

    def dormi(self, s):
        self.dormito.append(s)
        self.t += s


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    monkeypatch.delenv("INVOICETRONIC_API_BASE", raising=False)
    monkeypatch.delenv("INVOICETRONIC_EXPORT_KEY", raising=False)
    monkeypatch.setenv("INVOICETRONIC_API_KEY", CHIAVE)


def _client(*risposte):
    tempo = Tempo()
    http = HTTP(*risposte)
    return ic.ClientInvoicetronic(http=http, dormi=tempo.dormi, orologio=tempo.orologio), http, tempo


def _doc(i, created, company=1756, committente="07863990961"):
    return {"id": i, "created": created, "company_id": company, "committente": committente}


# ─── Chiave e host ───────────────────────────────────────────────────────────

def test_senza_chiave_non_si_parte(monkeypatch):
    monkeypatch.delenv("INVOICETRONIC_API_KEY")
    with pytest.raises(ic.ErroreInvoicetronic) as e:
        ic.ClientInvoicetronic(http=HTTP())
    assert e.value.configurazione


def test_una_chiave_di_test_leggerebbe_la_sandbox_e_viene_rifiutata(monkeypatch):
    monkeypatch.setenv("INVOICETRONIC_API_KEY", "ik_test_prova")
    with pytest.raises(ic.ErroreInvoicetronic, match="produzione") as e:
        ic.ClientInvoicetronic(http=HTTP())
    assert e.value.configurazione


def test_la_sotto_chiave_in_sola_lettura_ha_la_precedenza(monkeypatch):
    monkeypatch.setenv("INVOICETRONIC_EXPORT_KEY", "ik_test_sottochiave")
    with pytest.raises(ic.ErroreInvoicetronic, match="produzione"):
        ic.ClientInvoicetronic(http=HTTP())


@pytest.mark.parametrize("base", ["https://evil.example.com/v1", "http://api.invoicetronic.com/v1", "https://invoicetronic.com.evil.io/v1"])
def test_solo_l_host_invoicetronic_in_https(monkeypatch, base):
    monkeypatch.setenv("INVOICETRONIC_API_BASE", base)
    with pytest.raises(ic.ErroreInvoicetronic, match="host"):
        ic.ClientInvoicetronic(http=HTTP())


# ─── Risposte ────────────────────────────────────────────────────────────────

def test_429_si_aspetta_quanto_dice_retry_after_poi_si_riprova():
    c, http, tempo = _client(R(429, headers={"Retry-After": "7"}), R(200, {"id": 5, "vat": "IT07863990961"}))
    assert c.azienda(5)["id"] == 5
    assert 7 in tempo.dormito and len(http.chiamate) == 2


def test_429_attesa_limitata_a_60_secondi_e_a_5_volte():
    c, http, tempo = _client(*[R(429, headers={"Retry-After": "600"})] * 6)
    with pytest.raises(ic.ErroreInvoicetronic, match="429"):
        c.azienda(5)
    assert max(tempo.dormito) == 60 and len(http.chiamate) == 6


def test_403_del_saldo_e_saldo_esaurito():
    c, _, _ = _client(R(403, {"status": 403, "code": "usage_limit_exceeded"}))
    with pytest.raises(SaldoInvoicetronicEsaurito):
        c.azienda(5)


@pytest.mark.parametrize("status,codice", [(401, None), (403, "subkey_not_allowed"), (400, None), (422, None)])
def test_errori_di_configurazione_non_si_ritentano(status, codice):
    c, http, _ = _client(R(status, {"code": codice} if codice else {}))
    with pytest.raises(ic.ErroreInvoicetronic) as e:
        c.azienda(5)
    assert e.value.configurazione and e.value.status == status and len(http.chiamate) == 1


def test_5xx_e_rete_si_ritentano_tre_volte():
    c, http, tempo = _client(R(502), ConnectionError("giu"), R(200, {"id": 5, "vat": "IT07863990961"}))
    assert c.azienda(5)["id"] == 5
    assert tempo.dormito[:2] == [2, 8]


def test_rete_giu_dopo_tre_attese_e_un_errore():
    c, http, tempo = _client(*[ConnectionError("giu")] * 4)
    with pytest.raises(ic.ErroreInvoicetronic, match="non raggiungibile"):
        c.azienda(5)
    assert [d for d in tempo.dormito if d >= 2] == [2, 8, 30]


def test_al_massimo_due_chiamate_al_secondo():
    c, _, tempo = _client(R(200, {"id": 1, "vat": "IT07863990961"}), R(200, {"id": 1, "vat": "IT07863990961"}))
    c.azienda(1)
    c.azienda(1)
    assert tempo.dormito == [0.5]


# ─── Aziende ─────────────────────────────────────────────────────────────────

def test_azienda_per_piva_sempre_col_prefisso_it():
    c, http, _ = _client(R(200, {"id": 1756, "vat": "IT07863990961", "name": "X"}))
    assert c.azienda_per_piva("07863990961")["id"] == 1756
    assert http.chiamate[0][0].endswith("/company/IT07863990961")


def test_azienda_inesistente_e_none():
    c, _, _ = _client(R(404))
    assert c.azienda_per_piva("07863990961") is None


def test_azienda_con_un_altra_piva_e_un_errore():
    c, _, _ = _client(R(200, {"id": 1756, "vat": "IT12345678903"}))
    with pytest.raises(ic.ErroreInvoicetronic, match="altra P.IVA"):
        c.azienda_per_piva("07863990961")


@pytest.mark.parametrize("piva", ["0786399096", "IT07863990961", "0786399096a"])
def test_piva_non_di_11_cifre_rifiutata_prima_di_chiamare(piva):
    c, http, _ = _client()
    with pytest.raises(ic.ErroreInvoicetronic):
        c.azienda_per_piva(piva)
    assert http.chiamate == []


# ─── Elenco ──────────────────────────────────────────────────────────────────

def _pagina(ids, totale, inizio_minuto=59):
    docs = [_doc(i, f"2026-09-20T10:{max(inizio_minuto - k, 0):02d}:00Z") for k, i in enumerate(ids)]
    return R(200, docs, {"Invoicetronic-Total-Count": str(totale)})


def test_elenco_completo_su_piu_pagine_senza_filtri_di_data():
    prima = [_doc(1000 - k, f"2026-09-{20 - k // 20:02d}T10:00:00Z") for k in range(200)]
    seconda = [_doc(800 - k, "2026-08-01T10:00:00Z") for k in range(3)]
    c, http, _ = _client(
        R(200, prima, {"Invoicetronic-Total-Count": "203"}),
        R(200, seconda, {"Invoicetronic-Total-Count": "203"}),
        R(200, [], {"Invoicetronic-Total-Count": "203"}),
    )
    elenco = c.elenco_ricevute(1756)
    assert len(elenco) == 203
    for _, params in http.chiamate:
        assert set(params) == {"company_id", "page", "page_size", "sort"}, "niente filtri di data"
        assert params["sort"] == "-created" and params["page_size"] == 200 and params["company_id"] == 1756
    assert [p["page"] for _, p in http.chiamate] == [1, 2, 3]


def test_un_doppione_fra_pagine_si_conta_una_volta():
    c, _, _ = _client(
        R(200, [_doc(3, "2026-09-20T10:00:00Z"), _doc(2, "2026-09-19T10:00:00Z")], {"Invoicetronic-Total-Count": "3"}),
        R(200, [_doc(2, "2026-09-19T10:00:00Z"), _doc(1, "2026-09-18T10:00:00Z")], {"Invoicetronic-Total-Count": "3"}),
        R(200, [], {"Invoicetronic-Total-Count": "3"}),
    )
    assert sorted(d["id"] for d in c.elenco_ricevute(1756)) == [1, 2, 3]


def test_totale_che_non_torna_e_un_errore_non_un_elenco_corto():
    letture = [r for _ in range(ic.LETTURE_ELENCO) for r in (_pagina([3, 2], 5), R(200, [], {"Invoicetronic-Total-Count": "5"}))]
    c, http, _ = _client(*letture)
    with pytest.raises(ic.ErroreInvoicetronic, match="incompleto"):
        c.elenco_ricevute(1756)
    assert len(http.chiamate) == 2 * ic.LETTURE_ELENCO, "si rilegge prima di arrendersi"


def test_un_arrivo_durante_la_lettura_fa_rileggere():
    """Il totale cambia fra una pagina e l'altra: le pagine si sono spostate e un
    documento puo' essere saltato. Si rilegge; la seconda lettura e' stabile."""
    c, http, _ = _client(
        _pagina([3, 2], 3), R(200, [], {"Invoicetronic-Total-Count": "4"}),
        _pagina([4, 3, 2, 1], 4), R(200, [], {"Invoicetronic-Total-Count": "4"}),
    )
    assert sorted(d["id"] for d in c.elenco_ricevute(1756)) == [1, 2, 3, 4]
    assert len(http.chiamate) == 4


def test_una_cancellazione_a_meta_lista_non_passa():
    """Totale 3 poi 2 e due documenti letti: prima tornava col totale finale, e un
    documento poteva mancare senza che nessuno lo vedesse."""
    letture = [r for _ in range(ic.LETTURE_ELENCO) for r in (_pagina([3, 2], 3), R(200, [], {"Invoicetronic-Total-Count": "2"}))]
    c, _, _ = _client(*letture)
    with pytest.raises(ic.ErroreInvoicetronic, match="instabile"):
        c.elenco_ricevute(1756)


def test_senza_intestazione_del_totale_non_si_procede():
    c, _, _ = _client(R(200, [_doc(1, "2026-09-20T10:00:00Z")], {}))
    with pytest.raises(ic.ErroreInvoicetronic, match="Total-Count"):
        c.elenco_ricevute(1756)


def test_ordine_non_rispettato_e_un_errore():
    c, _, _ = _client(R(200, [_doc(1, "2026-09-18T10:00:00Z"), _doc(2, "2026-09-20T10:00:00Z")], {"Invoicetronic-Total-Count": "2"}))
    with pytest.raises(ic.ErroreInvoicetronic, match="ordinato"):
        c.elenco_ricevute(1756)


@pytest.mark.parametrize("doc", [{"id": "7", "created": "2026-09-20T10:00:00Z"}, {"id": True, "created": "x"},
                                 {"id": 7}, {"id": 7, "created": "ieri"}])
def test_documento_malformato_nell_elenco_e_un_errore(doc):
    c, _, _ = _client(R(200, [doc], {"Invoicetronic-Total-Count": "1"}))
    with pytest.raises(ic.ErroreInvoicetronic):
        c.elenco_ricevute(1756)


def test_404_sull_elenco_e_un_errore_non_un_elenco_vuoto():
    c, _, _ = _client(R(404))
    with pytest.raises(ic.ErroreInvoicetronic):
        c.elenco_ricevute(1756)


def test_elenco_vuoto_dichiarato_vuoto_e_vuoto():
    c, _, _ = _client(R(200, [], {"Invoicetronic-Total-Count": "0"}))
    assert c.elenco_ricevute(1756) == []


# ─── Documento ───────────────────────────────────────────────────────────────

def test_documento_scaricato_in_json_con_payload():
    c, http, _ = _client(R(200, {"id": 42, "payload": "PD94", "encoding": "Base64"}))
    assert c.documento(42)["payload"] == "PD94"
    url, params = http.chiamate[0]
    assert url.endswith("/receive/42") and params == {"include_payload": "true"}


@pytest.mark.parametrize("corpo", [{"id": 43, "payload": "x"}, {"id": 42}, {"id": 42, "payload": ""}, b"<xml>"])
def test_documento_sbagliato_o_vuoto_e_un_errore(corpo):
    c, _, _ = _client(R(200, corpo))
    with pytest.raises(ic.ErroreInvoicetronic):
        c.documento(42)


# ─── Giorni di Roma ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("istante,giorno", [
    ("2026-12-31T23:30:00Z", date(2027, 1, 1)),
    ("2026-12-31T22:30:00Z", date(2026, 12, 31)),
    ("2026-06-30T22:30:00Z", date(2026, 7, 1)),
    ("2026-06-30T21:59:59.9999999Z", date(2026, 6, 30)),
    ("2026-03-29T00:30:00Z", date(2026, 3, 29)),
    ("2026-10-25T23:30:00", date(2026, 10, 26)),
])
def test_data_di_roma(istante, giorno):
    assert ic.data_roma(istante) == giorno


@pytest.mark.parametrize("fuso", ["Pacific/Kiritimati", "Pacific/Pago_Pago"])
def test_data_senza_fuso_e_utc_anche_se_il_processo_vive_altrove(monkeypatch, fuso):
    """In UTC «ora locale» e «UTC» coincidono e l'errore non si vede: si
    ripete con i fusi estremi (+14, -11)."""
    import time as _time

    monkeypatch.setenv("TZ", fuso)
    _time.tzset()
    try:
        assert ic.data_roma("2026-10-25T23:30:00") == date(2026, 10, 26)
        assert ic.data_roma("2026-06-30T21:30:00") == date(2026, 6, 30)
    finally:
        monkeypatch.undo()
        _time.tzset()
