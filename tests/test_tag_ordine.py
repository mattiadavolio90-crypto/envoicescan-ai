"""Tag ordinabili a mano dentro la loro cartella (migration 20261016141417).

Endpoint: PUT /api/tag/ordine (sede) e PUT /api/gruppo/tag/ordine (catena),
body {cartella_id, ids}: `ids` e' il gruppo (una cartella o «Senza cartella»)
come deve risultare, dall'alto, compresi i tag che ci arrivano da un'altra
cartella. In piu': GET risponde `ordine`, e lo spostamento dal riquadro
«Modifica tag» (PATCH cartella_id) mette il tag in fondo alla cartella nuova.

Ogni caso gira sui due ambiti: la sede filtra user_id + ristorante_id, la
catena il solo user_id. Il fake (tests/fake_supabase_tag.py) applica filtri e
FK composta; il trigger «in fondo» sull'INSERT si prova su Postgres
(tests/test_sql_tag_ordine.py). Le funzioni del router sono chiamate
direttamente.
"""
import pytest
from fastapi import HTTPException
from starlette.routing import Match

import services
import services.db_service as dbs
import services.routers.gruppo as gr
import services.routers.tag as rt
import services.tag_organizza_service as tos
from tests.fake_supabase_tag import FakeSupabase, fake_catena


def _cartella(cid, nome, ordine, **chiave):
    return {"id": cid, "nome": nome, "ordine": ordine, "created_at": "2026-10-01T10:00:00+00:00", **chiave}


def _tag(tid, nome, cartella_id=None, ordine=0, **chiave):
    return {"id": tid, "nome": nome, "emoji": None, "colore": None, "created_at": "2026-10-01T10:00:00+00:00",
            "cartella_id": cartella_id, "preferito": False, "ordine": ordine, **chiave}


def _dati(mio, altro_stesso_utente, altro_cliente):
    """Cartella 1 (Pesce) con tre tag mai riordinati (tutti 0), cartella 2 (Carne)
    con MANZO, AGLIO senza cartella. Cartella 3 e tag 30 di un altro ambito dello
    stesso utente (solo sede: un'altra sede), 8 e 80 di un altro cliente."""
    cartelle = [_cartella(1, "Pesce", 0, **mio), _cartella(2, "Carne", 1, **mio),
                _cartella(8, "Segreta", 0, **altro_cliente)]
    tags = [_tag(9, "SALMONE", 1, **mio), _tag(10, "ORATA", 1, **mio), _tag(13, "BRANZINO", 1, **mio),
            _tag(11, "MANZO", 2, **mio), _tag(12, "AGLIO", None, **mio),
            _tag(80, "SEGRETO", 8, **altro_cliente)]
    if altro_stesso_utente is not None:
        cartelle.append(_cartella(3, "Pesce", 0, **altro_stesso_utente))
        tags.append(_tag(30, "TONNO", 3, **altro_stesso_utente))
    return cartelle, tags


def _sede(monkeypatch):
    cartelle, tags = _dati({"user_id": "u1", "ristorante_id": "sedeA"},
                           {"user_id": "u1", "ristorante_id": "sedeB"},
                           {"user_id": "u2", "ristorante_id": "sedeX"})
    sb = FakeSupabase(
        {"custom_tags": tags, "custom_tag_cartelle": cartelle},
        fk={"custom_tags": (("cartella_id", "user_id", "ristorante_id"), "custom_tag_cartelle",
                            ("id", "user_id", "ristorante_id"))},
    )
    monkeypatch.setattr(rt, "_resolve_user_from_token", lambda *_a, **_k: {"id": "u1"})
    monkeypatch.setattr(rt, "_get_supabase_client", lambda *_a, **_k: sb)
    monkeypatch.setattr(rt, "_resolve_ristorante_id", lambda *_a, **_k: "sedeA")
    monkeypatch.setattr(services, "get_supabase_client", lambda *_a, **_k: sb)
    return sb, "custom_tags", {
        "riordina": lambda cartella_id, ids: rt.riordina_tag_endpoint(
            rt.RiordinaTagRequest(cartella_id=cartella_id, ids=ids), authorization="Bearer x"),
        "patch": lambda tag_id, **campi: rt.patch_tag(tag_id, rt.TagPatchRequest(**campi), authorization="Bearer x"),
        "lista": lambda: rt.list_tags(authorization="Bearer x")["tags"],
        "tabella_rompi": ("update", "custom_tags"),
    }


