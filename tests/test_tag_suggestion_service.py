"""Unit test motore suggerimenti tag (helper puri)."""

from services.tag_suggestion_service import (
    _build_extend_tag_suggestions,
    _build_new_tag_suggestions,
    _similarity_score,
)


def test_similarity_score_identical_is_high():
    score = _similarity_score("SALMONE AFFUMICATO", "SALMONE AFFUMICATO")
    assert score >= 0.99


def test_build_new_tag_suggestions_respects_thresholds():
    untagged_pool = {
        "SALMONE NORVEGESE": {
            "descrizione": "Salmone Norvegese",
            "descrizione_key": "SALMONE NORVEGESE",
            "occorrenze": 5,
            "fornitori_count": 2,
            "ultima_data": "2026-05-24",
        },
        "SALMONE AFFUMICATO": {
            "descrizione": "Salmone Affumicato",
            "descrizione_key": "SALMONE AFFUMICATO",
            "occorrenze": 4,
            "fornitori_count": 1,
            "ultima_data": "2026-05-23",
        },
        "SALMONE FRESCO": {
            "descrizione": "Salmone Fresco",
            "descrizione_key": "SALMONE FRESCO",
            "occorrenze": 3,
            "fornitori_count": 2,
            "ultima_data": "2026-05-22",
        },
    }

    out = _build_new_tag_suggestions(
        untagged_pool,
        min_products=3,
        min_rows=10,
        window_days=30,
    )

    assert len(out) == 1
    suggestion = out[0]
    assert suggestion["suggestion_type"] == "new_tag"
    assert suggestion["matched_products_count"] == 3
    assert suggestion["matched_rows_count"] == 12
    assert suggestion["cluster_key"].startswith("new_tag::SALMONE")


def test_build_extend_tag_suggestions_matches_existing_tag():
    tags = [{"id": 10, "nome": "Salmone"}]
    tag_assoc_keys = {10: ["SALMONE NORVEGESE", "SALMONE AFFUMICATO"]}
    untagged_pool = {
        "SALMONE FRESCO": {
            "descrizione": "Salmone Fresco",
            "descrizione_key": "SALMONE FRESCO",
            "occorrenze": 4,
            "fornitori_count": 2,
            "ultima_data": "2026-05-24",
        },
        "SALMONE FILETTO": {
            "descrizione": "Salmone Filetto",
            "descrizione_key": "SALMONE FILETTO",
            "occorrenze": 3,
            "fornitori_count": 1,
            "ultima_data": "2026-05-23",
        },
    }

    out = _build_extend_tag_suggestions(
        tags,
        tag_assoc_keys,
        untagged_pool,
        min_products=2,
        min_score=0.5,
        window_days=30,
    )

    assert len(out) == 1
    suggestion = out[0]
    assert suggestion["suggestion_type"] == "extend_tag"
    assert suggestion["target_tag_id"] == 10
    assert suggestion["matched_products_count"] == 2
    assert suggestion["cluster_key"] == "extend_tag::10"
