"""Cartelle, stella e modifica in blocco dei prodotti dei tag di catena.

Endpoint: GET /api/gruppo/tag (con cartelle), POST /api/gruppo/tag/cartelle,
PUT /api/gruppo/tag/cartelle/ordine, PUT/DELETE /api/gruppo/tag/cartelle/{id},
PATCH /api/gruppo/tag/{tag_id}, PATCH /api/gruppo/tag/{tag_id}/prodotti.

Stesso perimetro di tests/test_tag_cartelle.py (sede), ma la chiave e' il solo
account: un'altra sede dello stesso account vede le stesse cartelle, un altro
account no. Il fake (tests/fake_supabase_tag.py) applica filtri, indice unico,
FK composta e SET NULL; quelli veri si provano in test_sql_gruppo_tag_cartelle.py.
Le funzioni del router sono chiamate direttamente.
"""
import pytest
from fastapi import HTTPException
from starlette.routing import Match

import services
import services.routers.gruppo as gr
import services.tag_organizza_service as tos
from tests.fake_supabase_tag import fake_catena


def _cartella(cid, nome, ordine, user_id="u1"):
    return {"id": cid, "user_id": user_id, "nome": nome, "ordine": ordine,
            "created_at": f"2026-10-0{cid % 9 + 1}T10:00:00+00:00"}


def _tag(tid, nome, cartella_id=None, preferito=False, user_id="u1", emoji="🐟"):
    return {"id": tid, "user_id": user_id, "nome": nome, "emoji": emoji, "colore": None,
            "created_at": "2026-10-01T10:00:00+00:00", "cartella_id": cartella_id, "preferito": preferito}


def _prodotto(pid, tag_id, descrizione, user_id="u1"):
    return {"id": pid, "tag_id": tag_id, "user_id": user_id, "descrizione": descrizione,
            "descrizione_key": " ".join(descrizione.upper().split()), "fattore_kg": None}


# Account u1: cartelle 2 (Carne, ordine 0), 4 (Vini, ordine 1) e 1 (Pesce, ordine 1:
# pari merito con la 4, vince l'id). Cartella 8: un altro account.
_CARTELLE = [
    _cartella(4, "Vini", 1),
    _cartella(1, "Pesce", 1),
    _cartella(2, "Carne", 0),
    _cartella(8, "Segreta", 0, user_id="u2"),
]
_TAGS = [
    _tag(9, "SALMONE", cartella_id=1, preferito=True),
    _tag(10, "ORATA", cartella_id=1),
    _tag(11, "MANZO", cartella_id=2),
    _tag(12, "AGLIO"),
    _tag(77, "SEGRETO", cartella_id=8, user_id="u2"),
]
_PRODOTTI = [
    _prodotto(101, 9, "SALMONE NORVEGESE"),
    _prodotto(102, 9, "SALMONE FUME"),
    _prodotto(103, 10, "ORATA"),
    _prodotto(170, 77, "SALMONE NORVEGESE", user_id="u2"),
]


@pytest.fixture
def ctx(monkeypatch):
    def _apply(user_id="u1"):
        sb = fake_catena({
            "gruppo_tags": _TAGS, "gruppo_tag_cartelle": _CARTELLE, "gruppo_tag_prodotti": _PRODOTTI,
        })
        monkeypatch.setattr(gr, "_resolve_gruppo", lambda *_a, **_k: (sb, user_id, [], "Gruppo", {}, ["r1", "r2"]))
        monkeypatch.setattr(services, "get_supabase_client", lambda *_a, **_k: sb)
        return sb

    return _apply


def _riga(sb, tabella, rid):
    return next(r for r in sb.tabelle[tabella] if r["id"] == rid)


def _patch(tag_id, **campi):
    return gr.gruppo_tag_patch(tag_id, gr.GruppoTagPatch(**campi), authorization="Bearer x")


def _prodotti(tag_id, aggiungi=(), togli=()):
    body = gr.GruppoModificaProdottiRequest(
        aggiungi=[gr.GruppoTagAssocItem(descrizione=d) for d in aggiungi], togli=list(togli)
    )
    return gr.gruppo_tag_prodotti_modifica(tag_id, body, authorization="Bearer x")


def _status(funzione, *args, **kwargs):
    with pytest.raises(HTTPException) as exc:
        funzione(*args, **kwargs)
    return exc.value.status_code


def _chiavi_del_tag(sb, tag_id):
    return sorted(r["descrizione_key"] for r in sb.tabelle["gruppo_tag_prodotti"] if r["tag_id"] == tag_id)


