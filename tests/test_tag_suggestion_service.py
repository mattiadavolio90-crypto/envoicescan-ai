"""Unit test motore suggerimenti tag — logica a radice (v2)."""

from services.tag_suggestion_service import (
    _build_extend_tag_suggestions,
    _build_new_tag_suggestions,
    _get_product_root,
    _get_product_token,
)


# ── _get_product_root ───────────────────────────────────────────────────────

def test_root_primo_token_significativo():
    # La radice è la forma canonica singolare (stemmata): SALMONE→SALMON
    assert _get_product_root("SALMONE NORVEGESE") == "SALMON"


def test_root_singolare_e_plurale_stessa_radice():
    # Cuore della fix: "SALMONI" (plurale del fornitore) e "SALMONE" (singolare
    # del cliente) devono condividere la stessa radice per agganciarsi.
    assert _get_product_root("SALMONI 5/6 FRESCHI") == _get_product_root("SALMONE 5-6")


def test_token_salta_stopword_iniziale():
    # "DI" è stopword, "POLLO" è il token scelto (grezzo, non stemmato)
    assert _get_product_token("DI POLLO INTERO") == "POLLO"


def test_token_salta_token_con_cifre():
    # "1LT" ha cifre → escluso, "ACQUA" è il token scelto
    assert _get_product_token("ACQUA 1LT NATURALE") == "ACQUA"


def test_token_salta_token_corti():
    # "EVO" è 3 chars → escluso, "OLIO" è il token scelto
    assert _get_product_token("OLIO EVO") == "OLIO"


def test_token_none_se_solo_stopwords_e_cifre():
    # nessun token valido
    assert _get_product_token("1LT 500ML KG") is None
    assert _get_product_root("1LT 500ML KG") is None


def test_token_con_cifre_esclusi():
    # "33CL" ha cifre, "BIRRA" è il token scelto
    assert _get_product_token("BIRRA 33CL") == "BIRRA"


# ── _build_new_tag_suggestions ──────────────────────────────────────────────

def _pool_salmone():
    return {
        "SALMONE NORVEGESE": {"descrizione": "Salmone Norvegese", "descrizione_key": "SALMONE NORVEGESE", "occorrenze": 5, "fornitori_count": 2, "ultima_data": "2026-05-24"},
        "SALMONE AFFUMICATO": {"descrizione": "Salmone Affumicato", "descrizione_key": "SALMONE AFFUMICATO", "occorrenze": 4, "fornitori_count": 1, "ultima_data": "2026-05-23"},
        "SALMONE FRESCO": {"descrizione": "Salmone Fresco", "descrizione_key": "SALMONE FRESCO", "occorrenze": 3, "fornitori_count": 2, "ultima_data": "2026-05-22"},
    }


def test_new_tag_suggerito_per_radice_comune():
    out = _build_new_tag_suggestions(_pool_salmone(), min_products=3, min_rows=5, window_days=30)
    assert len(out) == 1
    s = out[0]
    assert s["suggestion_type"] == "new_tag"
    assert s["cluster_key"] == "new_tag::SALMON"
    assert s["matched_products_count"] == 3
    assert s["matched_rows_count"] == 12
    # Il nome mostrato resta la forma reale leggibile, non la radice stemmata
    assert s["suggested_tag_name"] == "Salmone"


def test_new_tag_sotto_soglia_prodotti_non_suggerito():
    out = _build_new_tag_suggestions(_pool_salmone(), min_products=4, min_rows=5, window_days=30)
    assert len(out) == 0


def test_new_tag_sotto_soglia_righe_non_suggerito():
    out = _build_new_tag_suggestions(_pool_salmone(), min_products=3, min_rows=20, window_days=30)
    assert len(out) == 0


def test_new_tag_token_con_cifre_non_diventano_radice():
    """Prodotti con solo token numerici non devono generare suggerimenti."""
    pool = {
        "ACQUA 1LT": {"descrizione": "Acqua 1lt", "descrizione_key": "ACQUA 1LT", "occorrenze": 5, "fornitori_count": 1, "ultima_data": "2026-05-24"},
        "VINO 1LT": {"descrizione": "Vino 1lt", "descrizione_key": "VINO 1LT", "occorrenze": 4, "fornitori_count": 1, "ultima_data": "2026-05-23"},
        "OLIO 1LT": {"descrizione": "Olio 1lt", "descrizione_key": "OLIO 1LT", "occorrenze": 3, "fornitori_count": 1, "ultima_data": "2026-05-22"},
    }
    out = _build_new_tag_suggestions(pool, min_products=3, min_rows=5, window_days=30)
    # Devono essere 3 suggerimenti distinti (ACQUA, VINO, OLIO), non uno per "1LT"
    cluster_keys = {s["cluster_key"] for s in out}
    assert "new_tag::1LT" not in cluster_keys
    # Le radici corrette
    assert "new_tag::ACQUA" in cluster_keys or len(out) == 0  # singoli prodotti → sotto min_products=3


