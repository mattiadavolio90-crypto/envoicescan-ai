"""La vista scelta per Gestione Fatture torna indietro, non solo si salva.

Perche' esiste
==============
La preferenza attraversa SEI punti: la colonna `users.vista_fatture`, l'endpoint
che la scrive, le cinque `select` esplicite che la rileggono, `UserPublic` che la
mette nel payload, `SessionUser` lato Next e le due pagine che la passano al
client.

Se ne manca UNO — tipicamente una select che elenca le colonne a mano — il POST
risponde 200, il DB e' corretto, e la pagina riapre sulla vista di default per
sempre. Nessun errore, nessun log, nessun test rosso: il cliente pensa solo che
"non si salva". Un test sul solo POST sarebbe verde su quel bug, ed e' il motivo
per cui qui si misura il RITORNO, non la scrittura.

Le select sono cinque e non una perche' `auth_service` le ripete per login,
sessione e refresh: le elenca tutte `test_tutte_le_select_utente_portano_la_vista`.
"""
from __future__ import annotations

import pathlib
import re

import pytest
from fastapi import HTTPException

import services.fastapi_worker as fw
import services.routers.account as account

RADICE = pathlib.Path(__file__).resolve().parent.parent


def _bind(monkeypatch, sb, user_id="u1"):
    monkeypatch.setattr(account, "_resolve_user_from_token", lambda *a, **k: {"id": user_id})
    monkeypatch.setattr(account, "_get_supabase_client", lambda *a, **k: sb)


class _FakeUsers:
    """Tiene UNA riga utente e registra cosa ci viene scritto."""

    def __init__(self, riga=None):
        self.riga = riga or {"id": "u1", "tema": "dark", "vista_fatture": "agenda"}
        self.scritture = []
        self._payload = None

    def table(self, nome):
        assert nome == "users"
        return self

    def update(self, payload):
        self._payload = payload
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        self.scritture.append(dict(self._payload))
        self.riga.update(self._payload)
        return type("R", (), {"data": [self.riga]})()


def test_salva_la_vista_senza_dover_rispedire_il_tema(monkeypatch):
    """Il client manda solo il campo che cambia: con `tema` obbligatorio questa
    chiamata sarebbe un 422 e la preferenza non si salverebbe mai."""
    sb = _FakeUsers()
    _bind(monkeypatch, sb)

    res = account.account_preferenze(
        account.PreferenzeBody(vista_fatture="lista_mensile"), authorization="Bearer x"
    )

    assert res["ok"] is True
    assert res["vista_fatture"] == "lista_mensile"
    assert sb.scritture == [{"vista_fatture": "lista_mensile"}]


def test_salva_il_tema_da_solo_come_prima(monkeypatch):
    """Regressione: il tema e' l'uso storico dell'endpoint e non deve cambiare."""
    sb = _FakeUsers()
    _bind(monkeypatch, sb)

    res = account.account_preferenze(
        account.PreferenzeBody(tema="light"), authorization="Bearer x"
    )
    assert res["tema"] == "light"
    assert sb.scritture == [{"tema": "light"}]


@pytest.mark.parametrize("vista", ["agenda", "calendario", "lista_mensile"])
def test_accetta_le_tre_viste_esistenti(monkeypatch, vista):
    """Le stesse tre del CHECK sul DB e di TABS.scadenziario: se divergono, una
    vista salvabile dall'app verrebbe rifiutata dal database."""
    sb = _FakeUsers()
    _bind(monkeypatch, sb)
    assert account.account_preferenze(
        account.PreferenzeBody(vista_fatture=vista), authorization="Bearer x"
    )["vista_fatture"] == vista


def test_rifiuta_una_vista_inventata(monkeypatch):
    sb = _FakeUsers()
    _bind(monkeypatch, sb)
    with pytest.raises(HTTPException) as ei:
        account.account_preferenze(
            account.PreferenzeBody(vista_fatture="kanban"), authorization="Bearer x"
        )
    assert ei.value.status_code == 400
    assert sb.scritture == []


