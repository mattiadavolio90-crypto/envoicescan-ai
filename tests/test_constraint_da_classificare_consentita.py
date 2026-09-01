"""D9 — la migration che vieta "Da Classificare" a DB e' una mina, non uno hardening.

`supabase/migrations/20260429223000_enforce_no_unclassified_categoria.sql` aggiunge
un CHECK che rifiuta `categoria = 'Da Classificare'`. Contraddice la regola di dominio
n.1 del progetto (CLAUDE.md, "flusso categorizzazione = onesto"): una riga che nessuno
riconosce DEVE poter restare esplicitamente in coda invece di ricevere una categoria
inventata — e' il "fallback travestito" eliminato il 23/06.

Stato accertato sul DB di produzione il 1/9/2026:
  - constraint attivo: `fatture_categoria_not_empty_chk` (vieta solo NULL/vuoto) — giusto
  - `fatture_categoria_not_unclassified_chk`: NON applicato
  - 172 righe di 3 clienti reali lo violerebbero all'istante

Il file del 29/4 resta agli atti, ma chi rilanciasse le migration in ordine su un
ambiente nuovo si troverebbe il vincolo sbagliato attivo e il salvataggio rotto.
`20260901160000_annulla_enforce_no_unclassified.sql` lo rimuove, essendo successiva.

Questo test sorveglia che quella protezione non venga tolta per distrazione.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path("supabase/migrations")
_ANNULLA = "20260901160000_annulla_enforce_no_unclassified.sql"


def _sql(nome: str) -> str:
    return (MIGRATIONS / nome).read_text(encoding="utf-8")


def test_la_migration_di_annullamento_esiste():
    assert (MIGRATIONS / _ANNULLA).exists(), (
        "senza questa migration un ambiente nuovo applica il vincolo sbagliato"
    )


def test_annulla_droppa_il_constraint_sbagliato():
    sql = _sql(_ANNULLA).lower()
    assert "drop constraint if exists fatture_categoria_not_unclassified_chk" in sql


def test_annulla_e_successiva_alla_migration_che_annulla():
    """L'ordine e' tutto: se il timestamp fosse precedente, il vincolo sbagliato
    verrebbe riapplicato dopo e la protezione sarebbe inutile."""
    assert _ANNULLA > "20260429223000_enforce_no_unclassified_categoria.sql"


def test_nessuna_migration_successiva_rivieta_da_classificare():
    """Il presidio vero: se qualcuno domani riaggiungesse il divieto in una
    migration nuova, questo test lo intercetta prima del deploy."""
    colpevoli = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name <= _ANNULLA:
            continue
        testo = f.read_text(encoding="utf-8")
        # Un CHECK che nomina "DA CLASSIFICARE" in una disuguaglianza la sta vietando.
        for match in re.finditer(r"<>\s*'([^']*)'", testo, re.IGNORECASE):
            if match.group(1).strip().upper() == "DA CLASSIFICARE":
                colpevoli.append(f.name)
                break
    assert not colpevoli, (
        f"queste migration rivietano 'Da Classificare' a DB: {colpevoli}. "
        "Contraddice la regola di dominio n.1 (CLAUDE.md): una riga non riconosciuta "
        "deve poter restare in coda."
    )


def test_il_vincolo_corretto_resta_dichiarato():
    """L'annullamento non deve lasciare la colonna senza presidio: NULL e stringa
    vuota restano vietati, e' solo "Da Classificare" a essere legittima."""
    sql = _sql(_ANNULLA).lower()
    assert "fatture_categoria_not_empty_chk" in sql
    assert "categoria is not null" in sql
