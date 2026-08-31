"""Le aliquote IVA sono scritte in due posti: qui si controlla che coincidano.

`scorporoNetto` (in `margini/periodi.ts`) e' il punto unico dichiarato per lo
scorporo — il commento sopra le costanti dice "tenuto qui in un solo punto per
evitare divergenze tra UI e worker". **Non e' vero**: `carica-ricavi-dialog.tsx`
hardcoda `/ 1.10` e `/ 1.22` in 4 punti (righe 451, 452, 477, 478) invece di
chiamarla.

Il delta economico oggi e' **zero**: i valori coincidono. Per questo non e' stata
fatta la sostituzione (decisione dell'audit del 31/8/2026, fase F) — un fix
tocca un dialog di scrittura sui ricavi veri, il test e' una rete piu' larga:
intercetta anche la divergenza **futura**, cioe' il caso in cui qualcuno cambi
un'aliquota in un posto solo. E' quello lo scenario che costa: l'utente vedrebbe
un totale nel riepilogo del dialog e un altro nella tabella dei margini.
"""
import pathlib
import re

import pytest

from tests.helpers_ts import esegui_ts

_MODULO = "app/(app)/margini/periodi"
_DIALOG = (
    pathlib.Path(__file__).resolve().parents[1]
    / "apps/web/src/app/(app)/margini/carica-ricavi-dialog.tsx"
)


def test_le_costanti_valgono_le_aliquote_italiane():
    """Se un giorno l'IVA cambia, questo test va aggiornato **insieme** al
    worker: lo scorporo lato Python usa gli stessi divisori."""
    got = esegui_ts(
        _MODULO,
        "emit({ d10: m.IVA_DIVISORE_10, d22: m.IVA_DIVISORE_22 });",
        richiede=["scorporoNetto"],
    )
    assert got["d10"] == 1.10
    assert got["d22"] == 1.22


def test_scorporo_e_equivalente_alla_formula_espansa():
    """Bit per bit, non "a meno di un epsilon": e' la stessa espressione.

    Un `toFixed(2)` o un arrotondamento intermedio dentro `scorporoNetto`
    romperebbe questo test — ed e' giusto che lo rompa, perche' introdurrebbe
    una differenza fra il totale del dialog e quello dei margini.
    """
    got = esegui_ts(
        _MODULO,
        """
        const casi = [
          [0, 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100],
          [1234.56, 7890.12, 345.67], [0.01, 0.01, 0.01],
          [-500, 250, 0], [73322.73, 0, 0],
        ];
        emit(casi.map(([a, b, c]) => ({
          fn: m.scorporoNetto(a, b, c),
          espansa: a / 1.10 + b / 1.22 + c,
        })));
        """,
        richiede=["scorporoNetto"],
    )
    for caso in got:
        assert caso["fn"] == caso["espansa"]


def test_il_dialog_hardcoda_ancora_le_aliquote():
    """FOTOGRAFIA. Se questo test diventa rosso, il dialog e' stato migrato a
    `scorporoNetto`: e' un miglioramento — cancella questo test e togli la
    riga corrispondente dalla coda nel verbale.

    Il conteggio e' esatto (4) e non un `>= 1`: se ne comparisse un quinto,
    e' una copia nuova, e va saputo.
    """
    testo = _DIALOG.read_text(encoding="utf-8")
    letterali = re.findall(r"/ 1\.(?:10|22)\b", testo)
    assert len(letterali) == 4, (
        f"attesi 4 letterali IVA hardcoded in carica-ricavi-dialog.tsx, "
        f"trovati {len(letterali)}. Se sono diminuiti qualcuno sta migrando a "
        "scorporoNetto (bene, aggiorna il test); se sono aumentati e' una copia "
        "nuova da fermare."
    )


@pytest.mark.parametrize("iva10,iva22,altri", [
    (110.0, 122.0, 50.0),
    (0.0, 0.0, 0.0),
    (1100.0, 0.0, 0.0),
])
def test_dialog_e_scorporo_danno_lo_stesso_netto(iva10, iva22, altri):
    """Il calcolo del dialog, riprodotto letteralmente, deve dare lo stesso
    numero di `scorporoNetto`. E' il test che si rompe il giorno in cui una
    delle due parti cambia aliquota senza l'altra."""
    got = esegui_ts(
        _MODULO,
        """
        const [a, b, c] = input;
        // Copia letterale di carica-ricavi-dialog.tsx:451-452 + altri.
        const comeIlDialog = a / 1.10 + b / 1.22 + c;
        emit({ dialog: comeIlDialog, centrale: m.scorporoNetto(a, b, c) });
        """,
        argomento=[iva10, iva22, altri],
        richiede=["scorporoNetto"],
    )
    assert got["dialog"] == got["centrale"]