# ─── Rotte e permessi ─────────────────────────────────────────────────────────
_NUOVE = [
    ("PATCH", "/api/gruppo/tag/{tag_id}", "/api/gruppo/tag/5", "gruppo_tag_patch"),
    ("PATCH", "/api/gruppo/tag/{tag_id}/prodotti", "/api/gruppo/tag/5/prodotti", "gruppo_tag_prodotti_modifica"),
    ("POST", "/api/gruppo/tag/cartelle", "/api/gruppo/tag/cartelle", "gruppo_tag_cartella_create"),
    ("PUT", "/api/gruppo/tag/cartelle/ordine", "/api/gruppo/tag/cartelle/ordine", "gruppo_tag_cartelle_riordina"),
    ("PUT", "/api/gruppo/tag/cartelle/{cartella_id}", "/api/gruppo/tag/cartelle/3", "gruppo_tag_cartella_rinomina"),
    ("DELETE", "/api/gruppo/tag/cartelle/{cartella_id}", "/api/gruppo/tag/cartelle/3", "gruppo_tag_cartella_elimina"),
]


def test_tutte_le_rotte_dei_tag_di_catena_stanno_sulla_pagina_catena():
    """Una voce mancante e' 403 per tutti i sotto-utenti; una sulla pagina
    sbagliata lascia toccare le cartelle di catena a chi la Catena non ce l'ha."""
    from services import permessi_rotte as pr

    rotte = {r: p for r, p in pr.PAGINE_PER_ROTTA.items() if r[1].startswith("/api/gruppo/tag")}
    assert {(m, modello) for m, modello, _u, _f in _NUOVE} <= set(rotte)
    fuori = {r: sorted(p) for r, p in rotte.items() if p != pr._p(pr.C)}
    assert not fuori, f"rotte dei tag di catena non assegnate alla sola pagina {pr.C!r}: {fuori}"


@pytest.mark.parametrize("metodo, _modello, url, funzione", _NUOVE, ids=[f"{m} {u}" for m, u, _x, _f in _NUOVE])
def test_ogni_url_arriva_alla_sua_funzione(metodo, _modello, url, funzione):
    """La prima rotta che combacia e' quella giusta: «ordine» dichiarata dopo
    `{cartella_id}` diventerebbe un 422 sull'intero «ordine»."""
    scope = {"type": "http", "method": metodo, "path": url, "root_path": ""}
    prima = next(r for r in gr.router.routes if r.matches(scope)[0] == Match.FULL)
    assert prima.endpoint.__name__ == funzione


@pytest.mark.parametrize("chiama", [
    lambda: gr.gruppo_tag_list(authorization="Bearer x"),
    lambda: _patch(9, preferito=True),
    lambda: _prodotti(9, togli=["ORATA"]),
    lambda: gr.gruppo_tag_cartella_create(gr.GruppoCartellaRequest(nome="X"), authorization="Bearer x"),
    lambda: gr.gruppo_tag_cartelle_riordina(gr.GruppoRiordinaCartelleRequest(ids=[]), authorization="Bearer x"),
    lambda: gr.gruppo_tag_cartella_rinomina(1, gr.GruppoCartellaRequest(nome="X"), authorization="Bearer x"),
    lambda: gr.gruppo_tag_cartella_elimina(1, authorization="Bearer x"),
], ids=["get", "patch", "patch-prodotti", "crea", "riordina", "rinomina", "elimina"])
def test_ogni_rotta_passa_dal_controllo_della_catena(monkeypatch, chiama):
    """`_resolve_gruppo` verifica la Catena del sotto-utente e le due sedi: una
    rotta che lo saltasse servirebbe a chiunque abbia un token."""
    def _rifiuta(*_a, **_k):
        raise HTTPException(status_code=400, detail="Account non multi-sede")

    monkeypatch.setattr(gr, "_resolve_gruppo", _rifiuta)
    with pytest.raises(HTTPException) as exc:
        chiama()
    assert exc.value.status_code == 400


# ─── GET /api/gruppo/tag ──────────────────────────────────────────────────────
def test_get_risponde_cartelle_ordinate_tag_con_stella_cartella_e_conteggio(ctx):
    ctx()

    out = gr.gruppo_tag_list(authorization="Bearer x")

    assert [c["id"] for c in out["cartelle"]] == [2, 1, 4]
    assert set(out["cartelle"][0]) == {"id", "nome", "ordine", "created_at"}
    per_id = {t["id"]: t for t in out["tags"]}
    assert set(per_id) == {9, 10, 11, 12}
    assert per_id[9]["cartella_id"] == 1 and per_id[9]["preferito"] is True
    assert per_id[12]["cartella_id"] is None and per_id[12]["preferito"] is False
    assert {t: per_id[t]["n_prodotti"] for t in per_id} == {9: 2, 10: 1, 11: 0, 12: 0}


