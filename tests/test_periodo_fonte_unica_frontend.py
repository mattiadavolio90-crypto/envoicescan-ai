"""Gli intervalli di date dei filtri periodo: una sola matematica.

Il 22/09/2026 la stessa funzione viveva in CINQUE copie — `isoDateRange` in
prezzi/nc-tab, prezzi/sconti-tab, prezzi/score-tab, prezzi/variazioni-tab e
`isoRange` in analisi-e-tag, che aveva le chiavi diverse (`{da, a}` invece di
`{data_da, data_a}`) ed e' la ragione per cui cercando un nome solo non si
trovavano tutte.

Due difetti che le copie avevano:
 - il giorno finale non era zero-paddato (`2026-02-9`). Non capita, perche'
   nessun mese finisce prima del 28, ma era una trappola in attesa;
 - «tutto l'anno» finiva al 31 DICEMBRE, cioe' nel futuro: in Osservatorio si
   leggeva «01/01/26 → 31/12/26» mentre Margini diceva «→ oggi». Misurato a DB
   il 22/09: zero righe con `data_documento` futura in tutto il parco, quindi
   nessun numero cambia — cambia solo cio' che la pagina dichiara.

**Perche' due implementazioni e non una.** `lib/catena-confronti.ts` tiene la
propria `intervalloMese`: `tests/helpers_ts.py` esegue quel modulo con node, che
non risolve un import relativo senza estensione, e un re-export lo rompe
(provato: 12 test rossi con ERR_MODULE_NOT_FOUND). L'ultimo test di questo file
e' la rete che impedisce alle due di divergere.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/periodo"


def _periodo(anno, mese, oggi_iso="2026-09-22"):
    return esegui_ts(
        MODULO,
        f"emit(m.intervalloPeriodo(input.anno, input.mese, new Date('{oggi_iso}T12:00:00')));",
        argomento={"anno": anno, "mese": mese},
        richiede=["intervalloPeriodo"],
    )


def _mese(anno, mese):
    return esegui_ts(
        MODULO,
        "emit(m.intervalloMese(input.anno, input.mese));",
        argomento={"anno": anno, "mese": mese},
        richiede=["intervalloMese"],
    )


class TestIntervalloMese:
    def test_mese_normale(self):
        assert _mese(2026, 3) == {"data_da": "2026-03-01", "data_a": "2026-03-31"}

    def test_febbraio(self):
        assert _mese(2026, 2) == {"data_da": "2026-02-01", "data_a": "2026-02-28"}

    def test_febbraio_bisestile(self):
        assert _mese(2024, 2) == {"data_da": "2024-02-01", "data_a": "2024-02-29"}

    def test_il_mese_e_sempre_a_due_cifre(self):
        assert _mese(2026, 1)["data_da"] == "2026-01-01"

    def test_anche_il_giorno_finale_e_a_due_cifre(self):
        """Le copie scrivevano `${anno}-${mm}-${lastDay}` senza padding.

        Con i mesi veri non si vede: nessuno finisce prima del 28, quindi
        togliendo il `padStart` questo test resta verde — provato per
        mutazione, ed e' il motivo del test qui sotto. Resta perche' fotografa
        il contratto (10 caratteri, sempre), non perche' protegga.
        """
        for m in range(1, 13):
            assert len(_mese(2026, m)["data_a"]) == 10, m

    def test_il_padding_del_giorno_c_e_davvero(self):
        """La prova che il test sopra non puo' dare: si guarda il SORGENTE.

        Il mutante «togli `padStart` dal giorno» sopravvive a qualunque test
        che chiami la funzione con mesi reali. L'unico modo di presidiarlo e'
        verificare che la formattazione ci sia — il difetto non e' raggiungibile
        dai dati, ma una riscrittura futura potrebbe renderlo tale (un mese
        parziale, un range che finisce a meta').
        """
        from pathlib import Path
        sorgente = (Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
                    / "lib" / "periodo.ts").read_text(encoding="utf-8")
        assert 'String(ultimo).padStart(2, "0")' in sorgente, (
            "il giorno finale non e' piu' zero-paddato: `2026-02-9` non e' una "
            "data ISO valida e il backend la rifiuterebbe"
        )


class TestIntervalloPeriodo:
    def test_il_mese_delega_a_intervallo_mese(self):
        assert _periodo(2026, 4) == _mese(2026, 4)

    def test_l_anno_in_corso_finisce_oggi(self):
        """Era il difetto visibile: «Anno in corso» dichiarava un periodo che
        comprende i mesi non ancora accaduti."""
        assert _periodo(2026, None) == {"data_da": "2026-01-01", "data_a": "2026-09-22"}

    def test_un_anno_passato_resta_intero(self):
        assert _periodo(2025, None) == {"data_da": "2025-01-01", "data_a": "2025-12-31"}

    def test_l_ultimo_giorno_dell_anno(self):
        """Il 31 dicembre l'anno in corso coincide con l'anno intero: il
        troncamento a oggi non deve accorciarlo."""
        assert _periodo(2026, None, "2026-12-31") == {
            "data_da": "2026-01-01", "data_a": "2026-12-31",
        }

    def test_il_primo_gennaio(self):
        assert _periodo(2026, None, "2026-01-01") == {
            "data_da": "2026-01-01", "data_a": "2026-01-01",
        }

    def test_giorno_e_mese_a_due_cifre_anche_a_inizio_anno(self):
        assert _periodo(2026, None, "2026-03-05")["data_a"] == "2026-03-05"


def test_le_due_implementazioni_di_intervallo_mese_non_divergono():
    """`lib/catena-confronti.ts` tiene la sua copia per un limite dell'harness
    (vedi il docstring in testa). Questa e' la rete che impedisce alle due di
    allontanarsi in silenzio: l'anno intero, mese per mese, su un bisestile e
    su un anno normale."""
    for anno in (2024, 2026):
        for mese in range(1, 13):
            dalla_catena = esegui_ts(
                "lib/catena-confronti",
                "emit(m.intervalloMese(input.anno, input.mese));",
                argomento={"anno": anno, "mese": mese},
                richiede=["intervalloMese"],
            )
            assert dalla_catena == _mese(anno, mese), (anno, mese)
