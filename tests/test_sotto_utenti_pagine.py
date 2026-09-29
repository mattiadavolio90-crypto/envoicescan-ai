"""Pagine effettive di un sotto-utente: pagine del titolare ∩ pagine del sotto-utente.

Il dict effettivo passa poi da `_normalize_pagine` come quello di qualunque
account: questi test lo verificano anche attraverso il normalizzatore vero,
perche' e' lui che decide menu, chat e briefing.
"""
import pytest

from services import sotto_utenti_service as su

TUTTE = {p: True for p in su.PAGINE_ACCOUNT}


@pytest.fixture(scope="module")
def fw():
    import services.fastapi_worker as fw

    return fw


def _lista(fw, raw_titolare, pagine_su, catena=False):
    return sorted(fw._normalize_pagine(su.pagine_effettive(raw_titolare, pagine_su, catena)))


@pytest.mark.parametrize("raw_titolare", [
    None,                                        # nessuna restrizione
    {"blocco_mesi_precedenti": True},            # caso OFFSIDE: nessuna chiave-pagina
    {"tab_off_margini_coperti": True},           # solo tab_off
    dict(TUTTE),                                 # tutte esplicite
    sorted(su.PAGINE_ACCOUNT),                   # forma lista
])
def test_titolare_aperto_passa_le_pagine_del_sotto_utente(fw, raw_titolare):
    lista = _lista(fw, raw_titolare, {"analisi_fatture": True, "prezzi": True})
    pagine = [p for p in lista if p in su.PAGINE_ACCOUNT]
    assert pagine == ["analisi_fatture", "prezzi"]


def test_pagina_spenta_al_titolare_resta_spenta_al_sotto_utente(fw):
    titolare = dict(TUTTE, margini=False)
    assert _lista(fw, titolare, {"margini": True, "prezzi": True}) == ["prezzi"]


def test_nessuna_pagina_non_diventa_tutto_aperto(fw):
    # Il rischio OFFSIDE al contrario: un sotto-utente senza pagine non deve
    # ricadere nel "None = tutto aperto" del normalizzatore.
    assert fw._normalize_pagine(su.pagine_effettive(None, {}, False)) == []


def test_solo_true_accende(fw):
    assert _lista(fw, None, {"margini": "true", "prezzi": 1, "agenda": True}) == ["agenda"]


def test_impostazioni_del_titolare_restano_sue(fw):
    titolare = {"blocco_mesi_precedenti": True, "tab_off_margini_coperti": True,
                "trigger_servizi_off": True, **TUTTE}
    effettive = su.pagine_effettive(titolare, {"margini": True, "blocco_mesi_precedenti": False}, False)
    assert effettive["blocco_mesi_precedenti"] is True
    lista = fw._normalize_pagine(effettive)
    assert "tab_off_margini_coperti" in lista and "trigger_servizi_off" in lista


def test_home_e_catena(fw):
    effettive = su.pagine_effettive(None, {"home": True, "catena": True}, catena_consentita=False)
    assert effettive["home"] is True and effettive["catena"] is False
    assert su.pagine_effettive(None, {"catena": True}, True)["catena"] is True


def test_home_e_catena_non_entrano_nelle_pagine_dell_account(fw):
    # Per il titolare `home`/`catena` non esistono: aggiungerle a _PAGINE_FLAG
    # spegnerebbe la Home agli account con un dict di pagine (4 su 8 il 28/9).
    assert "home" not in fw._PAGINE_FLAG and "catena" not in fw._PAGINE_FLAG


def _titolare(pagine=None):
    return {"id": "u1", "email": "titolare@x.it", "pagine_abilitate": pagine, "ultimo_ristorante_id": "s1"}


SEDI = [{"id": "s1", "sede_tecnica": False}, {"id": "s2", "sede_tecnica": False},
        {"id": "t", "sede_tecnica": True}]


