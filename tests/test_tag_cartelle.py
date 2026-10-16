"""Cartelle e preferiti dei tag di sede (Analisi e Tag, Fase 2).

Endpoint: GET /api/tag (con cartelle), POST /api/tag/cartelle,
PUT /api/tag/cartelle/ordine, PUT/DELETE /api/tag/cartelle/{cartella_id},
PATCH /api/tag/{tag_id}.

Il fake Supabase applica DAVVERO i filtri e fa cio' che fa il DB: indice unico
sul nome (23505), FK composta custom_tags -> custom_tag_cartelle (23503) e
`ON DELETE SET NULL (cartella_id)`. Un fake che registra soltanto le chiamate
lascerebbe verde anche un update senza il filtro di sede. La FK vera e il SET
NULL vero si provano su Postgres in tests/test_sql_tag_cartelle.py.

Le funzioni del router sono chiamate direttamente, come in
test_tag_modifica_prodotti.py.
"""
import copy
import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import services
import services.db_service as dbs
import services.routers.tag as rt
import services.tag_organizza_service as tos


class _ErroreDb(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class _Q:
    def __init__(self, sb, nome):
        self.sb = sb
        self.nome = nome
        self.modo = "select"
        self.payload = None
        self.filtri = []
        self.ordini = []
        self.limite = None
        self.colonne = None

    def select(self, colonne="*", **_k):
        self.colonne = None if colonne.strip() == "*" else [c.strip() for c in colonne.split(",")]
        return self

    def eq(self, col, val):
        self.filtri.append(lambda r, c=col, v=val: str(r.get(c)) == str(v))
        return self

    def in_(self, col, valori):
        valori = [str(v) for v in valori]
        self.filtri.append(lambda r, c=col: str(r.get(c)) in valori)
        return self

    def order(self, col, desc=False, **_k):
        self.ordini.append((col, desc))
        return self

    def limit(self, n):
        self.limite = n
        return self

    def insert(self, payload):
        self.modo, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.modo, self.payload = "update", payload
        return self

    def delete(self):
        self.modo = "delete"
        return self

    def _match(self, r):
        return all(f(r) for f in self.filtri)

    def execute(self):
        righe = self.sb.tabelle.setdefault(self.nome, [])
        if self.modo == "insert":
            riga = dict(self.payload)
            self.sb.prossimo_id += 1
            riga.setdefault("id", self.sb.prossimo_id)
            riga.setdefault("created_at", "2026-10-13T08:00:00+00:00")
            self.sb.vincoli(self.nome, riga, escluso=None)
            righe.append(riga)
            self.sb.scritture.append(("insert", self.nome, riga["id"], dict(self.payload)))
            return SimpleNamespace(data=[dict(riga)])
        if self.modo == "update":
            if self.sb.rompi_update_dopo is not None:
                if self.sb.update_eseguiti >= self.sb.rompi_update_dopo:
                    raise RuntimeError("connessione persa")
                self.sb.update_eseguiti += 1
            colpite = [r for r in righe if self._match(r)]
            for r in colpite:
                nuova = {**r, **self.payload}
                self.sb.vincoli(self.nome, nuova, escluso=r)
            for r in colpite:
                r.update(self.payload)
                self.sb.scritture.append(("update", self.nome, r["id"], dict(self.payload)))
            return SimpleNamespace(data=[dict(r) for r in colpite])
        if self.modo == "delete":
            via = [r for r in righe if self._match(r)]
            self.sb.tabelle[self.nome] = [r for r in righe if not self._match(r)]
            for r in via:
                self.sb.scritture.append(("delete", self.nome, r["id"], None))
                if self.nome == "custom_tag_cartelle":
                    for t in self.sb.tabelle.get("custom_tags", []):
                        if (t.get("cartella_id") == r["id"] and t["user_id"] == r["user_id"]
                                and t["ristorante_id"] == r["ristorante_id"]):
                            t["cartella_id"] = None
            return SimpleNamespace(data=[dict(r) for r in via])
        trovate = [dict(r) for r in righe if self._match(r)]
        for col, desc in reversed(self.ordini):
            trovate.sort(key=lambda r, c=col: (r.get(c) is None, r.get(c)), reverse=desc)
        if self.limite is not None:
            trovate = trovate[: self.limite]
        if self.colonne:
            trovate = [{c: r.get(c) for c in self.colonne} for r in trovate]
        return SimpleNamespace(data=trovate)


class _Sb:
    def __init__(self, tabelle):
        self.tabelle = copy.deepcopy(tabelle)
        self.scritture = []
        self.prossimo_id = 5000
        self.rompi_update_dopo = None
        self.update_eseguiti = 0

    def table(self, nome):
        return _Q(self, nome)

    def vincoli(self, tabella, riga, escluso):
        """Indice unico (user_id, ristorante_id, lower(btrim(nome))) e FK composta."""
        chiave = (riga["user_id"], riga["ristorante_id"], str(riga.get("nome", "")).strip().lower())
        for altra in self.tabelle.get(tabella, []):
            if altra is escluso:
                continue
            if (altra["user_id"], altra["ristorante_id"], str(altra.get("nome", "")).strip().lower()) == chiave:
                raise _ErroreDb("23505", "duplicate key value violates unique constraint")
        if tabella == "custom_tags" and riga.get("colore") is not None \
                and not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(riga["colore"])):
            raise _ErroreDb("23514", 'new row violates check constraint "custom_tags_colore_hex_valido"')
        if tabella == "custom_tags" and riga.get("cartella_id") is not None:
            ok = any(
                c["id"] == riga["cartella_id"] and c["user_id"] == riga["user_id"]
                and c["ristorante_id"] == riga["ristorante_id"]
                for c in self.tabelle.get("custom_tag_cartelle", [])
            )
            if not ok:
                raise _ErroreDb("23503", "insert or update violates foreign key constraint")


