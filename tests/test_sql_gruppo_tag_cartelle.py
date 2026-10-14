"""Cartelle e preferiti dei tag di catena, su Postgres vero (migration 20261013141040).

Con i due clienti del test di isolamento (A e B, due sedi ciascuno; ognuno ha
un tag di catena dentro una sua cartella di catena). Si prova:
- la FK composta rifiuta un tag nella cartella di un altro account, in INSERT
  e in UPDATE diretti, senza passare dal worker;
- eliminare una cartella lascia vivo il tag con cartella_id NULL e NON azzera
  user_id (`ON DELETE SET NULL (cartella_id)`);
- il riordino con un id altrui non cambia niente per nessuno;
- il giro completo via endpoint (crea, sposta, stella, prodotti, GET, elimina);
- anon e authenticated non hanno privilegi sulla tabella nuova.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_isolamento_per_risorsa import CHIAVE_WORKER, scenario, worker  # noqa: F401

pytestmark = pytest.mark.sql

MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "supabase" / "migrations" / "20261013141040_gruppo_tag_cartelle_preferiti.sql"
)


@pytest.fixture
def psycopg():
    return pytest.importorskip("psycopg")


def _uno(sc, query, *params):
    return sc.conn.execute(query, params).fetchone()


def _nuova_cartella(sc, chi, nome, ordine=0):
    return _uno(
        sc,
        "INSERT INTO public.gruppo_tag_cartelle (user_id, nome, ordine) VALUES (%s, %s, %s) RETURNING id",
        chi.ids["user_id"], nome, ordine,
    )[0]


def _tag(sc, tag_id):
    return _uno(
        sc,
        "SELECT user_id::text, nome, cartella_id, preferito FROM public.gruppo_tags WHERE id = %s",
        tag_id,
    )


def _ordini(sc):
    return sc.conn.execute("SELECT id, ordine FROM public.gruppo_tag_cartelle ORDER BY id").fetchall()


# ─── La FK composta ───────────────────────────────────────────────────────────
def test_insert_di_un_tag_nella_cartella_di_un_altro_account_e_rifiutato(scenario, psycopg):
    sc = scenario
    a, b = sc.a, sc.b
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with sc.conn.transaction():
            sc.conn.execute(
                "INSERT INTO public.gruppo_tags (id, user_id, nome, cartella_id) VALUES (950001, %s, 'INTRUSO', %s)",
                (a.ids["user_id"], b.ids["gcartella_id"]),
            )


def test_update_di_un_tag_nella_cartella_di_un_altro_account_e_rifiutato(scenario, psycopg):
    sc = scenario
    a, b = sc.a, sc.b
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with sc.conn.transaction():
            sc.conn.execute(
                "UPDATE public.gruppo_tags SET cartella_id = %s WHERE id = %s",
                (b.ids["gcartella_id"], a.ids["gtag_id"]),
            )
    assert _tag(sc, a.ids["gtag_id"])[2] == a.ids["gcartella_id"]


def test_tag_senza_cartella_e_ammesso_e_nasce_senza_stella(scenario):
    sc = scenario
    a = sc.a
    sc.conn.execute(
        "INSERT INTO public.gruppo_tags (id, user_id, nome) VALUES (950002, %s, 'NUOVO')", (a.ids["user_id"],)
    )
    assert _tag(sc, 950002)[2:] == (None, False)


# ─── ON DELETE SET NULL (cartella_id) ────────────────────────────────────────
def test_delete_della_cartella_lascia_il_tag_vivo_senza_cartella(scenario):
    sc = scenario
    a, b = sc.a, sc.b
    sc.conn.execute("UPDATE public.gruppo_tags SET preferito = true WHERE id = %s", (a.ids["gtag_id"],))

    sc.conn.execute("DELETE FROM public.gruppo_tag_cartelle WHERE id = %s", (a.ids["gcartella_id"],))

    assert _tag(sc, a.ids["gtag_id"]) == (
        a.ids["user_id"], f"TAGCATENA_{a.lettera}_SEGRETO", None, True
    ), "il tag resta, perde solo la cartella: user_id e stella intatti"
    assert _tag(sc, b.ids["gtag_id"])[2] == b.ids["gcartella_id"]
    assert _uno(
        sc, "SELECT count(*) FROM public.gruppo_tag_prodotti WHERE tag_id = %s", a.ids["gtag_id"]
    )[0] == 1


# ─── Vincoli della tabella ────────────────────────────────────────────────────
def test_nome_unico_per_account_senza_badare_a_maiuscole_e_spazi(scenario, psycopg):
    sc = scenario
    a = sc.a
    _nuova_cartella(sc, a, "Pesce")
    with pytest.raises(psycopg.errors.UniqueViolation):
        with sc.conn.transaction():
            _nuova_cartella(sc, a, "  PESCE ")
    _nuova_cartella(sc, sc.b, "Pesce")


def test_nome_vuoto_rifiutato(scenario, psycopg):
    sc = scenario
    with pytest.raises(psycopg.errors.CheckViolation):
        with sc.conn.transaction():
            _nuova_cartella(sc, sc.a, "   ")


# ─── Riordino via endpoint ────────────────────────────────────────────────────
def test_riordino_con_un_id_altrui_non_cambia_niente_per_nessuno(scenario):
    sc = scenario
    a, b = sc.a, sc.b
    seconda = _nuova_cartella(sc, a, "SECONDA", ordine=1)
    _nuova_cartella(sc, b, "SECONDA B", ordine=1)
    prima = _ordini(sc)

    resp = sc.chiama(a, "PUT", "/api/gruppo/tag/cartelle/ordine",
                     json_={"ids": [seconda, a.ids["gcartella_id"], b.ids["gcartella_id"]]})

    assert resp.status_code == 404, resp.text
    assert _ordini(sc) == prima


def test_controllo_il_riordino_dei_propri_id_scrive(scenario):
    """Senza questo, il 404 qui sopra potrebbe venire da un endpoint che non
    scrive mai."""
    sc = scenario
    a = sc.a
    seconda = _nuova_cartella(sc, a, "SECONDA", ordine=1)

    resp = sc.chiama(a, "PUT", "/api/gruppo/tag/cartelle/ordine", json_={"ids": [seconda, a.ids["gcartella_id"]]})

    assert resp.status_code == 200, resp.text
    ordini = dict(_ordini(sc))
    assert (ordini[seconda], ordini[a.ids["gcartella_id"]]) == (0, 1)


# ─── Il giro completo via endpoint ────────────────────────────────────────────
def test_giro_completo_crea_sposta_stella_prodotti_leggi_elimina(scenario):
    sc = scenario
    a, b = sc.a, sc.b
    tag = a.ids["gtag_id"]

    resp = sc.chiama(a, "POST", "/api/gruppo/tag/cartelle", json_={"nome": "  Mare "})
    assert resp.status_code == 200, resp.text
    nuova = resp.json()["cartella"]
    assert (nuova["nome"], nuova["ordine"]) == ("Mare", 1)

    resp = sc.chiama(a, "POST", "/api/gruppo/tag/cartelle", json_={"nome": "MARE"})
    assert resp.status_code == 409, resp.text

    resp = sc.chiama(a, "PATCH", f"/api/gruppo/tag/{tag}", json_={"cartella_id": nuova["id"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tag"]["preferito"] is False
    resp = sc.chiama(a, "PATCH", f"/api/gruppo/tag/{tag}", json_={"preferito": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tag"]["cartella_id"] == nuova["id"], "la stella non ha spostato il tag"

    resp = sc.chiama(a, "PATCH", f"/api/gruppo/tag/{tag}/prodotti", json_={
        "aggiungi": [{"descrizione": "  Branzino  intero "}], "togli": [f"prodotto_{a.lettera}_segreto"],
    })
    assert resp.status_code == 200, resp.text
    assert (resp.json()["aggiunte"], resp.json()["tolte"]) == (1, 1)
    chiavi = [r[0] for r in sc.conn.execute(
        "SELECT descrizione_key FROM public.gruppo_tag_prodotti WHERE tag_id = %s", (tag,)
    ).fetchall()]
    assert chiavi == ["BRANZINO INTERO"]
    assert _uno(sc, "SELECT count(*) FROM public.gruppo_tag_prodotti WHERE tag_id = %s", b.ids["gtag_id"])[0] == 1

    corpo = sc.chiama(a, "GET", "/api/gruppo/tag").json()
    assert [c["id"] for c in corpo["cartelle"]] == [a.ids["gcartella_id"], nuova["id"]]
    riga = next(t for t in corpo["tags"] if t["id"] == tag)
    assert (riga["cartella_id"], riga["preferito"], riga["n_prodotti"]) == (nuova["id"], True, 1)
    assert b.marker not in str(corpo)

    resp = sc.chiama(a, "DELETE", f"/api/gruppo/tag/cartelle/{nuova['id']}")
    assert resp.status_code == 200, resp.text
    assert _tag(sc, tag)[2:] == (None, True)

    resp = sc.chiama(a, "PATCH", f"/api/gruppo/tag/{tag}", json_={"cartella_id": b.ids["gcartella_id"]})
    assert resp.status_code == 404, resp.text
    assert _tag(sc, tag)[2] is None


# ─── Permessi ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ruolo", ["anon", "authenticated"])
def test_i_ruoli_pubblici_non_toccano_le_cartelle_di_catena(scenario, ruolo):
    """Su Supabase anon/authenticated ricevono grant nominali sulle tabelle nuove
    dalle default privileges; lo snapshot dei test non le riproduce. Si concede
    come fa Supabase, poi si riesegue la migration (idempotente): la sua REVOKE
    deve toglierli."""
    sc = scenario
    if not _uno(sc, "SELECT count(*) FROM pg_roles WHERE rolname = %s", ruolo)[0]:
        pytest.skip(f"ruolo {ruolo} assente nello snapshot")
    sc.conn.execute(f"GRANT ALL ON public.gruppo_tag_cartelle TO {ruolo}")
    sc.conn.execute(f"GRANT USAGE, SELECT ON SEQUENCE public.gruppo_tag_cartelle_id_seq TO {ruolo}")
    assert _uno(sc, "SELECT has_table_privilege(%s, 'public.gruppo_tag_cartelle', 'SELECT')", ruolo)[0] is True
    assert _uno(
        sc, "SELECT has_sequence_privilege(%s, 'public.gruppo_tag_cartelle_id_seq', 'USAGE')", ruolo
    )[0] is True, "senza il grant la REVOKE della sequenza non e' provata"

    sc.conn.execute(MIGRATION.read_text(encoding="utf-8"))

    for permesso in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert _uno(
            sc, "SELECT has_table_privilege(%s, 'public.gruppo_tag_cartelle', %s)", ruolo, permesso
        )[0] is False, permesso
    assert _uno(
        sc, "SELECT has_sequence_privilege(%s, 'public.gruppo_tag_cartelle_id_seq', 'USAGE')", ruolo
    )[0] is False


def test_rls_attiva_e_forzata_e_service_role_scrive(scenario):
    sc = scenario
    assert _uno(
        sc,
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid = 'public.gruppo_tag_cartelle'::regclass",
    ) == (True, True)
    for permesso in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert _uno(
            sc, "SELECT has_table_privilege('service_role', 'public.gruppo_tag_cartelle', %s)", permesso
        )[0] is True, permesso


# ─── I tag di catena seguono l'account (migration 20261014054557) ────────────
MIGRATION_FK = (
    Path(__file__).resolve().parent.parent
    / "supabase" / "migrations" / "20261014054557_gruppo_tags_fk_users.sql"
)


def _righe_di_catena(sc, chi):
    user = chi.ids["user_id"]
    return tuple(
        _uno(sc, f"SELECT count(*) FROM public.{t} WHERE user_id = %s", user)[0]
        for t in ("gruppo_tags", "gruppo_tag_prodotti", "gruppo_tag_cartelle")
    )


@pytest.mark.parametrize("tabella, colonne, valori", [
    ("gruppo_tags", "(id, user_id, nome)", "(950003, %s, 'ORFANO')"),
    ("gruppo_tag_prodotti", "(id, tag_id, user_id, descrizione, descrizione_key)", "(950004, %s, %s, 'X', 'X')"),
], ids=["tag", "prodotto"])
def test_un_account_inesistente_e_rifiutato(scenario, psycopg, tabella, colonne, valori):
    sc = scenario
    fantasma = "00000000-0000-4000-8000-00000000dead"
    params = (fantasma,) if tabella == "gruppo_tags" else (sc.a.ids["gtag_id"], fantasma)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with sc.conn.transaction():
            sc.conn.execute(f"INSERT INTO public.{tabella} {colonne} VALUES {valori}", params)


def test_cancellare_l_account_porta_via_tag_prodotti_e_cartelle_di_catena(scenario):
    """Prima della FK restavano tag e prodotti (dati scritti dal cliente): le
    cartelle sparivano e i tag perdevano solo la cartella."""
    sc = scenario
    a, b = sc.a, sc.b
    assert _righe_di_catena(sc, a) == (1, 1, 1)

    sc.conn.execute("DELETE FROM public.users WHERE id = %s", (a.ids["user_id"],))

    assert _righe_di_catena(sc, a) == (0, 0, 0)
    assert _righe_di_catena(sc, b) == (1, 1, 1)
    assert _tag(sc, b.ids["gtag_id"])[2] == b.ids["gcartella_id"]


def test_elimina_account_dal_cliente_non_lascia_tag_di_catena(scenario):
    """La strada vera: POST /api/account/elimina conta sul CASCADE da users."""
    sc = scenario
    a, b = sc.a, sc.b

    resp = sc.chiama(a, "POST", "/api/account/elimina", json_={"conferma": "ELIMINA"})

    assert resp.status_code == 200, resp.text
    assert _uno(sc, "SELECT count(*) FROM public.users WHERE id = %s", a.ids["user_id"])[0] == 0
    assert _righe_di_catena(sc, a) == (0, 0, 0)
    assert _righe_di_catena(sc, b) == (1, 1, 1)


def test_la_migration_della_fk_si_riapplica_senza_errori(scenario):
    sc = scenario
    sc.conn.execute(MIGRATION_FK.read_text(encoding="utf-8"))
    for tabella, nome in (("gruppo_tags", "gruppo_tags_user_id_fkey"), ("gruppo_tag_prodotti", "gruppo_tag_prodotti_user_id_fkey")):
        assert _uno(
            sc,
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s AND conrelid = %s::regclass",
            nome, f"public.{tabella}",
        )[0] == "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
