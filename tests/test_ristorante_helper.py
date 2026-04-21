from unittest.mock import MagicMock, patch

import utils.ristorante_helper as rh


class SessionState(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


class QueryStub:
    def __init__(self, data=None):
        self._data = data or []

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def execute(self):
        return type("Resp", (), {"data": self._data})()


def test_ensure_admin_test_workspace_reuses_existing_workspace():
    existing = {
        'id': 'rist-test-1',
        'nome_ristorante': 'Ambiente Test Admin',
        'partita_iva': '00000000000',
        'ragione_sociale': 'Workspace Test Admin',
        'user_id': 'admin-1',
    }

    supabase = MagicMock()
    supabase.table.return_value = QueryStub([existing])

    with patch.object(rh, 'st') as mock_st:
        mock_st.session_state = SessionState({'user_is_admin': True, 'impersonating': False})
        result = rh.ensure_admin_test_workspace(supabase, {'id': 'admin-1'})

    assert result == existing


def test_ensure_admin_test_workspace_creates_workspace_if_missing():
    created = {
        'id': 'rist-new',
        'nome_ristorante': 'Ambiente Test Admin',
        'partita_iva': '00000000000',
        'ragione_sociale': 'Workspace Test Admin',
        'user_id': 'admin-2',
    }

    query = QueryStub([])
    insert_query = MagicMock()
    insert_query.execute.return_value = type("Resp", (), {"data": [created]})()

    supabase = MagicMock()
    supabase.table.return_value = query
    query.insert = MagicMock(return_value=insert_query)

    with patch.object(rh, 'st') as mock_st:
        mock_st.session_state = SessionState({'user_is_admin': True, 'impersonating': False})
        result = rh.ensure_admin_test_workspace(supabase, {'id': 'admin-2'})

    assert result == created
    query.insert.assert_called_once()
    payload = query.insert.call_args.args[0]
    assert payload['nome_ristorante'] == 'Ambiente Test Admin'
    assert payload['partita_iva'] == '00000000000'