def _cartella(cid, nome, ordine, user_id="u1", ristorante_id="sedeA"):
    return {"id": cid, "user_id": user_id, "ristorante_id": ristorante_id, "nome": nome,
            "ordine": ordine, "created_at": f"2026-10-0{cid % 9 + 1}T10:00:00+00:00"}


def _tag(tid, nome, cartella_id=None, preferito=False, user_id="u1", ristorante_id="sedeA",
         emoji="🐟", colore="#112233"):
    return {"id": tid, "user_id": user_id, "ristorante_id": ristorante_id, "nome": nome,
            "emoji": emoji, "colore": colore, "created_at": "2026-10-01T10:00:00+00:00",
            "cartella_id": cartella_id, "preferito": preferito}


# Sede A di u1: cartelle 1 (Pesce, ordine 1) e 2 (Carne, ordine 0), 4 (Vini, ordine 1: pari
# merito con 1, vince l'id). La 4 sta PRIMA della 1 nella lista: senza il secondo criterio
# `.order("id")` il fake, stabile, le lascerebbe in ordine di inserimento. Cartella 3:
# stesso utente, sede B. Cartella 8: un altro cliente. Cartella 5: la stessa sede A ma un
# altro utente (un filtro per sola sede la farebbe passare).
_CARTELLE = [
    _cartella(4, "Vini", 1),
    _cartella(1, "Pesce", 1),
    _cartella(2, "Carne", 0),
    _cartella(3, "Pesce", 0, ristorante_id="sedeB"),
    _cartella(8, "Segreta", 0, user_id="u2", ristorante_id="sedeX"),
    _cartella(5, "Intrusa", 0, user_id="u3"),
]
_TAGS = [
    _tag(9, "SALMONE", cartella_id=1, preferito=True),
    _tag(10, "ORATA", cartella_id=1),
    _tag(11, "MANZO", cartella_id=2),
    _tag(12, "AGLIO"),
    _tag(99, "SALMONE", cartella_id=3, ristorante_id="sedeB"),
    _tag(77, "SEGRETO", cartella_id=8, user_id="u2", ristorante_id="sedeX"),
]


@pytest.fixture
def ctx(monkeypatch):
    dbs.clear_tags_cache()

    def _apply(ristorante_id="sedeA", user_id="u1"):
        sb = _Sb({"custom_tags": _TAGS, "custom_tag_cartelle": _CARTELLE})
        monkeypatch.setattr(rt, "_resolve_user_from_token", lambda *_a, **_k: {"id": user_id})
        monkeypatch.setattr(rt, "_get_supabase_client", lambda *_a, **_k: sb)
        monkeypatch.setattr(rt, "_resolve_ristorante_id", lambda *_a, **_k: ristorante_id)
        monkeypatch.setattr(services, "get_supabase_client", lambda *_a, **_k: sb)
        return sb

    yield _apply
    dbs.clear_tags_cache()


