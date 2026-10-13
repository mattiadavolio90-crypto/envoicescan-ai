"""PATCH /api/tag/{tag_id}/prodotti — aggiunte e rimozioni in blocco (riquadro «Modifica tag»).

Il fake Supabase applica DAVVERO i filtri (.eq / .in_) e, sull'upsert, fa cio'
che fa il trigger `custom_tag_prodotti_prepare_row`: chiave ricalcolata dalla
descrizione, user_id e ristorante_id copiati dal tag. Un fake che registra
soltanto i filtri lascerebbe verde anche un delete senza il filtro di sede.

Le funzioni sono chiamate direttamente (come in test_tag_router_audit_fix.py):
importare fastapi_worker per intero non serve a provare questa logica.
"""
import copy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import services
import services.db_service as dbs
import services.routers.tag as rt
import services.tag_organizza_service as tos
from services.tag_organizza_service import LOTTO_RIMOZIONI, MAX_ELEMENTI_PER_LISTA


class _Q:
    def __init__(self, sb, nome):
        self.sb = sb
        self.nome = nome
        self.modo = "select"
        self.payload = None
        self.singolo = False
        self.filtri = []
        self.intervallo = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filtri.append((col, lambda r, v=val: str(r.get(col)) == str(v)))
        return self

    def in_(self, col, valori):
        valori = [str(v) for v in valori]
        self.sb.in_chiamate.append((self.nome, col, list(valori)))
        self.filtri.append((col, lambda r: str(r.get(col)) in valori))
        return self

    def limit(self, _n):
        return self

    def range(self, da, a):
        self.intervallo = (da, a)
        return self

    def order(self, *_a, **_k):
        return self

    def maybe_single(self):
        self.singolo = True
        return self

    def delete(self):
        self.modo = "delete"
        return self

    def upsert(self, payload, on_conflict=None):
        self.modo = "upsert"
        self.payload = payload
        return self

    def _match(self, r):
        return all(f(r) for _c, f in self.filtri)

    def execute(self):
        righe = self.sb.tabelle.setdefault(self.nome, [])
        if self.modo == "delete" and self.sb.rompi_delete:
            self.sb.delete_eseguiti += 1
            if self.sb.delete_eseguiti >= self.sb.rompi_delete:
                raise RuntimeError("414 Request-URI Too Large")
        if self.modo == "delete":
            via = [r for r in righe if self._match(r)]
            self.sb.tabelle[self.nome] = [r for r in righe if not self._match(r)]
            self.sb.scritture.append(("delete", self.nome, [r["id"] for r in via]))
            return SimpleNamespace(data=via)
        if self.modo == "upsert":
            create = []
            for item in self.payload:
                tag = next(t for t in self.sb.tabelle["custom_tags"] if t["id"] == item["tag_id"])
                riga = dict(item)
                riga["descrizione_key"] = dbs._normalize_custom_tag_key(item["descrizione"])
                riga["user_id"] = tag["user_id"]
                riga["ristorante_id"] = tag["ristorante_id"]
                esistente = next(
                    (r for r in righe
                     if r["tag_id"] == riga["tag_id"] and r["descrizione_key"] == riga["descrizione_key"]),
                    None,
                )
                if esistente:
                    esistente.update(riga)
                    create.append(esistente)
                else:
                    self.sb.prossimo_id += 1
                    riga["id"] = self.sb.prossimo_id
                    righe.append(riga)
                    create.append(riga)
            self.sb.scritture.append(("upsert", self.nome, [r["id"] for r in create]))
            return SimpleNamespace(data=create)
        trovate = [r for r in righe if self._match(r)]
        if self.intervallo:
            self.sb.letture_paginate += 1
            trovate = sorted(trovate, key=lambda r: r["id"])[self.intervallo[0]:self.intervallo[1] + 1]
        if self.singolo:
            return SimpleNamespace(data=trovate[0] if trovate else None)
        return SimpleNamespace(data=trovate)


class _Sb:
    def __init__(self, tabelle):
        self.tabelle = copy.deepcopy(tabelle)
        self.scritture = []
        self.in_chiamate = []
        self.prossimo_id = 1000
        self.letture_paginate = 0
        self.rompi_delete = 0          # n > 0: l'n-esima DELETE solleva
        self.delete_eseguiti = 0

    def table(self, nome):
        return _Q(self, nome)


