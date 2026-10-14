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


class TestTogliPreferito:
    """La richiesta si costruisce col vero client postgrest-py e si intercetta
    prima dell'HTTP: e' la serializzazione dei filtri a decidere se PostgREST
    capisce la richiesta, e un mock non la riproduce."""

    def _richieste(self, monkeypatch, prodotto, fornitore):
        from postgrest import SyncPostgrestClient
        from postgrest._sync.request_builder import SyncFilterRequestBuilder
        from services.routers.prezzi import _togli_preferito

        mandate = []
        monkeypatch.setattr(
            SyncFilterRequestBuilder, "execute",
            lambda self: mandate.append(dict(self.request.params.multi_items())),
        )
        _togli_preferito(SyncPostgrestClient("http://x"), "r1", prodotto, fornitore)
        return mandate

    def test_virgolette_e_parentesi_arrivano_intatte(self, monkeypatch):
        mandate = self._richieste(monkeypatch, 'TUBO 1/2" (10PZ)', "IDRAULICA, SRL")
        assert mandate == [{
            "ristorante_id": "eq.r1",
            "descrizione_key": 'eq.TUBO 1/2" (10PZ)',
            "fornitore_key": "eq.IDRAULICA, SRL",
        }]

    def test_toglie_anche_le_forme_troncate(self, monkeypatch):
        prodotto, fornitore = "A" * 70, "F" * 40
        mandate = self._richieste(monkeypatch, prodotto, fornitore)
        coppie = {(m["descrizione_key"], m["fornitore_key"]) for m in mandate}
        assert coppie == {
            (f"eq.{d}", f"eq.{f}")
            for d in ("A" * 70, "A" * 60)
            for f in ("F" * 40, "F" * 30)
        }
        assert all(m["ristorante_id"] == "eq.r1" for m in mandate)

    def test_fornitore_vuoto_si_toglie(self, monkeypatch):
        # Con .in_ diventava `in.()`, una lista vuota: la stella restava accesa.
        mandate = self._richieste(monkeypatch, "OLIO", "")
        assert [m["fornitore_key"] for m in mandate] == ["eq."]
