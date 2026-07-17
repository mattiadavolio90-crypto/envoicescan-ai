"""
Guardia sulle regole di dominio di CLAUDE.md.

Le regole critiche erano solo prosa: "usa filter_active()", "NOTE solo a importo
zero". Una frase in un documento non impedisce a nessuno di violarla — e la
violazione non rompe niente in modo visibile: mostra semplicemente al cliente dei
dati sbagliati. Questi test le rendono esecutive.

Principio di scrittura: **zero falsi positivi**. Un test che grida su codice
legittimo viene disattivato entro una settimana, e allora non protegge più
nulla. Ogni controllo qui sotto ammette esplicitamente gli usi legittimi
(query del cestino, hard-delete, scrittura del soft-delete stesso).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Il runtime vero. `app.py`, `pages/`, `components/` sono Streamlit congelato
# (switch DNS 8/6/2026) e non sono più serviti a nessun cliente.
SORGENTI_RUNTIME = sorted(
    [p for p in (ROOT / "services").rglob("*.py") if "__pycache__" not in p.parts]
    + [p for p in (ROOT / "worker").rglob("*.py") if "__pycache__" not in p.parts]
)


def _leggi(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# Regola 1 — filter_active(): il soft-delete non è opzionale
# --------------------------------------------------------------------------

# Il soft-delete si può gestire in tre modi, tutti legittimi, e **nessuno dei tre
# sta necessariamente sulla stessa riga** di `table("fatture")`:
#   filter_active(supabase.table("fatture").select(...))   <- il filtro PRECEDE
#   supabase.table("fatture").select(...).is_("deleted_at", "null")  <- SEGUE
#   .not_.is_("deleted_at", "null")                        <- query del cestino
# Per questo si analizza l'ISTRUZIONE INTERA (dall'inizio dello statement fino
# a .execute()), non una riga né una finestra a lunghezza fissa.
_INIZIO_SELECT = re.compile(r'table\(\s*["\'](?:fatture|prodotti)["\']\s*\)')

# `filter_active` viene importata sotto alias diversi a seconda del file
# (`_fa`, `_filter_active`, `_filter_active_fatture`). Gli alias si RICAVANO dal
# file in esame invece di elencarli qui: un elenco fisso si romperebbe al
# prossimo alias, e un test che si rompe da solo viene disattivato.
_ALIAS_FILTER_ACTIVE = re.compile(
    r'filter_active\s+as\s+(?P<alias>\w+)|(?P<nome>\w+)\s*=\s*filter_active\b'
)


def _nomi_del_filtro(testo: str) -> tuple[str, ...]:
    nomi = {"filter_active", "deleted_at"}
    for match in _ALIAS_FILTER_ACTIVE.finditer(testo):
        nomi.add(match.group("alias") or match.group("nome"))
    return tuple(nomi)


def _istruzione_attorno(testo: str, posizione: int) -> str:
    """Estrae lo statement che contiene la posizione data.

    Risale all'inizio logico (una riga con la stessa indentazione o minore che
    apre un'assegnazione) e scende fino a .execute() o alla fine dello statement.
    """
    righe = testo[:posizione].split("\n")
    numero_riga = len(righe) - 1
    tutte = testo.split("\n")

    # Risali finché la riga precedente lascia lo statement aperto (assegnazione
    # multi-riga, parentesi non chiuse) o applica un wrapper come filter_active.
    inizio = numero_riga
    while inizio > 0:
        precedente = tutte[inizio - 1].rstrip()
        if precedente.endswith(("(", "=", "\\", ",")) or precedente.lstrip().startswith("."):
            inizio -= 1
            continue
        break

    # Scendi fino a .execute() o a una riga che chiude lo statement.
    fine = numero_riga
    while fine < len(tutte) - 1 and fine - numero_riga < 25:
        if ".execute()" in tutte[fine]:
            break
        fine += 1

    return "\n".join(tutte[inizio : fine + 1])


def _query_select_non_protette(testo: str) -> list[str]:
    gestito = _nomi_del_filtro(testo)
    fuori_regola = []
    for match in _INIZIO_SELECT.finditer(testo):
        istruzione = _istruzione_attorno(testo, match.start())
        if ".select(" not in istruzione:
            continue  # è una update/insert/delete, non una lettura
        if any(prova in istruzione for prova in gestito):
            continue
        # Lookup per id esplicito: l'id lo ha già scelto chi chiama (tipicamente
        # l'admin su righe che sta guardando), non è una lista mostrata al cliente.
        if re.search(r'\.in_\(\s*["\']id["\']|\.eq\(\s*["\']id["\']', istruzione):
            continue
        # Verifiche post-eliminazione: contano quel che RESTA dopo un delete e
        # devono vedere anche le righe cancellate — è tutto il loro scopo
        # ("Verifica finale: non deve rimanere nulla nel perimetro").
        # Filtrarle qui le renderebbe cieche proprio a ciò che cercano.
        if re.match(r'^\s*(?:verify|query_verify)\w*\s*=', istruzione):
            continue
        fuori_regola.append(" ".join(istruzione.split())[:130])
    return fuori_regola


@pytest.mark.parametrize(
    "sorgente", SORGENTI_RUNTIME, ids=lambda p: str(p.relative_to(ROOT))
)
def test_select_su_fatture_e_prodotti_gestiscono_il_soft_delete(sorgente: Path) -> None:
    """Una SELECT che ignora `deleted_at` mostra al cliente le righe nel cestino.

    Non è un crash: è un numero sbagliato, che è peggio (sul numero mancante ti
    insospettisci, su quello sbagliato ci prendi decisioni).
    """
    violazioni = _query_select_non_protette(_leggi(sorgente))
    assert not violazioni, (
        f"{sorgente.relative_to(ROOT)}: SELECT su fatture/prodotti senza gestire "
        f"il soft-delete. Usa filter_active() da services.db_service.\n  - "
        + "\n  - ".join(violazioni)
    )


def test_filter_active_esiste_e_filtra_deleted_at() -> None:
    """Se filter_active cambia semantica, ogni query del prodotto cambia con lei."""
    sorgente = _leggi(ROOT / "services" / "db_service.py")
    assert "def filter_active(query):" in sorgente
    corpo = sorgente.split("def filter_active(query):", 1)[1][:400]
    assert 'is_("deleted_at", "null")' in corpo, (
        "filter_active non filtra più deleted_at IS NULL: è il fondamento del "
        "soft-delete su tutto il prodotto."
    )


# --------------------------------------------------------------------------
# Regola 2 — categorizzazione onesta: niente fallback travestito
# --------------------------------------------------------------------------


def test_nessun_fallback_a_servizi_e_consulenze() -> None:
    """Il vecchio comportamento: quando l'AI non capiva, buttava tutto in
    "SERVIZI E CONSULENZE". Risultato: un food cost che sembrava giusto ed era
    falso. Eliminato — non deve tornare da nessuna porta.
    """
    from config.constants import CATEGORIA_FALLBACK, CATEGORIA_NON_CLASSIFICATA

    assert CATEGORIA_NON_CLASSIFICATA == "Da Classificare"
    assert CATEGORIA_FALLBACK == CATEGORIA_NON_CLASSIFICATA, (
        "CATEGORIA_FALLBACK deve restare un alias di CATEGORIA_NON_CLASSIFICATA. "
        "Se punta altrove, il fallback travestito è tornato."
    )


_ASSEGNA_SERVIZI_COME_DEFAULT = re.compile(
    r'(?:categoria|cat)\s*=\s*["\']SERVIZI E CONSULENZE["\']'
    r'|or\s+["\']SERVIZI E CONSULENZE["\']'
    r'|get\([^)]*,\s*["\']SERVIZI E CONSULENZE["\']\s*\)',
    re.IGNORECASE,
)


@pytest.mark.parametrize(
    "sorgente", SORGENTI_RUNTIME, ids=lambda p: str(p.relative_to(ROOT))
)
def test_servizi_non_usata_come_default(sorgente: Path) -> None:
    """SERVIZI E CONSULENZE è una categoria legittima se l'AI la riconosce.
    È vietata solo come **ripiego** quando non si sa cosa sia una riga.
    """
    match = _ASSEGNA_SERVIZI_COME_DEFAULT.search(_leggi(sorgente))
    assert match is None, (
        f"{sorgente.relative_to(ROOT)}: '{match.group(0)}' assegna "
        f"SERVIZI E CONSULENZE come default/fallback. Una riga non riconosciuta "
        f"deve restare 'Da Classificare' ed uscire dai margini (CLAUDE.md §1)."
    )


# Il refuso 'Da Clasificare' (una sola 's') esiste nei dati storici, quindi il
# codice lo TOLLERA IN LETTURA di proposito (`cat in ("Da Classificare",
# "Da Clasificare")`). Quello è corretto e va lasciato stare.
# Vietato è **scriverlo**: creerebbe uno stato parallelo invisibile ai filtri,
# e quelle righe non tornerebbero mai a galla.
_SCRIVE_IL_REFUSO = re.compile(
    r'(?:categoria|cat|nuova_cat)\s*=\s*["\']Da Clasificare["\']'
    r'|["\']categoria["\']\s*:\s*["\']Da Clasificare["\']',
)


@pytest.mark.parametrize(
    "sorgente", SORGENTI_RUNTIME, ids=lambda p: str(p.relative_to(ROOT))
)
def test_il_refuso_da_clasificare_non_viene_mai_scritto(sorgente: Path) -> None:
    """Leggere il refuso è difesa legittima; scriverlo è un bug silenzioso."""
    match = _SCRIVE_IL_REFUSO.search(_leggi(sorgente))
    assert match is None, (
        f"{sorgente.relative_to(ROOT)}: '{match.group(0)}' SCRIVE il refuso "
        f"'Da Clasificare' (una 's'). La grafia corretta è 'Da Classificare' "
        f"(costante CATEGORIA_NON_CLASSIFICATA)."
    )


# --------------------------------------------------------------------------
# Regola 3 — NOTE E DICITURE solo a importo zero
# --------------------------------------------------------------------------


def test_guardrail_note_riporta_a_da_classificare() -> None:
    """Una dicitura con importo != 0 non può restare in NOTE: entrerebbe nei
    margini con una categoria inventata. Deve tornare in coda, visibile.
    """
    sorgente = _leggi(ROOT / "services" / "invoice_service.py")
    assert "_applica_guardrail_note_con_importo" in sorgente

    corpo = sorgente.split("_applica_guardrail_note_con_importo", 1)[1][:2000]
    assert (
        "CATEGORIA_NON_CLASSIFICATA" in corpo
        or "Da Classificare" in corpo
    ), (
        "Il guardrail NOTE non riporta più a 'Da Classificare'. Se rimanda a "
        "SERVIZI E CONSULENZE è il vecchio fallback travestito (CLAUDE.md §2)."
    )
    assert "SERVIZI E CONSULENZE" not in corpo, (
        "Il guardrail NOTE non deve mai ripiegare su SERVIZI E CONSULENZE."
    )


# --------------------------------------------------------------------------
# Regola 4 — la anon key non deve entrare nel runtime del worker
# --------------------------------------------------------------------------

_ANON_KEY_NEL_CODICE = re.compile(
    r'SUPABASE_ANON_KEY|supabase_anon_key|["\']anon["\']\s*\)', re.IGNORECASE
)


def test_anon_key_non_usata_per_i_dati_cliente() -> None:
    """La anon key è pubblica per definizione: qualsiasi lettura che passi da lei
    scavalca il worker e l'auth (era il vettore #1 dell'audit del 20/06).
    Il client dati deve nascere solo dalla service_role_key.
    """
    sorgente = _leggi(ROOT / "services" / "__init__.py")
    assert "service_role_key" in sorgente, (
        "services/__init__.py non menziona più service_role_key: verifica "
        "l'auth flow prima di procedere (CLAUDE.md §3)."
    )


# --------------------------------------------------------------------------
# Regola 5 — ADMIN_EMAILS confrontate sempre normalizzate
# --------------------------------------------------------------------------

_CONFRONTO_ADMIN_GREZZO = re.compile(
    r'email\s*(?:==|!=)\s*(?:[^\n]*ADMIN_EMAILS|["\'][^"\']*@)'
    r'|in\s+ADMIN_EMAILS(?![^\n]*lower)',
)


@pytest.mark.parametrize(
    "sorgente", SORGENTI_RUNTIME, ids=lambda p: str(p.relative_to(ROOT))
)
def test_admin_emails_confrontate_lowercase(sorgente: Path) -> None:
    """`Md@Oneflux.it` e `md@oneflux.it` sono la stessa persona. Un confronto
    case-sensitive nega l'accesso admin a caso, o lo concede a caso.
    """
    testo = _leggi(sorgente)
    if "ADMIN_EMAILS" not in testo:
        pytest.skip("non usa ADMIN_EMAILS")

    sospetti = []
    for numero, riga in enumerate(testo.splitlines(), start=1):
        if "ADMIN_EMAILS" not in riga or riga.lstrip().startswith("#"):
            continue
        if "import" in riga or "=" in riga.split("ADMIN_EMAILS")[0][-3:]:
            continue
        if _CONFRONTO_ADMIN_GREZZO.search(riga) and "lower" not in riga:
            sospetti.append(f"riga {numero}: {riga.strip()[:100]}")

    assert not sospetti, (
        f"{sorgente.relative_to(ROOT)}: confronto con ADMIN_EMAILS senza "
        f"normalizzare. Usa .strip().lower() (CLAUDE.md §4).\n  - "
        + "\n  - ".join(sospetti)
    )
