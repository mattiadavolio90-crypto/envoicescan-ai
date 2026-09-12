"""L'endpoint "Escludi dai conti": isolamento, i due rifiuti, e le DUE cache.

Perche' esiste
==============
`POST /api/fatture/oscura` scrive su `fatture` senza passare da `db_service`, e
cambia i numeri di CINQUE pagine insieme (Analisi Fatture, Prezzi, Margini,
Foodcost, Home). Tre cose possono andare storte in silenzio:

1. **La sede sbagliata.** Con una P.IVA e piu' sedi lo stesso `file_origine`
   esiste su piu' ristoranti: senza il vincolo di sede si escluderebbe la
   fattura di un'altra sede. E' il Bug A gia' capitato al cestino
   (tests/test_cestino_multisede.py).
2. **La fattura ripartita.** Escludere una fattura di struttura gia' ripartita
   NON toglierebbe il costo dai punti vendita: `riparto_service`, senza righe
   reali, cade sul ramo SINTETICO e proietta le quote lo stesso — "esclusa alla
   fonte, viva a valle". Il rifiuto e' l'unica difesa, perche' il difetto non si
   vede da nessuna parte.
3. **Una cache dimenticata.** `clear_fatture_cache` copre db_service;
   `_invalidate_fatture_rows_cache` copre il funnel Analisi Fatture, PREZZI e lo
   snapshot Home. Chiamarne una sola lascia il cliente a guardare i numeri
   vecchi senza alcun errore a schermo — ed e' esattamente cio' che fa oggi
   `elimina_fattura_soft`, che chiama solo la prima.

I test esercitano la logica REALE dell'endpoint con un fake client in-memory,
non una replica.
"""
import services.fastapi_worker as fw  # noqa: F401 — carica i moduli condivisi
import services.routers.cestino as cestino
import pytest
from fastapi import HTTPException

from tests.test_flusso_dati_admin import FakeClient


def _bind(monkeypatch, sb, user_id="u1", ristorante_id="r1"):
    monkeypatch.setattr(cestino, "_resolve_user_from_token", lambda *a, **k: {"id": user_id})
    monkeypatch.setattr(cestino, "_get_supabase_client", lambda *a, **k: sb)
    monkeypatch.setattr(cestino, "_resolve_ristorante_id", lambda *a, **k: ristorante_id)


def _riga(id_, rid="r1", file="F.xml", numero=1, oscurata=False, deleted=None):
    return {
        "id": id_, "user_id": "u1", "ristorante_id": rid, "file_origine": file,
        "numero_riga": numero, "deleted_at": deleted, "oscurata": oscurata,
        "oscurata_at": None,
    }


def _chiamata(file="F.xml", oscurata=True, ristorante_id=None):
    return cestino.FatturaOscuraRequest(
        file_origine=file, oscurata=oscurata, ristorante_id=ristorante_id
    )


def test_esclude_tutte_le_righe_della_fattura_e_solo_quelle(monkeypatch):
    sb = FakeClient({"fatture": [
        _riga("a1"), _riga("a2", numero=2),
        _riga("b1", rid="r2"),          # stessa fattura, ALTRA sede
        _riga("c1", file="ALTRA.xml"),  # altra fattura, stessa sede
    ]})
    _bind(monkeypatch, sb)

    res = cestino.oscura_fattura(_chiamata(), authorization="Bearer x")

    assert res["success"] is True and res["oscurata"] is True
    assert res["righe"] == 2
    stato = {r["id"]: r["oscurata"] for r in sb.dump("fatture")}
    assert stato == {"a1": True, "a2": True, "b1": False, "c1": False}


def test_rimette_nei_conti_azzerando_la_data(monkeypatch):
    """Il ritorno indietro e' completo: senza azzerare `oscurata_at` resterebbe
    la data di un'esclusione che non c'e' piu'."""
    sb = FakeClient({"fatture": [_riga("a1", oscurata=True)]})
    _bind(monkeypatch, sb)

    res = cestino.oscura_fattura(_chiamata(oscurata=False), authorization="Bearer x")

    assert res["oscurata"] is False
    riga = sb.dump("fatture")[0]
    assert riga["oscurata"] is False
    assert riga["oscurata_at"] is None


