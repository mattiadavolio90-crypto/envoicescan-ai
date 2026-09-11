"""
Il client Supabase condiviso non deve parlare HTTP/2 con PostgREST.

Incidente 11/09/2026: su una connessione HTTP/2 riusata dal pool, il GOAWAY di
chiusura regolare (error_code:0) non invalidava la connessione lato client. La
richiesta successiva la riprendeva e moriva con ConnectionTerminated; essendo un
INSERT, httpx non ritenta -> login 500 con le credenziali gia' verificate.

Il fix agisce sul client gia' costruito da supabase-py invece di sostituirlo:
passare un httpx_client nostro farebbe perdere gli header che la libreria
inietta (apikey su tutti), e senza apikey ogni query risponde 401. Questi test
presidiano entrambe le meta': HTTP/2 spento E header intatti.
"""
import pytest

from supabase import create_client
from supabase.lib.client_options import SyncClientOptions

import services


@pytest.fixture
def client():
    c = create_client(
        "https://fake.supabase.co",
        "SERVICE_ROLE_FAKE",
        options=SyncClientOptions(postgrest_client_timeout=30, storage_client_timeout=30),
    )
    services._disattiva_http2(c)
    return c


def _pool(client):
    return client.postgrest.session._transport._pool


def test_http2_disattivato_sul_client_postgrest(client):
    assert _pool(client)._http2 is False


def test_keepalive_non_oltre_cinque_secondi(client):
    """Limita la finestra in cui una connessione gia' chiusa lato server resta
    riusabile dal pool."""
    assert _pool(client)._keepalive_expiry <= 5.0


@pytest.mark.parametrize("header", ["apikey", "authorization", "accept-profile", "content-profile"])
def test_header_di_supabase_preservati(client, header):
    """Senza apikey ogni query risponde 401: il fix non deve costare gli header."""
    assert client.postgrest.session.headers.get(header)


def test_il_pool_propaga_il_flag_alle_connessioni_nuove(client):
    """_http2 non e' un attributo inerte: il pool lo legge a ogni connessione
    che crea, quindi spegnerlo vale anche per quelle aperte dopo."""
    import inspect
    import httpcore._sync.connection_pool as cp

    assert "http2=self._http2" in inspect.getsource(cp)