@pytest.fixture
def svuotamenti(monkeypatch):
    chiamate = []
    vero = dbs.clear_tags_cache

    def _spia():
        chiamate.append(1)
        vero()

    monkeypatch.setattr(dbs, "clear_tags_cache", _spia)
    return chiamate


def _riga(sb, tabella, rid):
    return next(r for r in sb.tabelle[tabella] if r["id"] == rid)


def _patch(tag_id, **campi):
    return rt.patch_tag(tag_id, rt.TagPatchRequest(**campi), authorization="Bearer x")


def _status(funzione, *args, **kwargs):
    with pytest.raises(HTTPException) as exc:
        funzione(*args, **kwargs)
    return exc.value.status_code


# ─── Permessi dei sotto-utenti ────────────────────────────────────────────────
def test_tutte_le_rotte_dei_tag_stanno_sulla_pagina_analisi_e_tag():
    """Una voce con la pagina sbagliata passa il presidio «ogni rotta e' dichiarata»:
    un sotto-utente con la sola pagina Fatture eliminerebbe le cartelle, e uno
    con la pagina Tag prenderebbe 403."""
    from services import permessi_rotte as pr

    rotte_tag = {rotta: pagine for rotta, pagine in pr.PAGINE_PER_ROTTA.items() if rotta[1].startswith("/api/tag")}
    nuove = {
        ("PATCH", "/api/tag/{tag_id}"), ("POST", "/api/tag/cartelle"), ("PUT", "/api/tag/cartelle/ordine"),
        ("PUT", "/api/tag/cartelle/{cartella_id}"), ("DELETE", "/api/tag/cartelle/{cartella_id}"),
    }
    assert nuove <= set(rotte_tag)
    fuori = {rotta: sorted(pagine) for rotta, pagine in rotte_tag.items() if pagine != pr._p(pr.T)}
    assert not fuori, f"rotte dei tag non assegnate alla sola pagina {pr.T!r}: {fuori}"


# ─── PATCH /api/tag/{tag_id} ──────────────────────────────────────────────────
def test_patch_solo_preferito_non_tocca_gli_altri_campi(ctx):
    sb = ctx()

    out = _patch(10, preferito=True)

    assert out["tag"]["preferito"] is True
    riga = _riga(sb, "custom_tags", 10)
    assert (riga["nome"], riga["emoji"], riga["colore"], riga["cartella_id"]) == (
        "ORATA", "🐟", "#112233", 1
    )
    assert sb.scritture == [("update", "custom_tags", 10, {"preferito": True})]


def test_patch_solo_nome_non_azzera_emoji_cartella_e_stella(ctx):
    sb = ctx()

    _patch(9, nome="  SALMONE NORVEGESE ")

    riga = _riga(sb, "custom_tags", 9)
    assert riga["nome"] == "SALMONE NORVEGESE"
    assert (riga["emoji"], riga["colore"], riga["cartella_id"], riga["preferito"]) == (
        "🐟", "#112233", 1, True
    )


def test_patch_cartella_null_sposta_in_senza_cartella(ctx):
    sb = ctx()

    out = _patch(9, cartella_id=None)

    assert out["tag"]["cartella_id"] is None
    assert _riga(sb, "custom_tags", 9)["cartella_id"] is None
    assert _riga(sb, "custom_tags", 9)["preferito"] is True


def test_patch_sposta_in_un_altra_cartella_della_sede(ctx):
    sb = ctx()

    out = _patch(12, cartella_id=2)

    assert out["tag"]["cartella_id"] == 2
    assert _riga(sb, "custom_tags", 12)["cartella_id"] == 2


def test_patch_solo_emoji_cambia_solo_l_emoji(ctx):
    """«Modifica tag» cambia l'emoji di un tag esistente con la PATCH: il PUT non lo usa piu'."""
    sb = ctx()

    out = _patch(10, emoji="🥩")

    assert out["tag"]["emoji"] == "🥩"
    riga = _riga(sb, "custom_tags", 10)
    assert (riga["nome"], riga["colore"], riga["cartella_id"], riga["preferito"]) == ("ORATA", "#112233", 1, False)
    assert sb.scritture == [("update", "custom_tags", 10, {"emoji": "🥩"})]