def test_rifiuta_un_tema_inventato_anche_con_la_vista_valida(monkeypatch):
    """La whitelist e' per campo: un tema sbagliato non deve passare solo perche'
    la vista accanto e' giusta, e non deve scrivere nulla a meta'."""
    sb = _FakeUsers()
    _bind(monkeypatch, sb)
    with pytest.raises(HTTPException) as ei:
        account.account_preferenze(
            account.PreferenzeBody(tema="fucsia", vista_fatture="agenda"),
            authorization="Bearer x",
        )
    assert ei.value.status_code == 400
    assert sb.scritture == []


def test_una_richiesta_vuota_e_un_errore_non_un_no_op(monkeypatch):
    """Un UPDATE senza campi sarebbe una scrittura inutile e un 200 bugiardo."""
    sb = _FakeUsers()
    _bind(monkeypatch, sb)
    with pytest.raises(HTTPException) as ei:
        account.account_preferenze(account.PreferenzeBody(), authorization="Bearer x")
    assert ei.value.status_code == 400


# ─── Il ritorno: il presidio che conta ───────────────────────────────────────

def _auth_me(monkeypatch, riga_utente):
    """Esegue `auth_me` vero sulla riga utente data, isolando solo il DB.

    Passa dalla funzione REALE e non costruisce `UserPublic` a mano: provato per
    mutazione, un payload costruito nel test resta verde anche se `auth_me`
    smette di valorizzare il campo — cioe' esattamente sul bug che questo file
    esiste per catturare.
    """
    # L'import e' lazy dentro `auth_me`: va mockato sul modulo di origine, non
    # su fastapi_worker (dove il nome non esiste a import-time).
    import services.auth_service as auth_service
    monkeypatch.setattr(auth_service, "verifica_sessione_da_cookie", lambda *a, **k: riga_utente)
    monkeypatch.setattr(fw, "_get_supabase_client", lambda *a, **k: None)
    monkeypatch.setattr(fw, "_resolve_sede_attiva", lambda *a, **k: (None, None))
    return fw.auth_me(authorization="Bearer x")


def test_la_vista_salvata_torna_nel_payload_di_sessione(monkeypatch):
    """Round-trip vero: dalla riga utente al payload che il frontend riceve.

    E' il test che cattura il fallimento silenzioso — POST 200, DB corretto,
    pagina sempre sul default perche' il campo non arriva mai a `UserPublic`.
    """
    payload = _auth_me(monkeypatch, {
        "id": "u1", "email": "a@b.it", "vista_fatture": "lista_mensile",
    })
    assert payload.vista_fatture == "lista_mensile"


def test_un_utente_senza_preferenza_atterra_sulla_lista(monkeypatch):
    """Default esplicito: i token emessi prima di questa colonna non la portano,
    e chi non ha mai scelto deve trovare la pagina com'era."""
    payload = _auth_me(monkeypatch, {"id": "u1", "email": "a@b.it"})
    assert payload.vista_fatture == "agenda"


def test_tutte_le_select_utente_portano_la_vista():
    """Ogni `select` che legge `tema` deve leggere anche `vista_fatture`.

    `tema` e' il gemello gia' in produzione e attraversa gli stessi percorsi
    (login, sessione, refresh, pagina account): dove passa lui deve passare la
    vista, o la preferenza si perde su UNO dei percorsi — quello meno battuto,
    che nessuno prova a mano.
    """
    mancanti = []
    for rel in ("services/auth_service.py", "services/routers/account.py"):
        testo = (RADICE / rel).read_text(encoding="utf-8-sig")
        for m in re.finditer(r'\.select\(\s*((?:"[^"]*"\s*)+)\)', testo, re.S):
            colonne = m.group(1)
            if "tema" in colonne and "vista_fatture" not in colonne:
                riga = testo[:m.start()].count("\n") + 1
                mancanti.append(f"{rel}:{riga}")
    assert not mancanti, (
        "select che leggono `tema` ma non `vista_fatture` — la preferenza si "
        "salva e non torna indietro:\n  " + "\n  ".join(mancanti)
    )