# Tag 9 e 10: utente u1, sede A. Tag 99: stesso utente, sede B. Tag 77: un altro cliente.
_TAGS = [
    {"id": 9, "user_id": "u1", "ristorante_id": "sedeA", "nome": "SALMONE"},
    {"id": 10, "user_id": "u1", "ristorante_id": "sedeA", "nome": "PESCE"},
    {"id": 99, "user_id": "u1", "ristorante_id": "sedeB", "nome": "SALMONE"},
    {"id": 77, "user_id": "u2", "ristorante_id": "sedeX", "nome": "SALMONE"},
]


def _assoc(aid, tag_id, chiave, user_id="u1", ristorante_id="sedeA"):
    return {"id": aid, "tag_id": tag_id, "user_id": user_id, "ristorante_id": ristorante_id,
            "descrizione": chiave, "descrizione_key": chiave, "fattore_kg": None}


_PRODOTTI = [
    _assoc(1, 9, "SALMONE NORVEGESE"),
    _assoc(2, 9, "SALMONE AFFUMICATO"),
    _assoc(3, 10, "SALMONE NORVEGESE"),                         # stessa chiave, altro tag
    _assoc(4, 99, "SALMONE NORVEGESE", ristorante_id="sedeB"),  # stessa chiave, altra sede
    _assoc(5, 77, "SALMONE NORVEGESE", user_id="u2", ristorante_id="sedeX"),
    # Righe incoerenti che il trigger oggi impedisce: tag 9 ma utente o sede diversi.
    # Il delete non deve affidarsi al trigger per restare dentro il tenant.
    _assoc(6, 9, "SALMONE NORVEGESE", ristorante_id="sedeB"),
    _assoc(7, 9, "SALMONE NORVEGESE", user_id="u2"),
]


@pytest.fixture
def ctx(monkeypatch):
    dbs.clear_tags_cache()

    def _apply(ristorante_id="sedeA"):
        sb = _Sb({"custom_tags": _TAGS, "custom_tag_prodotti": _PRODOTTI})
        monkeypatch.setattr(rt, "_resolve_user_from_token", lambda *_a, **_k: {"id": "u1"})
        monkeypatch.setattr(rt, "_get_supabase_client", lambda *_a, **_k: sb)
        monkeypatch.setattr(rt, "_resolve_ristorante_id", lambda *_a, **_k: ristorante_id)
        monkeypatch.setattr(services, "get_supabase_client", lambda *_a, **_k: sb)
        return sb

    yield _apply
    dbs.clear_tags_cache()


def _patch(tag_id, aggiungi=(), togli=()):
    body = rt.ModificaProdottiRequest(aggiungi=list(aggiungi), togli=list(togli))
    return rt.modifica_tag_prodotti(tag_id, body, authorization="Bearer x")


def _ids(sb):
    return sorted(r["id"] for r in sb.tabelle["custom_tag_prodotti"])


def test_rimozione_resta_nel_tag_nell_utente_e_nella_sede(ctx):
    sb = ctx()

    out = _patch(9, togli=["SALMONE NORVEGESE"])

    assert out["tolte"] == 1
    assert out["aggiunte"] == 0
    assert _ids(sb) == [2, 3, 4, 5, 6, 7], (
        "sparisce solo la riga 1: le righe con la stessa chiave in un altro tag, "
        "in un'altra sede, di un altro cliente o fuori tenant restano"
    )


def test_chiave_che_non_e_nel_tag_non_toglie_niente(ctx):
    sb = ctx()

    out = _patch(10, togli=["SALMONE AFFUMICATO"])   # e' nel tag 9, non nel 10

    assert out == {"aggiunte": 0, "tolte": 0, "associazioni": []}
    assert _ids(sb) == [1, 2, 3, 4, 5, 6, 7]


def test_aggiunte_creano_le_righe_nel_tag(ctx):
    sb = ctx()

    out = _patch(10, aggiungi=[{"descrizione": "  orata   fresca ", "fattore_kg": 1.5}])

    assert out["aggiunte"] == 1
    assert out["tolte"] == 0
    nuova = out["associazioni"][0]
    assert nuova["tag_id"] == 10
    assert nuova["descrizione_key"] == "ORATA FRESCA"
    assert nuova["fattore_kg"] == 1.5
    assert (nuova["user_id"], nuova["ristorante_id"]) == ("u1", "sedeA")
    assert nuova in sb.tabelle["custom_tag_prodotti"]


