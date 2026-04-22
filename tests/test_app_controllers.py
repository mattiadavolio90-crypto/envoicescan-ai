"""
Test unitari per utils/app_controllers.py
Copertura iniziale: is_admin_or_impersonating
"""

from unittest.mock import patch

from utils.app_controllers import is_admin_or_impersonating


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
