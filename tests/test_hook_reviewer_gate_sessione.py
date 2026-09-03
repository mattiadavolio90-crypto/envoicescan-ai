"""Il gate di review deve contare il lavoro di CHI preme Stop, non del working tree.

Con piu' sessioni Claude Code in parallelo sulla stessa cartella — che su questo
progetto e' il regime normale — il gate misurava `git diff <merge-base con main>`,
cioe' tutti i commit non ancora pushati, di chiunque. Il 3/9/2026 una sessione che
aveva toccato due soli .md si e' vista contestare "11 file / 293 righe": il lavoro
di un'altra sessione sui residui. Un avviso che parla di file non tuoi viene
ignorato per riflesso, ed e' cosi' che un gate smette di servire.

Questi test costruiscono repo git veri in tmp_path (nessun mock: il gate legge
git, e un mock del comando misurerebbe il mock).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parent.parent
GATE = RADICE / "scripts" / "claude_hook_reviewer_gate.py"

# Orari fissi: base, commit altrui, avvio della mia sessione, commit mio.
T0 = 1_700_000_000
T_ALTRUI = T0 + 60
T_AVVIO = T0 + 120
T_MIO = T0 + 180


def _git(repo: Path, *args: str, quando: int | None = None) -> str:
    """git nel repo di prova.

    `quando` fissa la data del commit: git ha risoluzione al secondo, e senza
    date esplicite i commit di un test finiscono tutti nello stesso secondo —
    condizione che in produzione non si verifica (le sessioni distano minuti) e
    che renderebbe il test una misura del proprio setup invece che del gate.
    """
    ambiente = None
    if quando is not None:
        import os

        ambiente = dict(os.environ)
        stamp = f"{quando} +0000"
        ambiente["GIT_AUTHOR_DATE"] = stamp
        ambiente["GIT_COMMITTER_DATE"] = stamp
    esito = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
        env=ambiente,
    )
    return esito.stdout.strip()


def _file_di_codice(repo: Path, quanti: int, prefisso: str) -> None:
    (repo / "services").mkdir(exist_ok=True)
    for i in range(quanti):
        (repo / "services" / f"{prefisso}_{i}.py").write_text("riga\n" * 40)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "DOCUMENTAZIONE").mkdir()
    for nome in ("claude_hook_reviewer_gate.py", "claude_hook_promemoria.py"):
        (repo / "scripts" / nome).write_text(
            (RADICE / "scripts" / nome).read_text(encoding="utf-8"), encoding="utf-8"
        )
    _git(repo, "init", "-q", "-b", "main", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "T")
    (repo / "base.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base", quando=T0)
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def _esegui(repo: Path, session_id: str | None) -> str:
    payload = {} if session_id is None else {"session_id": session_id}
    esito = subprocess.run(
        [sys.executable, str(repo / "scripts" / "claude_hook_reviewer_gate.py")],
        cwd=repo,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return esito.stdout.strip()


def _n_file(uscita: str) -> int | None:
    """File contestati dall'avviso, o None se il gate ha taciuto."""
    if not uscita:
        return None
    motivo = json.loads(uscita)["reason"]
    fra_parentesi = motivo.split("(", 1)[1].split(" file", 1)[0]
    return int(fra_parentesi)


def _registra(repo: Path, session_id: str, avvio: float) -> None:
    (repo / ".claude" / ".sessioni_attive.json").write_text(
        json.dumps(
            [{"pid": 1, "session_id": session_id, "branch_atteso": "main", "timestamp_avvio": avvio}]
        )
    )


def test_non_imputa_i_commit_di_un_altra_sessione(tmp_path):
    """Il caso reale del 3/9: altra sessione scrive codice, la mia due .md."""
    repo = _repo(tmp_path)
    _file_di_codice(repo, 9, "altrui")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "lavoro di un'altra sessione", quando=T_ALTRUI)

    (repo / "DOCUMENTAZIONE" / "AUDIT_ONEFLUX_STATO_2026-09.md").write_text("doc")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "solo documentazione", quando=T_MIO)
    _registra(repo, "MIA", T_AVVIO)

    assert _n_file(_esegui(repo, "MIA")) is None, (
        "il gate ha contestato lavoro di un'altra sessione a chi ha toccato solo .md"
    )


