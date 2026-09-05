"""Le ore extra si validano dove il dato entra, non a valle con un clamp.

**Lo squilibrio, misurato il 05/09/2026 notte.** Il ramo MENSILE rifiutava gia'
`ore_extra > ore_totali` con un 400 esplicito (workspace.py, POST /mensile). Il
ramo GIORNALIERO — quello che i dati reali usano: `mensile` false su 107 turni
su 107 — accettava qualunque valore **in silenzio**. Le extra sono un
sottoinsieme del turno (modello 05/09), quindi 8 ore di orario con 10 di extra
descrivono un turno che non esiste.

**Perche' non bastava il clamp a valle.** Ogni consumatore doveva difendersi da
solo con `min(extra, ore)`, ed erano cinque copie: worker, margini, workspace,
export, desktop, mobile. Una se l'era dimenticata — l'aggregazione per persona
del tab Personale — e mostrava **10 ore e 100 EUR** invece di 8 e 80, il 25% in
piu' su monte ore e costo. Un dato impossibile accettato in scrittura diventa un
difetto in ogni lettore che dimentica la guardia.

**Perche' un 400 e non un clamp silenzioso.** Il frontend clampava senza dirlo:
digitando 10 su un turno da 8 il campo mostrava 10 e ne salvava 8. Salvare un
numero diverso da quello digitato, senza avvisare, e' peggio di rifiutarlo: il
cliente crede di aver inserito un dato che non c'e'.

I test chiamano gli **endpoint veri** (non ricalcolano la formula): un test che
riscrive la regola sopravvive al mutante che rompe il codice di produzione.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.workspace as workspace

from tests.test_turni_mensili import _query_mock, _patch_workspace


def _body_nuovo(**over):
    campi = {
        "dipendente_id": "dip-1", "data_turno": "2026-09-02",
        "ora_inizio": "09:00", "ora_fine": "17:00",   # 8 ore
        "ora_inizio2": None, "ora_fine2": None,
        "ore_extra": None, "costo_orario": None,
        "costo_orario_extra": None, "note": None,
    }
    campi.update(over)
    return workspace.NuovoTurnoBody(**campi)


def _crea(**over):
    """Chiama l'endpoint di creazione vero, con il mensile assente."""
    patcher, _ = _patch_workspace(lambda _n: _query_mock([]))
    with patcher, patch.object(workspace, "_dipendente_esiste", MagicMock(return_value=True)), \
            patch.object(workspace, "_esiste_riga_mese", MagicMock(return_value=False)):
        return workspace.ws_personale_crea(_body_nuovo(**over), authorization="Bearer x")


def _aggiorna(esistente, **over):
    """Chiama l'endpoint di aggiornamento vero, con `esistente` gia' a DB."""
    patcher, _ = _patch_workspace(lambda _n: _query_mock([esistente]))
    campi = {
        "dipendente_id": None, "data_turno": None,
        "ora_inizio": None, "ora_fine": None,
        "ora_inizio2": None, "ora_fine2": None,
        "ore_extra": None, "costo_orario": None,
        "costo_orario_extra": None, "note": None,
    }
    campi.update(over)
    with patcher:
        return workspace.ws_personale_aggiorna(
            "turno-1", workspace.AggiornaTurnoBody(**campi), authorization="Bearer x"
        )


# ── creazione ────────────────────────────────────────────────────────────────

def test_piu_extra_che_ore_del_turno_viene_rifiutato():
    """Il caso misurato: 8 ore di orario, 10 dichiarate come straordinario."""
    with pytest.raises(HTTPException) as e:
        _crea(ore_extra=10)
    assert e.value.status_code == 400
    assert "non possono superare" in e.value.detail
    # L'errore dice i due numeri: senza, il cliente non sa cosa correggere.
    assert "10" in e.value.detail and "8" in e.value.detail


def test_extra_pari_alle_ore_e_ammesso():
    """Un turno interamente di straordinario esiste: 8 su 8 deve passare."""
    _crea(ore_extra=8)


def test_extra_negative_rifiutate():
    with pytest.raises(HTTPException) as e:
        _crea(ore_extra=-1)
    assert e.value.status_code == 400
    assert "negative" in e.value.detail


def test_il_turno_spezzato_conta_entrambi_gli_slot():
    """9-13 + 14-18 = 8 ore: 7 extra sono valide, e senza il secondo slot no.

    Se la validazione guardasse solo il primo slot vedrebbe 4 ore e rifiuterebbe
    un turno legittimo.
    """
    _crea(ora_inizio="09:00", ora_fine="13:00", ora_inizio2="14:00", ora_fine2="18:00", ore_extra=7)
    with pytest.raises(HTTPException):
        _crea(ora_inizio="09:00", ora_fine="13:00", ore_extra=7)


def test_il_turno_notturno_non_viene_rifiutato():
    """22:00-02:00 = 4 ore, non -20: e' il turno normale di un ristorante.

    `_ore_turno` usa `timedelta.seconds`, che su un delta negativo riporta al
    giorno dopo. Se la guardia calcolasse le ore in modo ingenuo, ogni turno
    serale con straordinario verrebbe rifiutato — il caso piu' frequente del
    dominio bloccato da una validazione nata per un caso raro.
    """
    _crea(ora_inizio="22:00", ora_fine="02:00", ore_extra=3)
    with pytest.raises(HTTPException):
        _crea(ora_inizio="22:00", ora_fine="02:00", ore_extra=5)


def test_senza_ore_extra_non_si_valida_niente():
    """Il campo e' facoltativo: assente non deve mai bloccare l'inserimento."""
    _crea(ore_extra=None)


