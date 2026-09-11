"""Le etichette cambiano per settore, e per i ristoranti non cambiano affatto.

Fase 3, terza casella. "Costi F&B" e "Food Cost" descrivono un ristorante: per
un negozio la stessa grandezza e' il costo della merce che rivende.

Il presidio che conta non e' "il retail dice Costi Merce" — e' che **i
ristoranti vedono esattamente le stringhe di ieri**, che e' il vincolo di
Mattia. Per questo ogni funzione del blocco ha il settore OPZIONALE e ricade sul
ramo ristorazione: un chiamante che si dimentica di passarlo non rompe un
cliente pagante, e il test lo verifica sulle stringhe letterali, non sul fatto
che "esista un default".

Esegue il TypeScript vero con node (tests/helpers_ts.py): un assert sul sorgente
passerebbe col bug dentro un commento.
"""
from __future__ import annotations

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/categorie-spesa"
_RICHIEDE = ("tipoSpesaLabel", "costoMerceLabel", "filtroMerceLabel", "attivitaLabel")


def _ts(espressione, argomento=None):
    return esegui_ts(MODULO, espressione, argomento=argomento, richiede=_RICHIEDE)


# ── Il vincolo: per un ristorante nulla cambia ──────────────────────────────
# Le stringhe sono scritte a mano QUI, non lette dal modulo: confrontare il
# modulo con se stesso passerebbe anche se qualcuno le cambiasse tutte.

@pytest.mark.parametrize("settore_js", ["undefined", "null", '"ristorazione"'])
def test_le_etichette_della_ristorazione_sono_quelle_di_ieri(settore_js):
    out = _ts(
        f"emit({{"
        f"fb: m.tipoSpesaLabel('fb', {settore_js}),"
        f"gen: m.tipoSpesaLabel('generale', {settore_js}),"
        f"costo: m.costoMerceLabel({settore_js}),"
        f"filtro: m.filtroMerceLabel({settore_js}),"
        f"attivita: m.attivitaLabel({settore_js})"
        f"}});"
    )
    assert out == {
        "fb": "Costi F&B",
        "gen": "Spese Generali",
        "costo": "Food Cost",
        "filtro": "Food & Beverage",
        "attivita": "Ristorante",
    }


def test_la_costante_storica_resta_intatta():
    """TIPO_SPESA_LABEL ha consumatori che non passano il settore: deve restare
    letteralmente quella di prima, o cambierebbero senza che nessuno lo chieda."""
    assert _ts("emit(m.TIPO_SPESA_LABEL);") == {"fb": "Costi F&B", "generale": "Spese Generali"}


@pytest.mark.parametrize("settore_js", ['"negozio"', '"RETAIL"', '""', '"ristorante"'])
def test_un_settore_scritto_male_ricade_sui_ristoranti(settore_js):
    """Fail-safe nella stessa direzione del backend: nel dubbio, il
    comportamento di oggi. 'RETAIL' maiuscolo non e' il valore del DB."""
    assert _ts(f"emit(m.tipoSpesaLabel('fb', {settore_js}));") == "Costi F&B"
    assert _ts(f"emit(m.costoMerceLabel({settore_js}));") == "Food Cost"


# ── Il negozio ──────────────────────────────────────────────────────────────

def test_il_negozio_vede_le_sue_etichette():
    out = _ts(
        "emit({"
        "fb: m.tipoSpesaLabel('fb', 'retail'),"
        "gen: m.tipoSpesaLabel('generale', 'retail'),"
        "costo: m.costoMerceLabel('retail'),"
        "filtro: m.filtroMerceLabel('retail'),"
        "attivita: m.attivitaLabel('retail')"
        "});"
    )
    assert out == {
        "fb": "Costi Merce",
        "gen": "Spese Generali",
        "costo": "Costo Merce",
        "filtro": "Merce",
        "attivita": "Negozio",
    }


def test_le_spese_generali_si_chiamano_uguale_nei_due_settori():
    """Le 4 spese generali esistono identiche per un ristorante e per un
    negozio: un'etichetta diversa qui sarebbe un cambiamento gratuito."""
    assert _ts("emit(m.tipoSpesaLabel('generale', 'retail'));") == _ts(
        "emit(m.tipoSpesaLabel('generale', 'ristorazione'));"
    )


def test_nessuna_etichetta_retail_e_vuota():
    """Una stringa vuota non da' errore: lascia un'etichetta invisibile in
    pagina, ed e' il modo tipico in cui un refactor la perde."""
    out = _ts(
        "emit([m.tipoSpesaLabel('fb','retail'), m.tipoSpesaLabel('generale','retail'),"
        " m.costoMerceLabel('retail'), m.filtroMerceLabel('retail'), m.attivitaLabel('retail')]);"
    )
    assert all(isinstance(v, str) and v.strip() for v in out)


# ── Il presidio sui CONSUMATORI, non solo sul centro ────────────────────────
# Il centro etichette puo' essere perfetto e un componente continuare a usare la
# costante diretta: sarebbe un negozio con l'etichetta del ristorante, e nessuno
# dei test qui sopra lo direbbe.

def test_nessun_componente_usa_piu_la_costante_diretta():
    """`TIPO_SPESA_LABEL[...]` in un componente e' un'etichetta che il settore
    non puo' piu' cambiare. La costante resta esportata (ha un valore come
    fonte), ma va letta attraverso `tipoSpesaLabel`."""
    from pathlib import Path
    src = Path("apps/web/src")
    colpevoli = [
        f"{p.relative_to(src)}:{i}"
        for p in src.rglob("*.tsx")
        for i, riga in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if "TIPO_SPESA_LABEL[" in riga
    ]
    assert not colpevoli, f"usano la costante invece della funzione: {colpevoli}"


def test_ogni_uso_del_filtro_merce_passa_dal_centro():
    """Stessa ragione per "Food & Beverage" hardcoded nei tab.

    Salta i commenti: la prima stesura contava anche le righe che SPIEGANO
    l'etichetta, e falliva su due commenti miei. Un presidio che legge il
    sorgente deve guardare il codice, o grida su una spiegazione e tace su un
    bug scritto dentro un commento.
    """
    from pathlib import Path
    src = Path("apps/web/src")
    colpevoli = [
        f"{p.relative_to(src)}:{i}"
        for p in src.rglob("*.tsx")
        for i, riga in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if '"Food & Beverage"' in riga and not riga.lstrip().startswith(("//", "*", "/*"))
    ]
    assert not colpevoli, f"etichetta hardcoded invece di filtroMerceLabel: {colpevoli}"