def test_new_tag_prodotti_diversi_non_raggruppati():
    """Prodotti con radici diverse non devono essere raggruppati."""
    pool = {
        "POLLO INTERO": {"descrizione": "Pollo Intero", "descrizione_key": "POLLO INTERO", "occorrenze": 5, "fornitori_count": 1, "ultima_data": "2026-05-24"},
        "SALMONE NORVEGESE": {"descrizione": "Salmone Norvegese", "descrizione_key": "SALMONE NORVEGESE", "occorrenze": 4, "fornitori_count": 1, "ultima_data": "2026-05-23"},
        "MANZO FILETTO": {"descrizione": "Manzo Filetto", "descrizione_key": "MANZO FILETTO", "occorrenze": 3, "fornitori_count": 1, "ultima_data": "2026-05-22"},
    }
    # Con min_products=3 nessuno ha 3 prodotti con stessa radice
    out = _build_new_tag_suggestions(pool, min_products=3, min_rows=5, window_days=30)
    assert len(out) == 0


# ── _build_extend_tag_suggestions ──────────────────────────────────────────

def test_extend_tag_radice_corrisponde():
    """Un nuovo prodotto con la stessa radice dei prodotti nel tag deve essere suggerito."""
    tags = [{"id": 10, "nome": "Salmone"}]
    tag_assoc_keys = {10: ["SALMONE NORVEGESE", "SALMONE AFFUMICATO"]}
    untagged_pool = {
        "SALMONE FRESCO": {"descrizione": "Salmone Fresco", "descrizione_key": "SALMONE FRESCO", "occorrenze": 3, "fornitori_count": 1, "ultima_data": "2026-05-24"},
    }

    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=2, window_days=30)
    assert len(out) == 1
    s = out[0]
    assert s["suggestion_type"] == "extend_tag"
    assert s["target_tag_id"] == 10
    assert s["matched_products_count"] == 1
    assert s["confidence_score"] == 95.0


def test_extend_tag_plurale_aggancia_singolare():
    """Caso reale LAND: tag con 'SALMONE', nuovo prodotto 'SALMONI' → suggerito.

    Regressione: prima il match era esatto e il plurale del fornitore non
    agganciava mai il singolare taggato dal cliente.
    """
    tags = [{"id": 19, "nome": "Salmone Sushi"}]
    tag_assoc_keys = {19: ["SALMONE 5-6", "SALMONE 5-6 ADC TOP QUALITY"]}
    untagged_pool = {
        "SALMONI 5/6 FRESCHI SJOR ACQUACUL SALMO SALAR": {
            "descrizione": "Salmoni 5/6 Freschi Sjor",
            "descrizione_key": "SALMONI 5/6 FRESCHI SJOR ACQUACUL SALMO SALAR",
            "occorrenze": 6, "fornitori_count": 1, "ultima_data": "2026-06-24",
        },
    }
    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=1, window_days=90)
    assert len(out) == 1
    assert out[0]["target_tag_id"] == 19


def test_extend_tag_una_sola_occorrenza_suggerito_con_soglia_1():
    """Con MIN_OCCORRENZE_EXTEND=1 anche un prodotto visto una volta è proposto."""
    tags = [{"id": 10, "nome": "Salmone"}]
    tag_assoc_keys = {10: ["SALMONE NORVEGESE"]}
    untagged_pool = {
        "SALMONE PREAFFETTATO": {"descrizione": "Salmone Preaffettato", "descrizione_key": "SALMONE PREAFFETTATO", "occorrenze": 1, "fornitori_count": 1, "ultima_data": "2026-06-22"},
    }
    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=1, window_days=90)
    assert len(out) == 1
    assert out[0]["target_tag_id"] == 10


def test_extend_tag_radice_diversa_non_suggerito():
    """Prodotto con radice diversa dai prodotti del tag non deve essere suggerito."""
    tags = [{"id": 10, "nome": "Salmone"}]
    tag_assoc_keys = {10: ["SALMONE NORVEGESE", "SALMONE AFFUMICATO"]}
    untagged_pool = {
        "POLLO PETTO": {"descrizione": "Pollo Petto", "descrizione_key": "POLLO PETTO", "occorrenze": 5, "fornitori_count": 1, "ultima_data": "2026-05-24"},
    }

    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=2, window_days=30)
    assert len(out) == 0


def test_extend_tag_sotto_soglia_occorrenze_non_suggerito():
    """Prodotto comprato solo 1 volta (sotto min_occurrenze) non genera suggerimento."""
    tags = [{"id": 10, "nome": "Salmone"}]
    tag_assoc_keys = {10: ["SALMONE NORVEGESE"]}
    untagged_pool = {
        "SALMONE FRESCO": {"descrizione": "Salmone Fresco", "descrizione_key": "SALMONE FRESCO", "occorrenze": 1, "fornitori_count": 1, "ultima_data": "2026-05-24"},
    }

    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=2, window_days=30)
    assert len(out) == 0


def test_extend_tag_token_con_cifre_non_matchano():
    """Prodotti raggruppabili solo per token numerico (es. 1LT) non devono estendere tag."""
    tags = [{"id": 20, "nome": "Acqua"}]
    # Il tag "Acqua" ha solo "ACQUA NATURALE" con radice ACQUA
    tag_assoc_keys = {20: ["ACQUA NATURALE"]}
    untagged_pool = {
        # "VINO 1LT": radice = VINO, non ACQUA → non deve matchare
        "VINO 1LT": {"descrizione": "Vino 1lt", "descrizione_key": "VINO 1LT", "occorrenze": 5, "fornitori_count": 1, "ultima_data": "2026-05-24"},
    }

    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=2, window_days=30)
    assert len(out) == 0
