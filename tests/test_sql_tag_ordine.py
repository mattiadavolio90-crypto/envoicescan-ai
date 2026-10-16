"""Tag ordinabili a mano, su Postgres vero (migration 20261016141417).

Con i due clienti del test di isolamento (A e B): ognuno ha un tag di sede in
una cartella di sede e un tag di catena in una cartella di catena. Si prova:
- il trigger: un tag nuovo va in fondo al SUO gruppo (stessa cartella, stessa
  sede per la sede, stesso account), non dopo i tag di altri gruppi o clienti;
- il giro completo dalle rotte: riordino, spostamento in un'altra cartella con
  la posizione scelta, GET che risponde l'ordine;
- un tag dell'altro cliente nell'elenco non sposta niente.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_isolamento_per_risorsa import CHIAVE_WORKER, scenario, worker  # noqa: F401

pytestmark = pytest.mark.sql

MIGRATION = Path(__file__).resolve().parent.parent / "supabase" / "migrations" / "20261016141417_tag_ordine.sql"


def _uno(sc, query, *params):
    return sc.conn.execute(query, params).fetchone()


def _nuovo_tag_sede(sc, chi, nome, cartella_id, sede="sede1"):
    return _uno(
        sc,
        "INSERT INTO public.custom_tags (user_id, ristorante_id, nome, cartella_id) VALUES (%s, %s, %s, %s) "
        "RETURNING id, ordine",
        chi.ids["user_id"], chi.ids[sede], nome, cartella_id,
    )


def _nuovo_tag_catena(sc, chi, nome, cartella_id):
    return _uno(
        sc,
        "INSERT INTO public.gruppo_tags (user_id, nome, cartella_id) VALUES (%s, %s, %s) RETURNING id, ordine",
        chi.ids["user_id"], nome, cartella_id,
    )


def _ordine(sc, tabella, tag_id):
    return _uno(sc, f"SELECT cartella_id, ordine FROM public.{tabella} WHERE id = %s", tag_id)


# ─── Il trigger sull'INSERT ───────────────────────────────────────────────────
def test_tag_di_sede_nuovo_va_in_fondo_alla_sua_cartella(sc_ordinata):
    sc, a = sc_ordinata, sc_ordinata.a
    sc.conn.execute("UPDATE public.custom_tags SET ordine = 4 WHERE id = %s", (a.ids["tag_id"],))

    _, ordine = _nuovo_tag_sede(sc, a, "NUOVO", a.ids["cartella_id"])

    assert ordine == 5


def test_tag_di_sede_nuovo_non_conta_gli_altri_gruppi(sc_ordinata):
    """Senza cartella, in un'altra sede, o di un altro cliente: si riparte da 0."""
    sc, a, b = sc_ordinata, sc_ordinata.a, sc_ordinata.b
    sc.conn.execute("UPDATE public.custom_tags SET ordine = 7 WHERE id IN (%s, %s)", (a.ids["tag_id"], b.ids["tag_id"]))
    libero_b = _nuovo_tag_sede(sc, b, "LIBERO DI B", None)[0]
    sc.conn.execute("UPDATE public.custom_tags SET ordine = 8 WHERE id = %s", (libero_b,))

    # Stessa sede di A ma utente B: un filtro per sola sede la conterebbe.
    intruso = _uno(
        sc,
        "INSERT INTO public.custom_tags (user_id, ristorante_id, nome) VALUES (%s, %s, 'INTRUSO') RETURNING id",
        b.ids["user_id"], a.ids["sede1"],
    )[0]
    sc.conn.execute("UPDATE public.custom_tags SET ordine = 12 WHERE id = %s", (intruso,))

    assert _nuovo_tag_sede(sc, a, "SENZA", None)[1] == 0
    assert _nuovo_tag_sede(sc, a, "ALTRA SEDE", None, sede="sede2")[1] == 0
    assert _nuovo_tag_sede(sc, a, "SECONDO SENZA", None)[1] == 1


def test_tag_di_catena_nuovo_va_in_fondo_alla_sua_cartella_e_non_conta_l_altro_account(sc_ordinata):
    """«Senza cartella» e' l'unico gruppo che due account condividono come valore
    (cartella_id NULL): li' il filtro per account e' quello che separa."""
    sc, a, b = sc_ordinata, sc_ordinata.a, sc_ordinata.b
    sc.conn.execute("UPDATE public.gruppo_tags SET ordine = 3 WHERE id = %s", (a.ids["gtag_id"],))
    libero_b = _nuovo_tag_catena(sc, b, "LIBERO DI B", None)[0]
    sc.conn.execute("UPDATE public.gruppo_tags SET ordine = 9 WHERE id = %s", (libero_b,))

    assert _nuovo_tag_catena(sc, a, "NUOVO", a.ids["gcartella_id"])[1] == 4
    assert _nuovo_tag_catena(sc, a, "SENZA", None)[1] == 0


