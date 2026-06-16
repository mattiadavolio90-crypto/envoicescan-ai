"""Test mirati per la risoluzione di piano e sede attiva nel modello account/sede.

Coprono i due helper introdotti dalla riprogettazione (piano-per-sede con fallback
all'account): _resolve_piano_effettivo e _resolve_sede_attiva. Sono logica pura su
client Supabase fittizio, nessun DB reale.
"""
from services import fastapi_worker as w


class _Query:
    """Stub di una query Supabase: ignora i filtri e ritorna i dati preconfigurati.

    `single=True` simula .single() (oggetto, non lista). Per le query con .limit(1)
    su lista, ritorna la lista cosi' com'e'.
    """
    def __init__(self, rows, single=False):
        self._rows = rows
        self._single = single

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        if self._single:
            data = self._rows[0] if self._rows else None
        else:
            data = self._rows
        return type("Resp", (), {"data": data})()


class _FakeSupabase:
    """Ritorna righe diverse a seconda della tabella interrogata."""
    def __init__(self, ristoranti=None, users=None):
        self._ristoranti = ristoranti or []
        self._users = users or []

    def table(self, name):
        if name == "ristoranti":
            return _Query(list(self._ristoranti))
        if name == "users":
            return _Query(list(self._users))
        return _Query([])


# ── _resolve_piano_effettivo ──────────────────────────────────────────────────

def test_piano_dalla_sede_attiva_ha_priorita():
    # La sede attiva ha piano 'pro' -> vince anche se l'account dice 'base'.
    sb = _FakeSupabase(ristoranti=[{"id": "r1", "piano": "pro"}])
    user = {"id": "u1", "ultimo_ristorante_id": "r1", "piano": "base"}
    assert w._resolve_piano_effettivo(user, sb) == "pro"


def test_piano_fallback_account_se_sede_senza_piano():
    # Sede senza piano (NULL) -> eredita da users.piano.
    sb = _FakeSupabase(ristoranti=[{"id": "r1", "piano": None}])
    user = {"id": "u1", "ultimo_ristorante_id": "r1", "piano": "plus"}
    assert w._resolve_piano_effettivo(user, sb) == "plus"


def test_piano_default_base_senza_sede_ne_account():
    # Nessuna sede e account senza piano -> default 'base'.
    sb = _FakeSupabase(ristoranti=[], users=[{"piano": None}])
    user = {"id": "u1", "piano": None}
    assert w._resolve_piano_effettivo(user, sb) == "base"


def test_piano_normalizzato_lowercase_trim():
    sb = _FakeSupabase(ristoranti=[{"id": "r1", "piano": "  PRO  "}])
    user = {"id": "u1", "ultimo_ristorante_id": "r1"}
    assert w._resolve_piano_effettivo(user, sb) == "pro"


# ── _resolve_sede_attiva (versione a 1 query) ───────────────────────────────────

def test_sede_attiva_da_ultimo_ristorante_id():
    sb = _FakeSupabase(ristoranti=[{"id": "r1", "nome_ristorante": "Sede Uno"}])
    user = {"id": "u1", "ultimo_ristorante_id": "r1", "nome_ristorante": "ACCOUNT"}
    rid, nome = w._resolve_sede_attiva(user, sb)
    assert rid == "r1"
    assert nome == "Sede Uno"  # NON il nome account


def test_sede_attiva_prima_sede_se_nessuna_selezione():
    sb = _FakeSupabase(ristoranti=[{"id": "rA", "nome_ristorante": "Prima"}])
    user = {"id": "u1", "nome_ristorante": "ACCOUNT"}  # nessun ultimo_ristorante_id
    rid, nome = w._resolve_sede_attiva(user, sb)
    assert rid == "rA"
    assert nome == "Prima"


def test_sede_attiva_fallback_nome_account_se_zero_sedi():
    # Account senza sedi -> id None, nome = etichetta account.
    sb = _FakeSupabase(ristoranti=[])
    user = {"id": "u1", "nome_ristorante": "SUSHILAND"}
    rid, nome = w._resolve_sede_attiva(user, sb)
    assert rid is None
    assert nome == "SUSHILAND"
