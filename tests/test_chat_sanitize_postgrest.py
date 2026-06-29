"""I tool della chat interpolano il termine del modello AI in un filtro PostgREST
.or_(...). _sanitize_postgrest_term rende il termine inerte rimuovendo i
metacaratteri (virgola/parentesi/asterisco/due punti/backslash/apici) che
potrebbero alterare la sintassi del gruppo OR. NON è una falla cross-tenant
(l'isolamento .eq("user_id") resta AND), ma evita query malformate."""
import os

os.environ.setdefault("WORKER_DEV_MODE", "1")

from services.fastapi_worker import _sanitize_postgrest_term


def test_termine_pulito_invariato():
    assert _sanitize_postgrest_term("birra") == "birra"
    assert _sanitize_postgrest_term("olio extravergine") == "olio extravergine"


def test_rimuove_virgole_e_parentesi():
    # una virgola spezzerebbe il gruppo OR di PostgREST
    assert "," not in _sanitize_postgrest_term("birra,categoria.ilike.%x%")
    assert "(" not in _sanitize_postgrest_term("a(b)c")
    assert ")" not in _sanitize_postgrest_term("a(b)c")


def test_rimuove_metacaratteri_vari():
    out = _sanitize_postgrest_term('birra*:test\\"x\'')
    for ch in ("*", ":", "\\", '"', "'"):
        assert ch not in out


def test_none_e_vuoto():
    assert _sanitize_postgrest_term(None) == ""
    assert _sanitize_postgrest_term("") == ""
    assert _sanitize_postgrest_term("   ") == ""


def test_wildcard_ilike_ammesse():
    # % e _ sono wildcard ilike legittime, non vanno rimosse
    out = _sanitize_postgrest_term("ac%ua_test")
    assert "%" in out and "_" in out


def test_tentativo_injection_neutralizzato():
    # un termine costruito per iniettare un filtro extra diventa testo inerte
    out = _sanitize_postgrest_term("x%,user_id.neq.altro")
    assert "," not in out
    # resta una stringa di ricerca innocua
    assert "user_id.neq.altro" in out.replace(" ", "")
