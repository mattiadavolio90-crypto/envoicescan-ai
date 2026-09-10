"""La coda qualita' dell'admin non suggerisce food a un negozio, e non lo promuove in memoria globale.

Terzo punto d'uscita trovato dal reviewer (seconda lettura). `admin_qualita_coda`
lavora su tutti gli utenti non-admin e propone `_suggerimento_deterministico`
(dizionario e regole dei ristoranti); il pulsante «Accetta tutti» del frontend
scrive in blocco le fonti `regola`/`memoria`. `admin_qualita_classifica` poi
promuove la descrizione in `prodotti_master` verified=True.

Scelta (coerente con la guardia gia' in `admin_qualita_risolvi_conflitto`): le
righe di un negozio RESTANO in coda — l'admin deve poterle classificare a mano —
ma senza suggerimento (ne' deterministico ne' AI), e la memoria globale non si
tocca quando le righe sono tutte di account retail.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi import HTTPException

import services.fastapi_worker  # noqa: F401 — carica i moduli condivisi
import services.routers.admin as admin
import services.settore_service as ss
from tests.test_admin_qualita_fix_audit import _ADMIN, _FakeSB as _ClassificaSB
from tests.test_categorie_admin import FakeClient, _Query


class _QueryConUpdate(_Query):
    """Il fake esistente non conosce `.update()`: senza, il ramo sconti/omaggi
    dell'auto-review moriva nell'`except` prima della promozione e il test
    passava a vuoto (memoria vuota per un errore, non per la guardia)."""

    def update(self, payload):
        self._op = "update"
        self._payload = dict(payload)
        return self

    def execute(self):
        if self._op == "update":
            for r in self._store:
                if self._matches(r):
                    r.update(self._payload)
            return super().execute()
        return super().execute()


class FakeClientConUpdate(FakeClient):
    def table(self, name):
        return _QueryConUpdate(self._tables.setdefault(name, []))

UTENTI = [
    {"id": "u-rist", "email": "rist@x.it", "nome_ristorante": "Trattoria"},
    {"id": "u-retail", "email": "shop@x.it", "nome_ristorante": "Ferramenta"},
]
SETTORI = {"u-rist": "ristorazione", "u-retail": "retail"}


def _riga(id_, desc, user):
    return {"id": id_, "descrizione": desc, "categoria": "Da Classificare", "fornitore": "X",
            "prezzo_unitario": 10.0, "totale_riga": 10.0, "quantita": 1, "tipo_documento": "TD01",
            "needs_review": True, "user_id": user}


def _coda(monkeypatch, righe):
    sb = FakeClient({"users": UTENTI, "fatture": righe, "prodotti_utente": [], "prodotti_master": []})
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)
    monkeypatch.setattr(admin, "_admin_emails_set", lambda: set())
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: SETTORI.get(uid, "ristorazione"))
    out = admin.admin_qualita_coda(admin_user=_ADMIN)
    return {g["descrizione"]: g for g in out["gruppi"]}


def test_un_gruppo_di_un_negozio_resta_in_coda_senza_suggerimento(monkeypatch):
    gruppi = _coda(monkeypatch, [_riga(1, "BISTECCA DI MANZO", "u-retail"), _riga(2, "BISTECCA DI MANZO", "u-rist")])
    # Stesso testo per i due clienti: un solo gruppo, e contiene righe retail.
    g = gruppi["BISTECCA DI MANZO"]
    assert sorted(g["ids"]) == [1, 2]
    assert g["categoria_suggerita"] is None and g["fonte"] is None


def test_per_un_ristorante_il_suggerimento_deterministico_resta(monkeypatch):
    gruppi = _coda(monkeypatch, [_riga(1, "BISTECCA DI MANZO", "u-rist")])
    g = gruppi["BISTECCA DI MANZO"]
    assert g["categoria_suggerita"] == "CARNE"
    assert g["fonte"] in ("regola", "memoria")


def test_una_riga_retail_da_sola_resta_in_coda_senza_suggerimento(monkeypatch):
    gruppi = _coda(monkeypatch, [_riga(1, "TROTA SALMONATA", "u-retail")])
    g = gruppi["TROTA SALMONATA"]
    assert g["ids"] == [1]
    assert g["categoria_suggerita"] is None and g["fonte"] is None


def _classifica(monkeypatch, righe, categoria="MANUTENZIONE E ATTREZZATURE"):
    sb = _ClassificaSB({"fatture": righe, "prodotti_master": [], "ai_review_log": []})
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: SETTORI.get(uid, "ristorazione"))
    with patch.multiple(
        admin,
        get_supabase_client=lambda *a, **k: sb,
        aggiorna_categoria_fatture=lambda *a, **k: len(k.get("ids") or []),
        _log_review_action=lambda *a, **k: None,
        _invalidate_fatture_rows_cache=lambda *a, **k: None,
    ):
        admin.admin_qualita_classifica(admin.ClassificaBody(ids=[r["id"] for r in righe], categoria=categoria), admin_user=_ADMIN)
    return [op for op in sb.ops if op[1] == "prodotti_master"]


def _riga_cl(id_, user):
    return {"id": id_, "descrizione": "SCAFFALE METALLICO", "prezzo_unitario": 90.0, "categoria": "Da Classificare",
            "ristorante_id": f"r-{user}", "user_id": user}


def test_classificare_righe_di_un_negozio_non_scrive_in_memoria_globale(monkeypatch):
    assert _classifica(monkeypatch, [_riga_cl(1, "u-retail")]) == []


def test_classificare_righe_di_un_ristorante_promuove_come_prima(monkeypatch):
    assert _classifica(monkeypatch, [_riga_cl(1, "u-rist")]) == [("upsert", "prodotti_master")]


def test_gruppo_misto_promuove_per_i_ristoranti(monkeypatch):
    assert _classifica(monkeypatch, [_riga_cl(1, "u-retail"), _riga_cl(2, "u-rist")]) == [("upsert", "prodotti_master")]


# ── auto-review e suggerimenti AI: le altre due porte della memoria globale ──
# Inventario di ogni scrittura su prodotti_master (terza lettura, fatta a mano):
# `admin_qualita_auto_review` promuoveva la categoria GIA' presente sulla riga —
# per un negozio ARTICOLO DI VENDITA — verified=True: da li' ai ristoranti come
# bypass. `admin_qualita_suggerisci_ai` mandava le righe dei negozi al prompt dei
# ristoranti e salvava il suggerimento in memoria globale.

def _riga_ar(id_, desc, user, prezzo, categoria=None, totale=None):
    return {"id": id_, "descrizione": desc, "categoria": categoria, "prezzo_unitario": prezzo,
            "totale_riga": prezzo if totale is None else totale, "quantita": 1, "tipo_documento": "TD01",
            "needs_review": True, "user_id": user, "fornitore": "X", "iva_percentuale": 22}


def _auto_review(monkeypatch, righe):
    sb = FakeClientConUpdate({"users": UTENTI, "fatture": righe, "prodotti_master": [], "ai_review_log": []})
    scritte: list = []
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)
    monkeypatch.setattr(admin, "_admin_emails_set", lambda: set())
    monkeypatch.setattr(admin, "aggiorna_categoria_fatture", lambda *_a, **kw: scritte.append((sorted(kw["ids"]), kw["categoria"])) or len(kw["ids"]))
    monkeypatch.setattr(admin, "_log_review_action", lambda *a, **k: None)
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: SETTORI.get(uid, "ristorazione"))
    admin.admin_qualita_auto_review(admin.AutoReviewBody(cliente_id=None), admin_user=_ADMIN)
    return scritte, [(r["descrizione"], r["categoria"]) for r in sb.dump("prodotti_master")]


def test_auto_review_una_dicitura_di_un_negozio_si_classifica_ma_non_entra_in_memoria_globale(monkeypatch):
    scritte, memoria = _auto_review(monkeypatch, [_riga_ar(1, "SPESE DI TRASPORTO", "u-retail", 0.0)])
    assert scritte == [([1], "📝 NOTE E DICITURE")]
    assert memoria == []


def test_auto_review_la_stessa_dicitura_di_un_ristorante_si_promuove_come_prima(monkeypatch):
    scritte, memoria = _auto_review(monkeypatch, [_riga_ar(1, "SPESE DI TRASPORTO", "u-rist", 0.0)])
    assert scritte == [([1], "📝 NOTE E DICITURE")]
    assert memoria == [("SPESE DI TRASPORTO", "📝 NOTE E DICITURE")]


def test_auto_review_uno_sconto_di_un_negozio_non_porta_articolo_di_vendita_ai_ristoranti(monkeypatch):
    scritte, memoria = _auto_review(monkeypatch, [_riga_ar(1, "SCONTO FINALE OMAGGIO", "u-retail", 0.0, categoria="ARTICOLO DI VENDITA")])
    assert all(cat != "ARTICOLO DI VENDITA" for _d, cat in memoria)
    assert memoria == []


def test_auto_review_gruppo_misto_promuove_per_i_ristoranti(monkeypatch):
    _, memoria = _auto_review(monkeypatch, [_riga_ar(1, "SPESE DI TRASPORTO", "u-retail", 0.0), _riga_ar(2, "SPESE DI TRASPORTO", "u-rist", 0.0)])
    assert memoria == [("SPESE DI TRASPORTO", "📝 NOTE E DICITURE")]


def test_suggerisci_ai_non_manda_i_negozi_al_prompt_dei_ristoranti(monkeypatch):
    sb = FakeClient({"users": UTENTI})
    ricevuti: list = []
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)
    monkeypatch.setattr(admin, "_admin_emails_set", lambda: set())
    monkeypatch.setattr(admin, "prepara_suggerimenti_ai", lambda _sb, allowed_ids, **kw: ricevuti.append(list(allowed_ids)) or {"suggerite": 0, "saltate": 0, "errori": 0})
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: SETTORI.get(uid, "ristorazione"))
    admin.admin_qualita_suggerisci_ai(admin.SuggerisciAiBody(), admin_user=_ADMIN)
    assert ricevuti == [["u-rist"]]


# ── classifica: la categoria scelta a mano non va sulle righe dei negozi ─────
# Quinta lettura del reviewer: il gate del commit 64fbe5b guardava solo la
# promozione in memoria globale, ma `aggiorna_categoria_fatture` riceveva TUTTI
# gli id del gruppo — e un gruppo e' regolarmente misto (47 su 264, fino a 5
# sedi). L'admin sceglieva SALUMI per il ristorante e la riga della ferramenta
# usciva SALUMI a DB.

def _classifica_scritture(monkeypatch, righe, categoria):
    sb = _ClassificaSB({"fatture": righe, "prodotti_master": [], "ai_review_log": []})
    scritte: list = []
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: SETTORI.get(uid, "ristorazione"))
    with patch.multiple(
        admin,
        get_supabase_client=lambda *a, **k: sb,
        aggiorna_categoria_fatture=lambda *_a, **kw: scritte.append((sorted(kw["ids"]), kw["categoria"])) or len(kw["ids"]),
        _log_review_action=lambda *a, **k: None,
        _invalidate_fatture_rows_cache=lambda *a, **k: None,
    ):
        try:
            out = admin.admin_qualita_classifica(admin.ClassificaBody(ids=[r["id"] for r in righe], categoria=categoria), admin_user=_ADMIN)
        except HTTPException as e:
            out = e.status_code
    return out, scritte, [op for op in sb.ops if op[1] == "prodotti_master"]


def test_gruppo_misto_una_food_va_solo_sulle_righe_del_ristorante(monkeypatch):
    out, scritte, master = _classifica_scritture(monkeypatch, [_riga_cl(1, "u-retail"), _riga_cl(2, "u-rist")], "SALUMI")
    assert scritte == [([2], "SALUMI")]
    assert out == {"ok": True, "righe_aggiornate": 1, "righe_in_coda": 1}
    assert master == [("upsert", "prodotti_master")]


def test_righe_di_un_negozio_con_una_food_restano_in_coda(monkeypatch):
    out, scritte, master = _classifica_scritture(monkeypatch, [_riga_cl(1, "u-retail")], "SALUMI")
    assert (out, scritte, master) == (422, [], [])


def test_gruppo_misto_una_spesa_generale_va_su_tutte_le_righe(monkeypatch):
    out, scritte, _ = _classifica_scritture(monkeypatch, [_riga_cl(1, "u-retail"), _riga_cl(2, "u-rist")], "MANUTENZIONE E ATTREZZATURE")
    assert scritte == [([1, 2], "MANUTENZIONE E ATTREZZATURE")]
    assert out["righe_in_coda"] == 0


def test_per_i_ristoranti_una_food_si_scrive_come_prima(monkeypatch):
    out, scritte, master = _classifica_scritture(monkeypatch, [_riga_cl(1, "u-rist"), _riga_cl(2, "u-rist")], "SALUMI")
    assert scritte == [([1, 2], "SALUMI")]
    assert out["righe_aggiornate"] == 2 and master == [("upsert", "prodotti_master")]
