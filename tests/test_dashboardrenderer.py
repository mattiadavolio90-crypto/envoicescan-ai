"""
Test unitari per components/dashboard_renderer.py
Copertura iniziale: mostra_statistiche (UI + percorsi DB/AI principali).
"""

from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pandas as pd

from components.dashboard_renderer import mostra_statistiche


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
        "select", "eq", "neq", "gte", "lte", "lt", "is_",
        "range", "insert", "update", "upsert", "order", "delete", "or_", "in_"
    ]:
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=data or [])
    return query


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _columns_factory(spec, *args, **kwargs):
    if isinstance(spec, int):
        return [_FakeContext() for _ in range(spec)]
    return [_FakeContext() for _ in range(len(spec))]


class TestDashboardRenderer:

    @patch("components.dashboard_renderer.st")
    def test_mostra_statistiche_df_vuoto(self, mock_st):
        """Se df e' vuoto deve mostrare info e terminare subito."""
        df = pd.DataFrame()

        mostra_statistiche(df, supabase=MagicMock(), uploaded_files=None)

        mock_st.info.assert_called_once()

    @patch("components.dashboard_renderer._is_admin_or_impersonating", return_value=False)
    @patch("components.dashboard_renderer.st")
    def test_mostra_statistiche_filtri_note_e_review_svuotano_df(self, mock_st, _mock_admin):
        """Quando tutte le righe sono NOTE/review il df diventa vuoto e la funzione esce con info."""
        mock_st.session_state = _AttrDict({})

        df = pd.DataFrame([
            {
                "Categoria": "📝 NOTE E DICITURE",
                "needs_review": False,
                "DataDocumento": "2026-04-01",
            },
            {
                "Categoria": "LATTICINI",
                "needs_review": True,
                "DataDocumento": "2026-04-02",
            },
        ])

        mostra_statistiche(df, supabase=MagicMock(), uploaded_files=None)

        # In questo percorso ci sono due st.info possibili (inizio o dopo filtri):
        # verifichiamo che sia stato invocato almeno una volta.
        assert mock_st.info.called

    @patch("components.dashboard_renderer._is_admin_or_impersonating", return_value=False)
    @patch("components.dashboard_renderer.st")
    def test_mostra_statistiche_sessione_invalida_stop(self, mock_st, _mock_admin):
        """Se manca user_data.id deve mostrare errore e fare stop."""
        mock_st.session_state = _AttrDict({"user_data": {}})
        mock_st.stop.side_effect = RuntimeError("stop")

        df = pd.DataFrame([
            {
                "Categoria": "LATTICINI",
                "needs_review": False,
                "DataDocumento": "2026-04-01",
            }
        ])

        try:
            mostra_statistiche(df, supabase=MagicMock(), uploaded_files=None)
        except RuntimeError as e:
            assert str(e) == "stop"

        mock_st.error.assert_called_once()
        mock_st.stop.assert_called_once()

    @patch("components.dashboard_renderer.invalida_cache_memoria")
    @patch("components.dashboard_renderer._is_admin_or_impersonating", return_value=True)
    @patch("components.dashboard_renderer.st")
    def test_mostra_statistiche_admin_debug_reload(self, mock_st, _mock_admin, mock_invalida_cache):
        """Nel blocco debug admin, click su debug_reload deve invalidare cache."""
        mock_st.session_state = _AttrDict({"user_data": {}})
        mock_st.expander.return_value = _FakeContext()
        mock_st.columns.side_effect = _columns_factory

        def _button_side_effect(label, *args, **kwargs):
            return kwargs.get("key") == "debug_reload"

        mock_st.button.side_effect = _button_side_effect

        df = pd.DataFrame([
            {
                "FileOrigine": "f1.xml",
                "Descrizione": "LATTE INTERO",
                "Categoria": "📝 NOTE E DICITURE",
                "Fornitore": "METRO ITALIA S.P.A",
                "TotaleRiga": 10.0,
                "needs_review": False,
                "DataDocumento": "2026-04-01",
            }
        ])

        mostra_statistiche(df, supabase=MagicMock(), uploaded_files=None)

        mock_invalida_cache.assert_called_once()
