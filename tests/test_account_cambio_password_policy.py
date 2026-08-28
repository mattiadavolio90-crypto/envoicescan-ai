"""Test guardia: il cambio password dall'area Account applica la policy GDPR.

Tre percorsi scrivono una password: reset da token (auth_service), imposta-password
admin (routers/admin) e questo. I primi due chiamavano gia'
`valida_password_compliance`; questo si fermava a `len < 8`, quindi dall'area
Account si poteva impostare una password che il reset via email avrebbe rifiutato.

Il mutante che conta e' "rimetti `len(...) < 8`": deve far fallire almeno un test,
altrimenti la suite misura solo che la funzione non esplode.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.routers.account as account


class _Row:
    def __init__(self, data):
        self.data = data


class FakeSB:
    """Mock supabase: select().eq().single().execute() per la lettura utente,
    update().eq().execute() per la scrittura (registrata, per asserirla)."""

    def __init__(self, utente):
        self.utente = utente
        self.updates = []

    def table(self, _name):
        return self

    def select(self, *_a, **_k):
        return self

    def update(self, payload):
        self.updates.append(payload)
        return self

    def eq(self, *_a, **_k):
        return self

    def single(self):
        return self

    def execute(self):
        return _Row(self.utente)


UTENTE = {
    "id": "u1",
    "email": "mario@ristorante.it",
    "nome_ristorante": "Da Mario",
    "password_hash": "$argon2id$fake",
}


def _chiama(nuova_password, sb):
    """Esegue la route con l'attuale sempre corretta: qui misuriamo la policy
    sulla NUOVA password, non la verifica di quella vecchia."""
    with patch.multiple(
        account,
        _resolve_user_from_token=MagicMock(return_value={"id": "u1"}),
        _get_supabase_client=MagicMock(return_value=sb),
    ), patch("services.auth_service.verify_and_migrate_password", return_value=True):
        return account.account_cambia_password(
            account.CambioPasswordBody(
                password_attuale="vecchia-qualsiasi",
                nuova_password=nuova_password,
            ),
            authorization="Bearer t",
        )


@pytest.mark.parametrize(
    "password, motivo",
    [
        ("pizza123", "8 caratteri: passava col vecchio len >= 8, la policy ne vuole 10"),
        ("ciao1234", "8 caratteri, nessuna maiuscola ne' simbolo"),
        ("Password1", "9 caratteri e in blacklist password comuni"),
        ("aaaaaaaaaaaa", "un solo carattere ripetuto"),
        ("mario1234567", "contiene la parte locale dell'email"),
        ("damario12345", "contiene il nome del ristorante"),
    ],
)
def test_password_debole_rifiutata(password, motivo):
    sb = FakeSB(UTENTE)
    with pytest.raises(account.HTTPException) as ei:
        _chiama(password, sb)
    assert ei.value.status_code == 400, motivo
    assert sb.updates == [], f"password scritta comunque nel DB: {motivo}"


def test_password_conforme_accettata():
    sb = FakeSB(UTENTE)
    with patch("services.auth_service.ph") as ph, \
         patch("services.session_service.revoca_tutte_sessioni"):
        ph.hash.return_value = "$argon2id$nuovo"
        out = _chiama("Ab1!defghij", sb)
    assert out.get("ok") is True or out is not None
    assert any("password_hash" in u for u in sb.updates), "l'hash non e' stato scritto"


def test_la_policy_e_la_stessa_del_reset():
    """Non basta che sia 'piu' severa di prima': deve essere ESATTAMENTE quella
    degli altri percorsi. Se un domani la policy cambia solo di la', questo
    test cade."""
    from services.auth_service import valida_password_compliance

    for password in ["pizza123", "Password1", "Ab1!defghij", "ciao1234"]:
        attesi_errori = bool(
            valida_password_compliance(password, UTENTE["email"], UTENTE["nome_ristorante"])
        )
        sb = FakeSB(UTENTE)
        if attesi_errori:
            with pytest.raises(account.HTTPException):
                _chiama(password, sb)
            assert sb.updates == []
        else:
            with patch("services.auth_service.ph") as ph, \
                 patch("services.session_service.revoca_tutte_sessioni"):
                ph.hash.return_value = "$argon2id$nuovo"
                _chiama(password, sb)
            assert sb.updates, f"{password!r} conforme al reset ma rifiutata qui"


def test_email_e_nome_ristorante_passati_alla_policy():
    """La policy va chiamata CON email e nome ristorante della riga utente.

    Passarle stringhe vuote non fa fallire nessun test sulle password deboli
    per altri motivi: le due regole "non usare la tua email" e "non usare il
    nome del ristorante" smetterebbero semplicemente di scattare, in silenzio.
    Qui si misura l'argomento, non solo l'esito.
    """
    sb = FakeSB(UTENTE)
    with patch.object(account, "HTTPException", account.HTTPException), \
         patch("services.auth_service.valida_password_compliance", return_value=[]) as spia, \
         patch("services.auth_service.ph") as ph, \
         patch("services.session_service.revoca_tutte_sessioni"):
        ph.hash.return_value = "$argon2id$nuovo"
        _chiama("Ab1!defghij", sb)

    assert spia.call_count == 1
    args = spia.call_args.args
    assert args[1] == UTENTE["email"], "email non passata alla policy"
    assert args[2] == UTENTE["nome_ristorante"], "nome ristorante non passato alla policy"


def test_password_col_nome_ristorante_rifiutata_davvero():
    """Controprova end-to-end della regola che dipende dal contesto: se il nome
    del ristorante non arrivasse alla policy, questa password passerebbe."""
    sb = FakeSB(UTENTE)
    with pytest.raises(account.HTTPException) as ei:
        _chiama("Damario!2345", sb)
    assert ei.value.status_code == 400
    assert "ristorante" in str(ei.value.detail).lower()
    assert sb.updates == []
