"""«Segna pagate» in blocco si puo' annullare in blocco, e chiede conferma.

Fino al 25/09/2026 la barra di selezione multipla aveva una sola azione e il
client scriveva `pagata: true` **fisso**, mentre l'endpoint accettava gia'
`body.pagata` (services/routers/scadenziario.py:91, `pagata: bool = True`).
Conseguenza operativa: segnare 50 fatture pagate per sbaglio costava ~150 clic
per tornare indietro, una fattura per volta dal dialog di dettaglio. E l'azione
di massa partiva **senza conferma**, in una pagina dove «Seleziona tutte» puo'
valere 1.089 fatture.

**Perche' questo presidio guarda il sorgente del .tsx e cosa vale davvero.**
`scadenziario-client.tsx` e' React: `tests/helpers_ts.py` non lo esegue (solo
moduli puri sotto `lib/`). Un assert sul testo del sorgente, da solo, sarebbe
debole — CLAUDE.md lo dice e la memoria del progetto pure. Per questo il
presidio e' in due pezzi che si coprono a vicenda:

1. la parte FORTE, che esegue davvero: `segna_fattura_pagata(pagata=False)`
   deve azzerare `pagata_at`. E' il comportamento su cui poggia lo storno: se
   il backend non lo facesse, il pulsante nuovo mentirebbe.
2. la parte di CABLAGGIO, sul sorgente: verifica che il client non torni a
   scrivere `pagata: true` fisso e che l'azione passi da una conferma. Non
   prova il comportamento, prova che il collegamento esista — ed e' la classe
   di regressione realmente accaduta qui (un fix server con il client
   indietro).
"""
import re
from pathlib import Path

import pytest

CLIENT = (
    Path(__file__).resolve().parents[1]
    / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
)


@pytest.fixture(scope="module")
def sorgente() -> str:
    assert CLIENT.exists(), f"{CLIENT} non esiste: se e' stato rinominato aggiorna il test"
    return CLIENT.read_text(encoding="utf-8")


# ── 1. Il comportamento vero, eseguito ───────────────────────────────────────

def test_storno_azzera_la_data_di_pagamento():
    """`pagata=False` deve togliere anche `pagata_at`.

    Senza questo, una fattura stornata resterebbe con la sua data di pagamento
    e il KPI "Pagate (mese)" continuerebbe a contarla.
    """
    from services.documenti_service import segna_fattura_pagata

    catturato = {}

    class _Q:
        def update(self, payload):
            catturato["payload"] = payload
            return self

        def eq(self, *_a, **_k):
            return self

        def is_(self, *_a, **_k):
            return self

        def not_(self, *_a, **_k):
            return self

        def execute(self):
            return type("R", (), {"data": [{"file_origine": "f.xml"}]})()

    class _SB:
        def table(self, _nome):
            return _Q()

    res = segna_fattura_pagata(
        file_origine="f.xml",
        user_id="u",
        ristorante_id="r",
        pagata=False,
        supabase_client=_SB(),
    )

    assert res.get("success") is True
    assert catturato["payload"]["pagata"] is False
    assert catturato["payload"]["pagata_at"] is None, (
        "storno senza azzerare pagata_at: la fattura resterebbe contata fra le "
        "pagate del mese"
    )


def test_segnare_pagata_scrive_la_data():
    """Il verso opposto, per non far passare un `pagata_at = None` sempre."""
    from services.documenti_service import segna_fattura_pagata

    catturato = {}

    class _Q:
        def update(self, payload):
            catturato["payload"] = payload
            return self

        def eq(self, *_a, **_k):
            return self

        def is_(self, *_a, **_k):
            return self

        def not_(self, *_a, **_k):
            return self

        def execute(self):
            return type("R", (), {"data": [{"file_origine": "f.xml"}]})()

    class _SB:
        def table(self, _nome):
            return _Q()

    segna_fattura_pagata(
        file_origine="f.xml", user_id="u", ristorante_id="r",
        pagata=True, supabase_client=_SB(),
    )
    assert catturato["payload"]["pagata"] is True
    assert catturato["payload"]["pagata_at"] is not None


# ── 2. Il cablaggio del client ───────────────────────────────────────────────

def test_il_client_non_scrive_piu_pagata_true_fisso(sorgente: str):
    """La chiamata di massa manda il verso scelto, non una costante.

    E' la riga che rendeva impossibile lo storno in blocco.
    """
    assert "pagata: true, ristorante_id" not in sorgente, (
        "il bulk e' tornato a scrivere `pagata: true` fisso: lo storno in blocco "
        "non funziona piu'"
    )
    assert re.search(r"file_origini,\s*pagata,\s*ristorante_id", sorgente), (
        "la chiamata di massa non passa piu' la variabile `pagata`"
    )


def test_handle_bulk_paga_prende_il_verso_come_parametro(sorgente: str):
    assert re.search(r"async function handleBulkPaga\(\s*pagata:\s*boolean\s*\)", sorgente), (
        "handleBulkPaga non accetta piu' il verso dell'operazione"
    )


def test_esiste_l_azione_di_storno_in_blocco(sorgente: str):
    assert "Segna non pagate" in sorgente, (
        "sparita l'azione di storno in blocco dalla barra di selezione"
    )


def test_l_azione_di_massa_passa_da_una_conferma(sorgente: str):
    """Entrambe le azioni aprono la conferma invece di partire subito.

    `ConfirmDialog` e' lo stesso componente usato da altre 11 pagine: questa
    era l'unica con un'azione di massa irreversibile senza conferma.
    """
    assert "ConfirmDialog" in sorgente, "ConfirmDialog non e' piu' montato"
    assert "setConfermaBulk(true)" in sorgente and "setConfermaBulk(false)" in sorgente, (
        "le azioni di massa non passano piu' dalla conferma"
    )
    # Il bottone non deve chiamare direttamente l'handler: sarebbe la conferma scavalcata.
    assert "onClick={handleBulkPaga}" not in sorgente, (
        "il bottone chiama handleBulkPaga direttamente: la conferma e' scavalcata"
    )
