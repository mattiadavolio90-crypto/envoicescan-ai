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
    update().eq().execute() per la scrittura (registrata, per asserirla).

    `select()` PROIETTA davvero le colonne richieste. Un mock che restituisce
    sempre la riga intera regala al codice colonne che la query reale non ha
    chiesto: cosi' togliere `nome_ristorante` dalla select non farebbe fallire
    nessun test, mentre in produzione la regola GDPR "non usare il nome del
    ristorante" smetterebbe di scattare in silenzio.
    """

    def __init__(self, utente):
        self.utente = utente
        self.updates = []
        self.colonne = None

    def table(self, _name):
        return self

    def select(self, colonne="*", *_a, **_k):
        self.colonne = [c.strip() for c in colonne.split(",")] if colonne != "*" else None
        return self

    def update(self, payload):
        self.updates.append(payload)
        return self

    def eq(self, *_a, **_k):
        return self

    def single(self):
        return self

    def execute(self):
        if self.colonne is None:
            return _Row(dict(self.utente))
        return _Row({k: v for k, v in self.utente.items() if k in self.colonne})


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


# ── Il gate sulla password attuale ───────────────────────────────────────────
#
# I test sopra mockano verify_and_migrate_password a True di proposito: isolano
# la policy sulla password NUOVA. Il rovescio e' che nessuno di loro misura il
# gate: disattivandolo restavano tutti verdi, cioe' si sarebbe potuta cambiare
# la password senza conoscere quella vecchia — chiunque avesse un token di
# sessione (browser lasciato aperto, token rubato) sarebbe diventato padrone
# dell'account. Questi test esercitano il gate invece di aggirarlo.


def _chiama_con_verifica(password_attuale, nuova_password, sb, esito_verifica):
    """Come _chiama, ma la verifica della password attuale risponde davvero:
    `esito_verifica` e' cio' che verify_and_migrate_password ritornerebbe."""
    spia = MagicMock(return_value=esito_verifica)
    with patch.multiple(
        account,
        _resolve_user_from_token=MagicMock(return_value={"id": "u1"}),
        _get_supabase_client=MagicMock(return_value=sb),
    ), patch("services.auth_service.verify_and_migrate_password", spia), \
         patch("services.auth_service.ph") as ph, \
         patch("services.session_service.revoca_tutte_sessioni"):
        ph.hash.return_value = "$argon2id$nuovo"
        try:
            return spia, account.account_cambia_password(
                account.CambioPasswordBody(
                    password_attuale=password_attuale,
                    nuova_password=nuova_password,
                ),
                authorization="Bearer t",
            )
        except account.HTTPException as exc:
            return spia, exc


def test_password_attuale_sbagliata_blocca_il_cambio():
    """Il caso che conta: nuova password perfettamente conforme, ma la vecchia
    non e' quella giusta. Deve fallire, e soprattutto NON scrivere nulla."""
    sb = FakeSB(UTENTE)
    _, esito = _chiama_con_verifica("non-e-la-mia", "Ab1!defghij", sb, esito_verifica=False)

    assert isinstance(esito, account.HTTPException), (
        "con la password attuale sbagliata la route ha lasciato passare il cambio"
    )
    assert esito.status_code == 400
    assert "attuale" in str(esito.detail).lower()
    assert sb.updates == [], "password cambiata senza conoscere quella vecchia"


def test_password_attuale_verificata_contro_la_riga_utente():
    """Non basta che la verifica venga chiamata: deve ricevere la riga del DB
    (con l'hash) e la password digitata. Passandole altro, il confronto
    avverrebbe contro il nulla e tornerebbe sempre vero."""
    sb = FakeSB(UTENTE)
    spia, _ = _chiama_con_verifica("la-mia-vecchia", "Ab1!defghij", sb, esito_verifica=True)

    assert spia.call_count == 1, "la password attuale non viene verificata affatto"
    riga, digitata = spia.call_args.args
    assert riga.get("password_hash") == UTENTE["password_hash"], (
        "la verifica non riceve l'hash dell'utente"
    )
    assert digitata == "la-mia-vecchia", "la verifica non riceve la password digitata"


def test_il_gate_precede_la_policy():
    """Ordine, non solo presenza: con password attuale sbagliata E nuova debole
    l'utente deve sentirsi dire che sbaglia la vecchia. Il contrario rivelerebbe
    a un attaccante i requisiti da soddisfare prima ancora di autenticarsi."""
    sb = FakeSB(UTENTE)
    _, esito = _chiama_con_verifica("non-e-la-mia", "corta", sb, esito_verifica=False)

    assert isinstance(esito, account.HTTPException)
    assert "attuale" in str(esito.detail).lower(), (
        f"la policy ha parlato prima del gate: {esito.detail!r}"
    )
    assert sb.updates == []
