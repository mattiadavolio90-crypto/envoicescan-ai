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


# Un blocco CHECK (fino a TRE livelli di parentesi annidate: il CHECK storico
# usa upper(btrim(categoria)); un coalesce(upper(btrim(...))) ne fa tre —
# rilievo della review 3/9).
# La disuguaglianza va cercata QUI DENTRO, non ovunque nel file: le migration
# delle RPC portano legittimamente `categoria <> 'Da Classificare'` nei WHERE
# dei calcoli margini (e' la regola di dominio stessa, presidiata da
# test_da_classificare_sql_allineato). La prima versione di questo test
# matchava anche quelle: falso positivo sulla migration Fase 4 del 3/9.
_CHECK_BLOCK = re.compile(
    r"check\s*\((?:[^()]|\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\))*\)",
    re.IGNORECASE | re.DOTALL,
)
_DIVIETO = re.compile(r"<>\s*'da classificare'", re.IGNORECASE)


def _rivieta_da_classificare(testo_sql: str) -> bool:
    return any(_DIVIETO.search(b.group(0)) for b in _CHECK_BLOCK.finditer(testo_sql))


def test_il_rilevatore_riconosce_il_check_storico():
    """Auto-verifica del rilevatore: DEVE scattare sul CHECK vero del 29/4 (il
    file agli atti) e NON su un WHERE di RPC — altrimenti il presidio e' cieco
    o grida a vuoto."""
    assert _rivieta_da_classificare(
        _sql("20260429223000_enforce_no_unclassified_categoria.sql")
    )
    assert not _rivieta_da_classificare(
        "CREATE FUNCTION f() AS $$ SELECT 1 FROM fatture "
        "WHERE categoria <> 'Da Classificare'; $$;"
    )
    # Tre livelli di annidamento (review 3/9): il rilevatore non deve accecarsi.
    assert _rivieta_da_classificare(
        "alter table fatture add constraint c check "
        "(coalesce(upper(btrim(categoria)), '') <> 'DA CLASSIFICARE');"
    )


def test_nessuna_migration_successiva_rivieta_da_classificare():
    """Il presidio vero: se qualcuno domani riaggiungesse il divieto in una
    migration nuova, questo test lo intercetta prima del deploy."""
    colpevoli = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name <= _ANNULLA:
            continue
        if _rivieta_da_classificare(f.read_text(encoding="utf-8")):
            colpevoli.append(f.name)
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