def test_get_non_mostra_tag_e_cartelle_di_un_altro_account(ctx):
    ctx(user_id="u2")

    out = gr.gruppo_tag_list(authorization="Bearer x")

    assert [t["id"] for t in out["tags"]] == [77]
    assert [c["id"] for c in out["cartelle"]] == [8]
    assert out["tags"][0]["n_prodotti"] == 1


def test_get_con_errore_di_lettura_non_risponde_lista_vuota(ctx, monkeypatch):
    ctx()

    def _rotto(*_a, **_k):
        raise RuntimeError("timeout")

    monkeypatch.setattr(tos, "lista_cartelle_in", _rotto)
    assert _status(gr.gruppo_tag_list, authorization="Bearer x") == 502


# ─── PATCH /api/gruppo/tag/{tag_id} ───────────────────────────────────────────
def test_patch_solo_preferito_non_tocca_gli_altri_campi(ctx):
    sb = ctx()

    out = _patch(10, preferito=True)

    assert out["tag"]["preferito"] is True and out["tag"]["cartella_id"] == 1
    assert sb.scritture == [("update", "gruppo_tags", 10, {"preferito": True})]


def test_patch_solo_nome_non_azzera_emoji_cartella_e_stella(ctx):
    sb = ctx()

    _patch(9, nome="  SALMONE FRESCO ")

    riga = _riga(sb, "gruppo_tags", 9)
    assert (riga["nome"], riga["emoji"], riga["cartella_id"], riga["preferito"]) == ("SALMONE FRESCO", "🐟", 1, True)


def test_patch_cartella_null_sposta_in_senza_cartella(ctx):
    sb = ctx()

    _patch(9, cartella_id=None)

    assert _riga(sb, "gruppo_tags", 9)["cartella_id"] is None


def test_patch_sposta_in_un_altra_cartella_dell_account(ctx):
    sb = ctx()

    _patch(12, cartella_id=4)

    assert _riga(sb, "gruppo_tags", 12)["cartella_id"] == 4


@pytest.mark.parametrize("cartella_id", [8, 424242], ids=["cartella-altro-account", "inesistente"])
def test_patch_cartella_non_dell_account_e_404_e_niente_scritto(ctx, cartella_id):
    sb = ctx()

    assert _status(_patch, 9, cartella_id=cartella_id, preferito=False) == 404

    assert sb.scritture == []


def test_patch_cartella_altrui_fermata_dalla_fk_se_il_controllo_manca(ctx, monkeypatch):
    """Seconda rete: senza il controllo in Python la FK composta rifiuta (23503)
    e la rotta risponde 404, non 500."""
    sb = ctx()
    monkeypatch.setattr(tos, "_cartella_dell_account", lambda *_a, **_k: {"id": 8})

    assert _status(_patch, 9, cartella_id=8) == 404
    assert _riga(sb, "gruppo_tags", 9)["cartella_id"] == 1


def test_patch_tag_di_un_altro_account_e_404(ctx):
    sb = ctx()

    assert _status(_patch, 77, preferito=False) == 404
    assert _riga(sb, "gruppo_tags", 77)["preferito"] is False and sb.scritture == []


@pytest.mark.parametrize("nome", ["", "   "])
def test_patch_nome_presente_ma_vuoto_e_400(ctx, nome):
    sb = ctx()

    assert _status(_patch, 9, nome=nome) == 400
    assert sb.scritture == []


def test_patch_preferito_null_e_400(ctx):
    sb = ctx()

    assert _status(_patch, 9, preferito=None) == 400
    assert sb.scritture == []


def test_patch_senza_campi_non_scrive_e_restituisce_il_tag(ctx):
    sb = ctx()

    out = _patch(11)

    assert out["tag"]["nome"] == "MANZO" and out["tag"]["cartella_id"] == 2
    assert sb.scritture == []


# ─── Cartelle ────────────────────────────────────────────────────────────────
def _crea(nome):
    return gr.gruppo_tag_cartella_create(gr.GruppoCartellaRequest(nome=nome), authorization="Bearer x")


def _rinomina(cartella_id, nome):
    return gr.gruppo_tag_cartella_rinomina(cartella_id, gr.GruppoCartellaRequest(nome=nome), authorization="Bearer x")


def _riordina(ids):
    return gr.gruppo_tag_cartelle_riordina(gr.GruppoRiordinaCartelleRequest(ids=ids), authorization="Bearer x")