def test_l_ordine_scritto_da_chi_inserisce_viene_comunque_messo_in_fondo(sc_ordinata):
    """Nessuna strada del codice lo scrive: il trigger decide sempre."""
    sc, a = sc_ordinata, sc_ordinata.a
    riga = _uno(
        sc,
        "INSERT INTO public.custom_tags (user_id, ristorante_id, nome, cartella_id, ordine) "
        "VALUES (%s, %s, 'FORZATO', %s, 99) RETURNING ordine",
        a.ids["user_id"], a.ids["sede1"], a.ids["cartella_id"],
    )
    assert riga[0] == 1


# ─── Il giro completo dalle rotte ─────────────────────────────────────────────
def test_sede_riordino_e_spostamento_dalle_rotte(sc_ordinata):
    sc, a = sc_ordinata, sc_ordinata.a
    t1 = a.ids["tag_id"]
    t2 = _nuovo_tag_sede(sc, a, "SECONDO", a.ids["cartella_id"])[0]
    senza = _nuovo_tag_sede(sc, a, "LIBERO", None)[0]

    resp = sc.chiama(a, "PUT", "/api/tag/ordine", json_={"cartella_id": a.ids["cartella_id"], "ids": [t2, t1]})
    assert resp.status_code == 200, resp.text
    assert _ordine(sc, "custom_tags", t2) == (a.ids["cartella_id"], 0)
    assert _ordine(sc, "custom_tags", t1) == (a.ids["cartella_id"], 1)

    resp = sc.chiama(a, "PUT", "/api/tag/ordine",
                     json_={"cartella_id": a.ids["cartella_id"], "ids": [t2, senza, t1]})
    assert resp.status_code == 200, resp.text
    assert _ordine(sc, "custom_tags", senza) == (a.ids["cartella_id"], 1)

    tags = {t["id"]: t["ordine"] for t in sc.chiama(a, "GET", "/api/tag").json()["tags"]}
    assert (tags[t2], tags[senza], tags[t1]) == (0, 1, 2)


def test_catena_riordino_dalle_rotte(sc_ordinata):
    sc, a = sc_ordinata, sc_ordinata.a
    t1 = a.ids["gtag_id"]
    t2 = _nuovo_tag_catena(sc, a, "SECONDO", a.ids["gcartella_id"])[0]

    resp = sc.chiama(a, "PUT", "/api/gruppo/tag/ordine", json_={"cartella_id": a.ids["gcartella_id"], "ids": [t2, t1]})

    assert resp.status_code == 200, resp.text
    tags = {t["id"]: t["ordine"] for t in sc.chiama(a, "GET", "/api/gruppo/tag").json()["tags"]}
    assert (tags[t2], tags[t1]) == (0, 1)


def test_spostare_dal_riquadro_mette_in_fondo_anche_su_postgres(sc_ordinata):
    sc, a = sc_ordinata, sc_ordinata.a
    libero = _nuovo_tag_sede(sc, a, "LIBERO", None)[0]
    sc.conn.execute("UPDATE public.custom_tags SET ordine = 6 WHERE id = %s", (a.ids["tag_id"],))

    resp = sc.chiama(a, "PATCH", f"/api/tag/{libero}", json_={"cartella_id": a.ids["cartella_id"]})

    assert resp.status_code == 200, resp.text
    assert _ordine(sc, "custom_tags", libero) == (a.ids["cartella_id"], 7)


@pytest.mark.parametrize("percorso, cartella, tag", [
    ("/api/tag/ordine", "cartella_id", "tag_id"),
    ("/api/gruppo/tag/ordine", "gcartella_id", "gtag_id"),
], ids=["sede", "catena"])
def test_tag_dell_altro_cliente_nella_mia_cartella_non_sposta_niente(sc_ordinata, percorso, cartella, tag):
    sc, a, b = sc_ordinata, sc_ordinata.a, sc_ordinata.b
    tabella = "custom_tags" if tag == "tag_id" else "gruppo_tags"
    prima = _ordine(sc, tabella, b.ids[tag])

    resp = sc.chiama(a, "PUT", percorso, json_={"cartella_id": a.ids[cartella], "ids": [a.ids[tag], b.ids[tag]]})

    assert resp.status_code == 404
    assert _ordine(sc, tabella, b.ids[tag]) == prima


def test_la_migration_si_riapplica_senza_errori(sc_ordinata):
    sc = sc_ordinata
    sc.conn.execute(MIGRATION.read_text(encoding="utf-8"))
    n = _uno(sc, "SELECT count(*) FROM pg_trigger WHERE tgname IN ('trg_custom_tags_in_fondo', 'trg_gruppo_tags_in_fondo')")
    assert n[0] == 2


@pytest.fixture
def sc_ordinata(scenario):
    return scenario
