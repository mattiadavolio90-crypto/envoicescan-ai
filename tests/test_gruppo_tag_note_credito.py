"""Guardia §3c (27/8/2026) — le RPC di catena `gruppo_tag_*` devono scalare le
note di credito dalla spesa.

Il difetto: tutte e 4 filtravano `AND f.prezzo_unitario > 0` nella WHERE. E'
corretto sui calcoli di PREZZO (una nota di credito ha prezzo negativo e
falserebbe la media) ma queste RPC calcolano solo SPESA (`sum(totale_riga)`):
scartare quelle righe significa non scalare i resi.

E' lo stesso filtro sulla grandezza sbagliata gia' corretto il 24/8 sul percorso
sede-singola (`services/tag_analytics_service.py`, flag `PrezzoValido`): il lato
catena era rimasto indietro, e lo stesso tag mostrava due totali diversi a
seconda che il cliente guardasse la sede o il gruppo.

Misurato sul DB live prima del fix (tag SALMONE, l'unico popolato): 7 note di
credito reali di ADC S.R.L., 285,50 EUR di spesa sovrastimata su 2 sedi.

Questi test leggono il FILE di migration: non esiste una suite pgTAP in questo
progetto e le RPC non sono esercitabili da pytest. Difendono l'invariante che
conta — quali RPC possono filtrare sul prezzo e quali no — e cadono se qualcuno
reintroduce il filtro sulla spesa.
"""
import pathlib
import re

import pytest

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "supabase" / "migrations" / "20260827230000_gruppo_tag_note_credito.sql"
)

# Le 4 RPC che aggregano SPESA: nessuna deve filtrare sul prezzo.
RPC_DI_SPESA = [
    "gruppo_tag_analisi",
    "gruppo_tag_fornitori",
    "gruppo_tag_trend",
    "gruppo_tag_descrizioni",
]


def _corpo_funzione(nome: str) -> str:
    sql = MIGRATION.read_text(encoding="utf-8")
    m = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{nome}\b.*?\$function\$(.*?)\$function\$",
        sql,
        re.S,
    )
    assert m, f"{nome} non trovata nella migration"
    return m.group(1)


def test_migration_esiste():
    assert MIGRATION.is_file(), f"migration mancante: {MIGRATION}"


@pytest.mark.parametrize("rpc", RPC_DI_SPESA)
def test_rpc_di_spesa_non_filtra_sul_prezzo(rpc):
    """Il filtro sul prezzo in una RPC di spesa e' il difetto stesso."""
    corpo = _corpo_funzione(rpc)
    assert "prezzo_unitario" not in corpo, (
        f"{rpc} aggrega spesa: filtrare su prezzo_unitario non scala le note "
        f"di credito e sovrastima il totale di catena"
    )


@pytest.mark.parametrize("rpc", RPC_DI_SPESA)
def test_rpc_somma_totale_riga(rpc):
    """Conferma che la grandezza aggregata sia davvero la spesa."""
    assert "sum(f.totale_riga)" in _corpo_funzione(rpc)


@pytest.mark.parametrize("rpc", RPC_DI_SPESA)
def test_rpc_mantiene_soft_delete(rpc):
    """Regola di dominio #5: le query su `fatture` filtrano `deleted_at IS NULL`."""
    assert "deleted_at IS NULL" in _corpo_funzione(rpc)


def test_quantita_resta_protetta_dal_segno():
    """Un reso scala la SPESA, non i chili acquistati.

    Senza il CASE, una nota di credito con quantita' valorizzata sottrarrebbe
    volume e falserebbe il prezzo medio al kg calcolato a valle.
    """
    corpo = _corpo_funzione("gruppo_tag_analisi")
    assert "CASE WHEN f.quantita > 0" in corpo


def test_gruppo_prezzi_categoria_non_e_toccata():
    """La RPC del prezzo medio DEVE continuare a escludere i prezzi <= 0.

    E' la controprova che il fix distingue le due grandezze invece di rimuovere
    il filtro ovunque: sul prezzo medio ponderato il filtro e' corretto.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "gruppo_prezzi_categoria" not in re.sub(r"--[^\n]*", "", sql), (
        "la migration non deve ridefinire gruppo_prezzi_categoria: li' il "
        "filtro sul prezzo e' corretto"
    )
