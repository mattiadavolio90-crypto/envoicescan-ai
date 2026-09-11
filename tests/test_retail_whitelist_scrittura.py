"""Le whitelist di scrittura della categoria guardano il settore, non una lista sola.

Fase 3, prima casella. Sei punti validavano la categoria in arrivo contro
`TUTTE_LE_CATEGORIE`: la lista dei ristoranti. Il menu del client era gia'
filtrato per settore dalla Fase 1, ma la whitelist e' l'ultimo cancello prima
del DB — e una chiamata API diretta (o un client vecchio in cache) scriveva
`CARNE` sulla riga di un negozio senza che niente la fermasse.

Quattro dei sei punti passano ora da `categorie_ammesse(settore)`. Gli altri due
(`admin.py` suggerisci-ai e memoria globale) restano su `TUTTE_LE_CATEGORIE` **di
proposito**: scrivono solo su `prodotti_master`, che e' la memoria dei ristoranti
e che la Fase 1 ha gia' chiuso al retail. Ammettere li' ARTICOLO DI VENDITA
creerebbe una voce che nessun negozio puo' leggere e che i ristoranti non devono
vedere. E' un'esclusione motivata, non una dimenticanza.

Il settimo punto e' nuovo di questa fase: la whitelist dell'admin e' l'unione dei
due settori (la coda raggruppa per descrizione su tutti i clienti insieme),
quindi serve un gate **speculare** a quello della Fase 2 — che ARTICOLO DI
VENDITA non raggiunga le righe di un ristorante.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from config.constants import CATEGORIA_ARTICOLO_DI_VENDITA, TUTTE_LE_CATEGORIE
from utils.validation import normalizza_categoria_richiesta


class TestNormalizzaCategoriaRichiesta:
    """Il punto unico delle correzioni cliente (riparto manuale e riga di gruppo)."""

    def test_senza_settore_e_esattamente_la_lista_di_ieri(self):
        # Il default protegge i ristoranti: chi non passa il settore si comporta
        # come prima del retail, categoria per categoria.
        for cat in TUTTE_LE_CATEGORIE:
            if cat == "Da Classificare":
                continue
            atteso = "📝 NOTE E DICITURE" if cat == "NOTE E DICITURE" else cat
            assert normalizza_categoria_richiesta(cat) == atteso

    def test_ristorazione_accetta_il_food_e_rifiuta_articolo_di_vendita(self):
        assert normalizza_categoria_richiesta("CARNE", "ristorazione") == "CARNE"
        with pytest.raises(ValueError):
            normalizza_categoria_richiesta(CATEGORIA_ARTICOLO_DI_VENDITA, "ristorazione")

    def test_retail_accetta_la_sua_merce_e_rifiuta_il_food(self):
        assert normalizza_categoria_richiesta(
            CATEGORIA_ARTICOLO_DI_VENDITA, "retail"
        ) == CATEGORIA_ARTICOLO_DI_VENDITA
        with pytest.raises(ValueError):
            normalizza_categoria_richiesta("CARNE", "retail")

    def test_le_spese_generali_valgono_per_entrambi(self):
        # Sono le 4 categorie in comune: un negozio ha le utenze come un ristorante.
        for settore in ("ristorazione", "retail"):
            assert normalizza_categoria_richiesta("UTENZE E LOCALI", settore) == "UTENZE E LOCALI"

    def test_da_classificare_resta_vietata_in_entrambi_i_settori(self):
        # Regola di dominio #1: e' uno stato che l'AI assegna, non una scelta
        # dell'utente. Il settore non c'entra e non deve aprire una porta.
        for settore in (None, "ristorazione", "retail"):
            for grafia in ("Da Classificare", "Da Clasificare"):
                with pytest.raises(ValueError):
                    normalizza_categoria_richiesta(grafia, settore)

    def test_un_settore_sconosciuto_cade_sui_ristoranti(self):
        # Fail-safe nella stessa direzione di settore_service: un valore ignoto
        # non deve aprire la whitelist piu' larga di quella di oggi.
        assert normalizza_categoria_richiesta("CARNE", "trattoria-spaziale") == "CARNE"
        with pytest.raises(ValueError):
            normalizza_categoria_richiesta(CATEGORIA_ARTICOLO_DI_VENDITA, "trattoria-spaziale")


# ── Il gate speculare nella coda admin ──────────────────────────────────────
# La Fase 2 aveva chiuso una direzione: una categoria food non raggiunge le
# righe di un negozio. Allargando la whitelist dell'admin all'unione dei due
# settori si apre l'altra: ARTICOLO DI VENDITA sulle righe di un ristorante.
# Il vincolo di Mattia vale nelle due direzioni.

from unittest.mock import patch  # noqa: E402

import services.fastapi_worker  # noqa: F401,E402 — carica i moduli condivisi
import services.routers.admin as admin  # noqa: E402
import services.settore_service as ss  # noqa: E402
from tests.test_admin_qualita_fix_audit import _ADMIN, _FakeSB  # noqa: E402

_SETTORI = {"u-rist": "ristorazione", "u-retail": "retail"}


def _riga(id_, user):
    return {"id": id_, "descrizione": "SCAFFALE METALLICO", "prezzo_unitario": 90.0,
            "totale_riga": 90.0, "categoria": "Da Classificare",
            "ristorante_id": f"r-{user}", "user_id": user}


def _classifica(monkeypatch, righe, categoria):
    """Ritorna gli id realmente scritti; solleva HTTPException se il gate blocca."""
    sb = _FakeSB({"fatture": righe, "prodotti_master": [], "ai_review_log": []})
    scritti = {}
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: _SETTORI.get(uid, "ristorazione"))

    def _cattura(*a, **k):
        scritti["ids"] = list(k.get("ids") or [])
        return len(scritti["ids"])

    with patch.multiple(
        admin,
        get_supabase_client=lambda *a, **k: sb,
        aggiorna_categoria_fatture=_cattura,
        _log_review_action=lambda *a, **k: None,
        _invalidate_fatture_rows_cache=lambda *a, **k: None,
    ):
        admin.admin_qualita_classifica(
            admin.ClassificaBody(ids=[r["id"] for r in righe], categoria=categoria),
            admin_user=_ADMIN,
        )
    return scritti.get("ids", [])


def test_admin_puo_finalmente_classificare_la_riga_di_un_negozio(monkeypatch):
    # Prima della Fase 3 la whitelist era TUTTE_LE_CATEGORIE: 422 secco, e la
    # riga di un negozio non era classificabile da nessuna interfaccia.
    assert _classifica(monkeypatch, [_riga(1, "u-retail")], CATEGORIA_ARTICOLO_DI_VENDITA) == [1]


def test_articolo_di_vendita_non_raggiunge_le_righe_di_un_ristorante(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _classifica(monkeypatch, [_riga(1, "u-rist")], CATEGORIA_ARTICOLO_DI_VENDITA)
    assert e.value.status_code == 422


def test_gruppo_misto_scrive_solo_al_negozio(monkeypatch):
    # La coda raggruppa per descrizione su tutti i clienti: il gruppo misto e'
    # il caso reale (misurati 47 gruppi su 264), non un caso di laboratorio.
    scritti = _classifica(
        monkeypatch,
        [_riga(1, "u-rist"), _riga(2, "u-retail")],
        CATEGORIA_ARTICOLO_DI_VENDITA,
    )
    assert scritti == [2], "la riga del ristorante non deve essere toccata"


def test_una_categoria_inventata_resta_rifiutata(monkeypatch):
    # Allargare la whitelist all'unione non deve aver aperto la porta a tutto.
    with pytest.raises(HTTPException) as e:
        _classifica(monkeypatch, [_riga(1, "u-retail")], "CATEGORIA INVENTATA")
    assert e.value.status_code == 422


# ── Le due correzioni del cliente su fatture.py ─────────────────────────────
# Il menu e' filtrato dalla Fase 1, ma la whitelist e' l'ultimo cancello: una
# chiamata API diretta, o un client vecchio rimasto in cache, arriva qui.

import services.routers.fatture as fatture  # noqa: E402
from tests.test_fatture_categoria_guardrail import _FakeSB as _FattureSB, _patch_common  # noqa: E402


def _patch_riga(monkeypatch, settore, categoria):
    sb = _FattureSB([{"id": 1, "totale_riga": 42.0, "prezzo_unitario": 42.0, "descrizione": "X"}])
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: settore)
    p, _ = _patch_common(sb)
    with p:
        fatture.aggiorna_categoria_riga(
            1, fatture.AggiornaCategoriaRequest(categoria=categoria), authorization="Bearer x",
        )
    return sb.updates["fatture"][0]["payload"]["categoria"]


def test_patch_riga_di_un_negozio_rifiuta_il_food(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _patch_riga(monkeypatch, "retail", "CARNE")
    assert e.value.status_code == 400


def test_patch_riga_di_un_negozio_accetta_la_sua_merce(monkeypatch):
    assert _patch_riga(monkeypatch, "retail", CATEGORIA_ARTICOLO_DI_VENDITA) == CATEGORIA_ARTICOLO_DI_VENDITA


def test_patch_riga_di_un_ristorante_e_identica_a_ieri(monkeypatch):
    # Il vincolo: per un ristorante non cambia niente, nemmeno il percorso.
    assert _patch_riga(monkeypatch, "ristorazione", "CARNE") == "CARNE"


def test_patch_riga_di_un_ristorante_rifiuta_articolo_di_vendita(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _patch_riga(monkeypatch, "ristorazione", CATEGORIA_ARTICOLO_DI_VENDITA)
    assert e.value.status_code == 400


def _batch(monkeypatch, settore, categoria):
    sb = _FattureSB([{"id": 1, "totale_riga": 42.0, "prezzo_unitario": 42.0, "descrizione": "X"}])
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: settore)
    p, _ = _patch_common(sb)
    with p, patch.object(fatture, "_salva_correzione_memoria", lambda *a, **k: None), \
            patch.object(fatture, "aggiorna_categoria_fatture", lambda *a, **k: len(k.get("ids") or [])):
        fatture.categoria_batch(
            fatture.CategoriaBatchRequest(descrizione="X", nuova_categoria=categoria),
            authorization="Bearer x",
        )


def test_batch_di_un_negozio_rifiuta_il_food(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _batch(monkeypatch, "retail", "CARNE")
    assert e.value.status_code == 400


def test_batch_di_un_ristorante_resta_come_ieri(monkeypatch):
    _batch(monkeypatch, "ristorazione", "CARNE")  # non solleva


# ── I due costi di gruppo su riparto.py ─────────────────────────────────────
# Qui il presidio deve stare sull'ENDPOINT, non sulla funzione: provare solo
# `normalizza_categoria_richiesta` lascia sopravvivere il mutante che toglie il
# settore alla chiamata. Misurato: il mutante 6 passava con 28 test verdi.

import services.routers.riparto as riparto  # noqa: E402
from tests.test_riparto_manuale import _FakeSB as _RipartoSB, _SEDI  # noqa: E402


def _riparto_manuale(monkeypatch, settore, categoria):
    sb = _RipartoSB()
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: settore)
    with patch.multiple(
        riparto,
        _resolve_user_from_token=lambda *a, **k: {"id": "user-1"},
        _get_supabase_client=lambda *a, **k: sb,
        _carica_sedi_attive=lambda *a, **k: _SEDI,
        _post_scrittura_riparto=lambda *a, **k: None,
    ):
        riparto.riparto_manuale(
            riparto.RipartoManualeBody(
                descrizione="Costo di prova", importo_totale=100.0, categoria=categoria,
                anno=2026, mese=8, regola="equa", percentuali=None,
            ),
            authorization="Bearer x",
        )


def test_costo_di_gruppo_di_un_negozio_rifiuta_il_food(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _riparto_manuale(monkeypatch, "retail", "CARNE")
    assert e.value.status_code == 400


def test_costo_di_gruppo_di_un_negozio_accetta_le_spese_generali(monkeypatch):
    _riparto_manuale(monkeypatch, "retail", "UTENZE E LOCALI")  # non solleva


def test_costo_di_gruppo_di_un_ristorante_resta_come_ieri(monkeypatch):
    _riparto_manuale(monkeypatch, "ristorazione", "CARNE")  # non solleva


def _riga_categoria(monkeypatch, settore, categoria):
    """L'ALTRO endpoint di riparto. Serve il suo test: il mutante che toglie il
    settore qui sopravviveva ai presidi di `riparto_manuale` — funzione diversa,
    stessa chiamata."""
    sb = _RipartoSB()
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: settore)
    with patch.multiple(
        riparto,
        _resolve_user_from_token=lambda *a, **k: {"id": "user-1"},
        _get_supabase_client=lambda *a, **k: sb,
        _carica_sedi_attive=lambda *a, **k: _SEDI,
        _post_scrittura_riparto=lambda *a, **k: None,
    ):
        riparto.riparto_riga_categoria(
            riparto.RipartoRigaCategoriaBody(
                file_origine="f.xml", descrizione="X", nuova_categoria=categoria,
            ),
            authorization="Bearer x",
        )


def test_riga_di_gruppo_di_un_negozio_rifiuta_il_food(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _riga_categoria(monkeypatch, "retail", "CARNE")
    assert e.value.status_code == 400


def test_riga_di_gruppo_di_un_ristorante_rifiuta_articolo_di_vendita(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _riga_categoria(monkeypatch, "ristorazione", CATEGORIA_ARTICOLO_DI_VENDITA)
    assert e.value.status_code == 400