def test_crea_cartella_in_fondo_con_ordine_massimo_dell_account_piu_uno(ctx):
    sb = ctx()

    out = _crea(" Formaggi ")

    assert out["cartella"]["nome"] == "Formaggi" and out["cartella"]["ordine"] == 2
    nuova = _riga(sb, "gruppo_tag_cartelle", out["cartella"]["id"])
    assert nuova["user_id"] == "u1" and "ristorante_id" not in nuova


def test_prima_cartella_dell_account_parte_da_zero(ctx):
    sb = ctx(user_id="u3")

    out = _crea("Prima")

    assert out["cartella"]["ordine"] == 0
    assert _riga(sb, "gruppo_tag_cartelle", out["cartella"]["id"])["user_id"] == "u3"


@pytest.mark.parametrize("nome, atteso", [("", 400), ("   ", 400), ("x" * 61, 400), ("x" * 60, None)],
                         ids=["vuoto", "spazi", "61", "60"])
def test_crea_cartella_nome_vuoto_o_troppo_lungo(ctx, nome, atteso):
    ctx()
    if atteso is None:
        assert len(_crea(nome)["cartella"]["nome"]) == 60
    else:
        assert _status(_crea, nome) == atteso


def test_crea_cartella_nome_gia_usato_nell_account_e_409(ctx):
    ctx()

    assert _status(_crea, " pesce ") == 409


def test_crea_cartella_stesso_nome_di_un_altro_account_e_permesso(ctx):
    ctx()

    assert _crea("Segreta")["cartella"]["nome"] == "Segreta"


def test_rinomina_cartella(ctx):
    sb = ctx()

    out = _rinomina(1, "Pesce di mare")

    assert out["cartella"]["nome"] == "Pesce di mare"
    assert _riga(sb, "gruppo_tag_cartelle", 1)["nome"] == "Pesce di mare"


@pytest.mark.parametrize("cartella_id", [8, 424242], ids=["altro-account", "inesistente"])
def test_rinomina_cartella_non_dell_account_e_404(ctx, cartella_id):
    sb = ctx()

    assert _status(_rinomina, cartella_id, "Mia") == 404
    assert sb.scritture == []


def test_rinomina_cartella_nome_duplicato_e_409(ctx):
    sb = ctx()

    assert _status(_rinomina, 1, "CARNE") == 409
    assert _riga(sb, "gruppo_tag_cartelle", 1)["nome"] == "Pesce"


def test_elimina_cartella_lascia_i_tag_senza_cartella(ctx):
    sb = ctx()

    gr.gruppo_tag_cartella_elimina(1, authorization="Bearer x")

    assert 1 not in [c["id"] for c in sb.tabelle["gruppo_tag_cartelle"]]
    assert _riga(sb, "gruppo_tags", 9)["cartella_id"] is None
    assert _riga(sb, "gruppo_tags", 10)["cartella_id"] is None
    assert _riga(sb, "gruppo_tags", 11)["cartella_id"] == 2


@pytest.mark.parametrize("cartella_id", [8, 424242], ids=["altro-account", "inesistente"])
def test_elimina_cartella_non_dell_account_e_404_e_niente_cancellato(ctx, cartella_id):
    sb = ctx()

    assert _status(gr.gruppo_tag_cartella_elimina, cartella_id, authorization="Bearer x") == 404

    assert len(sb.tabelle["gruppo_tag_cartelle"]) == 4
    assert _riga(sb, "gruppo_tags", 77)["cartella_id"] == 8


def test_riordina_scrive_l_indice_di_ogni_cartella_e_salta_quelle_al_loro_posto(ctx):
    sb = ctx()

    _riordina([1, 2, 4])

    assert {c["id"]: c["ordine"] for c in sb.tabelle["gruppo_tag_cartelle"] if c["user_id"] == "u1"} == {
        1: 0, 2: 1, 4: 2,
    }
    assert sorted(s[2] for s in sb.scritture) == [1, 2, 4]
    sb.scritture.clear()
    _riordina([1, 2, 4])
    assert sb.scritture == []


@pytest.mark.parametrize("ids", [[2, 1, 4, 8], [2, 1, 8]], ids=["in-piu", "al-posto-di-una"])
def test_riordina_con_un_id_di_un_altro_account_e_404_e_niente_scritto(ctx, ids):
    sb = ctx()

    assert _status(_riordina, ids) == 404
    assert sb.scritture == []
    assert _riga(sb, "gruppo_tag_cartelle", 8)["ordine"] == 0


@pytest.mark.parametrize("ids", [[2, 1], [2, 1, 4, 4]], ids=["manca-una", "doppione"])
def test_riordina_con_elenco_che_non_coincide_e_409_e_niente_scritto(ctx, ids):
    sb = ctx()

    assert _status(_riordina, ids) == 409
    assert sb.scritture == []


