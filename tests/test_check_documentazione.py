"""Presidio del presidio: le euristiche di `scripts/check_documentazione.py`.

Quello script decide se un riferimento .md e' rotto, e lo fa con tre esenzioni
tarate a mano (documenti vivi, narrazione al passato, segnaposto). Le esenzioni
sono la parte fragile: allargarne una di un carattere rende il controllo cieco
senza che niente diventi rosso.

Il 26/9/2026 il code-reviewer ha mostrato che mutando quella logica
(guardia-tabella rimossa, soglia 3->5, startswith->in) `check_documentazione.py`
restava a exit 0: sul repo pulito nessun dato vivo attraversa quel ramo, quindi
la prova per mutazione andava fatta su casi costruiti e non lasciava rete per il
futuro. Questi test sono quella rete: esercitano le funzioni direttamente.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "_check_doc", ROOT / "scripts" / "check_documentazione.py"
)
cd = importlib.util.module_from_spec(_SPEC)
sys.modules["_check_doc"] = cd
assert _SPEC.loader is not None
_SPEC.loader.exec_module(cd)


# --------------------------------------------------------------------------
# Una riga di TABELLA e' un indice: promette, non racconta.
# --------------------------------------------------------------------------

RIGHE_TABELLA = [
    "| `docs/x.md` | Come si e' spostata la logica dei margini: guida viva |",
    "|`a/b.md`|documento eliminato|",
    "  | `x.md` | era una copia | nota |",
]


@pytest.mark.parametrize("riga", RIGHE_TABELLA)
def test_riga_di_tabella_non_ottiene_l_esenzione(riga: str) -> None:
    """Il falso negativo trovato dal reviewer: parola narrativa in una cella.

    Uccide il mutante «guardia-tabella rimossa»: senza di essa queste righe
    tornerebbero True e un percorso rotto nell'indice resterebbe silenzioso.
    """
    assert cd._e_riga_di_tabella(riga) is True
    assert cd._e_narrazione_al_passato(riga) is False


# Prosa che nomina un file rimosso: l'esenzione DEVE valere, o il presidio
# suona a vuoto su documenti che raccontano correttamente una rimozione.
PROSA_NARRATIVA = [
    "- eliminato `docs/piani/PROMPT_PROSSIMA_SESSIONE.md` (diceva 51 commit)",
    "`docs/storico/audit-2026-09/AUDIT_COPERTURA.md` era una copia ferma al 07/09",
    "- piano rinominato `PIANO_SESSIONE_CORRENTE.md` -> `PIANO_CATEGORIZZAZIONE.md`",
    "Lo stato stava in `docs/piani/PIANO_RETAIL.md` (locale), eliminato alla Chiusura",
]


@pytest.mark.parametrize("riga", PROSA_NARRATIVA)
def test_prosa_al_passato_resta_esente(riga: str) -> None:
    assert cd._e_riga_di_tabella(riga) is False
    assert cd._e_narrazione_al_passato(riga) is True


def test_prosa_con_tre_pipe_non_e_una_tabella() -> None:
    """Uccide i mutanti sulla soglia e su `startswith` -> `in`.

    Una riga di prosa puo' contenere 3 pipe (una pipeline shell citata) senza
    essere una tabella: e' il `lstrip().startswith("|")` a reggere, non il
    conteggio. Con `"|" in riga` questa riga perderebbe l'esenzione.
    """
    riga = "Con `grep x | sort | uniq | wc -l` ho visto che `docs/x.md` e' stato eliminato"
    assert riga.count("|") >= 3
    assert cd._e_riga_di_tabella(riga) is False
    assert cd._e_narrazione_al_passato(riga) is True


def test_blockquote_e_lista_non_sono_tabelle() -> None:
    for riga in ["> `docs/x.md` e' stato eliminato", "- `docs/x.md` rimosso il 1/1"]:
        assert cd._e_riga_di_tabella(riga) is False


def test_due_pipe_non_bastano() -> None:
    """La soglia e' >= 3: due pipe sole non fanno una riga di tabella.

    Una tabella markdown ha almeno due celle, quindi tre pipe. Con due — es.
    una riga di prosa incorniciata — l'esenzione della narrazione deve restare.
    Uccide il mutante soglia 3 -> 2; la riga ha ESATTAMENTE due pipe, che e'
    l'unico modo per distinguere le due soglie (il primo tentativo ne aveva
    una sola e il mutante sopravviveva).
    """
    riga = "| `docs/x.md` eliminato |"
    assert riga.count("|") == 2
    assert cd._e_riga_di_tabella(riga) is False
    assert cd._e_narrazione_al_passato(riga) is True


# --------------------------------------------------------------------------
# Gli altri due filtri
# --------------------------------------------------------------------------

def test_solo_i_documenti_vivi(tmp_path: Path) -> None:
    """docs/storico/ e' una fotografia datata: nominare un file tolto e' il suo
    mestiere. Tutto il resto e' vivo."""
    assert cd._e_vivo(cd.ROOT / "DOCUMENTAZIONE" / "MAPPA_TECNICA.md") is True
    assert cd._e_vivo(cd.ROOT / "docs" / "storico" / "README.md") is False
    assert cd._e_vivo(cd.ROOT / "docs" / "storico" / "audit-2026-09" / "x.md") is False


def test_scratchpad_non_viene_letto() -> None:
    """E' git-ignorato: lo script cammina sul filesystem e senza l'esclusione
    leggeva appunti usa e getta come documenti vivi."""
    assert "scratchpad" in cd.ESCLUDI_DIR
    assert not any("scratchpad" in p.parts for p in cd._tutti_i_md())


SEGNAPOSTO = ["docs/piani/PIANO_<feature>.md", "memory/project_*.md"]


@pytest.mark.parametrize("target", SEGNAPOSTO)
def test_i_segnaposto_non_sono_percorsi(target: str) -> None:
    assert cd._SEGNAPOSTO.search(target)


def test_un_percorso_reale_non_e_un_segnaposto() -> None:
    """Uccide un mutante che allargasse _SEGNAPOSTO fino a scartare tutto."""
    assert not cd._SEGNAPOSTO.search("docs/storico/README.md")


# --------------------------------------------------------------------------
# Il controllo nel suo uso reale
# --------------------------------------------------------------------------

def test_il_repo_non_ha_percorsi_rotti_nei_doc_vivi() -> None:
    """Se questo diventa rosso, un documento vivo promette un file che non c'e'.

    Si passa la lista COMPLETA, come fa `main()`: la funzione filtra i vivi da
    se', e `_risolvi_nome_nudo` ha bisogno di tutti i file per sciogliere un
    nome citato senza percorso. Pre-filtrare i vivi rende irrisolvibili i nomi
    nudi che puntano all'archivio e produce 5 falsi rossi (provato).
    """
    rotti = cd.check_percorsi_backtick(cd._tutti_i_md())
    assert rotti == [], f"riferimenti rotti: {rotti}"
