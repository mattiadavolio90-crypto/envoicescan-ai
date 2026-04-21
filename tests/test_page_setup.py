from unittest.mock import MagicMock, patch

import utils.page_setup as page_setup


class SessionState(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


def test_check_page_enabled_bypasses_admin():
    session = SessionState({
        'user_is_admin': True,
        'impersonating': False,
        'user_data': {},
    })

    with patch.object(page_setup, '_fetch_pagine_abilitate', return_value={'workspace': False}), \
         patch.object(page_setup, 'st') as mock_st:
        mock_st.session_state = session
        mock_st.warning = MagicMock()
        mock_st.stop = MagicMock(side_effect=AssertionError('admin should not be stopped'))

        page_setup.check_page_enabled('workspace', 'admin-user')

        mock_st.warning.assert_not_called()
        mock_st.stop.assert_not_called()


def test_check_page_enabled_bypasses_impersonation():
    session = SessionState({
        'user_is_admin': False,
        'impersonating': True,
        'user_data': {},
    })

    with patch.object(page_setup, '_fetch_pagine_abilitate', return_value={'workspace': False}), \
         patch.object(page_setup, 'st') as mock_st:
        mock_st.session_state = session
        mock_st.warning = MagicMock()
        mock_st.stop = MagicMock(side_effect=AssertionError('impersonation should not be stopped'))

        page_setup.check_page_enabled('workspace', 'client-user')

        mock_st.warning.assert_not_called()
        mock_st.stop.assert_not_called()
