"""Test coverage aggiuntiva per services/ai_service.py (classificazione AI)."""

import json
import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.ai_service as ai_mod


class _AttrDict(dict):
    def __getattr__(self, key):
        return self[key] if key in self else None

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        self.pop(key, None)


def _build_query_mock(data=None, execute_side_effect=None):
    query = MagicMock()
    for method in [
        "select", "eq", "neq", "gte", "lte", "lt", "is_",
        "range", "insert", "update", "upsert", "order", "delete", "or_", "in_", "limit"
    ]:
        getattr(query, method).return_value = query

    if execute_side_effect is not None:
        query.execute.side_effect = execute_side_effect
    else:
        query.execute.return_value = SimpleNamespace(data=data or [])

    return query


def _reload_ai_module_without_retry_wrapper():
    """Ricarica il modulo sostituendo tenacity.retry con identity decorator."""
    def _identity_retry(*args, **kwargs):
        def _decorator(fn):
            return fn
        return _decorator

    with patch("tenacity.retry", new=_identity_retry):
        return importlib.reload(ai_mod)


class TestAiService:

    @patch("services.ai_cost_service.track_ai_usage")
    def test_chiama_gpt_classificazione_parsing_ok(self, _mock_track):
        mod = _reload_ai_module_without_retry_wrapper()

        fake_openai = MagicMock()
        fake_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"categorie": ["BEVANDE"]}'))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )

        result = mod._chiama_gpt_classificazione(
            ["Coca Cola 33cl"],
            openai_client=fake_openai,
            max_tokens=256,
        )

        assert result == ["BEVANDE"]
        fake_openai.chat.completions.create.assert_called_once()

    @patch("services.ai_service.st")
    @patch("services.ai_service._chiama_gpt_classificazione")
    def test_classifica_con_ai_usa_openai_iniettato(self, mock_chiama, mock_st):
        mock_st.session_state = _AttrDict({"user_is_admin": False, "impersonating": False})
        mock_chiama.return_value = ["BEVANDE"]

        fake_openai = MagicMock()
        result = ai_mod.classifica_con_ai(["Coca Cola 33cl"], openai_client=fake_openai)

        assert result == ["BEVANDE"]
        mock_chiama.assert_called_once()

    @patch("services.ai_service.st")
    @patch("services.ai_service.applica_correzioni_dizionario", return_value="Da Classificare")
    @patch("services.ai_service._chiama_gpt_classificazione", side_effect=json.JSONDecodeError("msg", "doc", 0))
    def test_classifica_con_ai_jsondecode_fallback(self, _mock_chiama, _mock_dict, mock_st):
        mock_st.session_state = _AttrDict({"user_is_admin": False, "impersonating": False})

        result = ai_mod.classifica_con_ai(
            ["ARTICOLO GENERICO XYZ", "ALTRO ARTICOLO"],
            openai_client=MagicMock(),
        )

        assert result == ["Da Classificare", "Da Classificare"]

    def test_fetch_all_rows_paginato(self):
        page1 = [{"descrizione": f"Prod{i}", "categoria": "BEVANDE"} for i in range(1000)]
        page2 = [{"descrizione": "Prod1000", "categoria": "BEVANDE"}]

        query = _build_query_mock(
            execute_side_effect=[
                SimpleNamespace(data=page1),
                SimpleNamespace(data=page2),
            ]
        )

        supabase = MagicMock()
        supabase.table.return_value.select.return_value = query

        rows = ai_mod._fetch_all_rows(
            supabase,
            table="prodotti_utente",
            select="descrizione, categoria",
            filters={"user_id": "u1"},
        )

        assert len(rows) == 1001
        assert query.range.call_count == 2

    def test_carica_memoria_completa_con_client_iniettato(self):
        ai_mod.invalida_cache_memoria()

        q_locale = _build_query_mock(data=[
            {"descrizione": "Coca Cola 33cl", "categoria": "BEVANDE"}
        ])
        q_master = _build_query_mock(data=[
            {
                "descrizione": "Acqua Naturale 50cl",
                "categoria": "ACQUA",
                "confidence": "alta",
                "consecutive_correct_classifications": 0,
            },
            {
                "descrizione": "Sciroppo Vaniglia",
                "categoria": "VARIE BAR",
                "confidence": "media",
                "consecutive_correct_classifications": 0,
            },
        ])
        q_manuali = _build_query_mock(data=[
            {
                "descrizione": "Riga Fattura",
                "categoria_corretta": "📝 NOTE E DICITURE",
                "is_dicitura": True,
            }
        ])
        q_brand = _build_query_mock(data=[
            {"brand": "BRAND-X"}
        ])

        supabase = MagicMock()

        def _table_side_effect(name):
            if name == "prodotti_utente":
                return q_locale
            if name == "prodotti_master":
                return q_master
            if name == "classificazioni_manuali":
                return q_manuali
            if name == "brand_ambigui":
                return q_brand
            return _build_query_mock(data=[])

        supabase.table.side_effect = _table_side_effect

        cache = ai_mod.carica_memoria_completa("user-1", supabase_client=supabase)

        assert cache["prodotti_utente"]["user-1"]["Coca Cola 33cl"] == "BEVANDE"
        assert cache["prodotti_master"]["Acqua Naturale 50cl"] == "ACQUA"
        assert cache["prodotti_master_hint"]["Sciroppo Vaniglia"] == "VARIE BAR"
        assert cache["classificazioni_manuali"]["Riga Fattura"]["is_dicitura"] is True
        assert "BRAND-X" in cache["brand_ambigui"]
