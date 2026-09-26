"""La ricerca apre le sezioni solo quando filtra, e svuotata le riporta com'erano.

Due difetti segnalati dalla review del 26/09/2026 sulla ricerca di Gestione
Fatture (`baf6a03`, `8857560`):

- `normalizzaRicerca` toglie le parole «n», «doc», «fattura» (prefissi dei
  numeri di documento): digitare «n» come prima lettera dava una query vuota,
  che non filtrava niente, ma `ricerca.trim() !== ""` apriva comunque tutte le
  sezioni — fino a ~1.700 righe stese in vista catena;
- le sezioni aperte dalla ricerca restavano aperte dopo averla svuotata, e
  «Scadute» (chiusa di default: 414 righe su una sede reale) restava stesa.

La decisione vive in `ricercaAttiva` e `aperturaSezione` (lib/scadenziario.ts),
eseguite qui. La seconda parte controlla che la pagina le usi: i mutanti della
review (useEffect svuotato, `forzaAperta` tolto dall'Archivio, riga di
`sharedProps` cambiata) restavano verdi perche' nessun test guardava li'.
"""
import re
from pathlib import Path

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"
CLIENT = (
    Path(__file__).resolve().parents[1]
    / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
)


# ── 1. Le decisioni, eseguite ────────────────────────────────────────────────

def test_la_ricerca_e_attiva_solo_se_filtra():
    testi = ["", "   ", "n", "N.", "doc", "fattura", "n 4521", "Metro", "1.250,00", "fatt. 12"]
    esito = esegui_ts(
        MODULO,
        "emit(input.map(t => [t, m.ricercaAttiva(t), m.normalizzaRicerca(t)]));",
        argomento=testi,
        richiede=["ricercaAttiva", "normalizzaRicerca"],
    )
    attive = {t: a for t, a, _ in esito}
    assert attive == {
        "": False, "   ": False, "n": False, "N.": False, "doc": False, "fattura": False,
        "n 4521": True, "Metro": True, "1.250,00": True, "fatt. 12": True,
    }
    # Stessa base del filtro: attiva se e solo se la query normalizzata non e' vuota.
    for t, attiva, normalizzata in esito:
        assert attiva == (normalizzata != ""), t


def _sequenza(iniziale_open, passi):
    """Applica in ordine: True/False = forzaAperta, "clic" = chevron."""
    return esegui_ts(
        MODULO,
        "let s = { open: input.open, primaDellaRicerca: null };"
        "const visti = [];"
        "for (const p of input.passi) {"
        "  s = p === 'clic' ? { ...s, open: !s.open } : m.aperturaSezione(s, p);"
        "  visti.push(s.open);"
        "}"
        "emit(visti);",
        argomento={"open": iniziale_open, "passi": passi},
        richiede=["aperturaSezione"],
    )


def test_la_ricerca_apre_una_sezione_chiusa_e_svuotata_la_richiude():
    """Il caso di «Scadute»: chiusa di default, la ricerca la apre, poi torna chiusa."""
    assert _sequenza(False, [False, True, True, False]) == [False, True, True, False]


def test_una_sezione_gia_aperta_resta_aperta():
    assert _sequenza(True, [True, False]) == [True, True]


def test_durante_la_ricerca_il_chevron_resta_di_chi_guarda():
    """Chiusa a mano durante la ricerca: resta chiusa finche' la ricerca dura
    (niente `open || forzaAperta`), e a ricerca finita torna com'era prima."""
    assert _sequenza(False, [True, "clic", True, False]) == [True, False, False, False]
    assert _sequenza(True, [True, "clic", False]) == [True, False, True]


def test_senza_ricerca_il_chevron_funziona_e_nulla_si_ricorda():
    assert _sequenza(False, ["clic", False, "clic", False]) == [True, True, False, False]


# ── 2. Il cablaggio della pagina ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def sorgente() -> str:
    assert CLIENT.exists(), f"{CLIENT} non esiste: se e' stato rinominato aggiorna il test"
    return CLIENT.read_text(encoding="utf-8")


def _normalizza(testo: str) -> str:
    return re.sub(r"\s+", " ", testo).strip()


def _agenda_section(src: str) -> str:
    i = src.index("function AgendaSection(")
    return _normalizza(src[i:src.index("return (", i)])


def test_la_sezione_usa_aperturaSezione(sorgente: str):
    corpo = _agenda_section(sorgente)
    assert (
        "const [apertura, setApertura] = useState<AperturaSezione>({ open: defaultOpen, primaDellaRicerca: null });"
        in corpo
    )
    assert "const open = apertura.open;" in corpo
    assert "useEffect(() => { setApertura(s => aperturaSezione(s, forzaAperta)); }, [forzaAperta]);" in corpo, (
        "la ricerca non apre piu' le sezioni, o non le riporta com'erano"
    )
    i = sorgente.index("function AgendaSection(")
    sezione = _normalizza(sorgente[i:sorgente.index("function ", i + 30)])
    assert "onClick={() => setApertura(s => ({ ...s, open: !s.open }))}" in sezione, (
        "il chevron non cambia piu' lo stato di apertura"
    )


def test_la_ricerca_apre_le_sezioni_solo_se_filtra(sorgente: str):
    testo = _normalizza(sorgente)
    i = testo.index("const sharedProps = {")
    shared = testo[i:testo.index("};", i)]
    assert "forzaAperta: ricercaAttiva(ricerca)," in shared, (
        f"le sezioni di «Da pagare» non si aprono piu' con la ricerca, o si aprono anche con «n»: {shared}"
    )

    j = testo.index('view === "lista_mensile" ? (')
    archivio = testo[j:testo.index("/>", testo.index("<AgendaSection", j))]
    assert "forzaAperta={ricercaAttiva(ricerca)}" in archivio, (
        f"in Archivio i mesi non si aprono piu' con la ricerca: {archivio}"
    )
    assert 'ricerca.trim() !== ""' not in shared + archivio
