"""La tavolozza emoji condivisa dai due selettori di tag.

`EMOJI_TAG` (apps/web/src/lib/tag.ts) e' nata il 23/09/2026 unificando due copie
scritte a mano, identiche byte per byte, in `analisi-e-tag-client.tsx` e in
`catena/gruppo-tag-section.tsx`. Il commit che l'ha estratta la dichiarava
«raggiungibile da un test» — e non lo era: svuotandola a `[]` entrambi i
selettori sparivano dalla UI e la suite restava verde (rilievo della review
dello stesso giorno).

Qui si prova cio' che un cliente vedrebbe: che la tavolozza esista, che sia la
stessa per i due selettori, e che le emoji siano tali.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers_ts import esegui_ts  # noqa: E402

MODULO = "lib/tag"

# La tavolozza storica, ANCORATA QUI e non riletta dal sorgente: un atteso che
# legge la stessa costante dell'ottenuto si muove insieme a lei e non prova
# nulla. Se un giorno cambia davvero, questo test va aggiornato apposta.
TAVOLOZZA_ATTESA = [
    "🐟", "🍗", "🥩", "🐄", "🦐", "🍕", "🍝", "🥗", "🧀", "🥚", "🧈", "🥛",
    "🍞", "🌾", "🫒", "🍷", "🍺", "☕", "🧃", "🌿", "🍋", "🧅", "🥦", "🍅",
    "🧄", "🥕", "🌶️", "🍄",
]


def _tavolozza():
    return esegui_ts(MODULO, "emit(m.EMOJI_TAG);")


def test_la_tavolozza_e_quella_attesa():
    """Uccide il mutante «EMOJI_TAG = []»: i selettori resterebbero vuoti."""
    assert _tavolozza() == TAVOLOZZA_ATTESA


def test_la_tavolozza_non_e_vuota_e_non_ha_doppioni():
    tav = _tavolozza()
    assert len(tav) == 28
    assert len(set(tav)) == len(tav), "un doppione occupa un posto senza aggiungere scelta"


def test_ogni_voce_e_una_sola_emoji_non_una_stringa_vuota():
    """Una voce vuota renderebbe un bottone invisibile ma cliccabile."""
    for em in _tavolozza():
        assert em.strip() == em and em != "", f"voce non valida: {em!r}"
        assert not em.isascii(), f"{em!r} non e' un'emoji"


def test_i_due_selettori_usano_la_STESSA_tavolozza():
    """La ragione per cui la costante esiste.

    Il presidio guarda i due `.tsx` perche' e' li' che la duplicazione puo'
    tornare: un selettore che ridichiara la lista inline si ri-sgancia in
    silenzio, e i due selettori divergono senza che nulla fallisca.
    """
    web = Path(__file__).resolve().parents[1] / "apps/web/src"
    consumatori = [
        web / "app/(app)/analisi-e-tag/analisi-e-tag-client.tsx",
        web / "app/(app)/catena/gruppo-tag-section.tsx",
    ]
    for f in consumatori:
        assert f.exists(), f"{f} spostato: aggiorna il test invece di cancellarlo"
        testo = f.read_text(encoding="utf-8")
        assert "EMOJI_TAG" in testo, f"{f.name} non usa piu' la tavolozza condivisa"
        # La prima emoji della lista scritta a mano: se ricompare come letterale
        # di un array, qualcuno ha reintrodotto una copia locale.
        assert '["🐟"' not in testo.replace(" ", ""), (
            f"{f.name} ridichiara la tavolozza inline invece di importarla"
        )
