"""Piani abbonamento lato client (`lib/piani.ts`) — una sola fonte per cliente e admin.

Perche' esiste: le mappe dei piani erano DUE e divergenti. `impostazioni/
account-client.tsx` conosceva solo base/plus/pro in Title Case; `lib/admin.ts`
free/base/plus/pro in MAIUSCOLO. Il backend conosce "free"
(`config/constants.py::PIANO_LIMITI_FATTURE_MESE`) e il menu admin lo OFFRE
(`PIANO_OPTIONS`): assegnarlo a una sede faceva mostrare al cliente la stringa
grezza minuscola "free", senza prezzo, perche' il fallback rende la chiave
com'e'. Misurato il 2/9/2026: nessun cliente lo vedeva ancora — due utenti hanno
`users.piano='free'` ma la sede risolta li porta entrambi su "base". Difetto
latente a un click, non un incidente in corso.

Il test che conta e' `test_chiavi_allineate_al_backend`: e' l'unico che impedisce
al difetto di ripetersi quando il backend aggiungera' un piano.
"""

import re
from pathlib import Path

from tests.helpers_ts import esegui_ts

MODULO = "lib/piani"
FUNZIONI = ["etichettaPiano", "etichettaPianoAdmin", "prezzoPiano"]


def _chiama(funzione, argomento):
    return esegui_ts(
        MODULO,
        f"emit(m.{funzione}(input));",
        argomento=argomento,
        richiede=FUNZIONI,
    )


def _piani():
    return esegui_ts(MODULO, "emit(m.PIANI);", richiede=FUNZIONI)


# ─── il difetto: "free" non era conosciuto dal frontend ──────────────────────

def test_free_ha_una_etichetta_leggibile():
    """La regressione originale: il badge mostrava la chiave grezza minuscola."""
    assert _chiama("etichettaPiano", "free") == "Free"


def test_free_ha_una_dicitura_al_posto_del_prezzo():
    """Deciso dall'owner: non una cifra, ma il perche' la cifra non c'e'.
    Il componente nasconde il prezzo se vuoto, quindi "" lascerebbe il badge nudo."""
    assert _chiama("prezzoPiano", "free") == "Piano di prova"


# ─── contratto del fallback (comportamento attuale, congelato) ───────────────

def test_piano_sconosciuto_torna_la_stringa_in_ingresso():
    """Era il comportamento del vecchio `?? data.piano` e resta: meglio una
    chiave grezza di un badge vuoto, se un giorno il backend ne inventa uno."""
    assert _chiama("etichettaPiano", "enterprise") == "enterprise"
    assert _chiama("prezzoPiano", "enterprise") == ""


def test_valori_assenti_non_esplodono():
    """`data.piano` e' tipato string ma arriva da JSON non validato."""
    for vuoto in (None, ""):
        assert _chiama("etichettaPiano", vuoto) == ""
        assert _chiama("prezzoPiano", vuoto) == ""


# ─── normalizzazione: la difesa vera ─────────────────────────────────────────

def test_maiuscole_e_spazi_non_mancano_il_match():
    """`admin.ts` legge `sede.piano` dal DB senza normalizzare: con la vecchia
    mappa "Base" cadeva nel fallback e mostrava la chiave grezza."""
    for variante in ("BASE", " base ", "Base", "bAsE"):
        assert _chiama("etichettaPiano", variante) == "Base"


# ─── coerenza fra le due rese e col backend ──────────────────────────────────

def test_resa_admin_invariata_chiave_per_chiave():
    """Non "sono maiuscole": i valori esatti di prima del refactor. E' il punto
    dove una regressione visiva sull'area admin passerebbe muta."""
    attese = {"free": "FREE", "base": "BASE", "plus": "PLUS", "pro": "PRO"}
    for chiave, atteso in attese.items():
        assert _chiama("etichettaPianoAdmin", chiave) == atteso


def test_ogni_piano_ha_label_e_prezzo_non_vuoti():
    for chiave, piano in _piani().items():
        assert piano["label"], f"{chiave} senza label cliente"
        assert piano["labelAdmin"], f"{chiave} senza label admin"
        assert piano["prezzo"], f"{chiave} senza prezzo o dicitura"


def test_chiavi_allineate_al_backend():
    """Il test che impedisce il ripetersi del difetto.

    Se il backend aggiunge un piano che il frontend non conosce, qui fallisce in
    CI invece di mostrarlo grezzo al cliente mesi dopo.
    """
    sorgente = Path(__file__).resolve().parents[1] / "config/constants.py"
    riga = re.search(
        r"^PIANO_LIMITI_FATTURE_MESE\s*=\s*\{(.+?)\}", sorgente.read_text(encoding="utf-8"), re.M | re.S
    )
    assert riga, "PIANO_LIMITI_FATTURE_MESE non trovata: rinominata? aggiorna il test"
    backend = dict(re.findall(r'"(\w+)"\s*:\s*(\d+)', riga.group(1)))
    assert backend, "nessun piano estratto da constants.py: formato cambiato"

    piani = _piani()
    assert set(piani) == set(backend), (
        "piani noti al backend e al frontend divergenti — e' esattamente la "
        f"regressione del badge 'free'. backend={sorted(backend)} frontend={sorted(piani)}"
    )
    for chiave, limite in backend.items():
        assert piani[chiave]["limiteFatture"] == int(limite), (
            f"limite fatture di '{chiave}' diverso fra backend e frontend"
        )
