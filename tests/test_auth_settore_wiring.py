"""Il settore dell'account arriva al frontend da `/api/auth/login` e `/api/auth/me`.

`UserPublic.tipo_attivita` nasce 'ristorazione' per default: senza questo
cablaggio un account retail resterebbe ristorazione per il client senza che
nessun test lo dica. Qui si prova che i due endpoint chiedono il settore a
`settore_service` PER L'UTENTE GIUSTO e ne riportano la risposta.
"""
from __future__ import annotations

from types import SimpleNamespace

import services.fastapi_worker as fw
import services.settore_service as ss

UTENTE = {"id": "u-retail", "email": "negozio@oneflux.test", "nome_ristorante": "Bottega", "pagine_abilitate": None}


class _Contati:
    def __init__(self, count=1):
        self.count = count

    def table(self, _n):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a):
        return self

    def execute(self):
        return SimpleNamespace(data=[], count=self.count)


def _settore_finto(monkeypatch, risposta="retail"):
    chiamate = []

    def _finto(user_id, supabase_client=None):
        chiamate.append(user_id)
        return risposta

    monkeypatch.setattr(ss, "settore_utente", _finto)
    return chiamate


def test_auth_me_riporta_il_settore_dell_utente(monkeypatch):
    monkeypatch.setattr("services.auth_service.verifica_sessione_da_cookie", lambda _t: dict(UTENTE))
    monkeypatch.setattr(fw, "_get_supabase_client", lambda: _Contati())
    monkeypatch.setattr(fw, "_resolve_sede_attiva", lambda _u, _sb: ("sede-1", "Bottega"))
    chiamate = _settore_finto(monkeypatch)

    out = fw.auth_me(authorization="Bearer tok")

    assert out.tipo_attivita == "retail"
    assert chiamate == ["u-retail"]


def test_auth_login_riporta_il_settore_dell_utente(monkeypatch):
    monkeypatch.setattr(fw, "_check_rate_limit", lambda _h: None)
    monkeypatch.setattr("services.auth_service.verifica_credenziali", lambda _e, _p: (dict(UTENTE), None))
    monkeypatch.setattr("services.session_service.crea_sessione", lambda *_a, **_k: "tok")
    monkeypatch.setattr(fw, "_get_supabase_client", lambda: _Contati())
    chiamate = _settore_finto(monkeypatch)
    richiesta = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})

    out = fw.auth_login(fw.LoginRequest(email="negozio@oneflux.test", password="x"), richiesta)

    assert out.user.tipo_attivita == "retail"
    assert chiamate == ["u-retail"]


def test_un_ristorante_resta_ristorazione(monkeypatch):
    monkeypatch.setattr("services.auth_service.verifica_sessione_da_cookie", lambda _t: dict(UTENTE))
    monkeypatch.setattr(fw, "_get_supabase_client", lambda: _Contati())
    monkeypatch.setattr(fw, "_resolve_sede_attiva", lambda _u, _sb: ("sede-1", "Trattoria"))
    _settore_finto(monkeypatch, "ristorazione")
    assert fw.auth_me(authorization="Bearer tok").tipo_attivita == "ristorazione"
