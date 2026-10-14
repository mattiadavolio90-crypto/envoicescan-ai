"""I due caricamenti dei prezzi paginano con un ordine totale.

Contare un acquisto per fattura somma le quantita' delle righe della stessa
fattura: una riga letta due volte al confine fra due pagine raddoppierebbe la
quantita', e con essa l'impatto €/mese. Oggi:
- `_load_fatture_for_prezzi` (Osservatorio, catena PV, score) ordina per data:
  `fetch_all` non aggiunge `id` se c'e' gia' un ordine;
- `_carica_fatture_da_supabase` (avvisi di Home, chat, briefing) paginava
  senza nessun ordine. Sul live 2 sedi su 7 superano le 1.000 righe nella
  finestra degli avvisi (14/10/2026).
"""
from types import SimpleNamespace

import pandas as pd
from postgrest import SyncPostgrestClient


def test_l_osservatorio_pagina_per_data_e_poi_per_id(monkeypatch):
    from services.routers import prezzi

    client = SyncPostgrestClient("http://db.invalid")
    sb = SimpleNamespace(table=client.from_)
    visti = []
    monkeypatch.setattr(prezzi, "fetch_all", lambda builder: visti.append(dict(builder.request.params)) or [])
    monkeypatch.setattr(prezzi._PREZZI_ROWS_CACHE, "get_or_set", lambda chiave, produci: produci())

    prezzi._load_fatture_for_prezzi(sb, "sede-ordine", "2026-01-01", "2026-12-31")

    assert visti, "il caricamento non e' passato da fetch_all"
    assert visti[0]["order"] == "data_documento.asc,id.asc"


class _Pagine:
    """Builder finto che registra ogni chiamata e serve 1.000 righe a pagina."""

    def __init__(self, registro, totale):
        self.registro = registro
        self.totale = totale

    def __getattr__(self, nome):
        def _metodo(*a, **k):
            self.registro.append((nome, a))
            return self
        return _metodo

    def range(self, a, b):
        self.registro.append(("range", (a, b)))
        self._pagina = (a, b)
        return self

    def execute(self):
        if self.registro and self.registro[-1][0] == "range":
            a, b = self._pagina
            righe = [
                {"file_origine": f"f{i}.xml", "numero_riga": 1, "data_documento": "2026-04-01",
                 "fornitore": "F", "descrizione": "X", "quantita": 1, "unita_misura": "PZ",
                 "prezzo_unitario": 1.0, "iva_percentuale": 10, "totale_riga": 1.0,
                 "categoria": "CARNE", "codice_articolo": None}
                for i in range(a, min(b + 1, self.totale))
            ]
            return SimpleNamespace(data=righe, count=None)
        return SimpleNamespace(data=[], count=self.totale)


def test_gli_avvisi_ordinano_per_id_prima_di_ogni_pagina(monkeypatch):
    import services
    from services import db_service

    registro = []
    monkeypatch.setattr(services, "get_supabase_client", lambda: SimpleNamespace(table=lambda n: _Pagine(registro, 1500)))
    monkeypatch.setattr(db_service, "escludi_oscurate", lambda q: q)
    monkeypatch.setattr(db_service, "_filter_active", lambda q: q)

    db_service._carica_fatture_da_supabase.clear()
    df = db_service._carica_fatture_da_supabase("utente-ordine", "sede-ordine")
    db_service._carica_fatture_da_supabase.clear()

    pagine = [i for i, (nome, _) in enumerate(registro) if nome == "range"]
    assert len(pagine) == 2, registro
    for i in pagine:
        precedenti = [nome_args for nome_args in registro[:i]]
        ultimo_order = [a for nome, a in precedenti if nome == "order"]
        assert ultimo_order and ultimo_order[-1] == ("id",), f"pagina senza ordine per id: {registro[:i]}"
    assert isinstance(df, pd.DataFrame)
