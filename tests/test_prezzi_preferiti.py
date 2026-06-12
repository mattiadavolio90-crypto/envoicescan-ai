"""Fase 1 — Preferiti pagina Prezzi.

Test sui pure helper del router prezzi: normalizzazione delle chiavi preferiti
(coppia descrizione+fornitore) e arricchimento del campo `preferito` nelle
variazioni. Non toccano auth/Supabase: la logica di dominio sta tutta nelle
funzioni sincrone.
"""
from services.routers.prezzi import (
    _pulisci_desc_key,
    _pulisci_forn_key,
    _calcola_variazioni_prezzi_sync,
    StoricoPrezzoPoint,
)


class TestNormalizzazioneChiavi:
    def test_desc_key_upper_trim(self):
        assert _pulisci_desc_key("  Pomodoro Pelato  ") == "POMODORO PELATO"

    def test_desc_key_rimuove_suffisso_ui(self):
        # Il suffisso UI " ⚠️ >6m" aggiunto alle variazioni NON deve finire nella
        # chiave, altrimenti la stella non combacerebbe al ricaricamento.
        assert _pulisci_desc_key("SALMONE ⚠️ >6M") == "SALMONE"
        assert _pulisci_desc_key("salmone ⚠️ >6m") == "SALMONE"

    def test_desc_key_suffisso_solo_in_coda(self):
        # Un "⚠️ >6m" a meta' descrizione non e' un suffisso: non va rimosso.
        assert _pulisci_desc_key("X ⚠️ >6M Y") == "X ⚠️ >6M Y"

    def test_forn_key_upper_trim(self):
        assert _pulisci_forn_key("  H.D. Italia S.r.l ") == "H.D. ITALIA S.R.L"


def _rows(desc, forn, prezzi):
    """Righe fattura minime per N acquisti dello stesso prodotto/fornitore."""
    out = []
    for i, p in enumerate(prezzi):
        out.append({
            "descrizione": desc,
            "categoria": "CARNE",
            "fornitore": forn,
            "prezzo_unitario": p,
            "quantita": 1.0,
            "totale_riga": p,
            "data_documento": f"2026-0{i+1}-01",
            "file_origine": f"f{i}.xml",
            "tipo_documento": "TD01",
        })
    return out


class TestArricchimentoPreferito:
    def test_preferito_false_di_default(self):
        rows = _rows("ANATRA ARROSTO", "H.D. ITALIA", [10.0, 12.0])
        out = _calcola_variazioni_prezzi_sync(rows, soglia=5.0)
        assert len(out) == 1
        assert out[0]["preferito"] is False

    def test_preferito_true_se_in_set(self):
        rows = _rows("ANATRA ARROSTO", "H.D. ITALIA", [10.0, 12.0])
        keys = {"ANATRA ARROSTO|H.D. ITALIA"}
        out = _calcola_variazioni_prezzi_sync(rows, soglia=5.0, preferiti_keys=keys)
        assert out[0]["preferito"] is True

    def test_match_ignora_case_e_spazi(self):
        rows = _rows("  Anatra Arrosto ", " h.d. italia ", [10.0, 12.0])
        keys = {"ANATRA ARROSTO|H.D. ITALIA"}
        out = _calcola_variazioni_prezzi_sync(rows, soglia=5.0, preferiti_keys=keys)
        assert out[0]["preferito"] is True

    def test_preferito_non_combacia_fornitore_diverso(self):
        rows = _rows("ANATRA ARROSTO", "ALTRO FORNITORE", [10.0, 12.0])
        keys = {"ANATRA ARROSTO|H.D. ITALIA"}
        out = _calcola_variazioni_prezzi_sync(rows, soglia=5.0, preferiti_keys=keys)
        assert out[0]["preferito"] is False


class TestStoricoPrezzoPoint:
    """I campi fattura del punto storico alimentano la lista acquisti cliccabile
    nella pagina Prezzi. Devono avere default sicuri: durante un deploy
    incrementale un worker vecchio potrebbe restituire solo data+prezzo, e il
    frontend filtra le righe su `fattura` non vuoto."""

    def test_campi_fattura_default_vuoti(self):
        p = StoricoPrezzoPoint(data="2026-01-01", prezzo_unitario=10.0)
        assert p.fattura == ""
        assert p.numero_documento == ""
        assert p.quantita is None
        assert p.totale_riga is None

    def test_campi_fattura_valorizzati(self):
        p = StoricoPrezzoPoint(
            data="2026-01-01",
            prezzo_unitario=10.0,
            fattura="f0.xml",
            numero_documento="FT/123",
            quantita=2.5,
            totale_riga=25.0,
        )
        assert p.fattura == "f0.xml"
        assert p.numero_documento == "FT/123"
        assert p.quantita == 2.5
        assert p.totale_riga == 25.0
