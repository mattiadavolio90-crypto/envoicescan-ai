"""scripts/crea_sotto_utente.py: l'unico modo di creare un sotto-utente finche'
non c'e' il pannello Admin. Scrive credenziali e permessi sui dati veri: la
validazione e il dry-run si provano, non si leggono.
"""
from argparse import Namespace
import importlib.util
from pathlib import Path

import pytest

from tests.test_isolamento_per_risorsa import scenario, worker  # noqa: F401
from tests.test_sql_sotto_utenti import _cache_pulita  # noqa: F401

_SPEC = importlib.util.spec_from_file_location(
    "crea_sotto_utente", Path(__file__).resolve().parent.parent / "scripts" / "crea_sotto_utente.py")
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)

SEDI = [{"id": "r1", "nome_ristorante": "NAVIGLI"}, {"id": "r2", "nome_ristorante": "CASATI 14"}]


def test_pagine_esplicite_e_sedi_per_nome_o_id():
    pagine, ids, errori = script.valida_richiesta(["home", "Margini"], ["navigli", "r2", "r1"], SEDI)
    assert errori == []
    assert ids == ["r1", "r2"]
    assert {p for p, v in pagine.items() if v} == {"home", "margini"}
    assert pagine["catena"] is False and len(pagine) == 9


def test_errori_di_richiesta():
    assert script.valida_richiesta(["menu"], ["r1"], SEDI)[2] == ["pagine sconosciute: menu"]
    assert "sede non trovata" in script.valida_richiesta(["home"], ["BRERA"], SEDI)[2][0]
    assert script.valida_richiesta(["home"], [""], SEDI)[2] == ["serve almeno una sede"]


def test_catena_solo_con_tutte_le_sedi():
    assert script.valida_richiesta(["catena"], ["r1"], SEDI)[2] == ["la Catena si puo' dare solo con TUTTE le sedi"]
    assert script.valida_richiesta(["catena"], ["tutte"], SEDI)[2] == []


PASSWORD = "Turno-Serale-Sede-2027!"


def _args(sc, **kw):
    base = dict(titolare="a@isolamento.test", email="script@isolamento.test", nome="Sala",
                pagine="home,margini", sedi=sc.a.ids["sede1"], password=PASSWORD, esegui=False)
    base.update(kw)
    return Namespace(**base)


def _righe(sc):
    return sc.conn.execute("SELECT count(*) FROM public.sotto_utenti WHERE email = 'script@isolamento.test'").fetchone()[0]


@pytest.mark.sql
def test_dry_run_non_scrive_e_esegui_crea_un_sotto_utente_che_entra(scenario):
    from tests.test_sql_sotto_utenti import _login

    sc = scenario
    script.crea(sc.sb, _args(sc))
    assert _righe(sc) == 0
    script.crea(sc.sb, _args(sc, esegui=True))
    assert _righe(sc) == 1
    r = _login(sc, "script@isolamento.test", PASSWORD)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["sotto_utente"] is True
    assert sorted(r.json()["user"]["pagine_abilitate"]) == ["home", "margini"]

    script.disattiva(sc.sb, "script@isolamento.test", esegui=False)
    assert _login(sc, "script@isolamento.test", PASSWORD).status_code == 200
    script.disattiva(sc.sb, "script@isolamento.test", esegui=True)
    assert _login(sc, "script@isolamento.test", PASSWORD).status_code == 401


@pytest.mark.sql
def test_catena_senza_tutte_le_sedi_non_crea_niente(scenario):
    sc = scenario
    with pytest.raises(SystemExit):
        script.crea(sc.sb, _args(sc, pagine="home,catena", esegui=True))
    assert _righe(sc) == 0


@pytest.mark.sql
def test_password_debole_non_crea_niente(scenario):
    # Stesse regole del titolare: il script non e' una porta di servizio.
    sc = scenario
    with pytest.raises(SystemExit) as e:
        script.crea(sc.sb, _args(sc, password="ristorante", esegui=True))
    assert "password" in str(e.value).lower()
    assert _righe(sc) == 0