def _catena(monkeypatch):
    cartelle, tags = _dati({"user_id": "u1"}, None, {"user_id": "u2"})
    sb = fake_catena({"gruppo_tags": tags, "gruppo_tag_cartelle": cartelle, "gruppo_tag_prodotti": []})
    monkeypatch.setattr(gr, "_resolve_gruppo", lambda *_a, **_k: (sb, "u1", [], "Gruppo", {}, ["r1", "r2"]))
    monkeypatch.setattr(services, "get_supabase_client", lambda *_a, **_k: sb)
    return sb, "gruppo_tags", {
        "riordina": lambda cartella_id, ids: gr.gruppo_tag_riordina(
            gr.GruppoRiordinaTagRequest(cartella_id=cartella_id, ids=ids), authorization="Bearer x"),
        "patch": lambda tag_id, **campi: gr.gruppo_tag_patch(tag_id, gr.GruppoTagPatch(**campi),
                                                             authorization="Bearer x"),
        "lista": lambda: gr.gruppo_tag_list(authorization="Bearer x")["tags"],
        "tabella_rompi": ("update", "gruppo_tags"),
    }


@pytest.fixture(params=["sede", "catena"])
def ambito(request, monkeypatch):
    dbs.clear_tags_cache()
    yield (_sede if request.param == "sede" else _catena)(monkeypatch)
    dbs.clear_tags_cache()


def _riga(sb, tabella, tid):
    return next(r for r in sb.tabelle[tabella] if r["id"] == tid)


def _gruppo(sb, tabella, cartella_id, user_id="u1"):
    """Il gruppo com'e' sul DB, nell'ordine della lista (ordine, nome, id)."""
    righe = [r for r in sb.tabelle[tabella] if r["cartella_id"] == cartella_id and r["user_id"] == user_id
             and r.get("ristorante_id", "sedeA") == "sedeA"]
    return [r["id"] for r in sorted(righe, key=lambda r: (r["ordine"], r["nome"], r["id"]))]


def _status(funzione, *args, **kwargs):
    with pytest.raises(HTTPException) as exc:
        funzione(*args, **kwargs)
    return exc.value.status_code


# ─── Rotte e permessi ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("modulo, url, funzione", [
    (rt, "/api/tag/ordine", "riordina_tag_endpoint"),
    (gr, "/api/gruppo/tag/ordine", "gruppo_tag_riordina"),
], ids=["sede", "catena"])
def test_put_ordine_arriva_al_riordino_e_non_alla_modifica_del_tag(modulo, url, funzione):
    """PUT /api/tag/{tag_id} esiste: se fosse registrata prima, «ordine» finirebbe
    nel tag_id e il riordino risponderebbe 422."""
    scope = {"type": "http", "path": url, "method": "PUT"}
    for route in modulo.router.routes:
        if route.matches(scope)[0] == Match.FULL:
            assert route.endpoint.__name__ == funzione
            return
    pytest.fail(f"nessuna rotta per PUT {url}")


@pytest.mark.parametrize("rotta, pagina", [
    (("PUT", "/api/tag/ordine"), "analisi_e_tag"),
    (("PUT", "/api/gruppo/tag/ordine"), "catena"),
])
def test_le_rotte_del_riordino_sono_dichiarate_sulla_loro_pagina(rotta, pagina):
    from services import permessi_rotte as pr

    assert pr.PAGINE_PER_ROTTA[rotta] == pr._p(pagina)


# ─── Riordino dentro una cartella ─────────────────────────────────────────────
def test_riordino_scrive_la_posizione_di_ogni_tag_del_gruppo(ambito):
    sb, tabella, f = ambito

    assert f["riordina"](1, [10, 9, 13]) == {"ok": True}

    assert _gruppo(sb, tabella, 1) == [10, 9, 13]
    assert [_riga(sb, tabella, t)["ordine"] for t in (10, 9, 13)] == [0, 1, 2]


def test_riordino_non_riscrive_i_tag_gia_al_loro_posto(ambito):
    """Gruppo mai riordinato, tutti a 0: il primo resta 0 e non si scrive."""
    sb, tabella, f = ambito

    f["riordina"](1, [13, 10, 9])

    assert [s[2] for s in sb.scritture if s[0] == "update"] == [10, 9]


def test_riordino_non_tocca_gli_altri_gruppi(ambito):
    sb, tabella, f = ambito
    prima = {r["id"]: (r["cartella_id"], r["ordine"]) for r in sb.tabelle[tabella] if r["id"] not in (9, 10, 13)}

    f["riordina"](1, [10, 9, 13])

    dopo = {r["id"]: (r["cartella_id"], r["ordine"]) for r in sb.tabelle[tabella] if r["id"] not in (9, 10, 13)}
    assert dopo == prima


