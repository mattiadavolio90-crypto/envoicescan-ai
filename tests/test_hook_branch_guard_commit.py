"""La guardia sul commit: su quale branch crede di essere questa sessione.

Presidia il caso 2 del docstring di `claude_hook_branch_guard.py`: un'altra
sessione sposta `HEAD` (globale al filesystem, niente worktree per sessione) e
il commit finisce sul branch sbagliato.

Il buco che questi test chiudono, trovato dalla review del 3/9/2026: una
sessione ripresa dopo una pausa lunga si ri-registra, ma il branch da cui era
partita e' perso. Riempirlo con l'HEAD di adesso rendeva il confronto della
guardia (`branch_atteso != branch_reale`) **falso per costruzione**: la guardia
taceva proprio nel caso che deve coprire.

Si esegue l'hook vero come processo, col payload che riceve da Claude Code.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parent.parent


def _git(repo: Path, *args: str) -> str:
    esito = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, timeout=30
    )
    return esito.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / "scripts").mkdir()
    for nome in ("claude_hook_branch_guard.py", "_registro_sessioni.py"):
        (repo / "scripts" / nome).write_text(
            (RADICE / "scripts" / nome).read_text(encoding="utf-8"), encoding="utf-8"
        )
    _git(repo, "init", "-q", "-b", "main", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "T")
    (repo / "base.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def _esegui(repo: Path, session_id: str, comando: str) -> dict | None:
    """L'hook sul comando dato. None se ha taciuto (nessun attrito)."""
    esito = subprocess.run(
        [sys.executable, str(repo / "scripts" / "claude_hook_branch_guard.py")],
        cwd=repo,
        input=json.dumps(
            {"session_id": session_id, "tool_name": "Bash", "tool_input": {"command": comando}}
        ),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(esito.stdout) if esito.stdout.strip() else None


def _scrivi_registro(repo: Path, entries: list[dict]) -> None:
    (repo / ".claude" / ".sessioni_attive.json").write_text(json.dumps(entries))


def _chiede_conferma(uscita: dict | None) -> bool:
    return bool(uscita) and uscita["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_commit_sul_branch_atteso_non_da_attrito(repo):
    ora = time.time()
    _scrivi_registro(repo, [
        {"session_id": "MIA", "branch_atteso": "main",
         "timestamp_avvio": ora, "ultimo_visto": ora},
    ])

    assert not _chiede_conferma(_esegui(repo, "MIA", "git commit -m x"))


def test_commit_su_un_branch_diverso_chiede_conferma(repo):
    """Un'altra sessione ha spostato HEAD mentre questa lavorava."""
    ora = time.time()
    _scrivi_registro(repo, [
        {"session_id": "MIA", "branch_atteso": "feature/x",
         "timestamp_avvio": ora, "ultimo_visto": ora},
    ])

    uscita = _esegui(repo, "MIA", "git commit -m x")

    assert _chiede_conferma(uscita)
    assert "feature/x" in uscita["hookSpecificOutput"]["permissionDecisionReason"]


def test_sessione_ripresa_senza_branch_noto_non_tace(repo):
    """Il buco trovato dalla review: `branch_atteso` assente non e' un via libera.

    Se `tocca()` riempisse il campo con l'HEAD di adesso, il confronto sarebbe
    vero per costruzione e la guardia tacerebbe. L'assenza significa «non lo
    so», e va segnalata: e' proprio durante la pausa che un'altra sessione puo'
    aver spostato HEAD.
    """
    ora = time.time()
    _scrivi_registro(repo, [
        {"session_id": "RIPRESA", "branch_atteso": None,
         "timestamp_avvio": ora, "ultimo_visto": ora},
    ])

    uscita = _esegui(repo, "RIPRESA", "git commit -m x")

    assert _chiede_conferma(uscita), (
        "una sessione che non sa su quale branch era partita deve chiedere "
        "conferma, non ricevere un via libera"
    )
    motivo = uscita["hookSpecificOutput"]["permissionDecisionReason"]
    assert "None" not in motivo, (
        "senza il ramo dedicato il campo assente finisce nel messaggio "
        f"generico come se fosse un nome di branch: {motivo}"
    )
    assert "pausa" in motivo, "il motivo deve dire perche' il branch non e' noto"


def test_sessione_mai_vista_chiede_conferma_al_commit(repo):
    """Una sessione assente viene ri-registrata senza branch noto, quindi
    ricade nel caso sopra: non sappiamo da dove e' partita, e HEAD e' globale.
    """
    _scrivi_registro(repo, [])

    assert _chiede_conferma(_esegui(repo, "SCONOSCIUTA", "git commit -m x"))


def test_checkout_su_branch_di_un_altra_sessione_chiede_conferma(repo):
    ora = time.time()
    _scrivi_registro(repo, [
        {"session_id": "ALTRA", "branch_atteso": "feature/x",
         "timestamp_avvio": ora, "ultimo_visto": ora},
        {"session_id": "MIA", "branch_atteso": "main",
         "timestamp_avvio": ora, "ultimo_visto": ora},
    ])

    assert _chiede_conferma(_esegui(repo, "MIA", "git checkout feature/x"))


def test_una_sessione_non_segnala_se_stessa(repo):
    ora = time.time()
    _scrivi_registro(repo, [
        {"session_id": "MIA", "branch_atteso": "feature/x",
         "timestamp_avvio": ora, "ultimo_visto": ora},
    ])

    assert not _chiede_conferma(_esegui(repo, "MIA", "git checkout feature/x"))
