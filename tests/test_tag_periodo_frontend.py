"""Il controllo «Periodo» del riquadro del tag (lib/tag-periodo.ts).

Fase 3 di «Analisi e Tag» (13/10/2026): i tre chip a mano del periodo sono
diventati un controllo segmentato. La regola nuova e' che «Mese» apre subito il
mese in corso: prima la voce apriva solo il menu dei mesi, e i numeri restavano
quelli dell'anno mentre il controllo diceva «Mese».

Casi scelti dove la versione sbagliata da' un altro risultato:
- l'anno attuale del filtro (2025) e' diverso da quello di oggi (2026): chi
  riusa l'anno attuale invece di quello di oggi sbaglia anno;
- il mese e' `getMonth() + 1`: ottobre deve dare 10, non 9;
- a gennaio l'anno e' quello nuovo (31/12 -> 1/1);
- riscegliere la voce attiva non ricarica (null), e «Personalizzato» conserva
  date e periodo di prima.

Limite dichiarato: si prova la regola, non che il .tsx la colleghi al controllo.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/tag-periodo"
RICHIEDE = ["periodoScelto"]


def _scelto(scelta, attuale, oggi):
    return esegui_ts(
        MODULO,
        """
const [a, mm, g] = input.oggi;
emit(m.periodoScelto(input.scelta, input.attuale, new Date(a, mm - 1, g)) ?? "NESSUNO");
""",
        argomento={"scelta": scelta, "attuale": attuale, "oggi": oggi},
        tz="Europe/Rome",
        richiede=RICHIEDE,
    )


MARZO_2025 = {"anno": 2025, "mese": 3, "preset": "mese_specifico", "dataDa": None, "dataA": None}
ANNO_2025 = {"anno": 2025, "mese": None, "preset": "anno_corrente", "dataDa": None, "dataA": None}


def test_mese_apre_subito_il_mese_in_corso_dell_anno_di_oggi():
    assert _scelto("mese_specifico", ANNO_2025, [2026, 10, 13]) == {
        "anno": 2026, "mese": 10, "preset": "mese_specifico",
    }


def test_mese_a_gennaio_e_dell_anno_nuovo():
    assert _scelto("mese_specifico", ANNO_2025, [2027, 1, 1]) == {
        "anno": 2027, "mese": 1, "preset": "mese_specifico",
    }


def test_anno_in_corso_e_l_anno_di_oggi_senza_mese():
    assert _scelto("anno_corrente", MARZO_2025, [2026, 10, 13]) == {
        "anno": 2026, "mese": None, "preset": "anno_corrente",
    }


@pytest.mark.parametrize("attuale", [ANNO_2025, MARZO_2025], ids=["anno", "mese"])
def test_riscegliere_la_voce_attiva_non_cambia_niente(attuale):
    assert _scelto(attuale["preset"], attuale, [2026, 10, 13]) == "NESSUNO"


def test_personalizzato_conserva_periodo_e_date_gia_scritte():
    attuale = {**MARZO_2025, "dataDa": "2025-02-01", "dataA": "2025-02-28"}
    assert _scelto("personalizzato", attuale, [2026, 10, 13]) == {
        "anno": 2025, "mese": 3, "preset": "personalizzato",
        "dataDa": "2025-02-01", "dataA": "2025-02-28",
    }


def test_personalizzato_senza_date_non_ne_inventa():
    assert _scelto("personalizzato", MARZO_2025, [2026, 10, 13]) == {
        "anno": 2025, "mese": 3, "preset": "personalizzato",
    }
