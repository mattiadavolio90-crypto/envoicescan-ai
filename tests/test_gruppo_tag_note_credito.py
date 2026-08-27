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
    """Il difetto era il filtro nella WHERE, che toglie le note di credito dalla
    somma. Un `FILTER (WHERE ...)` su una singola colonna aggregata e' un'altra
    cosa: non tocca `spesa`, serve a costruire il numeratore del prezzo medio.
    """
    corpo = _corpo_funzione(rpc)
    # Il filtro incriminato viveva nella clausola WHERE, dopo `deleted_at`.
    assert "AND f.prezzo_unitario > 0" not in corpo, (
        f"{rpc} aggrega spesa: filtrare su prezzo_unitario nella WHERE non scala "
        f"le note di credito e sovrastima il totale di catena"
    )
    # `spesa` deve restare la somma di TUTTE le righe.
    assert "sum(f.totale_riga) AS spesa" in corpo


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


# ─── Il prezzo medio di catena deve restare coerente ──────────────────────────
# Trovato dalla review delle inerenze (27/8): togliere il filtro dalla spesa
# senza toccare la quantita' (giustamente protetta da `CASE WHEN quantita > 0`)
# rendeva il prezzo medio un ibrido — numeratore NETTO dei resi, denominatore
# LORDO — cioe' sottostimato. Distorsione misurata 0,10% su LAND DEI SAPORI:
# sotto l'arrotondamento, ma ASIMMETRICA fra sedi, e la UI di catena colora
# min/max per dire quale sede compra meglio.

def test_analisi_espone_spesa_prezzo_valido():
    """La colonna separata e' il numeratore omogeneo alla quantita'."""
    corpo = _corpo_funzione("gruppo_tag_analisi")
    assert "spesa_prezzo_valido" in corpo
    assert "FILTER (WHERE f.prezzo_unitario > 0)" in corpo


def test_analisi_dichiara_la_colonna_nel_returns_table():
    """Senza il RETURNS TABLE aggiornato PostgREST non restituirebbe la colonna."""
    sql = MIGRATION.read_text(encoding="utf-8")
    import re
    m = re.search(
        r"CREATE OR REPLACE FUNCTION public\.gruppo_tag_analisi.*?RETURNS TABLE\((.*?)\)",
        sql, re.S,
    )
    assert m and "spesa_prezzo_valido numeric" in m.group(1)


def test_analisi_ha_il_drop_perche_cambia_la_firma():
    """`CREATE OR REPLACE` non puo' cambiare il tipo di ritorno (errore 42P13).

    Senza il DROP la migration fallirebbe in applicazione, non a runtime: e' il
    genere di errore che si scopre solo provando ad applicarla.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "DROP FUNCTION IF EXISTS public.gruppo_tag_analisi(uuid[], text[], date, date);" in sql
    assert sql.index("DROP FUNCTION IF EXISTS public.gruppo_tag_analisi") < sql.index(
        "CREATE OR REPLACE FUNCTION public.gruppo_tag_analisi"
    ), "il DROP deve precedere il CREATE"


def test_il_router_divide_la_spesa_giusta():
    """Il consumatore deve usare `spesa_prezzo_valido`, non `spesa`, al numeratore."""
    import inspect
    from services.routers import gruppo as G

    src = inspect.getsource(G.gruppo_tag_analisi)
    assert "spesa_pv / qta" in src, (
        "il prezzo medio deve dividere la spesa a prezzo valido per la quantita': "
        "usare `spesa` (netta dei resi) su una quantita' lorda lo sottostima"
    )
    assert "round(spesa / qta, 2)" not in src


def test_il_router_regge_la_rpc_pre_migration():
    """Fallback: se il codice arriva prima della migration, la colonna non c'e'
    ancora e il prezzo medio deve restare quello di prima, non sparire."""
    import inspect
    from services.routers import gruppo as G

    src = inspect.getsource(G.gruppo_tag_analisi)
    assert 'r.get("spesa_prezzo_valido") is not None' in src
    assert "else spesa" in src
