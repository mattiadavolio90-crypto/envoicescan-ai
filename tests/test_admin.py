"""
Test unitari per pages/admin.py
Copertura: logica pura, funzioni DB e una funzione UI.
"""

import sys
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

# Admin importa componenti Streamlit non presenti nell'ambiente test mockato.
for mod in ["streamlit.components", "streamlit.components.v1", "extra_streamlit_components"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import pages.admin as admin_module


class _AttrDict(dict):
    def __getattr__(self, k):
        return self[k] if k in self else None

    def __setattr__(self, k, v):
        self[k] = v

    def __delattr__(self, k):
        self.pop(k, None)


def _build_query_mock(data=None):
    query = MagicMock()
    for method in [
        "select", "eq", "neq", "gte", "lte", "lt", "is_", "range",
        "insert", "update", "upsert", "order", "delete", "ilike", "limit", "in_"
    ]:
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=data or [])
    return query


class TestAdmin:

    # =========================
    # 1) Logica pura
    # =========================

    def test_is_valid_email_format_valida(self):
        assert admin_module._is_valid_email_format("cliente@demo.it") is True

    def test_is_valid_email_format_non_valida(self):
        assert admin_module._is_valid_email_format("cliente-demo.it") is False

    def test_empty_stats_struttura(self):
        stats = admin_module._empty_stats()
        assert stats["num_fatture"] == 0
        assert stats["num_righe"] == 0
        assert stats["totale_costi"] == 0.0
        assert isinstance(stats["debug"], dict)

    def test_update_stats_bucket_incrementa_e_somma(self):
        bucket = admin_module._empty_stats()
        bucket["_file_unici"] = set()

        row = {
            "id": 1,
            "file_origine": "fattura_001.xml",
            "created_at": "2026-04-20T10:30:00+00:00",
            "data_documento": "2026-04-20",
            "totale_riga": 125.5,
            "categoria": "LATTICINI",
            "needs_review": False,
        }

        admin_module._update_stats_bucket(bucket, row)

        assert bucket["num_righe"] == 1
        assert "fattura_001.xml" in bucket["_file_unici"]
        assert bucket["totale_costi"] == 125.5
        assert bucket["debug"]["incluse_finale"] == 1

    def test_finalize_bucket_calcola_num_fatture(self):
        bucket = admin_module._empty_stats()
        bucket["_file_unici"] = {"f1.xml", "f2.xml"}
        bucket["num_righe"] = 3
        bucket["totale_costi"] = 99.9

        result = admin_module._finalize_bucket(bucket)

        assert result["num_fatture"] == 2
        assert result["num_righe"] == 3
        assert result["totale_costi"] == 99.9

    # =========================
    # 2) Funzioni DB (mock chain)
    # =========================

    def test_email_exists_for_other_user_true(self):
        mock_supabase = MagicMock()
        query = _build_query_mock(data=[{"id": "u-2", "email": "cliente@demo.it"}])
        mock_supabase.table.return_value = query

        with patch.object(admin_module, "supabase", mock_supabase):
            exists = admin_module._email_exists_for_other_user("cliente@demo.it", "u-1")

        assert exists is True
        mock_supabase.table.assert_called_with("users")
        query.select.assert_called_once()
        query.execute.assert_called_once()

    def test_email_exists_for_other_user_false_same_user(self):
        mock_supabase = MagicMock()
        query = _build_query_mock(data=[{"id": "u-1", "email": "cliente@demo.it"}])
        mock_supabase.table.return_value = query

        with patch.object(admin_module, "supabase", mock_supabase):
            exists = admin_module._email_exists_for_other_user("cliente@demo.it", "u-1")

        assert exists is False

    def test_merge_and_save_pagina_abilitata_merge_json(self):
        mock_supabase = MagicMock()
        query = _build_query_mock(data=[{"pagine_abilitate": {"foodcost": True, "margini": False}}])
        mock_supabase.table.return_value = query

        with patch.object(admin_module, "supabase", mock_supabase), \
             patch.object(admin_module.st.cache_data, "clear", return_value=None):
            merged = admin_module._merge_and_save_pagina_abilitata(
                user_id="u-1",
                page_key="margini",
                enabled=True,
            )

        assert merged["foodcost"] is True
        assert merged["margini"] is True
        query.update.assert_called_once()

    # =========================
    # 3) Funzioni UI Streamlit
    # =========================

    def test_invalida_cache_memoria_ui(self):
        with patch.object(admin_module.st.cache_data, "clear", return_value=None) as mock_clear, \
             patch("services.ai_service.invalida_cache_memoria", return_value=None) as mock_ai_clear:
            admin_module.invalida_cache_memoria()

        mock_clear.assert_called_once()
        mock_ai_clear.assert_called_once()
