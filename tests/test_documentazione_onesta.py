"""
Guardia contro il drift della documentazione.

La doc è l'unico artefatto del progetto che può mentire per mesi senza rompere
nulla: il codice non compila, i test diventano rossi, la doc resta lì e viene
letta come verità. Questi test la rendono incapace di mentire in silenzio su
ciò che è verificabile in automatico: simboli citati, fatti anagrafici, e
componenti dichiarati dismessi.

Coprono solo le affermazioni meccanicamente controllabili — il "perché" di una
scelta di design resta responsabilità di chi scrive.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

CLAUDE_MD = ROOT / "CLAUDE.md"
MAPPA_MD = ROOT / "DOCUMENTAZIONE" / "MAPPA_TECNICA.md"

# Documenti che descrivono lo stato corrente e devono restare veri.
# I file sotto docs/storico/ sono esclusi di proposito: sono fotografie
# datate di problemi chiusi, non affermano nulla sul presente.
DOC_VIVI = [
    CLAUDE_MD,
    MAPPA_MD,
    ROOT / "DOCUMENTAZIONE" / "RUNBOOK_INCIDENTI.md",
    ROOT / "docs" / "DEPLOY_RUNBOOK.md",
    ROOT / "docs" / "COMPLIANCE_GDPR.md",
    ROOT / "LOGICA_BRIEFING.md",
    ROOT / "README.md",
]

# P.IVA reale del titolare (RECOMASYSTEM Srl, Trezzano sul Naviglio).
PIVA_CORRETTA = "12993240154"
# P.IVA storica errata: è ricomparsa 4 volte in documenti diversi.
PIVA_ERRATA = "09599210961"


def _leggi(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _doc_esistenti() -> list[Path]:
    return [p for p in DOC_VIVI if p.exists()]


# --------------------------------------------------------------------------
# 1. I simboli citati dalla doc esistono davvero nel codice
# --------------------------------------------------------------------------

# (simbolo citato nella doc, file che deve contenerlo)
SIMBOLI_CITATI = [
    ("CATEGORIA_NON_CLASSIFICATA", "config/constants.py"),
    ("CATEGORIA_FALLBACK", "config/constants.py"),
    ("def filter_active", "services/db_service.py"),
    ("_applica_guardrail_note_con_importo", "services/invoice_service.py"),
]


@pytest.mark.parametrize("simbolo,file_atteso", SIMBOLI_CITATI)
def test_simbolo_citato_esiste_nel_codice(simbolo: str, file_atteso: str) -> None:
    """Un simbolo nominato dalla doc deve esistere, o la doc manda fuori strada."""
    target = ROOT / file_atteso
    assert target.exists(), f"{file_atteso} non esiste ma la doc lo cita"
    assert simbolo in _leggi(target), (
        f"'{simbolo}' è citato nella documentazione ma non esiste più in "
        f"{file_atteso}. Aggiorna la doc o ripristina il simbolo."
    )


FILE_CITATI = [
    "config/constants.py",
    "services/db_service.py",
    "services/fastapi_worker.py",
    "services/routers",
    "worker/run.py",
    "supabase/functions",
    "supabase/migrations",
    "apps/web/src/lib/page-guard.ts",
    "utils/ttl_cache.py",
    "docker/docker-entrypoint.sh",
]


@pytest.mark.parametrize("percorso", FILE_CITATI)
def test_percorso_citato_esiste(percorso: str) -> None:
    """Ogni percorso indicato come punto di riferimento deve esistere."""
    assert (ROOT / percorso).exists(), (
        f"'{percorso}' è citato nella documentazione ma non esiste nel repo."
    )


def test_categoria_non_classificata_ha_grafia_corretta() -> None:
    """La variante con una sola 's' è un errore ricorrente e silenzioso."""
    from config.constants import CATEGORIA_NON_CLASSIFICATA

    assert CATEGORIA_NON_CLASSIFICATA == "Da Classificare"


# --------------------------------------------------------------------------
# 2. Fatti anagrafici: la P.IVA sbagliata non deve tornare
# --------------------------------------------------------------------------


@pytest.mark.parametrize("doc", _doc_esistenti(), ids=lambda p: p.name)
def test_nessuna_piva_errata_nei_doc_vivi(doc: Path) -> None:
    """La P.IVA storica errata è ricomparsa 4 volte: qui si ferma."""
    assert PIVA_ERRATA not in _leggi(doc), (
        f"{doc.name} contiene la P.IVA errata {PIVA_ERRATA}. "
        f"Quella corretta di RECOMASYSTEM Srl è {PIVA_CORRETTA}."
    )


# --------------------------------------------------------------------------
# 3. Streamlit è dismesso: i doc vivi non devono descriverlo come attivo
# --------------------------------------------------------------------------

# Frasi che presenterebbero Streamlit come parte viva del prodotto.
# Citarlo come legacy/dismesso resta legittimo.
STREAMLIT_COME_ATTIVO = re.compile(
    r"streamlit\s+(?:è\s+)?(?:attivo|in\s+produzione|resta\s+acceso)"
    r"|frontend\s+streamlit\b"
    r"|streamlit\s+run\s+app\.py\s*(?:#\s*(?:avvi|dev|prod))",
    re.IGNORECASE,
)


@pytest.mark.parametrize("doc", _doc_esistenti(), ids=lambda p: p.name)
def test_streamlit_non_descritto_come_attivo(doc: Path) -> None:
    """Streamlit è dismesso dallo switch DNS dell'8/6/2026."""
    match = STREAMLIT_COME_ATTIVO.search(_leggi(doc))
    assert match is None, (
        f"{doc.name} descrive Streamlit come attivo ('{match.group(0)}') ma è "
        f"dismesso dall'8/6/2026. Il frontend di produzione è Next.js su Vercel."
    )


