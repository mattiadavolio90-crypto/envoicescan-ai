"""Test guardia: l'anteprima della coda catena è PERSISTENTE (Fase 4, 23/07/2026).

Contesto (richiesta OFFSIDE): l'anteprima delle righe di una fattura 'da_assegnare'
ri-parsava l'XML a caldo a OGNI apertura, su unico container Railway senza cache →
sotto contesa scattava il timeout e l'anteprima "spariva" (la firma della contesa,
non di un documento rotto). Cura alla radice: parse UNA volta, salva le righe in
fatture_queue.anteprima_righe; le aperture successive leggono dalla cache.

Copre:
  - cache presente → ritorno istantaneo, NESSUN parse, NESSUN update;
  - cache assente → parse una volta, righe salvate in anteprima_righe, cache=False;
  - parsing riuscito ma vuoto ([]) → salvato lo stesso (non ri-parsare a vuoto);
  - xml_content assente e nessuna cache → disponibile:False, nessun parse;
  - salvataggio cache in errore → l'utente riceve comunque le righe (la cache è un
    di più, non deve rompere la risposta);
  - parsing fallito → disponibile:False, nessuna scrittura di cache.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.invoice_service as invoice_service
import services.routers.riparto as riparto


class _QueueQuery:
    """Query builder minimale per fatture_queue. Registra select/update così il test
    verifica se il parsing ha portato o meno a una scrittura di cache."""

    def __init__(self, client):
        self._c = client
        self._mode = None  # "select" | "update"
        self._payload = None

    def select(self, *a, **k):
        self._mode = "select"
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        self._c.updates.append(payload)
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        if self._mode == "update":
            if self._c.update_raise:
                raise RuntimeError("boom update")
            return SimpleNamespace(data=[{"id": self._c.row["id"]}])
        return SimpleNamespace(data=[self._c.row] if self._c.row else [])


class _FakeSB:
    def __init__(self, row, update_raise=False):
        self.row = row
        self.update_raise = update_raise
        self.updates = []

    def table(self, name):
        assert name == "fatture_queue"
        return _QueueQuery(self)


def _row(**over):
    base = {
        "id": 7,
        "user_id": "user-1",
        "xml_content": "<x/>",
        "payload_meta": {"nome_file": "f.xml"},
        "anteprima_righe": None,
    }
    base.update(over)
    return base


def _patch(sb):
    return patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
    )


def _riga_parsata(desc, tot):
    return {
        "Numero_Riga": 1, "Descrizione": desc, "Quantita": 1, "Unita_Misura": "PZ",
        "Prezzo_Unitario": tot, "IVA_Percentuale": 22, "Totale_Riga": tot,
        "Categoria": "PESCE",
    }


def test_cache_presente_ritorno_istantaneo_senza_parse():
    cache = [{"numero_riga": 1, "descrizione": "Salmone", "totale_riga": 10.0}]
    sb = _FakeSB(_row(anteprima_righe=cache))
    with _patch(sb), patch.object(invoice_service, "estrai_dati_da_xml") as parse:
        out = riparto.riparto_anteprima_coda(queue_id=7, authorization="Bearer x")
    parse.assert_not_called()               # niente ri-parse
    assert sb.updates == []                 # niente scrittura
    assert out["disponibile"] is True
    assert out["cache"] is True
    assert out["righe"] == cache


def test_cache_vuota_lista_e_valida():
    # Una cache = [] (parsing riuscito ma senza righe) è un esito legittimo: va
    # servita così com'è, senza ri-parsare.
    sb = _FakeSB(_row(anteprima_righe=[]))
    with _patch(sb), patch.object(invoice_service, "estrai_dati_da_xml") as parse:
        out = riparto.riparto_anteprima_coda(queue_id=7, authorization="Bearer x")
    parse.assert_not_called()
    assert out == {"disponibile": True, "righe": [], "cache": True}


def test_cache_assente_parsa_una_volta_e_salva():
    sb = _FakeSB(_row(anteprima_righe=None))
    righe = [_riga_parsata("Salmone", 10.0), _riga_parsata("Tonno", 20.0)]
    with _patch(sb), patch.object(invoice_service, "estrai_dati_da_xml", return_value=righe):
        out = riparto.riparto_anteprima_coda(queue_id=7, authorization="Bearer x")
    assert out["disponibile"] is True
    assert out["cache"] is False
    assert [r["descrizione"] for r in out["righe"]] == ["Salmone", "Tonno"]
    # Ha salvato la cache (una sola update) con righe + timestamp.
    assert len(sb.updates) == 1
    salvato = sb.updates[0]
    assert salvato["anteprima_righe"] == out["righe"]
    assert salvato["anteprima_at"]  # istante valorizzato


def test_parsing_vuoto_viene_cacheato():
    # Parsing riuscito ma 0 righe → salvo [] per non ri-parsare a vuoto ogni volta.
    sb = _FakeSB(_row(anteprima_righe=None))
    with _patch(sb), patch.object(invoice_service, "estrai_dati_da_xml", return_value=[]):
        out = riparto.riparto_anteprima_coda(queue_id=7, authorization="Bearer x")
    assert out == {"disponibile": True, "righe": [], "cache": False}
    assert len(sb.updates) == 1
    assert sb.updates[0]["anteprima_righe"] == []


def test_salvataggio_cache_in_errore_serve_comunque_le_righe():
    # La cache è un di più: se l'update fallisce l'utente riceve comunque le righe
    # appena parsate (verranno ricalcolate al prossimo accesso).
    sb = _FakeSB(_row(anteprima_righe=None), update_raise=True)
    righe = [_riga_parsata("Salmone", 10.0)]
    with _patch(sb), patch.object(invoice_service, "estrai_dati_da_xml", return_value=righe):
        out = riparto.riparto_anteprima_coda(queue_id=7, authorization="Bearer x")
    assert out["disponibile"] is True
    assert out["cache"] is False
    assert len(out["righe"]) == 1


def test_no_xml_no_cache_non_disponibile():
    # xml assente, MAI purgato → motivo 'assente' (caso degenere, non "perso").
    sb = _FakeSB(_row(xml_content=None, anteprima_righe=None, xml_url=None, xml_purged_at=None))
    with _patch(sb), patch.object(invoice_service, "estrai_dati_da_xml") as parse:
        out = riparto.riparto_anteprima_coda(queue_id=7, authorization="Bearer x")
    parse.assert_not_called()
    assert out == {"righe": [], "disponibile": False, "motivo": "assente"}
    assert sb.updates == []


def test_xml_purgato_senza_url_ritorna_perso():
    # Contenuto purgato e niente xml_url da cui riscaricare (canale manuale storico):
    # il server lo dice ONESTAMENTE con motivo='perso', così la UI non mente parlando
    # di "documento illeggibile". Nessun parse tentato, nessuna scrittura.
    sb = _FakeSB(_row(
        xml_content=None, anteprima_righe=None, xml_url=None,
        xml_purged_at="2026-07-20T09:22:54Z",
    ))
    with _patch(sb), patch.object(invoice_service, "estrai_dati_da_xml") as parse:
        out = riparto.riparto_anteprima_coda(queue_id=7, authorization="Bearer x")
    parse.assert_not_called()
    assert out == {"righe": [], "disponibile": False, "motivo": "perso"}
    assert sb.updates == []


def test_parsing_fallito_non_scrive_cache():
    sb = _FakeSB(_row(anteprima_righe=None))
    with _patch(sb), patch.object(
        invoice_service, "estrai_dati_da_xml", side_effect=RuntimeError("boom parse")
    ):
        out = riparto.riparto_anteprima_coda(queue_id=7, authorization="Bearer x")
    assert out == {"righe": [], "disponibile": False, "motivo": "illeggibile"}
    assert sb.updates == []
