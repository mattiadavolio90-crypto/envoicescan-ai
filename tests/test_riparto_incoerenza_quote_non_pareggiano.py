"""La classe `quote_non_pareggiano` di v_riparto_incoerenze (audit 2026-08, F-DRIFT).

La correzione vera del difetto sta nel codice
(`services/riparto_service.py`, difesa da `tests/test_riparto_drift_ricomposizione.py`).
Questa classe è la rete: rende VISIBILE un residuo invece di lasciarlo silenzioso.

Perché una view e non un CHECK o un RAISE nelle RPC: `sostituisci_quote_riparto` è
nell'hot-path del worker (`worker/queue_processor.py:976`), e la migration
20260827214500 aveva già deciso per il caso gemello che il worker non deve fallire
lì — «va segnalato dalla view, non bloccato dal DB». Due migration consecutive non
possono esprimere politiche opposte sullo stesso dato.

I test qui ESEGUONO la logica della classe (la stessa espressione SQL, in Python)
su casi costruiti, invece di verificare col regex che una stringa compaia nel file:
un test sul testo passerebbe identico anche se la migration non venisse mai
applicata, che è la classe di test-che-non-può-fallire già rilevata in F2.
"""
import re
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20260828210000_riparto_quote_pareggiano_header.sql"
)

SOGLIA = 0.005


def segnalato(importo_totale: float, quote: list[float]) -> bool:
    """La condizione della classe 5, identica alla view:
        abs(round(SUM(quota_importo), 2) - importo_totale) >= 0.005
    """
    scarto = round(round(sum(quote), 2) - importo_totale, 10)
    return abs(scarto) >= SOGLIA


# ── La condizione ────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "importo, quote",
    [
        (2.95, [1.48, 1.48]),    # +1 cent — il caso reale più piccolo
        (8.61, [4.30, 4.30]),    # -1 cent
        (32.73, [0.91, 0.91, 15.45, 15.45]),  # multi-categoria, -1 cent
    ],
)
def test_i_casi_reali_vengono_segnalati(importo, quote):
    """Gli scarti trovati live valgono ESATTAMENTE un centesimo: se la soglia
    fosse a 0.01 (col `>=` che diventa `>`) passerebbero tutti inosservati."""
    assert segnalato(importo, quote)


@pytest.mark.parametrize(
    "importo, quote",
    [
        (2.95, [1.48, 1.47]),
        (100.00, [50.0, 50.0]),
        (1.63, [0.81, 0.82]),
        (10.00, [3.33, 3.33, 3.34]),
        (-2.95, [-1.48, -1.47]),   # nota di credito pareggiata
        (0.0, [0.0, 0.0]),         # NC che azzera un costo: legittimo, non segnalato
    ],
)
def test_i_costi_in_equilibrio_non_vengono_segnalati(importo, quote):
    """Falsi positivi: la classe finisce in un alert giornaliero, e un alert che
    grida sempre non lo legge più nessuno."""
    assert not segnalato(importo, quote)


def test_la_soglia_intercetta_un_centesimo_esatto():
    """Il confine: le quote sono NUMERIC(12,2), quindi lo scarto minimo reale è
    un centesimo. La soglia deve stare SOTTO, non sopra."""
    assert segnalato(10.00, [5.00, 5.01])
    assert segnalato(10.00, [5.00, 4.99])
    assert not segnalato(10.00, [5.00, 5.00])


# ── Che la migration dica ciò che questi test assumono ───────────────────────

@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.exists(), (
        "la migration F-DRIFT non esiste più: se è stata rinominata aggiorna "
        "questo test, non cancellarlo"
    )
    return MIGRATION.read_text(encoding="utf-8")


def test_la_soglia_nella_view_coincide_con_quella_testata(sql):
    m = re.search(r"WHERE abs\(y\.scarto\) >= ([0-9.]+);", sql)
    assert m, "condizione della classe quote_non_pareggiano non riconosciuta"
    assert float(m.group(1)) == SOGLIA, (
        f"la view usa {m.group(1)}, i test misurano {SOGLIA}: uno dei due mente"
    )


def test_la_view_conserva_le_quattro_classi_preesistenti(sql):
    """`CREATE OR REPLACE VIEW` riscrive tutto: perdere una classe qui
    spegnerebbe in silenzio un alert che oggi funziona."""
    for classe in [
        "orfano",
        "riparto_senza_documento",
        "riparto_senza_quote",
        "riparto_segno_incoerente",
        "quote_non_pareggiano",
    ]:
        assert f"'{classe}'::text AS tipo_incoerenza" in sql, f"classe {classe} persa"


def test_la_view_resta_security_invoker(sql):
    """Senza, eredita SECURITY DEFINER e bypassa la RLS: è la regressione chiusa
    nell'audit anti-hacker del 20/6 e ripetuta in 20260827214500."""
    assert "SET (security_invoker = true)" in sql


def test_la_migration_e_transazionale(sql):
    """Sanatoria e nuova view devono applicarsi insieme o per niente."""
    assert sql.count("BEGIN;") == 1 and sql.count("COMMIT;") == 1


def test_la_sanatoria_corregge_una_riga_per_costo(sql):
    assert "DISTINCT ON (s.riparto_id)" in sql
    assert "ORDER BY s.riparto_id, abs(q.quota_importo) DESC, q.id" in sql, (
        "senza abs() la sanatoria sbaglia la riga sugli header negativi"
    )


def test_la_sanatoria_non_filtra_sul_segno(sql):
    """Il CHECK (quota_importo >= 0) è stato rimosso il 27/8 per le note di
    credito: un filtro `>= 0` qui scarterebbe in silenzio la correzione sugli
    header negativi."""
    assert "d.nuovo_importo >= 0" not in sql


def test_nessun_raise_nelle_rpc_di_scrittura(sql):
    """La decisione esplicita: niente blocco in hot-path worker. Se un domani
    qualcuno aggiunge un RAISE qui, deve prima cambiare questo test — e leggendo
    perché esiste."""
    corpo = re.sub(r"^--.*$", "", sql, flags=re.M)  # via i commenti
    assert "RAISE EXCEPTION" not in corpo
    assert "CREATE OR REPLACE FUNCTION" not in corpo, (
        "la migration non deve ridefinire le RPC: il fix sta nel codice Python"
    )
