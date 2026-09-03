"""Il registro delle sessioni Claude Code (R9).

Il difetto che questi test presidiano: il registro identificava le sessioni
con `os.getppid()`, che per un hook e' il wrapper che lo invoca e muore subito
dopo. Misurato il 3/9/2026: il PID scritto a SessionStart era gia' morto
mentre la sessione era attiva, quindi ogni lettura scartava tutte le entry —
il gate di review non ritrovava la propria sessione e ricadeva sul merge-base,
e le collisioni fra sessioni parallele erano invisibili.

Si prova il COMPORTAMENTO (una sessione registrata si ritrova, una scaduta
no), non il testo del sorgente: un assert su `getppid` assente sopravvivrebbe
a qualunque riscrittura sbagliata.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def registro(tmp_path, monkeypatch):
    """Il modulo del registro, con REGISTRO puntato a un file temporaneo.

    Caricato da zero sotto un nome privato invece che con `import_module` +
    `reload`: altri 7 file della suite fanno `importlib.reload`, e un modulo
    condiviso in `sys.modules` puo' tornare a puntare al registro VERO del
    repo — i test scriverebbero sulle sessioni di lavoro reali. Visto: 3 test
    rossi solo nella suite intera, verdi da soli.
    """
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        f"_registro_sessioni_test_{tmp_path.name}", SCRIPTS / "_registro_sessioni.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    monkeypatch.setattr(modulo, "REGISTRO", tmp_path / ".sessioni_attive.json")
    return modulo


def _scrivi(modulo, entries):
    modulo.REGISTRO.write_text(json.dumps(entries), encoding="utf-8")


def test_la_sessione_registrata_si_ritrova(registro):
    registro.registra("SESSIONE-A", "main")

    entry = registro.mia_entry("SESSIONE-A")
    assert entry is not None, (
        "una sessione appena registrata deve essere leggibile: e' esattamente "
        "cio' che con os.getppid() falliva subito dopo SessionStart"
    )
    assert entry["branch_atteso"] == "main"


def test_entry_scaduta_viene_scartata(registro):
    vecchio = time.time() - registro.SCADENZA_SECONDI - 1
    _scrivi(registro, [
        {"session_id": "VECCHIA", "branch_atteso": "main",
         "timestamp_avvio": vecchio, "ultimo_visto": vecchio},
    ])

    assert registro.carica() == []


def test_il_refresh_tiene_viva_una_sessione_lunga(registro):
    """Una sessione che dura piu' della soglia non deve sparire.

    E' il motivo per cui `tocca` esiste: senza refresh, una scadenza breve
    reintrodurrebbe R9 (sessione viva ma invisibile) su base temporale.
    """
    quasi_scaduta = time.time() - registro.SCADENZA_SECONDI + 5
    _scrivi(registro, [
        {"session_id": "LUNGA", "branch_atteso": "main",
         "timestamp_avvio": quasi_scaduta, "ultimo_visto": quasi_scaduta},
    ])

    registro.tocca("LUNGA")

    entry = registro.mia_entry("LUNGA")
    assert entry is not None
    assert time.time() - entry["ultimo_visto"] < 5
    assert entry["timestamp_avvio"] == pytest.approx(quasi_scaduta), (
        "il refresh non deve spostare timestamp_avvio: il gate di review lo usa "
        "per attribuire i commit alla sessione"
    )


def test_una_sessione_ripresa_dopo_una_pausa_lunga_torna_visibile(registro):
    """R9 daccapo, in forma piu' rara — trovato dalla review del commit.

    Una sessione scaduta viene cancellata dalla prima scrittura di un'altra
    (`salva` scrive solo le vive). Se poi riprende a lavorare — pausa pranzo,
    o `--continue` il giorno dopo — senza ri-registrazione resterebbe
    invisibile **per sempre**: nessuna collisione rilevata e il gate di review
    di nuovo cieco.
    """
    vecchio = time.time() - registro.SCADENZA_SECONDI - 60
    _scrivi(registro, [
        {"session_id": "PAUSA-LUNGA", "branch_atteso": "main",
         "timestamp_avvio": vecchio, "ultimo_visto": vecchio},
    ])
    registro.registra("ALTRA", "main")  # un'altra sessione riscrive il file
    assert registro.mia_entry("PAUSA-LUNGA") is None  # cancellata

    registro.tocca("PAUSA-LUNGA")

    entry = registro.mia_entry("PAUSA-LUNGA")
    assert entry is not None, "la sessione ripresa resterebbe invisibile per sempre"
    assert time.time() - entry["timestamp_avvio"] < 5, (
        "riparte da adesso: per l'attribuzione dei commit sbaglia dal lato "
        "prudente, misurando di meno e mai il lavoro altrui"
    )
    assert entry["branch_atteso"] is None, (
        "il branch di partenza e' perso: riempirlo con l'HEAD di adesso "
        "renderebbe il confronto della guardia commit vero per costruzione, "
        "e la guardia tacerebbe proprio nel caso che deve coprire"
    )


def test_entry_in_formato_vecchio_e_scaduta_non_fa_crashare(registro):
    """Un registro residuo col vecchio schema {pid: ...} non deve rompere."""
    _scrivi(registro, [
        {"pid": 4242, "session_id": "VECCHIO-SCHEMA", "branch_atteso": "main",
         "timestamp_avvio": time.time()},
    ])

    assert registro.carica() == []


@pytest.mark.parametrize("contenuto", ["", "{}", "non json", '"stringa"', "[1, 2]"])
def test_registro_illeggibile_non_fa_crashare(registro, contenuto):
    registro.REGISTRO.write_text(contenuto, encoding="utf-8")

    assert registro.carica() == []
    assert registro.mia_entry("QUALSIASI") is None


def test_carica_esclude_la_sessione_corrente(registro):
    ora = time.time()
    _scrivi(registro, [
        {"session_id": "MIA", "branch_atteso": "main",
         "timestamp_avvio": ora, "ultimo_visto": ora},
        {"session_id": "ALTRA", "branch_atteso": "feature/x",
         "timestamp_avvio": ora, "ultimo_visto": ora},
    ])

    altre = registro.carica(escludi_session_id="MIA")

    assert [e["session_id"] for e in altre] == ["ALTRA"], (
        "senza esclusione una sessione segnalerebbe se stessa come collisione"
    )


def test_sessioni_concorrenti_non_azzerano_il_registro(registro):
    """Il refresh gira su OGNI comando Bash, con piu' sessioni in parallelo.

    Misurato prima della scrittura atomica: `write_text` tronca il file, un
    lettore concorrente ne leggeva meta' e lo trattava come registro vuoto —
    284 letture sbagliate su 300 e **0 entry superstiti su 5**. Sarebbe stato
    R9 in forma peggiore: non entry morte, ma registro sparito.
    """
    import threading

    ora = time.time()
    _scrivi(registro, [
        {"session_id": f"S{i}", "branch_atteso": "main",
         "timestamp_avvio": ora, "ultimo_visto": ora}
        for i in range(5)
    ])

    visti = []

    def lavora(indice: int) -> None:
        for _ in range(40):
            registro.tocca(f"S{indice}")
            visti.append(len(registro.carica()))

    thread = [threading.Thread(target=lavora, args=(i,)) for i in range(5)]
    for t in thread:
        t.start()
    for t in thread:
        t.join()

    assert set(visti) == {5}, f"lettura di un registro a meta': viste {sorted(set(visti))}"
    assert len(registro.carica()) == 5


def test_registrare_due_volte_non_duplica_la_sessione(registro):
    registro.registra("SESSIONE-A", "main")
    registro.registra("SESSIONE-A", "feature/y")

    entries = registro.carica()
    assert len(entries) == 1
    assert entries[0]["branch_atteso"] == "feature/y"
