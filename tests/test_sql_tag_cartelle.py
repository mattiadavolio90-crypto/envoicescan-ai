"""Cartelle e preferiti dei tag di sede, su Postgres vero (migration 20261013082535).

Con i due clienti del test di isolamento (A e B, due sedi ciascuno; ognuno ha una
cartella in sede1 con dentro il suo tag). Si prova:
- la FK composta rifiuta un tag nella cartella di un'altra sede o di un altro
  cliente, in INSERT e in UPDATE diretti, senza passare dal worker;
- eliminare una cartella lascia vivo il tag con cartella_id NULL e NON azzera
  user_id / ristorante_id (`ON DELETE SET NULL (cartella_id)`);
- il riordino con un id altrui non cambia niente per nessuno;
- il giro completo via endpoint (crea, sposta, stella, GET, elimina);
- anon e authenticated non hanno privilegi sulla tabella nuova.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_isolamento_per_risorsa import CHIAVE_WORKER, scenario, worker  # noqa: F401

pytestmark = pytest.mark.sql

MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "supabase" / "migrations" / "20261013082535_tag_cartelle_preferiti.sql"
)


@pytest.fixture
def psycopg():
    return pytest.importorskip("psycopg")


def _uno(sc, query, *params):
    return sc.conn.execute(query, params).fetchone()


def _nuova_cartella(sc, chi, sede, nome, ordine=0):
    return _uno(
        sc,
        "INSERT INTO public.custom_tag_cartelle (user_id, ristorante_id, nome, ordine) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        chi.ids["user_id"], sede, nome, ordine,
    )[0]


def _tag(sc, tag_id):
    return _uno(
        sc,
        "SELECT user_id::text, ristorante_id::text, nome, cartella_id, preferito "
        "FROM public.custom_tags WHERE id = %s",
        tag_id,
    )


def _ordini(sc):
    return sc.conn.execute(
        "SELECT id, ordine FROM public.custom_tag_cartelle ORDER BY id"
    ).fetchall()


# ─── La FK composta ───────────────────────────────────────────────────────────
def test_insert_di_un_tag_nella_cartella_di_un_altro_cliente_e_rifiutato(scenario, psycopg):
    sc = scenario
    a, b = sc.a, sc.b
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with sc.conn.transaction():
            sc.conn.execute(
                "INSERT INTO public.custom_tags (user_id, ristorante_id, nome, cartella_id) "
                "VALUES (%s, %s, 'INTRUSO', %s)",
                (a.ids["user_id"], a.ids["sede1"], b.ids["cartella_id"]),
            )


def test_update_di_un_tag_nella_cartella_di_un_altra_sede_dello_stesso_cliente_e_rifiutato(scenario, psycopg):
    sc = scenario
    a = sc.a
    cartella_sede2 = _nuova_cartella(sc, a, a.ids["sede2"], "ALTRA SEDE")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with sc.conn.transaction():
            sc.conn.execute(
                "UPDATE public.custom_tags SET cartella_id = %s WHERE id = %s",
                (cartella_sede2, a.ids["tag_id"]),
            )
    assert _tag(sc, a.ids["tag_id"])[3] == a.ids["cartella_id"]


def test_update_di_un_tag_nella_cartella_di_un_altro_cliente_e_rifiutato(scenario, psycopg):
    sc = scenario
    a, b = sc.a, sc.b
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with sc.conn.transaction():
            sc.conn.execute(
                "UPDATE public.custom_tags SET cartella_id = %s WHERE id = %s",
                (b.ids["cartella_id"], a.ids["tag_id"]),
            )


def test_tag_senza_cartella_e_ammesso(scenario):
    sc = scenario
    a = sc.a
    sc.conn.execute("UPDATE public.custom_tags SET cartella_id = NULL WHERE id = %s", (a.ids["tag_id"],))
    assert _tag(sc, a.ids["tag_id"])[3] is None


# ─── ON DELETE SET NULL (cartella_id) ────────────────────────────────────────
def test_delete_della_cartella_lascia_il_tag_vivo_senza_cartella(scenario):
    sc = scenario
    a, b = sc.a, sc.b
    sc.conn.execute("UPDATE public.custom_tags SET preferito = true WHERE id = %s", (a.ids["tag_id"],))

    sc.conn.execute("DELETE FROM public.custom_tag_cartelle WHERE id = %s", (a.ids["cartella_id"],))

    assert _tag(sc, a.ids["tag_id"]) == (
        a.ids["user_id"], a.ids["sede1"], f"TAG_{a.lettera}_SEGRETO", None, True
    ), "il tag resta, perde solo la cartella: user_id, sede e stella intatti"
    assert _tag(sc, b.ids["tag_id"])[3] == b.ids["cartella_id"]
    assert _uno(
        sc, "SELECT count(*) FROM public.custom_tag_prodotti WHERE tag_id = %s", a.ids["tag_id"]
    )[0] == 1


# ─── Vincoli della tabella ────────────────────────────────────────────────────
def test_nome_unico_per_sede_senza_badare_a_maiuscole_e_spazi(scenario, psycopg):
    sc = scenario
    a = sc.a
    _nuova_cartella(sc, a, a.ids["sede1"], "Pesce")
    with pytest.raises(psycopg.errors.UniqueViolation):
        with sc.conn.transaction():
            _nuova_cartella(sc, a, a.ids["sede1"], "  PESCE ")
    _nuova_cartella(sc, a, a.ids["sede2"], "Pesce")
    _nuova_cartella(sc, sc.b, sc.b.ids["sede1"], "Pesce")


def test_nome_vuoto_rifiutato(scenario, psycopg):
    sc = scenario
    with pytest.raises(psycopg.errors.CheckViolation):
        with sc.conn.transaction():
            _nuova_cartella(sc, sc.a, sc.a.ids["sede1"], "   ")


# ─── Riordino via endpoint ────────────────────────────────────────────────────
def test_riordino_con_un_id_altrui_non_cambia_niente_per_nessuno(scenario):
    sc = scenario
    a, b = sc.a, sc.b
    seconda = _nuova_cartella(sc, a, a.ids["sede1"], "SECONDA", ordine=1)
    _nuova_cartella(sc, b, b.ids["sede1"], "SECONDA B", ordine=1)
    prima = _ordini(sc)

    resp = sc.chiama(a, "PUT", "/api/tag/cartelle/ordine",
                     json_={"ids": [seconda, a.ids["cartella_id"], b.ids["cartella_id"]]})

    assert resp.status_code == 404, resp.text
    assert _ordini(sc) == prima

    resp = sc.chiama(a, "PUT", "/api/tag/cartelle/ordine", json_={"ids": [b.ids["cartella_id"]]})
    assert resp.status_code == 404, resp.text
    assert _ordini(sc) == prima


def test_riordino_con_elenco_incompleto_e_409(scenario):
    sc = scenario
    a = sc.a
    _nuova_cartella(sc, a, a.ids["sede1"], "SECONDA", ordine=1)
    prima = _ordini(sc)

    resp = sc.chiama(a, "PUT", "/api/tag/cartelle/ordine", json_={"ids": [a.ids["cartella_id"]]})

    assert resp.status_code == 409, resp.text
    assert _ordini(sc) == prima


def test_controllo_il_riordino_dei_propri_id_scrive(scenario):
    """Senza questo, il 404 qui sopra potrebbe venire da un endpoint che non
    scrive mai."""
    sc = scenario
    a = sc.a
    seconda = _nuova_cartella(sc, a, a.ids["sede1"], "SECONDA", ordine=1)

    resp = sc.chiama(a, "PUT", "/api/tag/cartelle/ordine", json_={"ids": [seconda, a.ids["cartella_id"]]})

    assert resp.status_code == 200, resp.text
    ordini = dict(_ordini(sc))
    assert (ordini[seconda], ordini[a.ids["cartella_id"]]) == (0, 1)


# ─── Il giro completo via endpoint ────────────────────────────────────────────
def test_giro_completo_crea_sposta_stella_leggi_elimina(scenario):
    sc = scenario
    a, b = sc.a, sc.b

    resp = sc.chiama(a, "POST", "/api/tag/cartelle", json_={"nome": "  Mare "})
    assert resp.status_code == 200, resp.text
    nuova = resp.json()["cartella"]
    assert (nuova["nome"], nuova["ordine"]) == ("Mare", 1)

    resp = sc.chiama(a, "POST", "/api/tag/cartelle", json_={"nome": "MARE"})
    assert resp.status_code == 409, resp.text

    resp = sc.chiama(a, "PATCH", f"/api/tag/{a.ids['tag_id']}", json_={"cartella_id": nuova["id"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tag"]["preferito"] is False, "un tag seminato senza la colonna nasce senza stella"
    resp = sc.chiama(a, "PATCH", f"/api/tag/{a.ids['tag_id']}", json_={"preferito": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tag"]["cartella_id"] == nuova["id"], "la stella non ha spostato il tag"

    corpo = sc.chiama(a, "GET", "/api/tag").json()
    assert [c["id"] for c in corpo["cartelle"]] == [a.ids["cartella_id"], nuova["id"]]
    tag = next(t for t in corpo["tags"] if t["id"] == a.ids["tag_id"])
    assert (tag["cartella_id"], tag["preferito"]) == (nuova["id"], True)
    assert b.marker not in str(corpo)

    resp = sc.chiama(a, "DELETE", f"/api/tag/cartelle/{nuova['id']}")
    assert resp.status_code == 200, resp.text
    assert _tag(sc, a.ids["tag_id"])[2:] == (f"TAG_{a.lettera}_SEGRETO", None, True)

    resp = sc.chiama(a, "PATCH", f"/api/tag/{a.ids['tag_id']}", json_={"cartella_id": b.ids["cartella_id"]})
    assert resp.status_code == 404, resp.text
    assert _tag(sc, a.ids["tag_id"])[3] is None


# ─── Permessi ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ruolo", ["anon", "authenticated"])
def test_i_ruoli_pubblici_non_toccano_le_cartelle(scenario, ruolo):
    """Su Supabase anon/authenticated ricevono grant nominali sulle tabelle nuove
    dalle default privileges; lo snapshot dei test non le riproduce. Si concede
    come fa Supabase, poi si riesegue la migration (idempotente): la sua REVOKE
    deve toglierli."""
    sc = scenario
    if not _uno(sc, "SELECT count(*) FROM pg_roles WHERE rolname = %s", ruolo)[0]:
        pytest.skip(f"ruolo {ruolo} assente nello snapshot")
    sc.conn.execute(f"GRANT ALL ON public.custom_tag_cartelle TO {ruolo}")
    sc.conn.execute(f"GRANT USAGE, SELECT ON SEQUENCE public.custom_tag_cartelle_id_seq TO {ruolo}")
    assert _uno(sc, "SELECT has_table_privilege(%s, 'public.custom_tag_cartelle', 'SELECT')", ruolo)[0] is True
    assert _uno(
        sc, "SELECT has_sequence_privilege(%s, 'public.custom_tag_cartelle_id_seq', 'USAGE')", ruolo
    )[0] is True, "senza il grant la REVOKE della sequenza non e' provata"

    sc.conn.execute(MIGRATION.read_text(encoding="utf-8"))

    for permesso in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert _uno(
            sc, "SELECT has_table_privilege(%s, 'public.custom_tag_cartelle', %s)", ruolo, permesso
        )[0] is False, permesso
    assert _uno(
        sc, "SELECT has_sequence_privilege(%s, 'public.custom_tag_cartelle_id_seq', 'USAGE')", ruolo
    )[0] is False


def test_rls_attiva_e_forzata_e_service_role_scrive(scenario):
    sc = scenario
    assert _uno(
        sc,
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid = 'public.custom_tag_cartelle'::regclass",
    ) == (True, True)
    for permesso in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert _uno(
            sc, "SELECT has_table_privilege('service_role', 'public.custom_tag_cartelle', %s)", permesso
        )[0] is True, permesso
