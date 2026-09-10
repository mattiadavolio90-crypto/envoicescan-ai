"""L'anteprima della coda «da assegnare» parsa con user_id=None, ma il settore viaggia.

Settimo punto d'uscita (sesta lettura del reviewer). `riparto_anteprima_coda` e
l'ingresso ambiguo di `upload_invoice` chiamano `estrai_dati_da_xml(..., user_id=None)`
di proposito: senza utente il parser non carica memoria e non scrive. Ma senza utente
non risolveva nemmeno il settore, e per un negozio l'anteprima — mostrata al cliente e
salvata in `fatture_queue.anteprima_righe` all'ingresso — nasceva con categorie food.

Cura: `settore` esplicito e indipendente da `user_id`, risolto dall'utente autenticato
dai due chiamanti. Per i ristoranti (settore None o 'ristorazione') il parser fa
esattamente quello di prima.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.fastapi_worker as fw
import services.routers.riparto as riparto
import services.settore_service as ss
from services.invoice_service import estrai_dati_da_xml
from tests.test_retail_settore_per_documento import _xml
from tests.test_riparto_anteprima_coda import _FakeSB, _RIGA_OK, _RIGHE_PARSATE


# ── il parser ────────────────────────────────────────────────────────────────

def _parser(user_id, settore):
    chiamate: list = []
    ricevuti: list = []

    def _settore(uid, supabase_client=None):
        chiamate.append(uid)
        return "ristorazione"

    def _categorizza(*_a, **kw):
        ricevuti.append(kw.get("settore"))
        return ("Da Classificare", True)

    st_finto = MagicMock()
    st_finto.session_state.get = lambda _k, default=None: default
    with patch("services.invoice_service.st", st_finto), \
         patch("services.ai_service.carica_memoria_completa", return_value=None), \
         patch("services.ai_service.categorizza_con_memoria", side_effect=_categorizza), \
         patch.object(ss, "settore_utente", side_effect=_settore):
        righe = estrai_dati_da_xml(_xml("MARTELLO 500G", "VITI 4X40 100PZ"), user_id=user_id, settore=settore)
    return len(righe), chiamate, ricevuti


def test_il_parser_usa_il_settore_esplicito_anche_senza_utente():
    assert _parser(None, "retail") == (2, [], ["retail", "retail"])


def test_il_settore_esplicito_vince_sull_utente_e_nessuno_lo_richiede():
    assert _parser("u-rist", "retail") == (2, [], ["retail", "retail"])


def test_senza_settore_esplicito_si_risolve_dall_utente_come_prima():
    assert _parser("u-rist", None) == (2, ["u-rist"], ["ristorazione", "ristorazione"])


# ── l'endpoint anteprima ─────────────────────────────────────────────────────

def _anteprima(settore_risposta):
    sb = _FakeSB([_RIGA_OK])
    chiamate: list = []
    with patch.multiple(
        riparto,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
    ), patch.object(ss, "settore_utente", side_effect=lambda uid, supabase_client=None: chiamate.append(uid) or settore_risposta), \
       patch("services.invoice_service.estrai_dati_da_xml", return_value=_RIGHE_PARSATE) as mock_parse:
        out = riparto.riparto_anteprima_coda(queue_id=42, authorization="Bearer x")
    _, kwargs = mock_parse.call_args
    return out, chiamate, kwargs


def test_l_anteprima_coda_parsa_senza_utente_ma_col_settore_del_negozio():
    out, chiamate, kwargs = _anteprima("retail")
    assert out["disponibile"] is True and len(out["righe"]) == 1
    assert chiamate == ["user-1"]
    assert kwargs.get("user_id") is None and kwargs.get("settore") == "retail"


def test_per_un_ristorante_l_anteprima_viaggia_come_ristorazione():
    _, _, kwargs = _anteprima("ristorazione")
    assert kwargs.get("user_id") is None and kwargs.get("settore") == "ristorazione"


# ── l'ingresso ambiguo di upload_invoice ─────────────────────────────────────

class _SB:
    def __init__(self):
        self.rpc_calls: list = []

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=[{"queue_id": 7, "created": True}]))

    def table(self, *_a, **_k):
        raise AssertionError("nessuna query diretta attesa sul ramo ambiguo")


class _File:
    def __init__(self, data, filename="fattura.xml"):
        self._d = data
        self.filename = filename

    async def read(self):
        return self._d


def _upload_ambiguo(settore_risposta):
    sb = _SB()
    chiamate: list = []
    kwargs_parser: dict = {}

    def _parser_finto(_file_like, **kw):
        kwargs_parser.update(kw)
        return []

    sedi = [{"id": "r1", "nome_ristorante": "Sede A"}, {"id": "r2", "nome_ristorante": "Sede B"}]
    with patch.object(fw, "_resolve_user_from_token", return_value={"id": "u-shop"}), \
         patch("services.get_supabase_client", return_value=sb), \
         patch.object(fw, "_carica_sedi_attive_per_user", return_value=sedi), \
         patch.object(fw, "_get_ristorante_id_for_user", return_value="r1"), \
         patch("services.multisede_routing.decidi_destinazione_upload",
               return_value={"mode": "ambiguo", "best_score": 0.0, "gap": 0.0}), \
         patch("services.invoice_service.estrai_dati_da_xml", side_effect=_parser_finto), \
         patch.object(ss, "settore_utente", side_effect=lambda uid, supabase_client=None: chiamate.append(uid) or settore_risposta):
        out = asyncio.run(fw.upload_invoice(MagicMock(), MagicMock(), authorization="Bearer x",
                                            file=_File(_xml("MARTELLO 500G").getvalue())))
    return out, chiamate, kwargs_parser, sb.rpc_calls


def test_l_anteprima_all_ingresso_nasce_col_settore_del_negozio():
    out, chiamate, kwargs, rpc = _upload_ambiguo("retail")
    assert out.routing_status == "ambiguo" and out.queue_id == 7
    assert chiamate == ["u-shop"]
    assert kwargs == {"user_id": None, "settore": "retail"}
    assert rpc[0][0] == "accoda_upload_ambiguo" and rpc[0][1]["p_anteprima_righe"] == []


def test_per_un_ristorante_l_anteprima_all_ingresso_viaggia_come_ristorazione():
    _, _, kwargs, _ = _upload_ambiguo("ristorazione")
    assert kwargs == {"user_id": None, "settore": "ristorazione"}