def test_conta_il_lavoro_proprio_incluso_il_primo_commit(tmp_path):
    """Restringere la base non deve accecare il gate sul lavoro della sessione."""
    repo = _repo(tmp_path)
    _file_di_codice(repo, 3, "altrui")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "altra sessione", quando=T_ALTRUI)

    _file_di_codice(repo, 9, "mio")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "primo commit della sessione, codice", quando=T_MIO)
    _registra(repo, "MIA", T_AVVIO)

    contati = _n_file(_esegui(repo, "MIA"))
    assert contati is not None, "gate cieco sul lavoro proprio"
    assert contati >= 9, (
        f"il primo commit della sessione non e' contato: {contati} file invece di >=9"
    )


@pytest.mark.parametrize(
    "session_id, registro",
    [
        ("SCONOSCIUTA", "valido"),   # ripresa con --continue: nessun record
        ("MIA", "assente"),
        ("MIA", "corrotto"),
        (None, "valido"),            # payload senza session_id
    ],
)
def test_senza_attribuzione_torna_al_comportamento_storico(tmp_path, session_id, registro):
    """Quando non sa di chi e' il lavoro, il gate esagera: non tace mai."""
    repo = _repo(tmp_path)
    _file_di_codice(repo, 9, "qualcuno")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "lavoro", quando=T_ALTRUI)

    percorso = repo / ".claude" / ".sessioni_attive.json"
    if registro == "valido":
        _registra(repo, "ALTRA", 1.0)
    elif registro == "corrotto":
        percorso.write_text("{non e' json")

    assert _n_file(_esegui(repo, session_id)) is not None, (
        "senza attribuzione il gate deve ricadere sul merge-base, non spegnersi"
    )


def test_commit_nello_stesso_secondo_dell_avvio_non_azzera_la_misura(tmp_path):
    """git ha risoluzione al secondo: l'attribuzione puo' fallire legittimamente.

    Quando fallisce il gate deve tornare al merge-base, MAI misurare da HEAD:
    misurare da HEAD significa zero file e quindi silenzio su lavoro vero.
    Misurato il 3/9/2026 su un repo di prova — due commit con lo stesso %ct e il
    gate cieco su 9 file di codice.
    """
    repo = _repo(tmp_path)
    _file_di_codice(repo, 9, "mio")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "commit nello stesso secondo dell'avvio", quando=T_MIO)
    # avvio DOPO l'unico commit: nessun commit e' attribuibile alla sessione
    _registra(repo, "MIA", T_MIO + 5)

    assert _n_file(_esegui(repo, "MIA")) is not None, (
        "attribuzione fallita -> il gate ha misurato da HEAD e ha taciuto su 9 file"
    )


def test_il_registro_e_davvero_consultato(tmp_path):
    """Il gate deve leggere .sessioni_attive.json, non fingere di farlo.

    Senza questo test, spegnere la lettura del registro lascia la suite verde:
    tutti gli altri casi restano soddisfatti dal fallback.
    """
    repo = _repo(tmp_path)
    _file_di_codice(repo, 9, "altrui")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "altra sessione", quando=T_ALTRUI)
    (repo / "DOCUMENTAZIONE" / "AUDIT_ONEFLUX_STATO_2026-09.md").write_text("doc")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "solo doc", quando=T_MIO)

    percorso = repo / ".claude" / ".sessioni_attive.json"
    _registra(repo, "MIA", T_AVVIO)
    assert _n_file(_esegui(repo, "MIA")) is None, "precondizione: col registro il gate tace"

    # Stesso repo, stesso stato git: cambia SOLO il registro.
    percorso.unlink()
    assert _n_file(_esegui(repo, "MIA")) is not None, (
        "senza registro l'esito e' identico: il gate non lo sta leggendo"
    )


