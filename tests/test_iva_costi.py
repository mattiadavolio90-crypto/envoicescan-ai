"""Costi inseriti a mano IVA inclusa: si salva il netto (Mattia, 3/10/2026).

Lo scorporo vero e' del worker (`utils/iva.py`, usato da `ws_spese_crea` e
`ws_spese_aggiorna`); il modulo Spese mostra un'anteprima con lo stesso conto in
`lib/iva-costi.ts`. Qui: le due copie danno lo stesso netto al centesimo, e le
rotte salvano il netto.
"""
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import services.routers.workspace as workspace
from config.constants import ALIQUOTE_IVA_COSTI
from tests.helpers_ts import esegui_ts
from tests.test_spese_extra import _crea_e_leggi_payload, _patch_e_leggi_updates, _query_mock
from utils.iva import netto_da_lordo

MODULO = "lib/iva-costi"
_TS = Path(__file__).resolve().parents[1] / f"apps/web/src/{MODULO}.ts"


def test_le_aliquote_sono_le_stesse_nei_due_lati():
    m = re.search(r"ALIQUOTE_IVA_COSTI = \[([^\]]*)\]", _TS.read_text(encoding="utf-8"))
    assert m, "ALIQUOTE_IVA_COSTI sparita da lib/iva-costi.ts"
    assert tuple(int(x) for x in m.group(1).split(",")) == ALIQUOTE_IVA_COSTI == (4, 5, 10, 22)


@pytest.mark.parametrize("lordo,aliquota,netto", [
    (104, 4, 100.0), (105, 5, 100.0), (110, 10, 100.0), (122, 22, 100.0),
    (120, 10, 109.09), (20, 22, 16.39), (0, 10, 0.0),
    (0.11, 10, 0.1), (1.05, 10, 0.95),
])
def test_netto_noto(lordo, aliquota, netto):
    assert netto_da_lordo(lordo, aliquota) == netto


def test_aliquota_non_ammessa():
    with pytest.raises(ValueError):
        netto_da_lordo(100, 7)


def test_anteprima_e_worker_danno_lo_stesso_netto():
    """Griglia che passa per i mezzi centesimi: e' li' che due arrotondamenti
    diversi (per eccesso / al pari) si separano."""
    extra = [1234.56, 99999.99, 10.5, 2.1]
    lordi = [c / 100 for c in range(0, 3001)] + extra
    casi = [(l, a) for l in lordi for a in ALIQUOTE_IVA_COSTI]
    ts = esegui_ts(
        MODULO,
        "const lordi = [...Array(3001).keys()].map(c => c / 100).concat(input.extra);"
        "emit(lordi.flatMap(l => input.aliquote.map(a => m.nettoDaLordo(l, a))));",
        argomento={"extra": extra, "aliquote": list(ALIQUOTE_IVA_COSTI)},
        richiede=["nettoDaLordo"],
    )
    assert len(ts) == len(casi)
    diversi = [(l, a, n, netto_da_lordo(l, a)) for (l, a), n in zip(casi, ts) if n != netto_da_lordo(l, a)]
    assert not diversi, diversi[:10]


def test_la_scelta_del_modulo():
    out = esegui_ts(
        MODULO,
        'emit(["", "4", "5", "10", "22", "7", "abc"].map(m.aliquotaDaScelta));',
        richiede=["aliquotaDaScelta"],
    )
    assert out == [None, 4, 5, 10, 22, None, None]


def _body_nuova(**kw):
    base = dict(data_spesa="2026-10-02", tipo="fb", importo=120.0, descrizione="latte", categoria="LATTICINI")
    return workspace.NuovaSpesaBody(**{**base, **kw})


def test_la_spesa_iva_inclusa_si_salva_al_netto():
    assert _crea_e_leggi_payload(_body_nuova(iva_inclusa=10))["importo"] == 109.09


def test_senza_iva_l_importo_resta_quello():
    assert _crea_e_leggi_payload(_body_nuova())["importo"] == 120.0


def test_aliquota_sbagliata_e_rifiutata():
    client = MagicMock()
    client.table.return_value = _query_mock([{"id": "new"}])
    with patch.multiple(
        workspace,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    ), pytest.raises(HTTPException) as e:
        workspace.ws_spese_crea(body=_body_nuova(iva_inclusa=7), authorization="Bearer x")
    assert e.value.status_code == 400
    client.table.return_value.insert.assert_not_called()


def test_la_modifica_iva_inclusa_salva_il_netto():
    body = workspace.AggiornaSpesaBody(importo=22.0, iva_inclusa=22)
    assert _patch_e_leggi_updates(body, "LATTICINI")["importo"] == 18.03


def test_la_modifica_senza_iva_non_scorpora():
    body = workspace.AggiornaSpesaBody(importo=22.0)
    assert _patch_e_leggi_updates(body, "LATTICINI")["importo"] == 22.0


def test_iva_senza_importo_e_rifiutata():
    with pytest.raises(HTTPException) as e:
        _patch_e_leggi_updates(workspace.AggiornaSpesaBody(iva_inclusa=10, descrizione="x"), "LATTICINI")
    assert e.value.status_code == 400


def test_il_modulo_spese_manda_l_aliquota_scelta():
    """Cablaggio del .tsx (non eseguibile qui): la scelta passa da aliquotaDaScelta
    e arriva al worker in `iva_inclusa`; senza, il server non scorpora niente."""
    tsx = (Path(__file__).resolve().parents[1]
           / "apps/web/src/app/(app)/workspace/spese-view.tsx").read_text(encoding="utf-8")
    assert "const aliquota = aliquotaDaScelta(iva);" in tsx
    assert re.search(r"\n\s+iva_inclusa: aliquota,\n", tsx)
    assert 'setIva("");' in tsx, "aprendo il modulo la scelta dell'IVA deve ripartire da «No»"
