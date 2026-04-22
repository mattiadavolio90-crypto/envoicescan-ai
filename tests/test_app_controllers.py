"""
Test unitari per utils/app_controllers.py
Copertura iniziale: is_admin_or_impersonating
"""

from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from utils.app_controllers import (
    is_admin_or_impersonating,
    mostra_pagina_login,
    load_and_setup_session,
    render_sidebar_and_header,
)


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeQueryParams(dict):
    def clear(self):
        super().clear()


class _AttrDict(dict):
    """Dict con accesso ad attributi come streamlit.session_state."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        try:
            del self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _build_query_mock(execute_data=None):
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.gte.return_value = query
    query.lte.return_value = query
    query.lt.return_value = query
    query.neq.return_value = query
    query.is_.return_value = query
    query.range.return_value = query
    query.insert.return_value = query
    query.update.return_value = query
    query.upsert.return_value = query
    query.order.return_value = query
    query.delete.return_value = query
    query.execute.return_value = SimpleNamespace(data=execute_data or [])
    return query


class TestIsAdminOrImpersonating:

    def test_admin_puro(self):
        """
        user_is_admin=True e impersonating=False -> True
        """
        with patch("utils.app_controllers.st.session_state", new={
            "user_is_admin": True,
            "impersonating": False,
        }):
            assert is_admin_or_impersonating() is True

    def test_impersonating(self):
        """
        user_is_admin=False e impersonating=True -> True
        """
        with patch("utils.app_controllers.st.session_state", new={
            "user_is_admin": False,
            "impersonating": True,
        }):
            assert is_admin_or_impersonating() is True

    def test_admin_e_impersonating(self):
        """
        user_is_admin=True e impersonating=True -> True
        """
        with patch("utils.app_controllers.st.session_state", new={
            "user_is_admin": True,
            "impersonating": True,
        }):
            assert is_admin_or_impersonating() is True

    def test_utente_normale(self):
        """
        user_is_admin=False e impersonating=False -> False
        """
        with patch("utils.app_controllers.st.session_state", new={
            "user_is_admin": False,
            "impersonating": False,
        }):
            assert is_admin_or_impersonating() is False

    def test_session_state_vuoto(self):
        """
        Session state senza chiavi -> False senza KeyError
        """
        with patch("utils.app_controllers.st.session_state", new={}):
            assert is_admin_or_impersonating() is False

    def test_admin_none(self):
        """
        user_is_admin=None (falsy) e impersonating=False -> False
        """
        with patch("utils.app_controllers.st.session_state", new={
            "user_is_admin": None,
            "impersonating": False,
        }):
            assert is_admin_or_impersonating() is False


class TestAppControllersDB:

    def test_mostra_pagina_login_login_ok_salva_session_token(self):
        """
        Verifica percorso login OK: update su users + set cookie session_token.
        """
        mock_supabase = MagicMock()
        query = _build_query_mock(execute_data=[{"id": "u1"}])
        mock_supabase.table.return_value = query
        mock_cookie_manager = MagicMock()

        session_state = _AttrDict({
            "login_tab_attivo": "login",
            "_session_token_set_this_run": False,
        })

        fake_cols = [_FakeContext(), _FakeContext(), _FakeContext()]

        with patch("utils.app_controllers.st.session_state", new=session_state), \
             patch("utils.app_controllers.st.columns", return_value=fake_cols), \
             patch("utils.app_controllers.st.button", return_value=False), \
             patch("utils.app_controllers.st.form", return_value=_FakeContext()), \
             patch("utils.app_controllers.st.form_submit_button", return_value=True), \
             patch("utils.app_controllers.st.text_input", side_effect=["user@test.com", "pwd123456"]), \
             patch("utils.app_controllers.st.spinner", return_value=_FakeContext()), \
             patch("utils.app_controllers.verifica_credenziali", return_value=({"id": "u1", "email": "user@test.com"}, None)), \
             patch("utils.app_controllers.time.sleep", return_value=None), \
             patch("utils.app_controllers.st.rerun", side_effect=RuntimeError("rerun")), \
             patch("utils.app_controllers.st.markdown"), \
             patch("utils.app_controllers.st.warning"), \
             patch("utils.app_controllers.st.error"), \
             patch("utils.app_controllers.st.success"), \
             patch("utils.app_controllers.render_oh_yeah_header"):
            try:
                mostra_pagina_login(mock_supabase, mock_cookie_manager)
            except RuntimeError as e:
                assert str(e) == "rerun"

        mock_supabase.table.assert_called_with("users")
        query.update.assert_called_once()
        mock_cookie_manager.set.assert_called_once()
        assert session_state.get("logged_in") is True

    def test_load_and_setup_session_logout_query_params_invalida_token(self):
        """
        Verifica percorso logout=1: invalidazione token su users e reset sessione.
        """
        mock_supabase = MagicMock()
        query = _build_query_mock(execute_data=[{"id": "u1"}])
        mock_supabase.table.return_value = query

        session_state = _AttrDict({
            "user_data": {"email": "cliente@test.com"},
            "logged_in": True,
            "force_logout": False,
        })
        fake_query_params = _FakeQueryParams({"logout": "1"})

        with patch("utils.app_controllers.st.session_state", new=session_state), \
             patch("utils.app_controllers.st.query_params", new=fake_query_params), \
             patch("utils.app_controllers.st.rerun", side_effect=RuntimeError("rerun")):
            try:
                load_and_setup_session(mock_supabase, MagicMock(), cookie_manager=None)
            except RuntimeError as e:
                assert str(e) == "rerun"

        mock_supabase.table.assert_called_with("users")
        query.update.assert_called_once()
        assert session_state.get("logged_in") is False
        assert session_state.get("force_logout") is True

    def test_render_sidebar_and_header_ripristino_impersonazione_da_cookie(self):
        """
        Verifica query users per ripristino impersonazione quando cookie è presente.
        """
        mock_supabase = MagicMock()
        query = _build_query_mock(execute_data=[{
            "id": "cust-1",
            "email": "cliente@demo.it",
            "nome_ristorante": "Risto Demo",
            "attivo": True,
            "pagine_abilitate": None,
        }])
        mock_supabase.table.return_value = query

        mock_cookie_manager = MagicMock()
        mock_cookie_manager.get.return_value = "cust-1"

        session_state = _AttrDict({
            "logged_in": True,
            "force_logout": False,
            "user_data": {"id": "admin-1", "email": "mattiadavolio90@gmail.com"},
            "user_is_admin": True,
            "impersonating": False,
            "ristoranti": [],
            "ristorante_id": "r1",
        })

        def _fake_columns(spec, *args, **kwargs):
            if isinstance(spec, int):
                return [_FakeContext() for _ in range(spec)]
            return [_FakeContext() for _ in range(len(spec))]

        with patch("utils.app_controllers.st.session_state", new=session_state), \
             patch("utils.app_controllers.st.columns", side_effect=_fake_columns), \
               patch("utils.app_controllers.ADMIN_EMAILS", new=["mattiadavolio90@gmail.com", "cliente@demo.it"]), \
               patch("utils.app_controllers.st.button", return_value=False), \
             patch("utils.app_controllers.render_sidebar"), \
             patch("utils.app_controllers.render_oh_yeah_header"), \
             patch("utils.app_controllers.st.markdown"), \
             patch("utils.app_controllers.st.warning"), \
             patch("utils.app_controllers.st.success"):
            user = render_sidebar_and_header(mock_supabase, MagicMock(), mock_cookie_manager)

        mock_supabase.table.assert_any_call("users")
        query.select.assert_called()
        assert session_state.get("impersonating") is True
        assert user.get("id") == "cust-1"