def test_404_se_la_fattura_e_di_un_altra_sede(monkeypatch):
    """Isolamento multi-sede: dalla sede attiva r1 una fattura di r2 non esiste."""
    sb = FakeClient({"fatture": [_riga("b1", rid="r2")]})
    _bind(monkeypatch, sb, ristorante_id="r1")

    with pytest.raises(HTTPException) as ei:
        cestino.oscura_fattura(_chiamata(), authorization="Bearer x")
    assert ei.value.status_code == 404
    assert sb.dump("fatture")[0]["oscurata"] is False


def test_409_se_la_fattura_e_nel_cestino(monkeypatch):
    """Due stati di esclusione sovrapposti aprirebbero la domanda "e se la
    ripristino dal cestino?" senza una risposta scritta."""
    sb = FakeClient({"fatture": [_riga("a1", deleted="2026-06-01")]})
    _bind(monkeypatch, sb)

    with pytest.raises(HTTPException) as ei:
        cestino.oscura_fattura(_chiamata(), authorization="Bearer x")
    assert ei.value.status_code == 409
    assert ei.value.detail == "already_in_trash"


def test_409_se_la_fattura_e_ripartita_sul_gruppo(monkeypatch):
    """Il rifiuto che impedisce "esclusa alla fonte, viva a valle" (vedi docstring)."""
    sb = FakeClient({
        "fatture": [_riga("a1")],
        "riparto_costi_catena": [{"id": "rip1", "user_id": "u1", "file_origine": "F.xml"}],
    })
    _bind(monkeypatch, sb)

    with pytest.raises(HTTPException) as ei:
        cestino.oscura_fattura(_chiamata(), authorization="Bearer x")
    assert ei.value.status_code == 409
    assert ei.value.detail == "ripartita_su_gruppo"
    assert sb.dump("fatture")[0]["oscurata"] is False


def test_rimettere_nei_conti_e_permesso_anche_se_ripartita(monkeypatch):
    """Il rifiuto vale solo in USCITA: tornare nei conti non crea doppi conteggi,
    e sbarrarlo lascerebbe la fattura bloccata fuori per sempre."""
    sb = FakeClient({
        "fatture": [_riga("a1", oscurata=True)],
        "riparto_costi_catena": [{"id": "rip1", "user_id": "u1", "file_origine": "F.xml"}],
    })
    _bind(monkeypatch, sb)

    res = cestino.oscura_fattura(_chiamata(oscurata=False), authorization="Bearer x")
    assert res["oscurata"] is False


def test_e_idempotente_su_doppio_click(monkeypatch):
    """A differenza del cestino: qui non c'e' una race da proteggere, e un doppio
    click non deve diventare un errore rosso a video."""
    sb = FakeClient({"fatture": [_riga("a1", oscurata=True)]})
    _bind(monkeypatch, sb)

    res = cestino.oscura_fattura(_chiamata(oscurata=True), authorization="Bearer x")
    assert res["success"] is True
    assert res["righe"] == 0


def test_invalida_ENTRAMBE_le_cache(monkeypatch):
    """Il presidio contro il buco che ha oggi `elimina_fattura_soft`.

    `clear_fatture_cache` da sola lascerebbe Analisi Fatture, Prezzi e la Home
    con i numeri vecchi fino allo scadere del TTL, senza un errore da nessuna
    parte: il cliente esclude una fattura e i totali non si muovono.
    """
    sb = FakeClient({"fatture": [_riga("a1")]})
    _bind(monkeypatch, sb)

    chiamate = []
    import services.db_service as db
    monkeypatch.setattr(db, "clear_fatture_cache", lambda *a, **k: chiamate.append("db"))
    monkeypatch.setattr(fw, "_invalidate_fatture_rows_cache",
                        lambda rid=None: chiamate.append(("rows", rid)))

    cestino.oscura_fattura(_chiamata(), authorization="Bearer x")

    assert "db" in chiamate, "cache db_service non invalidata"
    assert ("rows", "r1") in chiamate, "cache righe/prezzi/briefing non invalidata"