def test_patch_emoji_vuota_la_toglie(ctx):
    sb = ctx()

    out = _patch(10, emoji="")

    assert out["tag"]["emoji"] is None
    assert sb.scritture == [("update", "custom_tags", 10, {"emoji": None})]


def test_patch_colore_scrive_il_colore(ctx):
    sb = ctx()

    out = _patch(10, colore="#AABBCC")

    assert out["tag"]["colore"] == "#AABBCC"
    assert sb.scritture == [("update", "custom_tags", 10, {"colore": "#AABBCC"})]


def test_patch_colore_non_esadecimale_e_400_e_niente_scritto(ctx):
    """Il CHECK custom_tags_colore_hex_valido (23514) diventa 400, non 500."""
    sb = ctx()

    assert _status(_patch, 10, colore="rosso") == 400

    assert sb.scritture == []
    assert _riga(sb, "custom_tags", 10)["colore"] == "#112233"


def test_patch_risponde_solo_i_campi_del_contratto(ctx):
    ctx()

    out = _patch(9, preferito=False)

    assert set(out["tag"]) == {"id", "nome", "emoji", "colore", "created_at", "cartella_id", "preferito", "ordine"}


@pytest.mark.parametrize("cartella_id", [3, 8, 5, 424242],
                         ids=["cartella-altra-sede", "cartella-altro-cliente", "stessa-sede-altro-utente", "inesistente"])
def test_patch_cartella_non_della_sede_e_404_e_niente_scritto(ctx, cartella_id):
    sb = ctx()

    assert _status(_patch, 9, cartella_id=cartella_id, preferito=False) == 404

    assert sb.scritture == []
    assert _riga(sb, "custom_tags", 9)["cartella_id"] == 1


def test_patch_cartella_altrui_fermata_dalla_fk_se_il_controllo_manca(ctx, monkeypatch):
    """Seconda rete: anche se il controllo in Python sparisse, la FK composta
    rifiuta (23503) e il router risponde 404, non 500."""
    sb = ctx()
    monkeypatch.setattr(tos, "_cartella_della_sede", lambda *_a, **_k: {"id": 3})

    assert _status(_patch, 9, cartella_id=3) == 404
    assert _riga(sb, "custom_tags", 9)["cartella_id"] == 1


@pytest.mark.parametrize("tag_id, sede, utente", [(99, "sedeA", "u1"), (77, "sedeA", "u1"), (9, "sedeB", "u1")],
                         ids=["tag-altra-sede", "tag-altro-cliente", "sede-attiva-diversa"])
def test_patch_tag_non_proprio_e_404(ctx, tag_id, sede, utente):
    sb = ctx(ristorante_id=sede, user_id=utente)

    assert _status(_patch, tag_id, preferito=True) == 404
    assert sb.scritture == []


@pytest.mark.parametrize("nome", ["", "   "])
def test_patch_nome_presente_ma_vuoto_e_400(ctx, nome):
    sb = ctx()

    assert _status(_patch, 9, nome=nome) == 400
    assert sb.scritture == []


def test_patch_nome_duplicato_nella_sede_e_409(ctx):
    sb = ctx()

    assert _status(_patch, 9, nome=" orata ") == 409
    assert _riga(sb, "custom_tags", 9)["nome"] == "SALMONE"


def test_patch_stesso_nome_in_un_altra_sede_e_permesso(ctx):
    sb = ctx(ristorante_id="sedeB")

    _patch(99, nome="ORATA")

    assert _riga(sb, "custom_tags", 99)["nome"] == "ORATA"


def test_patch_preferito_null_e_400(ctx):
    sb = ctx()

    assert _status(_patch, 9, preferito=None) == 400
    assert sb.scritture == []


def test_patch_senza_campi_non_scrive_e_restituisce_il_tag(ctx):
    sb = ctx()

    out = _patch(9)

    assert out["tag"]["nome"] == "SALMONE"
    assert sb.scritture == []