def test_aggiunte_e_rimozioni_nella_stessa_chiamata(ctx):
    sb = ctx()

    out = _patch(
        9,
        aggiungi=[{"descrizione": "ORATA", "descrizione_key": "ORATA"}],
        togli=["SALMONE AFFUMICATO"],
    )

    assert (out["aggiunte"], out["tolte"]) == (1, 1)
    chiavi_tag_9 = sorted(
        r["descrizione_key"] for r in sb.tabelle["custom_tag_prodotti"]
        if r["tag_id"] == 9 and r["user_id"] == "u1" and r["ristorante_id"] == "sedeA"
    )
    assert chiavi_tag_9 == ["ORATA", "SALMONE NORVEGESE"]


@pytest.mark.parametrize("tag_id, sede", [(99, "sedeA"), (77, "sedeA"), (9, "sedeB")],
                         ids=["tag-altra-sede", "tag-altro-cliente", "sede-attiva-diversa"])
def test_tag_non_proprio_e_404_e_niente_scritture(ctx, tag_id, sede):
    sb = ctx(ristorante_id=sede)

    with pytest.raises(HTTPException) as exc:
        _patch(tag_id, aggiungi=[{"descrizione": "ORATA"}], togli=["SALMONE NORVEGESE"])

    assert exc.value.status_code == 404
    assert sb.scritture == []
    assert _ids(sb) == [1, 2, 3, 4, 5, 6, 7]


def test_la_cache_dei_prodotti_del_tag_viene_svuotata(ctx):
    """La GET dei prodotti e' cachata 5 minuti: senza invalidazione il riquadro
    riaperto subito dopo il Salva mostrerebbe ancora i prodotti tolti."""
    ctx()
    prima = dbs.get_custom_tag_prodotti(9, "u1")
    assert "SALMONE AFFUMICATO" in {r["descrizione_key"] for r in prima}

    _patch(9, togli=["SALMONE AFFUMICATO"])

    dopo = dbs.get_custom_tag_prodotti(9, "u1")
    assert "SALMONE AFFUMICATO" not in {r["descrizione_key"] for r in dopo}


@pytest.mark.parametrize("aggiungi", [
    {"descrizione": "salmone  norvegese"},
    {"descrizione": "SALMONE NORVEGESE 1KG", "descrizione_key": "salmone norvegese"},
    # La descrizione e' in conflitto, la chiave inviata no: il trigger ricalcola la
    # chiave dalla descrizione, quindi upsert e delete colpirebbero la stessa riga.
    {"descrizione": "salmone norvegese", "descrizione_key": "ALTRO"},
], ids=["dalla-descrizione", "dalla-chiave", "descrizione-con-chiave-diversa"])
def test_stesso_prodotto_da_aggiungere_e_da_togliere_e_400(ctx, aggiungi):
    sb = ctx()

    with pytest.raises(HTTPException) as exc:
        _patch(9, aggiungi=[aggiungi], togli=["SALMONE NORVEGESE"])

    assert exc.value.status_code == 400
    assert sb.scritture == []


@pytest.mark.parametrize("campo", ["aggiungi", "togli"])
def test_lista_oltre_il_limite_e_400_e_niente_scritture(ctx, campo):
    sb = ctx()
    troppi = MAX_ELEMENTI_PER_LISTA + 1
    voci = (
        [{"descrizione": f"PRODOTTO {i}"} for i in range(troppi)]
        if campo == "aggiungi" else [f"PRODOTTO {i}" for i in range(troppi)]
    )

    with pytest.raises(HTTPException) as exc:
        _patch(9, **{campo: voci})

    assert exc.value.status_code == 400
    assert sb.scritture == []


def test_lista_al_limite_e_accettata(ctx):
    sb = ctx()
    voci = [f"PRODOTTO {i}" for i in range(MAX_ELEMENTI_PER_LISTA - 1)] + ["SALMONE NORVEGESE"]

    out = _patch(9, togli=voci)

    assert out["tolte"] == 1
    assert 1 not in _ids(sb)