def test_riordino_interrotto_a_meta_e_502(ctx):
    sb = ctx()
    sb.rompi[("update", "gruppo_tag_cartelle")] = 2

    assert _status(_riordina, [1, 4, 2]) == 502
    assert len(sb.scritture) == 1


# ─── PATCH /api/gruppo/tag/{tag_id}/prodotti ─────────────────────────────────
def test_aggiunge_e_toglie_in_una_chiamata(ctx):
    sb = ctx()

    out = _prodotti(9, aggiungi=["  salmone  affumicato "], togli=["SALMONE FUME"])

    assert (out["aggiunte"], out["tolte"]) == (1, 1)
    assert _chiavi_del_tag(sb, 9) == ["SALMONE AFFUMICATO", "SALMONE NORVEGESE"]
    nuova = next(r for r in sb.tabelle["gruppo_tag_prodotti"] if r["descrizione_key"] == "SALMONE AFFUMICATO")
    assert (nuova["user_id"], nuova["descrizione"]) == ("u1", "salmone  affumicato")


def test_toglie_solo_dal_tag_e_dall_account_giusti(ctx):
    """La stessa chiave sta nel tag 77 di u2: deve restare."""
    sb = ctx()

    out = _prodotti(9, togli=["SALMONE NORVEGESE"])

    assert out["tolte"] == 1
    assert _chiavi_del_tag(sb, 77) == ["SALMONE NORVEGESE"]
    assert _chiavi_del_tag(sb, 9) == ["SALMONE FUME"]


def test_riaggiungere_un_prodotto_gia_nel_tag_non_lo_duplica(ctx):
    sb = ctx()

    _prodotti(10, aggiungi=["orata", "ORATA "])

    assert _chiavi_del_tag(sb, 10) == ["ORATA"]


def test_stesso_prodotto_da_aggiungere_e_togliere_e_400_e_niente_scritto(ctx):
    sb = ctx()

    assert _status(_prodotti, 9, aggiungi=["Salmone fume"], togli=["SALMONE FUME"]) == 400
    assert sb.scritture == []


def test_modifica_prodotti_di_un_tag_di_un_altro_account_e_404(ctx):
    sb = ctx()

    assert _status(_prodotti, 77, togli=["SALMONE NORVEGESE"]) == 404
    assert _chiavi_del_tag(sb, 77) == ["SALMONE NORVEGESE"] and sb.scritture == []


def test_rimozione_fallita_dopo_le_aggiunte_e_502_e_le_aggiunte_restano(ctx):
    sb = ctx()
    sb.rompi[("delete", "gruppo_tag_prodotti")] = 1

    assert _status(_prodotti, 9, aggiungi=["SPIGOLA"], togli=["SALMONE FUME"]) == 502
    assert "SPIGOLA" in _chiavi_del_tag(sb, 9) and "SALMONE FUME" in _chiavi_del_tag(sb, 9)


def test_il_post_dei_prodotti_continua_a_non_duplicare(ctx):
    sb = ctx()
    body = gr.GruppoTagAssocRequest(descrizioni=[
        gr.GruppoTagAssocItem(descrizione="Branzino"), gr.GruppoTagAssocItem(descrizione=" BRANZINO "),
        gr.GruppoTagAssocItem(descrizione="   "),
    ])

    out = gr.gruppo_tag_prodotti_add(12, body, authorization="Bearer x")

    assert out["aggiunte"] == 1
    assert _chiavi_del_tag(sb, 12) == ["BRANZINO"]


# ─── La chiave dell'ambito ────────────────────────────────────────────────────
@pytest.mark.parametrize("chiave", [
    {"user_id": ""}, {"user_id": None}, {}, {"user_id": "u1", "ristorante_id": "r1"}, {"ristorante_id": "r1"},
], ids=["vuota", "none", "assente", "colonna-in-piu", "colonna-sbagliata"])
def test_una_chiave_incompleta_o_sbagliata_non_arriva_al_db(ctx, chiave):
    """Un filtro `user_id = ''` non trova niente, ma un filtro MANCANTE trova
    tutti: la chiave si controlla prima di costruire la query."""
    sb = ctx()
    with pytest.raises(ValueError):
        tos.lista_cartelle_in(tos.AMBITO_CATENA, chiave)
    with pytest.raises(ValueError):
        tos.elimina_cartella_in(tos.AMBITO_CATENA, chiave, 1)
    assert len(sb.tabelle["gruppo_tag_cartelle"]) == 4