# --------------------------------------------------------------------------
# 4. I link interni fra documenti non devono puntare nel vuoto
# --------------------------------------------------------------------------

_LINK_MD = re.compile(r"\[[^\]]+\]\(([^)#]+\.md)[^)]*\)")


@pytest.mark.parametrize("doc", _doc_esistenti(), ids=lambda p: p.name)
def test_link_interni_non_rotti(doc: Path) -> None:
    """Un link a un doc eliminato è un vicolo cieco che costa tempo."""
    rotti = []
    for match in _LINK_MD.finditer(_leggi(doc)):
        target = match.group(1)
        if target.startswith(("http://", "https://")):
            continue
        if not (doc.parent / target).resolve().exists():
            rotti.append(target)
    assert not rotti, f"{doc.name} ha link a documenti inesistenti: {rotti}"


# --------------------------------------------------------------------------
# 5. Le soglie citate nei doc devono coincidere col codice
# --------------------------------------------------------------------------


def test_logica_briefing_dichiara_il_vero_max_card() -> None:
    """`LOGICA_BRIEFING.md` è la mappa delle leve: se un numero è sbagliato,
    Mattia chiede una modifica basandosi su un valore falso.

    Caso reale: il doc ha detto '5 card' per settimane mentre il codice ne
    mostrava 4 (decisione del 19/06 mai riportata).
    """
    from services.daily_briefing_service import _MAX_CARD

    testo = _leggi(ROOT / "LOGICA_BRIEFING.md")
    assert f"| Quante card mostra al massimo | {_MAX_CARD} |" in testo, (
        f"LOGICA_BRIEFING.md non dichiara il vero _MAX_CARD ({_MAX_CARD}). "
        f"La tabella delle leve deve riportare il valore reale del codice."
    )


def test_pareto_e_finestra_alert_prezzi_coerenti() -> None:
    """Le costanti degli alert prezzi sono citate nei doc come scelte di design."""
    from services.price_impact_service import _FINESTRA_GIORNI, _PARETO_QUOTA

    assert _PARETO_QUOTA == 0.80, (
        "La quota Pareto è cambiata: aggiorna MAPPA_TECNICA.md §3, dove è "
        "documentata come '80% della spesa'."
    )
    assert _FINESTRA_GIORNI == 90


# --------------------------------------------------------------------------
# 6. CLAUDE.md è il contratto sempre in contesto: deve restare completo
# --------------------------------------------------------------------------


def test_claude_md_contiene_le_regole_critiche() -> None:
    """Le regole che, se violate, corrompono i dati dei clienti."""
    testo = _leggi(CLAUDE_MD)
    attese = [
        "Da Classificare",
        "service_role_key",
        "filter_active",
        "NOTE E DICITURE",
        "Argon2",
    ]
    mancanti = [r for r in attese if r not in testo]
    assert not mancanti, (
        f"CLAUDE.md non menziona più: {mancanti}. È l'unico documento sempre "
        f"in contesto: se una regola critica sparisce di lì, sparisce e basta."
    )


def test_claude_md_resta_leggibile() -> None:
    """Se cresce troppo smette di essere letto con attenzione: è il suo unico valore."""
    righe = len(_leggi(CLAUDE_MD).splitlines())
    assert righe < 200, (
        f"CLAUDE.md ha {righe} righe. Oltre ~200 diventa un manuale e perde la "
        f"sua funzione: sposta il dettaglio in DOCUMENTAZIONE/MAPPA_TECNICA.md."
    )
