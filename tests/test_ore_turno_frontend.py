"""Le ore extra sono un sottoinsieme del turno, anche nelle somme del frontend.

**Il difetto, misurato il 5/9/2026.** Il modello e' stato invertito quel giorno:
le extra erano additive (09-17 con 2 extra = 10 ore), ora sono comprese nel
turno (= 8 ore di cui 2 di straordinario). Il clamp `min(extra, ore)` era stato
messo nel worker, in `margini.py`, in `workspace.py`, nel costo del singolo
turno e su /m — ma **non** nell'aggregazione per persona del tab Personale
desktop, che e' proprio la card dei totali che il cliente guarda.

Misurato eseguendo le due versioni: un turno da 8 ore con `ore_extra = 10`
(errore di battitura plausibile) mostrava **10 ore e 100 €** invece di 8 e 80 —
il **25% in piu'** sul monte ore e sul costo, in silenzio.

E' la terza volta che lo stesso fix parziale lascia indietro un consumatore: il
04/09 erano l'export Excel e /m, trovati dal code-reviewer. Per questo la regola
ora vive in un solo modulo (`lib/ore-turno.ts`) che desktop e mobile importano,
invece che in cinque copie di `Math.min`.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/ore-turno"
RICHIEDE = ["ripartisciOre"]


def _ripartisci(ore, extra):
    return esegui_ts(
        MODULO,
        "emit(m.ripartisciOre(input.ore, input.extra))",
        {"ore": ore, "extra": extra},
        richiede=RICHIEDE,
    )


def test_le_extra_sono_comprese_nel_turno_non_aggiunte():
    """Il caso nominale: 09-17 con 2 extra = 8 ore, di cui 2 di straordinario."""
    r = _ripartisci(8.0, 2.0)
    assert r["ordinarie"] == 6.0
    assert r["extra"] == 2.0
    assert r["ordinarie"] + r["extra"] == 8.0, "il totale deve restare le ore del turno"


def test_extra_oltre_le_ore_non_gonfia_il_monte_ore():
    """Il difetto misurato: 8 ore con 10 extra davano 10 ore, non 8."""
    r = _ripartisci(8.0, 10.0)
    assert r["extra"] == 8.0, "lo straordinario non puo' eccedere le ore lavorate"
    assert r["ordinarie"] == 0.0, "l'ordinario non deve mai andare negativo"
    assert r["ordinarie"] + r["extra"] == 8.0


def test_extra_pari_alle_ore_azzera_l_ordinario_senza_negativi():
    r = _ripartisci(6.0, 6.0)
    assert r["ordinarie"] == 0.0
    assert r["extra"] == 6.0


def test_senza_extra_tutto_e_ordinario():
    for assente in (None, 0):
        r = _ripartisci(7.5, assente)
        assert r["ordinarie"] == 7.5, f"con extra={assente!r}"
        assert r["extra"] == 0


def test_valori_negativi_non_producono_ore_negative():
    """Un dato sporco a DB non deve diventare un monte ore negativo."""
    r = _ripartisci(8.0, -3.0)
    assert r["extra"] == 0
    assert r["ordinarie"] == 8.0

    r = _ripartisci(-2.0, 1.0)
    assert r["ordinarie"] == 0
    assert r["extra"] == 0


def test_i_decimali_non_si_accumulano():
    """Senza arrotondamento 8.7 - 0.3 vale 8.399999999999999 in floating point.

    Non e' pedanteria: quel valore risale fino al monte ore mostrato in card.
    Il caso va scelto misurando (`node -e`), non a intuito: 7.7 - 0.3 fa 7.4
    esatto e passerebbe anche senza arrotondamento.
    """
    r = _ripartisci(8.7, 0.3)
    assert r["ordinarie"] == 8.4, r["ordinarie"]
