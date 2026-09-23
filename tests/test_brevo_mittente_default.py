"""Test: senza BREVO_SENDER_EMAIL ogni invio parte da un sender verificato.

Contesto (23/09/2026). `invia_codice_reset` (reset password self-service) aveva
come default `contact@updates.brevo.com`, mentre `services/routers/admin.py`
usava gia' `agent@oneflux.it` con un commento esplicito: un mittente NON
verificato in Brevo fa fallire l'invio in silenzio (status != 201). Il difetto
era latente — su Railway `BREVO_SENDER_EMAIL` e' impostata — ma sarebbe
riemerso al primo ambiente senza quella variabile, e solo sul reset password:
onboarding e reinvio attivazione avrebbero continuato a funzionare, rendendo il
guasto difficile da leggere.

I test NON importano la costante dal codice: il valore atteso e' scritto per
esteso. Un test che legge `BREVO_SENDER_EMAIL_DEFAULT` da `config.constants` e
lo confronta col payload passerebbe anche se qualcuno cambiasse la costante in
un indirizzo non verificato — atteso e ottenuto si muoverebbero insieme.

Cosa viene verificato e' il PAYLOAD effettivamente spedito a Brevo, non il
sorgente: un assert sul testo della funzione sopravvive alla mutazione.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.auth_service as auth

# Sender verificato in Brevo. Scritto a mano di proposito (vedi docstring).
SENDER_VERIFICATO = "agent@oneflux.it"

# Env di base: la chiave c'e', il mittente NO. E' il caso che il fix indirizza.
_ENV_SENZA_SENDER = {"BREVO_API_KEY": "k"}


def _client_utente_esistente():
    """Client Supabase minimo: l'email risulta registrata, cosi' si arriva all'invio."""
    q = MagicMock()
    for m in ("select", "eq", "update", "insert", "maybe_single", "limit", "order"):
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(data={"id": "u1"})
    client = MagicMock()
    client.table.return_value = q
    return client


def _payload_reset(env: dict, secrets_brevo=None):
    """Esegue invia_codice_reset e restituisce il JSON spedito a Brevo."""
    post = MagicMock(return_value=SimpleNamespace(status_code=201, text=""))
    fake_st = SimpleNamespace(
        secrets={"brevo": secrets_brevo} if secrets_brevo is not None else {}
    )
    with patch.object(auth, "_check_reset_rate_limit", MagicMock(return_value=None)), \
         patch.object(auth, "_record_reset_request", MagicMock()), \
         patch.dict("os.environ", env, clear=True), \
         patch.dict("sys.modules", {"streamlit": fake_st}), \
         patch("requests.post", post):
        ok, _msg = auth.invia_codice_reset(
            "tizio@esempio.it", supabase_client=_client_utente_esistente()
        )
    assert ok is True, "l'invio doveva riuscire: il test misura il payload, non l'esito"
    assert post.call_count == 1
    return post.call_args.kwargs["json"]


class TestResetSelfService:
    """services/auth_service.py — invia_codice_reset."""

    def test_senza_env_usa_il_sender_verificato(self):
        payload = _payload_reset(_ENV_SENZA_SENDER)
        assert payload["sender"]["email"] == SENDER_VERIFICATO

    def test_env_impostata_vince_sul_default(self):
        """Railway resta padrone della configurazione: il default e' solo la rete."""
        env = dict(_ENV_SENZA_SENDER, BREVO_SENDER_EMAIL="altro@oneflux.it")
        payload = _payload_reset(env)
        assert payload["sender"]["email"] == "altro@oneflux.it"

    def test_secrets_vuoto_non_azzera_il_mittente(self):
        """Il ramo st.secrets (shim) non deve sovrascrivere il default con ''.

        Lo shim popola st.secrets['brevo'] solo se BREVO_API_KEY e' presente,
        ma un secrets.toml scritto a mano puo' avere la chiave vuota: con
        `.get('sender_email', default)` un valore '' passava come mittente.
        """
        payload = _payload_reset(
            {}, secrets_brevo={"api_key": "k", "sender_email": "", "sender_name": ""}
        )
        assert payload["sender"]["email"] == SENDER_VERIFICATO
        assert payload["sender"]["name"] == "ONEFLUX"

    def test_secrets_valorizzato_viene_usato(self):
        payload = _payload_reset(
            {}, secrets_brevo={"api_key": "k", "sender_email": "da-secrets@oneflux.it"}
        )
        assert payload["sender"]["email"] == "da-secrets@oneflux.it"


class TestEmailAmministrative:
    """services/routers/admin.py — _brevo_send (onboarding, reinvio attivazione)."""

    def test_senza_env_usa_lo_stesso_sender_verificato(self):
        from services.routers import admin

        post = MagicMock(return_value=SimpleNamespace(status_code=201, text=""))
        with patch.dict("os.environ", _ENV_SENZA_SENDER, clear=True), \
             patch("requests.post", post):
            assert admin._brevo_send("a@b.it", "Tizio", "Oggetto", "<p>x</p>") is True

        assert post.call_args.kwargs["json"]["sender"]["email"] == SENDER_VERIFICATO


class TestNessunMittenteNonVerificato:
    """Il vecchio default non deve rientrare da nessuna porta."""

    def test_i_due_canali_partono_dallo_stesso_mittente(self):
        """Se divergono di nuovo, il guasto torna visibile solo su un canale."""
        from services.routers import admin

        post = MagicMock(return_value=SimpleNamespace(status_code=201, text=""))
        with patch.dict("os.environ", _ENV_SENZA_SENDER, clear=True), \
             patch("requests.post", post):
            admin._brevo_send("a@b.it", "Tizio", "Oggetto", "<p>x</p>")
        sender_admin = post.call_args.kwargs["json"]["sender"]["email"]

        sender_reset = _payload_reset(_ENV_SENZA_SENDER)["sender"]["email"]

        assert sender_reset == sender_admin

    @pytest.mark.parametrize(
        "modulo",
        ["services/auth_service.py", "services/routers/admin.py", "services/_streamlit_shim.py"],
    )
    def test_nessun_riferimento_al_vecchio_default(self, modulo):
        """Presidio di contorno: il sorgente non deve piu' citarlo.

        Non sostituisce i test sul payload qui sopra — un grep resta verde se
        il default viene spostato altrove — ma intercetta il copia-incolla di
        `contact@updates.brevo.com` in un ramo nuovo non ancora coperto.
        """
        from pathlib import Path

        radice = Path(__file__).resolve().parent.parent
        testo = (radice / modulo).read_text(encoding="utf-8")
        assert "contact@updates.brevo.com" not in testo