def test_patch_svuota_la_cache_dei_tag(ctx):
    """get_custom_tags e' cachata 5 minuti: senza invalidazione il nome nuovo
    non comparirebbe nelle altre letture dei tag."""
    ctx()
    assert "SALMONE" in {t["nome"] for t in dbs.get_custom_tags("u1", "sedeA")}

    _patch(9, nome="TROTA")

    nomi = {t["nome"] for t in dbs.get_custom_tags("u1", "sedeA")}
    assert "TROTA" in nomi and "SALMONE" not in nomi


def test_il_put_esistente_resta_invariato(ctx):
    """Il PUT continua a riscrivere nome, emoji e colore (azzera quelli assenti)."""
    sb = ctx()

    rt.update_tag(9, rt.TagUpdateRequest(nome="SALMONE"), authorization="Bearer x")

    riga = _riga(sb, "custom_tags", 9)
    assert (riga["emoji"], riga["colore"]) == (None, None)
    assert (riga["cartella_id"], riga["preferito"]) == (1, True)


# ─── GET /api/tag ─────────────────────────────────────────────────────────────
def test_get_tag_risponde_cartelle_ordinate_e_campi_nuovi(ctx):
    ctx()

    out = rt.list_tags(authorization="Bearer x")

    assert [c["id"] for c in out["cartelle"]] == [2, 1, 4], "ordine, poi id a pari merito"
    assert set(out["cartelle"][0]) == {"id", "nome", "ordine", "created_at"}
    assert [t["nome"] for t in out["tags"]] == ["AGLIO", "MANZO", "ORATA", "SALMONE"]
    per_id = {t["id"]: t for t in out["tags"]}
    assert per_id[9]["cartella_id"] == 1 and per_id[9]["preferito"] is True
    assert per_id[12]["cartella_id"] is None and per_id[12]["preferito"] is False


def test_get_tag_non_mostra_altre_sedi_ne_altri_clienti(ctx):
    ctx()

    out = rt.list_tags(authorization="Bearer x")

    assert {t["id"] for t in out["tags"]} == {9, 10, 11, 12}
    assert {c["id"] for c in out["cartelle"]} == {1, 2, 4}


def test_get_tag_con_errore_di_lettura_non_risponde_lista_vuota(ctx, monkeypatch):
    ctx()

    def _rotto(*_a, **_k):
        raise RuntimeError("column custom_tags.cartella_id does not exist")

    monkeypatch.setattr(tos, "lista_tag_organizzati", _rotto)

    assert _status(rt.list_tags, authorization="Bearer x") == 502


# ─── POST /api/tag/cartelle ───────────────────────────────────────────────────
def test_crea_cartella_in_fondo_con_ordine_massimo_della_sede_piu_uno(ctx):
    sb = ctx()

    out = rt.create_cartella(rt.CartellaRequest(nome="  Verdure "), authorization="Bearer x")

    cartella = out["cartella"]
    assert cartella["nome"] == "Verdure"
    assert cartella["ordine"] == 2, "massimo della sede A e' 1; le cartelle di sede B e di u2 non contano"
    assert set(cartella) == {"id", "nome", "ordine", "created_at"}
    riga = _riga(sb, "custom_tag_cartelle", cartella["id"])
    assert (riga["user_id"], riga["ristorante_id"], riga["nome"]) == ("u1", "sedeA", "Verdure")


def test_prima_cartella_della_sede_parte_da_zero(ctx):
    ctx(ristorante_id="sedeNuova")

    out = rt.create_cartella(rt.CartellaRequest(nome="Pesce"), authorization="Bearer x")

    assert out["cartella"]["ordine"] == 0


@pytest.mark.parametrize("nome", ["", "  "])
def test_crea_cartella_nome_vuoto_e_400(ctx, nome):
    sb = ctx()

    assert _status(rt.create_cartella, rt.CartellaRequest(nome=nome), authorization="Bearer x") == 400
    assert sb.scritture == []


@pytest.mark.parametrize("lunghezza, atteso", [(60, 200), (61, 400)], ids=["al-limite", "oltre"])
def test_crea_cartella_nome_oltre_i_60_caratteri_e_400(ctx, lunghezza, atteso):
    """Il tetto del browser (maxLength=60) vale anche per una chiamata diretta."""
    sb = ctx()
    nome = "C" * lunghezza

    if atteso == 200:
        out = rt.create_cartella(rt.CartellaRequest(nome=nome), authorization="Bearer x")
        assert out["cartella"]["nome"] == nome
    else:
        assert _status(rt.create_cartella, rt.CartellaRequest(nome=nome), authorization="Bearer x") == 400
        assert sb.scritture == []


