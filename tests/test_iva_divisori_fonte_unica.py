"""Le aliquote IVA vivono in molti posti: qui si controlla che restino d'accordo.

Il netto scorporato è il **denominatore del MOL**. Un'aliquota cambiata in un
punto solo non solleva niente: sposta i margini di tutto lo storico, e se ne
accorge il cliente.

**La mappa, misurata il 03/09/2026** (`grep -rn "1\\.10\\|1\\.22" --include=*.py`):

    services/fastapi_worker.py     10      services/routers/gruppo.py   5
    services/routers/ricavi.py      6      services/routers/margini.py  4
    services/margine_service.py     4  →   0, migrato alle costanti

Attenzione a come si contano: `grep -c` conta le **righe**, non le occorrenze, e
molte righe ne portano due (`/1.10` e `/1.22` nella stessa espressione). Contate
a righe sembrano 18; contate davvero sono **29**, di cui 4 ora migrate.

Il residuo R7 diceva «4 letterali in `margine_service.py`». Erano **29 in 5
file**: correggerne 2 e chiudere il residuo avrebbe lasciato 25 consumatori
indietro — il difetto «fix parziale» già pagato dal progetto (KPI corretto e
grafici dimenticati nello stesso file, due totali diversi in pagina per mesi).

**Perché la sostituzione si è fermata a `margine_service.py`** (decisione
dell'owner, 03/09): sostituire 18 punti in 5 moduli tocca il MOL su tutto lo
storico e vuole la sua finestra. Questo file è la rete che rende la differenza
**visibile invece che silenziosa**: se qualcuno cambia un'aliquota in un posto
solo — Python o TypeScript — diventa rosso.

Stesso metodo di `test_margini_iva_equivalenza_frontend.py`, che sulla stessa
classe di problema ha scelto la rete e non il refactor di massa.
"""
import pathlib
import re

import pytest

from config.constants import IVA_DIVISORE_10, IVA_DIVISORE_22

_RADICE = pathlib.Path(__file__).resolve().parents[1]
_PERIODI_TS = _RADICE / "apps/web/src/app/(app)/margini/periodi.ts"

# I file che scorporano l'IVA a mano. Il conteggio è esatto e non un `>= 1`:
# se ne compare uno in più è una copia nuova, e va saputo.
_ATTESI = {
    "services/fastapi_worker.py": 10,
    "services/routers/gruppo.py": 5,
    "services/routers/ricavi.py": 6,
    "services/routers/margini.py": 4,
}

# `\s*` e non uno spazio letterale: `/1.10` e `/ 1.10` sono lo stesso letterale,
# e un test che ne conta uno solo diventerebbe rosso per una riformattazione.
_LETTERALE = re.compile(r"/\s*1\.(?:10|22)\b")


def test_le_costanti_valgono_le_aliquote_italiane():
    """Se l'IVA cambia davvero, questo test va aggiornato **insieme** a tutti i
    punti elencati sotto — è il promemoria che non basta cambiarne uno."""
    assert IVA_DIVISORE_10 == 1.10
    assert IVA_DIVISORE_22 == 1.22


def test_python_e_typescript_dichiarano_le_stesse_aliquote():
    """Le due copie sono lontane e nessuno le legge insieme.

    Se divergono, il totale del dialog e quello dei margini non tornano: è
    esattamente il difetto che il cliente ha trovato prima dell'audit (F&B e
    Spese Generali che non quadravano).
    """
    ts = _PERIODI_TS.read_text(encoding="utf-8")
    for nome, atteso in (("IVA_DIVISORE_10", IVA_DIVISORE_10),
                         ("IVA_DIVISORE_22", IVA_DIVISORE_22)):
        m = re.search(rf"export const {nome} = ([0-9.]+);", ts)
        assert m, f"{nome} non è più dichiarata in periodi.ts"
        assert float(m.group(1)) == atteso, (
            f"{nome} vale {m.group(1)} in TypeScript e {atteso} in Python: il "
            "netto calcolato dal frontend e quello del worker non coincidono più"
        )


def test_margine_service_non_ha_piu_letterali():
    """Il perimetro migrato. Se ricompaiono, la migrazione è stata annullata."""
    testo = (_RADICE / "services/margine_service.py").read_text(encoding="utf-8")
    trovati = _LETTERALE.findall(testo)
    assert trovati == [], (
        f"margine_service.py è tornato a hardcodare le aliquote ({trovati}): "
        "usa IVA_DIVISORE_10 / IVA_DIVISORE_22 da config.constants"
    )
    assert "IVA_DIVISORE_10" in testo and "IVA_DIVISORE_22" in testo


def test_margine_service_usa_davvero_le_costanti_nel_calcolo():
    """Importarle e non usarle sarebbe un test verde su un fix che non c'è.

    Cerca le costanti **nelle due righe di calcolo**, non solo nell'import.
    """
    testo = (_RADICE / "services/margine_service.py").read_text(encoding="utf-8")
    righe = [r for r in testo.splitlines() if "fatt_netto =" in r]
    assert len(righe) == 2, f"le righe di calcolo del netto sono {len(righe)}, attese 2"
    for r in righe:
        assert "IVA_DIVISORE_10" in r and "IVA_DIVISORE_22" in r, (
            f"una riga di calcolo non usa le costanti: {r.strip()}"
        )


@pytest.mark.parametrize("percorso,atteso", sorted(_ATTESI.items()))
def test_fotografa_i_letterali_rimasti(percorso, atteso):
    """FOTOGRAFIA del perimetro **non** migrato, dichiarato e non taciuto.

    Rosso se **diminuiscono**: qualcuno sta migrando — bene, aggiorna il numero.
    Rosso se **aumentano**: è una copia nuova, e va fermata prima che si
    moltiplichi (da 4 a 18 è successo così).
    """
    testo = (_RADICE / percorso).read_text(encoding="utf-8")
    trovati = _LETTERALE.findall(testo)
    assert len(trovati) == atteso, (
        f"attesi {atteso} letterali IVA in {percorso}, trovati {len(trovati)}. "
        "Se sono diminuiti qualcuno sta migrando alle costanti (aggiorna questo "
        "test); se sono aumentati è una copia nuova da fermare."
    )


def test_il_totale_dei_letterali_rimasti_e_dichiarato():
    """Il numero che va nel verbale: 25 occorrenze ancora da migrare."""
    totale = sum(
        len(_LETTERALE.findall((_RADICE / p).read_text(encoding="utf-8")))
        for p in _ATTESI
    )
    assert totale == 25, (
        f"i letterali IVA ancora sparsi nel backend sono {totale}, non 25: la "
        "mappa nel docstring di questo file non è più vera, ri-misurala"
    )