def test_con_piu_sessioni_nel_registro_usa_la_propria(tmp_path):
    """Il registro contiene TUTTE le sessioni vive: va cercata la propria.

    Prendere la prima voce disponibile fa misurare il lavoro dall'orario di
    un'altra sessione — e piu' sessioni insieme sono la condizione normale qui,
    cioe' esattamente quando questo codice serve.
    """
    repo = _repo(tmp_path)
    _file_di_codice(repo, 9, "altrui")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "lavoro di un'altra sessione", quando=T_ALTRUI)
    (repo / "DOCUMENTAZIONE" / "AUDIT_ONEFLUX_STATO_2026-09.md").write_text("doc")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "solo doc", quando=T_MIO)

    # L'ALTRA sessione e' partita prima del proprio commit ed e' listata per prima:
    # usare la sua voce farebbe rientrare i 9 file altrui.
    (repo / ".claude" / ".sessioni_attive.json").write_text(
        json.dumps(
            [
                {"pid": 1, "session_id": "ALTRA", "branch_atteso": "main", "timestamp_avvio": T0 + 1},
                {"pid": 2, "session_id": "MIA", "branch_atteso": "main", "timestamp_avvio": T_AVVIO},
            ]
        )
    )

    assert _n_file(_esegui(repo, "MIA")) is None, (
        "il gate ha usato l'orario di un'altra sessione del registro"
    )


def test_sessione_con_piu_commit_misura_dal_primo(tmp_path):
    """La base e' il PRIMO commit della sessione, non l'ultimo.

    Con un solo commit per sessione "primo" e "ultimo" coincidono, e il ciclo che
    scorre git log per tenere il piu' vecchio non e' provato: un `break` dopo la
    prima assegnazione lascerebbe la suite verde e il gate muto su meta' del
    lavoro. Segnalato dalla review del 3/9 e riprodotto: 10 file -> 5, sotto
    soglia, nessun avviso.
    """
    repo = _repo(tmp_path)
    _file_di_codice(repo, 5, "primo")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "primo commit della sessione", quando=T_AVVIO + 10)
    _file_di_codice(repo, 5, "secondo")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "secondo commit della sessione", quando=T_AVVIO + 20)
    _registra(repo, "MIA", T_AVVIO)

    contati = _n_file(_esegui(repo, "MIA"))
    assert contati is not None, "gate muto su due commit di sessione"
    assert contati >= 10, (
        f"misurato dall'ultimo commit invece che dal primo: {contati} file invece di >=10"
    )


def test_il_marker_anti_loop_non_zittisce_le_altre_sessioni(tmp_path):
    """Due sessioni, stesso HEAD, misure diverse: il marker deve essere per sessione.

    Era unico e indicizzato sul solo HEAD: la prima sessione che segnalava
    zittiva la seconda, anche con lavoro proprio sopra soglia.
    """
    repo = _repo(tmp_path)
    _file_di_codice(repo, 9, "di_mia")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "lavoro di MIA", quando=T_AVVIO + 10)
    _file_di_codice(repo, 9, "di_altra")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "lavoro di ALTRA", quando=T_AVVIO + 100)

    (repo / ".claude" / ".sessioni_attive.json").write_text(
        json.dumps(
            [
                {"pid": 1, "session_id": "MIA", "branch_atteso": "main", "timestamp_avvio": T_AVVIO},
                {"pid": 2, "session_id": "ALTRA", "branch_atteso": "main", "timestamp_avvio": T_AVVIO + 90},
            ]
        )
    )

    assert _n_file(_esegui(repo, "MIA")) is not None, "precondizione: MIA deve segnalare"
    assert _n_file(_esegui(repo, "ALTRA")) is not None, (
        "il marker scritto da MIA ha zittito ALTRA sullo stesso HEAD"
    )


@pytest.mark.parametrize("payload", ['"una stringa"', "[1, 2, 3]", "42", "null"])
def test_payload_json_valido_ma_non_oggetto_non_fa_crashare(tmp_path, payload):
    """Un JSON valido che non e' un oggetto non deve uccidere il gate.

    `payload.get()` su una stringa solleva AttributeError: il gate morirebbe con
    exit 1 invece di misurare.
    """
    repo = _repo(tmp_path)
    _file_di_codice(repo, 9, "codice")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "lavoro", quando=T_ALTRUI)

    esito = subprocess.run(
        [sys.executable, str(repo / "scripts" / "claude_hook_reviewer_gate.py")],
        cwd=repo,
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert esito.returncode != 1, f"gate crashato: {esito.stderr[-400:]}"
    assert _n_file(esito.stdout.strip()) is not None, "gate muto su payload anomalo"