def test_rinomina_cartella_nome_oltre_i_60_caratteri_e_400(ctx):
    sb = ctx()

    assert _status(rt.rinomina_cartella_endpoint, 1, rt.CartellaRequest(nome="C" * 61), authorization="Bearer x") == 400
    assert sb.scritture == []
    assert _riga(sb, "custom_tag_cartelle", 1)["nome"] == "Pesce"


def test_crea_cartella_nome_gia_usato_nella_sede_e_409(ctx):
    sb = ctx()

    assert _status(rt.create_cartella, rt.CartellaRequest(nome=" PESCE"), authorization="Bearer x") == 409
    assert len([c for c in sb.tabelle["custom_tag_cartelle"] if (c["user_id"], c["ristorante_id"]) == ("u1", "sedeA")]) == 3


def test_crea_cartella_stesso_nome_di_un_altra_sede_e_permesso(ctx):
    sb = ctx()

    rt.create_cartella(rt.CartellaRequest(nome="Segreta"), authorization="Bearer x")

    assert any(c["nome"] == "Segreta" and c["ristorante_id"] == "sedeA" for c in sb.tabelle["custom_tag_cartelle"])


# ─── PUT /api/tag/cartelle/{cartella_id} ─────────────────────────────────────
def test_rinomina_cartella(ctx):
    sb = ctx()

    out = rt.rinomina_cartella_endpoint(1, rt.CartellaRequest(nome=" Mare "), authorization="Bearer x")

    assert out["cartella"]["nome"] == "Mare"
    assert _riga(sb, "custom_tag_cartelle", 1)["nome"] == "Mare"
    assert _riga(sb, "custom_tag_cartelle", 3)["nome"] == "Pesce", "omonima di sede B intatta"


@pytest.mark.parametrize("cartella_id", [3, 8, 424242])
def test_rinomina_cartella_non_della_sede_e_404(ctx, cartella_id):
    sb = ctx()

    assert _status(rt.rinomina_cartella_endpoint, cartella_id, rt.CartellaRequest(nome="X"),
                   authorization="Bearer x") == 404
    assert sb.scritture == []


def test_rinomina_cartella_nome_vuoto_e_400(ctx):
    sb = ctx()

    assert _status(rt.rinomina_cartella_endpoint, 1, rt.CartellaRequest(nome=" "),
                   authorization="Bearer x") == 400
    assert sb.scritture == []


def test_rinomina_cartella_nome_duplicato_e_409(ctx):
    sb = ctx()

    assert _status(rt.rinomina_cartella_endpoint, 1, rt.CartellaRequest(nome="carne"),
                   authorization="Bearer x") == 409
    assert _riga(sb, "custom_tag_cartelle", 1)["nome"] == "Pesce"


# ─── DELETE /api/tag/cartelle/{cartella_id} ──────────────────────────────────
def test_elimina_cartella_lascia_i_tag_senza_cartella(ctx):
    sb = ctx()

    assert rt.elimina_cartella_endpoint(1, authorization="Bearer x") == {"ok": True}

    assert 1 not in {c["id"] for c in sb.tabelle["custom_tag_cartelle"]}
    for tid in (9, 10):
        riga = _riga(sb, "custom_tags", tid)
        assert riga["cartella_id"] is None
        assert (riga["user_id"], riga["ristorante_id"]) == ("u1", "sedeA")
    assert _riga(sb, "custom_tags", 9)["preferito"] is True
    assert _riga(sb, "custom_tags", 11)["cartella_id"] == 2


@pytest.mark.parametrize("cartella_id", [3, 8, 424242])
def test_elimina_cartella_non_della_sede_e_404_e_niente_cancellato(ctx, cartella_id):
    sb = ctx()

    assert _status(rt.elimina_cartella_endpoint, cartella_id, authorization="Bearer x") == 404
    assert sb.scritture == []
    assert len(sb.tabelle["custom_tag_cartelle"]) == len(_CARTELLE)


# ─── PUT /api/tag/cartelle/ordine ─────────────────────────────────────────────
def _ordine(sb, sede="sedeA", utente="u1"):
    return {c["id"]: c["ordine"] for c in sb.tabelle["custom_tag_cartelle"]
            if c["ristorante_id"] == sede and c["user_id"] == utente}