def test_aggiunte_al_limite_sono_accettate(ctx):
    ctx()
    voci = [{"descrizione": f"PRODOTTO {i}"} for i in range(MAX_ELEMENTI_PER_LISTA)]

    out = _patch(10, aggiungi=voci)

    assert out["aggiunte"] == MAX_ELEMENTI_PER_LISTA


def test_aggiunte_contano_le_righe_create_non_le_voci_inviate(ctx):
    """Una voce vuota viene scartata da aggiungi_associazioni: il riquadro mostra
    «N prodotti aggiunti» da questo numero, che non deve contarla."""
    ctx()

    out = _patch(10, aggiungi=[{"descrizione": "ORATA"}, {"descrizione": "   "}])

    assert out["aggiunte"] == 1


def _riempi_tag_9(sb, n):
    for i in range(n):
        sb.tabelle["custom_tag_prodotti"].append(_assoc(2000 + i, 9, f"PRODOTTO {i}"))
    return [f"PRODOTTO {i}" for i in range(n)]


def test_molte_rimozioni_vanno_a_lotti(ctx):
    """Gli id viaggiano nella URL della DELETE: ogni lotto resta sotto
    LOTTO_RIMOZIONI, e il totale tolto e' la somma dei lotti."""
    sb = ctx()
    voci = _riempi_tag_9(sb, 248) + ["SALMONE NORVEGESE", "SALMONE AFFUMICATO"]

    out = _patch(9, togli=voci)

    lotti = [c for c in sb.in_chiamate if c[0] == "custom_tag_prodotti"]
    assert len(lotti) == 3
    assert all(len(c[2]) <= LOTTO_RIMOZIONI for c in lotti)
    assert out["tolte"] == 250
    assert [r["id"] for r in sb.tabelle["custom_tag_prodotti"]
            if r["tag_id"] == 9 and r["ristorante_id"] == "sedeA" and r["user_id"] == "u1"] == []


def test_le_righe_del_tag_si_leggono_oltre_la_prima_pagina(ctx, monkeypatch):
    """PostgREST tronca a max_rows (1000): un tag piu' grande va letto a pagine,
    o le chiavi oltre la prima pagina non si tolgono mai."""
    monkeypatch.setattr(tos, "PAGINA_LETTURA", 10)
    sb = ctx()
    voci = _riempi_tag_9(sb, 25)

    out = _patch(9, togli=[voci[-1]])

    assert out["tolte"] == 1
    assert sb.letture_paginate >= 3


def test_la_delete_filtra_per_id_mai_per_chiave(ctx):
    """postgrest-py non fa l'escape delle `"` dentro `in.(...)`: una chiave come
    MOZZARELLA "FIOR DI LATTE" 1,5KG si spezzerebbe sulla virgola e non
    troverebbe la riga. Il confronto delle chiavi si fa in Python, la DELETE va
    sugli id numerici."""
    sb = ctx()
    chiave = 'MOZZARELLA "FIOR DI LATTE" 1,5KG (CONF:2)'
    sb.tabelle["custom_tag_prodotti"].append(_assoc(8, 9, chiave))

    out = _patch(9, togli=[chiave])

    assert out["tolte"] == 1
    assert 8 not in _ids(sb)
    colonne_delete = {c[1] for c in sb.in_chiamate}
    assert colonne_delete == {"id"}, colonne_delete


def test_il_testo_grezzo_trova_la_riga_normalizzata(ctx):
    sb = ctx()

    out = _patch(9, togli=["  salmone   norvegese "])

    assert out["tolte"] == 1
    assert 1 not in _ids(sb)


def test_due_chiavi_che_python_renderebbe_uguali_non_si_portano_via(ctx):
    """'STRAßE' (come lo salva Postgres) e 'STRASSE' sono due righe diverse; per
    Python normalizzano entrambe a 'STRASSE'. Togliendo l'una resta l'altra."""
    sb = ctx()
    sb.tabelle["custom_tag_prodotti"].extend([_assoc(8, 9, "STRAßE"), _assoc(18, 9, "STRASSE")])

    out = _patch(9, togli=["STRAßE"])

    assert out["tolte"] == 1
    assert 8 not in _ids(sb) and 18 in _ids(sb)


