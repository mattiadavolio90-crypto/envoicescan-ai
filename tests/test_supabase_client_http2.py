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


def test_http2_resta_spento_dopo_la_ricostruzione_di_postgrest(monkeypatch, client):
    """Sugli eventi auth (SIGNED_IN / TOKEN_REFRESHED / SIGNED_OUT) supabase-py
    azzera _postgrest, e l'accesso successivo lo ricostruisce con un pool nuovo
    che nasce http2=True. Senza una ri-applicazione a ogni get_supabase_client()
    il fix sparirebbe in silenzio proprio sul percorso che _riallinea_auth_header
    presidia (refresh_session sul singleton, non coperto da SKIP_SUPABASE_AUTH)."""
    import services

    monkeypatch.setattr(services, "_cached_client", lambda: client)
    monkeypatch.setattr(services, "_cached_service_role_key", lambda: "SERVICE_ROLE_FAKE")

    assert _pool(services.get_supabase_client())._http2 is False

    client._postgrest = None  # quello che fa _listen_to_auth_events

    ricostruito = services.get_supabase_client()
    assert _pool(ricostruito)._http2 is False
    # e la ri-applicazione non costa gli header
    assert ricostruito.postgrest.session.headers.get("apikey")


def test_riconosce_la_vera_eccezione_di_httpx():
    """_e_errore_di_connessione riconosce per NOME di classe, per non importare
    httpx in session_service. Gli altri test definiscono una classe col nome
    giusto, quindi resterebbero verdi anche se httpx la rinominasse: qui si usa
    quella vera, cosi' una rinomina a monte fa rumore."""
    import httpx
    from services.session_service import _e_errore_di_connessione

    assert _e_errore_di_connessione(httpx.RemoteProtocolError("boom")) is True
    assert _e_errore_di_connessione(httpx.ConnectError("boom")) is True
    assert _e_errore_di_connessione(Exception("permission denied")) is False


def test_il_client_anon_non_viene_usato_per_query_dati():
    """Il client anon e' condiviso per processo, e sign_in_with_password gli
    lascia negli header il JWT dell'ultimo utente. Oggi e' innocuo perche' tutti
    i suoi call site usano solo `.auth.*` (le operazioni sono body-scoped e
    GoTrue ignora quell'header). Se qualcuno ci aggiungesse un `.table()`
    erediterebbe il JWT altrui con apikey anon e RLS attiva: questo test tiene la
    regola verificata invece che solo scritta nel docstring."""
    import ast
    import pathlib

    sorgente = pathlib.Path("services/auth_service.py").read_text(encoding="utf-8")
    albero = ast.parse(sorgente)

    # Nomi locali a cui viene assegnato il client anon (es. `_anon = _get_...()`).
    nomi_anon = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Call):
            f = nodo.value.func
            if isinstance(f, ast.Name) and f.id == "_get_supabase_anon_client":
                for t in nodo.targets:
                    if isinstance(t, ast.Name):
                        nomi_anon.add(t.id)

    assert nomi_anon, "nessun assegnamento del client anon trovato: test da aggiornare"

    # Gli alias condizionali sono il modo in cui il client anon viene davvero
    # usato: `_refresh_client = _anon if _anon is not None else supabase_client`.
    # Senza questo passaggio un `_refresh_client.table()` sfuggirebbe al presidio
    # — punto cieco trovato dal code-reviewer. Si itera perche' un alias puo'
    # nascere da un altro alias.
    for _ in range(5):
        nuovi = set()
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.IfExp):
                rami = [nodo.value.body, nodo.value.orelse]
                if any(isinstance(r, ast.Name) and r.id in nomi_anon for r in rami):
                    for t in nodo.targets:
                        if isinstance(t, ast.Name) and t.id not in nomi_anon:
                            nuovi.add(t.id)
        if not nuovi:
            break
        nomi_anon |= nuovi

    assert "_refresh_client" in nomi_anon, (
        "l'alias condizionale del client anon non e' stato risolto: "
        f"nomi tracciati = {sorted(nomi_anon)}"
    )

    # Nessuno di quei nomi deve finire in una `.table(...)`.
    usi_vietati = []
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            if nodo.func.attr == "table" and isinstance(nodo.func.value, ast.Name):
                if nodo.func.value.id in nomi_anon:
                    usi_vietati.append(f"{nodo.func.value.id}.table() riga {nodo.lineno}")

    assert not usi_vietati, (
        "il client anon e' condiviso e porta il JWT dell'ultimo utente loggato: "
        f"non usarlo per query dati -> {usi_vietati}"
    )


def test_client_del_queue_worker_cachato(monkeypatch):
    """worker/run.py chiama questa factory dentro il suo `while True`: senza
    cache il queue-worker creava un client nuovo (pool proprio, mai chiuso) a
    ogni ciclo di polling — lo stesso pattern dell'incidente 11/09/2026."""
    from worker import queue_processor as qp

    monkeypatch.setattr(qp, "_CLIENT_CACHE", {})
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SERVICE_ROLE_FAKE")

    creati = []

    def _fake_create_client(url, key, options=None):
        creati.append(url)
        return client_finto

    class _Pool:
        def __init__(self):
            self._http2 = True
            self._keepalive_expiry = 60.0

    pool = _Pool()

    class _Sess:
        _transport = type("T", (), {"_pool": pool})()

    class _PG:
        session = _Sess()

    client_finto = type("C", (), {"postgrest": _PG()})()

    monkeypatch.setattr(qp, "create_client", _fake_create_client)

    primo = qp.get_supabase_client()
    for _ in range(20):
        qp.get_supabase_client()

    assert len(creati) == 1, f"client creati: {len(creati)} (atteso 1)"
    assert primo is client_finto
    # e il trasporto e' stato portato su HTTP/1.1 come sul worker web
    assert pool._http2 is False