def test_sovrapponi_tiene_il_tenant_e_cambia_la_persona():
    u = su.sovrapponi(_titolare(), {"id": "su1", "email": "resp@x.it", "pagine": {}}, ["s2"], SEDI)
    assert u["id"] == "u1"
    assert u["email"] == "resp@x.it" and u["_titolare_email"] == "titolare@x.it"
    assert u["ristorante_id"] == "s2" and u["ultimo_ristorante_id"] == "s2"
    assert su.sedi_consentite(u) == {"s2"}


def test_sede_attiva_salvata_fuori_dalle_sedi_ricade_sulla_prima():
    u = su.sovrapponi(_titolare(), {"id": "su1", "pagine": {}, "ultimo_ristorante_id": "s1"}, ["s2"], SEDI)
    assert u["ristorante_id"] == "s2"


def test_sede_tecnica_non_e_mai_la_sede_attiva_e_non_basta_per_entrare():
    assert su.sovrapponi(_titolare(), {"id": "su1", "pagine": {}}, ["t"], SEDI) is None
    u = su.sovrapponi(_titolare(), {"id": "su1", "pagine": {}, "ultimo_ristorante_id": "t"}, ["t", "s1"], SEDI)
    assert u["ristorante_id"] == "s1"


def test_catena_ignora_la_sede_tecnica():
    u = su.sovrapponi(_titolare(), {"id": "su1", "pagine": {"catena": True}}, ["s1", "s2"], SEDI)
    assert su.catena_consentita(u) is True


def test_sede_tecnica_solo_con_la_catena():
    # I costi comuni sono di tutta la catena: l'assegnazione da sola non basta.
    senza = su.sovrapponi(_titolare(), {"id": "su1", "pagine": {}}, ["s1", "t"], SEDI)
    assert su.sedi_consentite(senza) == {"s1"}
    con = su.sovrapponi(_titolare(), {"id": "su1", "pagine": {}}, ["s1", "s2"], SEDI)
    assert su.sedi_consentite(con) == {"s1", "s2", "t"}


def test_helper_per_il_titolare_non_restringono():
    t = _titolare()
    assert su.sedi_consentite(t) is None
    assert su.sede_consentita(t, "qualunque") is True
    assert su.ha_pagina(t, "margini") is True
    assert su.catena_consentita(t) is True
    assert su.pagine_per_client(t, None) is None
    su.vieta_ai_sotto_utenti(t)


# ─── Login: un guasto del DB non e' un tentativo fallito ─────────────────────


class _Catena:
    def __init__(self, dati=None, errore=None):
        self._dati, self._errore = dati, errore

    def __getattr__(self, _nome):
        return lambda *a, **k: self

    def execute(self):
        if self._errore:
            raise self._errore
        return type("R", (), {"data": self._dati})()


class _ClientFinto:
    def __init__(self, errore_sotto_utenti):
        self._errore = errore_sotto_utenti

    def table(self, nome):
        if nome == "users":
            return _Catena(dati=[])
        return _Catena(errore=self._errore)


@pytest.fixture
def tentativi(monkeypatch):
    from services import auth_service

    registrati = []
    monkeypatch.setattr(auth_service, "controlla_rate_limit", lambda *a, **k: (False, 0))
    monkeypatch.setattr(auth_service, "registra_tentativo", lambda email, ok, *a, **k: registrati.append(ok))
    return registrati


def test_guasto_del_db_sui_sotto_utenti_non_conta_come_tentativo(tentativi):
    from services.auth_service import verifica_credenziali

    utente, errore = verifica_credenziali(
        "chiunque@x.it", "Password-Lunga-1!", _ClientFinto(RuntimeError("connection reset"))
    )
    assert utente is None and "Credenziali errate" not in errore
    assert tentativi == []


def test_tabella_non_ancora_creata_e_credenziali_errate(tentativi):
    from services.auth_service import verifica_credenziali

    assenza = RuntimeError('relation "public.sotto_utenti" does not exist (42P01)')
    utente, errore = verifica_credenziali("chiunque@x.it", "Password-Lunga-1!", _ClientFinto(assenza))
    assert utente is None and errore == "Credenziali errate o account disattivato"
    assert tentativi == [False]