def test_la_chiave_salvata_dal_db_si_trova_anche_se_python_la_normalizza_diversamente(ctx):
    """Il trigger usa upper() di Postgres: 'STRAßE' resta 'STRAßE', Python lo fa
    diventare 'STRASSE'. Il riquadro rimanda la chiave letta dal DB."""
    sb = ctx()
    sb.tabelle["custom_tag_prodotti"].append(_assoc(8, 9, "STRAßE"))

    out = _patch(9, togli=["STRAßE"])

    assert out["tolte"] == 1
    assert 8 not in _ids(sb)


def test_rimozioni_fallite_danno_502_ma_le_aggiunte_restano_e_la_cache_si_svuota(ctx):
    sb = ctx()
    prima = dbs.get_custom_tag_prodotti(10, "u1")
    sb.rompi_delete = 1

    with pytest.raises(HTTPException) as exc:
        _patch(10, aggiungi=[{"descrizione": "ORATA"}], togli=["SALMONE NORVEGESE"])

    assert exc.value.status_code == 502
    assert "aggiunti sono salvati" in exc.value.detail
    assert any(r["tag_id"] == 10 and r["descrizione_key"] == "ORATA" for r in sb.tabelle["custom_tag_prodotti"])
    dopo = dbs.get_custom_tag_prodotti(10, "u1")
    assert len(dopo) == len(prima) + 1, "la cache va svuotata anche quando il delete fallisce"


def test_chiavi_da_togliere_normalizzate_deduplicate_e_senza_vuote(ctx):
    sb = ctx()

    out = _patch(9, togli=["salmone   norvegese", "SALMONE NORVEGESE", "", "   "])

    assert out["tolte"] == 1
    assert sb.in_chiamate == [("custom_tag_prodotti", "id", ["1"])]


def test_liste_vuote_rispondono_zero_senza_scrivere(ctx):
    sb = ctx()

    out = _patch(9)

    assert out == {"aggiunte": 0, "tolte": 0, "associazioni": []}
    assert sb.scritture == []


def test_rimozioni_fallite_a_meta_svuotano_comunque_la_cache(ctx):
    """Il primo lotto e' gia' cancellato quando il secondo fallisce, e non ci sono
    aggiunte che svuotino la cache per conto loro: senza la pulizia nel finally
    il riquadro riaperto mostrerebbe ancora prodotti che nel DB non ci sono piu'."""
    sb = ctx()
    prima = dbs.get_custom_tag_prodotti(9, "u1")
    assert "SALMONE AFFUMICATO" in {r["descrizione_key"] for r in prima}
    sb.rompi_delete = 2
    # Righe del tag in ordine di id: la 2 (AFFUMICATO) cade nel primo lotto.
    voci = ["SALMONE AFFUMICATO"] + _riempi_tag_9(sb, LOTTO_RIMOZIONI + 10)

    with pytest.raises(HTTPException) as exc:
        _patch(9, togli=voci)

    assert exc.value.status_code == 502
    assert 2 not in _ids(sb), "il primo lotto e' stato cancellato davvero"
    dopo = dbs.get_custom_tag_prodotti(9, "u1")
    assert "SALMONE AFFUMICATO" not in {r["descrizione_key"] for r in dopo}


@pytest.mark.parametrize("bulk", [False, True], ids=["singolo", "bulk"])
def test_i_prodotti_del_tag_si_leggono_tutti_oltre_max_rows(ctx, monkeypatch, bulk):
    """«Seleziona tutti» puo' portare un tag oltre le 1000 righe di max_rows: la
    lettura (riquadro, analisi del tag, alert prezzi) deve vederle tutte."""
    monkeypatch.setattr(dbs, "_PAGINA_TAG_PRODOTTI", 10)
    sb = ctx()
    _riempi_tag_9(sb, 25)

    if bulk:
        righe = dbs.get_custom_tag_prodotti_bulk([9], "u1")[9]
    else:
        righe = dbs.get_custom_tag_prodotti(9, "u1")

    ids = [r["id"] for r in righe]
    assert len(ids) == len(set(ids)), "nessuna riga ripetuta fra le pagine"
    assert {2000, 2024, 1, 2} <= set(ids)
    assert sb.letture_paginate >= 3