def test_riordino_di_senza_cartella(ambito):
    sb, tabella, f = ambito

    f["riordina"](None, [11, 12])

    assert _riga(sb, tabella, 11)["cartella_id"] is None
    assert _gruppo(sb, tabella, None) == [11, 12]


# ─── Spostamento in un'altra cartella, nella posizione scelta ─────────────────
def test_tag_lasciato_in_un_altra_cartella_prende_cartella_e_posizione(ambito):
    sb, tabella, f = ambito

    f["riordina"](2, [9, 11])

    assert _riga(sb, tabella, 9)["cartella_id"] == 2
    assert _gruppo(sb, tabella, 2) == [9, 11]
    assert _gruppo(sb, tabella, 1) == [13, 10]


# ─── Elenchi rifiutati senza scrivere niente ──────────────────────────────────
@pytest.mark.parametrize("ids", [[10, 9], [10, 9, 13, 13]], ids=["ne-manca-uno", "doppione"])
def test_elenco_non_aggiornato_e_409_e_niente_scritto(ambito, ids):
    """Un tag del gruppo che manca vuol dire che un'altra scheda ce l'ha messo:
    riordinare senza di lui lo lascerebbe con la posizione vecchia, a caso."""
    sb, tabella, f = ambito

    assert _status(f["riordina"], 1, ids) == 409
    assert sb.scritture == []


def test_tag_di_un_altro_cliente_e_404_e_niente_scritto(ambito):
    sb, tabella, f = ambito

    assert _status(f["riordina"], 1, [10, 9, 13, 80]) == 404
    assert sb.scritture == []
    assert _riga(sb, tabella, 80)["cartella_id"] == 8


def test_tag_di_un_altra_sede_dello_stesso_utente_e_404(monkeypatch):
    sb, tabella, f = _sede(monkeypatch)

    assert _status(f["riordina"], 1, [10, 9, 13, 30]) == 404
    assert sb.scritture == []


@pytest.mark.parametrize("cartella_id", [8, 424242], ids=["altro-cliente", "inesistente"])
def test_cartella_non_propria_e_404_e_niente_scritto(ambito, cartella_id):
    sb, tabella, f = ambito

    assert _status(f["riordina"], cartella_id, [9]) == 404
    assert sb.scritture == []


def test_cartella_di_un_altra_sede_dello_stesso_utente_e_404(monkeypatch):
    sb, tabella, f = _sede(monkeypatch)

    assert _status(f["riordina"], 3, [9]) == 404
    assert sb.scritture == []


def test_troppi_tag_in_un_riordino_e_400(ambito):
    sb, tabella, f = ambito

    assert _status(f["riordina"], 1, list(range(1, tos.MAX_ELEMENTI_PER_LISTA + 2))) == 400
    assert sb.scritture == []


def test_riordino_interrotto_a_meta_e_502(ambito):
    sb, tabella, f = ambito
    sb.rompi[f["tabella_rompi"]] = 2

    assert _status(f["riordina"], 1, [10, 9, 13]) == 502


# ─── La lista e lo spostamento dal riquadro ───────────────────────────────────
def test_get_risponde_la_posizione_di_ogni_tag(ambito):
    sb, tabella, f = ambito
    f["riordina"](1, [10, 9, 13])

    tags = {t["id"]: t for t in f["lista"]()}

    assert {t: tags[t]["ordine"] for t in (10, 9, 13)} == {10: 0, 9: 1, 13: 2}
    assert tags[11]["ordine"] == 0


def test_spostare_dal_riquadro_mette_il_tag_in_fondo_alla_cartella_nuova(ambito):
    sb, tabella, f = ambito
    f["riordina"](1, [10, 9, 13])

    f["patch"](11, cartella_id=1)

    assert _riga(sb, tabella, 11)["ordine"] == 3
    assert _gruppo(sb, tabella, 1) == [10, 9, 13, 11]


def test_spostare_dal_riquadro_in_un_gruppo_mai_riordinato(ambito):
    """Tutti a 0 (alfabetico): il tag spostato va dopo, non in mezzo per nome."""
    sb, tabella, f = ambito

    f["patch"](12, cartella_id=1)

    assert _riga(sb, tabella, 12)["ordine"] == 1
    assert _gruppo(sb, tabella, 1) == [13, 10, 9, 12]


@pytest.mark.parametrize("campi", [{"nome": "SALMONE NORVEGESE"}, {"preferito": True}, {"cartella_id": 1}],
                         ids=["nome", "stella", "stessa-cartella"])
def test_le_altre_modifiche_dal_riquadro_non_toccano_la_posizione(ambito, campi):
    sb, tabella, f = ambito
    f["riordina"](1, [10, 9, 13])

    f["patch"](9, **campi)

    assert _riga(sb, tabella, 9)["ordine"] == 1