def test_riordina_scrive_l_indice_di_ogni_cartella(ctx):
    sb = ctx()

    out = rt.riordina_cartelle_endpoint(rt.RiordinaCartelleRequest(ids=[4, 1, 2]), authorization="Bearer x")

    assert out == {"ok": True}
    assert _ordine(sb) == {4: 0, 1: 1, 2: 2}
    assert _ordine(sb, "sedeB") == {3: 0}
    assert _ordine(sb, "sedeX", "u2") == {8: 0}


def test_riordina_salta_le_cartelle_gia_al_loro_posto(ctx):
    sb = ctx()

    rt.riordina_cartelle_endpoint(rt.RiordinaCartelleRequest(ids=[2, 1, 4]), authorization="Bearer x")

    assert [s[2] for s in sb.scritture] == [4], "2 e 1 erano gia' a 0 e 1"


@pytest.mark.parametrize("ids", [[2, 1, 4, 3], [2, 1, 8], [2, 424242, 1, 4]],
                         ids=["piu-cartella-altra-sede", "cartella-altro-cliente", "inesistente"])
def test_riordina_con_un_id_non_della_sede_e_404_e_niente_scritto(ctx, ids):
    sb = ctx()

    assert _status(rt.riordina_cartelle_endpoint, rt.RiordinaCartelleRequest(ids=ids),
                   authorization="Bearer x") == 404
    assert sb.scritture == []
    assert _ordine(sb) == {1: 1, 2: 0, 4: 1}


@pytest.mark.parametrize("ids", [[2, 1], [2, 1, 4, 4], [], [1, 1, 2]],
                         ids=["incompleto", "duplicato", "vuoto", "duplicato-senza-una"])
def test_riordina_con_elenco_che_non_coincide_e_409_e_niente_scritto(ctx, ids):
    sb = ctx()

    assert _status(rt.riordina_cartelle_endpoint, rt.RiordinaCartelleRequest(ids=ids),
                   authorization="Bearer x") == 409
    assert sb.scritture == []


def test_riordina_sede_senza_cartelle_con_elenco_vuoto_e_ok(ctx):
    sb = ctx(ristorante_id="sedeNuova")

    assert rt.riordina_cartelle_endpoint(rt.RiordinaCartelleRequest(ids=[]), authorization="Bearer x") == {"ok": True}
    assert sb.scritture == []


# ─── Cache ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("operazione", ["crea", "rinomina", "elimina", "riordina", "patch"])
def test_ogni_scrittura_svuota_la_cache_dei_tag(ctx, svuotamenti, operazione):
    ctx()
    azioni = {
        "crea": lambda: rt.create_cartella(rt.CartellaRequest(nome="Nuova"), authorization="Bearer x"),
        "rinomina": lambda: rt.rinomina_cartella_endpoint(1, rt.CartellaRequest(nome="Mare"), authorization="Bearer x"),
        "elimina": lambda: rt.elimina_cartella_endpoint(1, authorization="Bearer x"),
        "riordina": lambda: rt.riordina_cartelle_endpoint(
            rt.RiordinaCartelleRequest(ids=[4, 1, 2]), authorization="Bearer x"),
        "patch": lambda: _patch(9, cartella_id=2),
    }

    azioni[operazione]()

    assert svuotamenti, f"{operazione}: clear_tags_cache non chiamata"


def test_riordino_interrotto_a_meta_e_502_col_detail_e_svuota_comunque_la_cache(ctx, svuotamenti):
    """Niente transazione: la prima scrittura resta sul DB. Il client deve
    ricaricare, non rimettere l'ordine di prima: per questo e' un 502 col suo
    detail e non un 500."""
    sb = ctx()
    sb.rompi_update_dopo = 1

    with pytest.raises(HTTPException) as exc:
        rt.riordina_cartelle_endpoint(rt.RiordinaCartelleRequest(ids=[4, 1, 2]), authorization="Bearer x")

    assert exc.value.status_code == 502
    assert "ricarica" in exc.value.detail
    assert [s for s in sb.scritture if s[0] == "update"] == [("update", "custom_tag_cartelle", 4, {"ordine": 0})]
    assert svuotamenti
