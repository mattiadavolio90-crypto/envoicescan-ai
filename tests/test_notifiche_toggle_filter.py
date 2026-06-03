"""
Test per il filtro dei toggle avvisi sulla campanella + pagina Avvisi.

Copre _filtra_notifiche_topic_spenti (worker), la logica centralizzata che fa sì
che gli avvisi disattivati nel configuratore assistente spariscano ANCHE da
get_notifiche (non solo dal briefing Home). È una funzione pura: nessun mock di
auth/supabase necessario.

Casi critici:
- topic spento -> filtrato
- topic NON spento -> resta
- topic bloccato (upload falliti) -> mai filtrato, anche se in topics_disabled
- input malformato (None / non-lista) -> fail-open (nessun filtro)
"""

import services.fastapi_worker as worker

_filtra = worker._filtra_notifiche_topic_spenti


def _rows(*topics):
    return [{"id": str(i), "topic_key": t} for i, t in enumerate(topics)]


def _keys(rows):
    return [r["topic_key"] for r in rows]


# ---------------------------------------------------------------------------
# Filtro base
# ---------------------------------------------------------------------------

def test_topic_spento_viene_filtrato():
    rows = _rows("incasso_mancante", "scadenza_superata")
    out = _filtra(rows, ["incasso_mancante"])
    assert _keys(out) == ["scadenza_superata"]


def test_topic_non_spento_resta():
    rows = _rows("incasso_mancante", "scadenza_superata")
    out = _filtra(rows, ["fatturato_mancante"])  # spento un topic non presente
    assert _keys(out) == ["incasso_mancante", "scadenza_superata"]


def test_piu_topic_spenti():
    rows = _rows("incasso_mancante", "fatturato_mancante", "scadenza_superata")
    out = _filtra(rows, ["incasso_mancante", "fatturato_mancante"])
    assert _keys(out) == ["scadenza_superata"]


def test_nessun_topic_spento_lista_vuota():
    rows = _rows("incasso_mancante", "scadenza_superata")
    out = _filtra(rows, [])
    assert _keys(out) == ["incasso_mancante", "scadenza_superata"]


# ---------------------------------------------------------------------------
# Topic bloccati: mai filtrati
# ---------------------------------------------------------------------------

def test_topic_bloccato_non_viene_mai_filtrato():
    # upload_failed/upload_ricavi_failed sono "sempre attivi": anche se per errore
    # finiscono in topics_disabled, devono restare visibili.
    rows = _rows("upload_failed", "upload_ricavi_failed", "incasso_mancante")
    out = _filtra(rows, ["upload_failed", "upload_ricavi_failed", "incasso_mancante"])
    assert _keys(out) == ["upload_failed", "upload_ricavi_failed"]


def test_bloccati_coerenti_con_config_topics():
    # La lista bloccati deriva da _CONFIG_TOPICS (flag True): niente seconda fonte.
    attesi = {k for (k, _l, b) in worker._CONFIG_TOPICS if b}
    assert worker._CONFIG_TOPICS_BLOCCATI == attesi
    assert "upload_failed" in worker._CONFIG_TOPICS_BLOCCATI


# ---------------------------------------------------------------------------
# Fail-open su input malformato
# ---------------------------------------------------------------------------

def test_topics_disabled_none_non_filtra():
    rows = _rows("incasso_mancante", "scadenza_superata")
    out = _filtra(rows, None)
    assert _keys(out) == ["incasso_mancante", "scadenza_superata"]


def test_topics_disabled_non_lista_non_filtra():
    rows = _rows("incasso_mancante")
    out = _filtra(rows, "incasso_mancante")  # stringa, non lista
    assert _keys(out) == ["incasso_mancante"]


def test_row_senza_topic_key_non_esplode():
    rows = [{"id": "1"}, {"id": "2", "topic_key": "incasso_mancante"}]
    out = _filtra(rows, ["incasso_mancante"])
    assert [r["id"] for r in out] == ["1"]


# ---------------------------------------------------------------------------
# incasso_mancante è un toggle reale del configuratore
# ---------------------------------------------------------------------------

def test_incasso_mancante_e_disattivabile_nel_configuratore():
    topics = {k: b for (k, _l, b) in worker._CONFIG_TOPICS}
    assert "incasso_mancante" in topics
    assert topics["incasso_mancante"] is False  # disattivabile (non bloccato)
