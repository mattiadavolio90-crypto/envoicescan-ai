"""Il settore arriva al classificatore UNA volta per documento (RETAIL_FASI.md 1.2/1.3).

`estrai_dati_da_xml` risolve `settore_utente(user_id)` fuori dal loop righe e lo
passa a ogni `categorizza_con_memoria` come argomento. Senza `user_id` e senza
`settore` esplicito (test) resta None: percorso ristorazione invariato. L'anteprima
coda passa il settore esplicitamente: `test_retail_anteprima_settore.py`.
Esterni mockati sul modulo sorgente (`services.ai_service`,
`services.settore_service`): sono import locali dentro la funzione.
"""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import services.settore_service as ss
from services.invoice_service import estrai_dati_da_xml


def _xml(*descrizioni):
    linee = "".join(
        f"""
      <DettaglioLinee>
        <NumeroLinea>{i}</NumeroLinea>
        <Descrizione>{d}</Descrizione>
        <Quantita>1.00</Quantita>
        <UnitaMisura>PZ</UnitaMisura>
        <PrezzoUnitario>10.00</PrezzoUnitario>
        <PrezzoTotale>10.00</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>"""
        for i, d in enumerate(descrizioni, start=1)
    )
    testo = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567897</IdCodice></IdFiscaleIVA>
        <Anagrafica><Denominazione>FERRAMENTA ROSSI SRL</Denominazione></Anagrafica>
      </DatiAnagrafici>
    </CedentePrestatore>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Data>2026-09-01</Data>
        <Numero>R-1</Numero>
        <ImportoTotaleDocumento>20.00</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>{linee}
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""
    f = io.BytesIO(testo.encode("utf-8"))
    f.name = "retail.xml"
    return f


def _esegui(user_id, risposta="retail"):
    chiamate_settore: list = []
    settori_ricevuti: list = []

    def _settore(uid, supabase_client=None):
        chiamate_settore.append(uid)
        return risposta

    def _categorizza(*_a, **kw):
        settori_ricevuti.append(kw.get("settore"))
        return ("Da Classificare", True)

    # Nei test `st` e' un MagicMock: senza questo, session_state.get restituirebbe un
    # id fantasma e "senza utente" non sarebbe mai davvero senza utente.
    st_finto = MagicMock()
    st_finto.session_state.get = lambda _k, default=None: default

    with patch("services.invoice_service.st", st_finto), \
         patch("services.ai_service.carica_memoria_completa", return_value=None), \
         patch("services.ai_service.categorizza_con_memoria", side_effect=_categorizza), \
         patch.object(ss, "settore_utente", side_effect=_settore):
        righe = estrai_dati_da_xml(_xml("MARTELLO 500G", "VITI 4X40 100PZ"), user_id=user_id)
    return righe, chiamate_settore, settori_ricevuti


def test_il_settore_si_risolve_una_volta_e_arriva_a_ogni_riga():
    righe, chiamate, ricevuti = _esegui("u-retail")
    assert len(righe) == 2
    assert chiamate == ["u-retail"]
    assert ricevuti == ["retail", "retail"]


def test_senza_utente_il_settore_resta_none_e_nessuno_lo_chiede():
    righe, chiamate, ricevuti = _esegui(None)
    assert len(righe) == 2
    assert chiamate == []
    assert ricevuti == [None, None]


def test_un_ristorante_viaggia_come_ristorazione():
    _, _, ricevuti = _esegui("u-rist", risposta="ristorazione")
    assert ricevuti == ["ristorazione", "ristorazione"]
