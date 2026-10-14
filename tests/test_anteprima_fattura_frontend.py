"""L'anteprima della fattura dagli acquisti di Analisi Fatture → Articoli
(`lib/anteprima-fattura.ts`), come gia' in Variazioni prezzi. Richiesta di Mattia
del 12/10/2026."""
import pytest

from tests.helpers_ts import esegui_ts


@pytest.mark.parametrize("riga, attesa", [
    ({"id": 7, "file_origine": "IT01_a.xml"}, True),
    ({"id": 7, "file_origine": "IT01_a.xml", "ripartita_su_gruppo": True}, False),
    ({"id": -3, "file_origine": "IT01_a.xml"}, False),
    ({"id": 7, "file_origine": ""}, False),
    ({"id": 7, "file_origine": None}, False),
])
def test_quali_acquisti_di_articoli_aprono_la_fattura(riga, attesa):
    """Una quota ripartita dal gruppo porta la fattura della capofila:
    l'anteprima la cercherebbe sulla sede di sessione e si aprirebbe vuota."""
    assert esegui_ts("lib/anteprima-fattura", "emit(m.rigaApribile(input))", argomento=riga, richiede=("rigaApribile",)) is attesa


def test_articoli_apre_l_anteprima_solo_sulle_righe_apribili():
    from pathlib import Path

    sorgente = (Path(__file__).resolve().parents[1] / "apps/web/src/app/(app)/analisi-fatture/articoli-tab.tsx").read_text(encoding="utf-8")
    assert "const apribile = rigaApribile(r);" in sorgente
    assert "onClick={apribile ? () => setAnteprima(r) : undefined}" in sorgente
    assert "fileOrigine={anteprima?.file_origine ?? null}" in sorgente