# ── aggiornamento ────────────────────────────────────────────────────────────

_ESISTENTE = {
    "ora_inizio": "09:00", "ora_fine": "17:00",
    "ora_inizio2": None, "ora_fine2": None,
}


def test_la_guardia_non_si_aggira_aggiornando_il_turno():
    """Creare valido e poi modificare le sole extra deve fallire uguale.

    E' la via naturale per aggirare una validazione presente solo sulla POST.
    """
    with pytest.raises(HTTPException) as e:
        _aggiorna(_ESISTENTE, ore_extra=10)
    assert e.value.status_code == 400


def test_aggiornare_le_extra_si_valida_sul_turno_che_resta():
    """Il PATCH e' parziale: senza orari nel body si usano quelli a DB.

    Se la validazione leggesse solo il body vedrebbe un turno vuoto (0 ore) e
    rifiuterebbe qualunque valore di extra, rendendo il campo immodificabile.
    """
    _aggiorna(_ESISTENTE, ore_extra=6)


def test_extra_e_orari_cambiati_insieme_usano_i_nuovi_orari():
    """Accorciando il turno a 4 ore, 6 di extra non ci stanno piu'."""
    _aggiorna(_ESISTENTE, ora_fine="13:00", ore_extra=4)
    with pytest.raises(HTTPException):
        _aggiorna(_ESISTENTE, ora_fine="13:00", ore_extra=6)


# ── ramo mensile ─────────────────────────────────────────────────────────────
# La POST mensile validava gia' dal 30/7; il PATCH no, e si aggirava allo stesso
# modo del giornaliero. Qui si prova la coppia intera (ore + importo).

_MENSILE = {"ore_dichiarate": 160.0, "lordo_mensile": 2000.0}


def _aggiorna_mensile(esistente, **over):
    patcher, _ = _patch_workspace(lambda _n: _query_mock([esistente]))
    with patcher:
        return workspace.ws_personale_aggiorna_mensile(
            "riga-1", workspace.AggiornaTurnoMensileBody(**over), authorization="Bearer x"
        )


def test_mensile_extra_oltre_il_monte_ore_rifiutate_anche_in_aggiornamento():
    with pytest.raises(HTTPException) as e:
        _aggiorna_mensile(_MENSILE, ore_extra=200)
    assert e.value.status_code == 400
    assert "160" in e.value.detail


def test_mensile_importo_extra_oltre_il_lordo_rifiutato():
    """L'importo ha la sua soglia: puo' eccedere il lordo pur con ore valide."""
    with pytest.raises(HTTPException) as e:
        _aggiorna_mensile(_MENSILE, ore_extra=10, importo_extra=5000)
    assert e.value.status_code == 400
    assert "lordo" in e.value.detail


def test_mensile_valori_dentro_i_totali_passano():
    _aggiorna_mensile(_MENSILE, ore_extra=20, importo_extra=300)


def test_mensile_il_nuovo_totale_nel_body_ha_la_precedenza():
    """Alzando il monte ore nella stessa chiamata, extra piu' alte sono valide.

    Se la validazione leggesse solo il valore a DB, un aumento coerente di ore
    e straordinario verrebbe rifiutato.
    """
    _aggiorna_mensile(_MENSILE, ore_totali=220, ore_extra=200)
    with pytest.raises(HTTPException):
        _aggiorna_mensile(_MENSILE, ore_totali=100, ore_extra=150)


def test_mensile_extra_negative_rifiutate_con_il_messaggio_giusto():
    """Il messaggio deve dire "negative", non "superare le ore totali".

    La condizione univa i due casi: chi inseriva -1 leggeva un errore vero ma
    non il suo, e non sapeva cosa correggere.
    """
    patcher, _ = _patch_workspace(lambda _n: _query_mock([]))
    body = workspace.TurnoMensileBody(
        dipendente_id="dip-1", mese="2026-09", ore_totali=160.0, lordo=2000.0, ore_extra=-1,
    )
    with patcher, patch.object(workspace, "_dipendente_esiste", MagicMock(return_value=True)), \
            patch.object(workspace, "_esiste_riga_mese", MagicMock(return_value=False)):
        with pytest.raises(HTTPException) as e:
            workspace.ws_personale_crea_mensile(body, authorization="Bearer x")
    assert "negative" in e.value.detail


def test_mensile_extra_negative_rifiutate_anche_in_aggiornamento():
    """Il negativo e' l'altro asse dello stesso bypass: crea valido, poi correggi.

    Non e' simmetrico all'eccesso: il clamp `min(extra, ore)` dei lettori
    difende solo dall'ALTO, quindi un valore sotto zero arriva intatto in
    margini.py, dove `ore - extra` cresce e **gonfia** costo_dipendenti. Il
    dialog non lo permette, ma l'API si chiama anche direttamente.
    """
    with pytest.raises(HTTPException) as e:
        _aggiorna_mensile(_MENSILE, ore_extra=-5)
    assert e.value.status_code == 400
    assert "negative" in e.value.detail

    with pytest.raises(HTTPException) as e:
        _aggiorna_mensile(_MENSILE, importo_extra=-100)
    assert e.value.status_code == 400
    assert "negativo" in e.value.detail


def test_giornaliero_extra_negative_rifiutate_anche_in_aggiornamento():
    """Lo stesso asse sul ramo giornaliero: gia' coperto, qui reso esplicito."""
    with pytest.raises(HTTPException) as e:
        _aggiorna(_ESISTENTE, ore_extra=-2)
    assert e.value.status_code == 400
    assert "negative" in e.value.detail
