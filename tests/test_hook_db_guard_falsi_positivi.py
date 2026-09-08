"""Il db_guard deve fermare l'SQL distruttivo senza WHERE e SOLO quello.

Il pattern originale cercava la nuda keyword (DELETE|UPDATE|DROP|TRUNCATE)
senza WHERE: chiedeva conferma su ogni `grep "def .*update"`, cioe' decine di
volte per sessione, rendendo il prompt rumore invece che segnale.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "scripts" / "claude_hook_db_guard.py"


def _decisione(comando: str) -> str | None:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": comando}})
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert res.returncode == 0, res.stderr
    if not res.stdout.strip():
        return None
    return json.loads(res.stdout)["hookSpecificOutput"]["permissionDecision"]


INNOCUI = [
    'grep -rn "def .*update\\|def .*upsert\\|filter_active" services/db_service.py',
    'grep -n "[Cc]ategoria" services/ai_service.py | grep -nE "update_payload|payload\\["',
    'grep -rn "update_data" services/ai_service.py',
    "cat supabase/migrations/20260101000000_drop_vecchia_colonna.sql",
    "ls scripts/ | grep delete",
    "git log --oneline --grep=truncate",
    'python -m pytest tests/test_update_categoria.py -q',
]

PERICOLOSI = [
    'psql -c "DELETE FROM fatture"',
    'psql -c "UPDATE fatture SET categoria = \'x\'"',
    'psql -c "DROP TABLE prodotti_utente"',
    'psql -c "TRUNCATE fatture"',
]

CON_WHERE = [
    'psql -c "DELETE FROM fatture WHERE user_id = 1"',
    'psql -c "UPDATE fatture SET categoria = \'x\' WHERE id = 3"',
]


@pytest.mark.parametrize("comando", INNOCUI)
def test_comando_di_lettura_non_chiede_conferma(comando):
    assert _decisione(comando) is None, f"falso positivo su: {comando}"


@pytest.mark.parametrize("comando", PERICOLOSI)
def test_sql_distruttivo_senza_where_chiede_conferma(comando):
    assert _decisione(comando) == "ask", f"non intercettato: {comando}"


@pytest.mark.parametrize("comando", CON_WHERE)
def test_sql_mirato_con_where_non_chiede_conferma(comando):
    assert _decisione(comando) is None, f"falso positivo su: {comando}"


def test_script_con_commit_resta_intercettato():
    assert _decisione("python scripts/backfill_prodotti.py --commit") == "ask"


def test_railway_redeploy_resta_intercettato():
    assert _decisione("railway redeploy") == "ask"
