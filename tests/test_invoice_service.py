"""Test per services/invoice_service.py — Normalizzazione unità di misura e logica TD04."""
import io
import pytest
from unittest.mock import MagicMock, patch
from services.invoice_service import normalizza_unita_misura


class TestNormalizzaUnitaMisura:
    """Verifica normalizzazione da esteso → abbreviato."""

    # ---- Peso ----
    @pytest.mark.parametrize("input_um,expected", [
        ("kilogrammi", "KG"),
        ("CHILOGRAMMI", "KG"),
        ("kilo", "KG"),
        ("KG", "KG"),
        ("grammi", "GR"),
        ("GR", "GR"),
    ])
    def test_peso(self, input_um, expected):
        assert normalizza_unita_misura(input_um) == expected

    # ---- Volume ----
    @pytest.mark.parametrize("input_um,expected", [
        ("litri", "LT"),
        ("LITRO", "LT"),
        ("LT", "LT"),
        ("millilitri", "ML"),
        ("centilitri", "CL"),
    ])
    def test_volume(self, input_um, expected):
        assert normalizza_unita_misura(input_um) == expected

    # ---- Quantità / Confezioni ----
    @pytest.mark.parametrize("input_um,expected", [
        ("pezzi", "PZ"),
        ("PEZZO", "PZ"),
        ("PZ", "PZ"),
        ("unità", "PZ"),
        ("confezione", "CF"),
        ("scatola", "SC"),
        ("cartone", "CT"),
        ("bottiglia", "BT"),
        ("busta", "BS"),
    ])
    def test_quantita_confezioni(self, input_um, expected):
        assert normalizza_unita_misura(input_um) == expected

    # ---- Default PZ per input vuoti/nulli ----
    def test_none(self):
        assert normalizza_unita_misura(None) == "PZ"

    def test_vuota(self):
        assert normalizza_unita_misura("") == "PZ"

    def test_non_stringa(self):
        assert normalizza_unita_misura(123) == "PZ"

    def test_unita_sconosciuta(self):
        """Unità non mappata → restituita com'è (uppercase)."""
        assert normalizza_unita_misura("FUSTI") == "FUSTI"


# ============================================================
# GROUP B: logica TD04 (nota di credito)
# ============================================================

def _xml_td04_minimal():
    """XML minimo di una nota di credito (TD04) con un articolo a 20 euro."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <DatiAnagrafici>
        <Anagrafica><Denominazione>FORNITORE TEST SRL</Denominazione></Anagrafica>
      </DatiAnagrafici>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA>
      </DatiAnagrafici>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD04</TipoDocumento>
        <Data>2025-01-15</Data>
        <Numero>NC001</Numero>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione>MOZZARELLA FIOR DI LATTE</Descrizione>
        <Quantita>2</Quantita>
        <UnitaMisura>KG</UnitaMisura>
        <PrezzoUnitario>10.00</PrezzoUnitario>
        <PrezzoTotale>20.00</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""


def _xml_td01_zero_price_with_description():
    """XML con riga a prezzo zero ma descrizione valida: deve essere mantenuta e marcata review."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <DatiAnagrafici>
        <Anagrafica><Denominazione>FORNITORE TEST SRL</Denominazione></Anagrafica>
      </DatiAnagrafici>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA>
      </DatiAnagrafici>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Data>2025-01-15</Data>
        <Numero>F001</Numero>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione>OMAGGIO PRODOTTO TEST</Descrizione>
        <Quantita>1</Quantita>
        <UnitaMisura>PZ</UnitaMisura>
        <PrezzoUnitario>0.00</PrezzoUnitario>
        <PrezzoTotale>0.00</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""


def _xml_td01_zero_price_blank_row():
    """XML con riga fantasma a zero: deve essere scartata."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <DatiAnagrafici>
        <Anagrafica><Denominazione>FORNITORE TEST SRL</Denominazione></Anagrafica>
      </DatiAnagrafici>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA>
      </DatiAnagrafici>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Data>2025-01-15</Data>
        <Numero>F002</Numero>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione> </Descrizione>
        <Quantita>0</Quantita>
        <UnitaMisura>PZ</UnitaMisura>
        <PrezzoUnitario>0.00</PrezzoUnitario>
        <PrezzoTotale>0.00</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""


def _run_estrai_xml(xml_bytes, user_id='user_test'):
    """
    Esegue estrai_dati_da_xml su xml_bytes con tutti gli esterni mockati.
    Ritorna la lista di righe estratte.

    Nota: carica_memoria_completa e categorizza_con_memoria vengono importati
    dentro la funzione estrai_dati_da_xml (import locale), quindi bisogna
    patchare il namespace sorgente services.ai_service.
    xmltodict è mockato dal conftest, quindi lo sostituiamo con quello reale.
    """
    import sys
    import importlib

    # Rimuovi il mock di xmltodict e carica il modulo reale
    sys.modules.pop('xmltodict', None)
    real_xmltodict = importlib.import_module('xmltodict')

    from services.invoice_service import estrai_dati_da_xml

    file_mock = io.BytesIO(xml_bytes)
    file_mock.name = 'test_fattura.xml'

    # session_state.get('user_data', {}) deve restituire un dict con 'id'
    # session_state.get('force_empty_until_upload', False) deve restituire False
    def _session_state_get(key, default=None):
        if key == 'user_data':
            return {'id': user_id}
        return default

    mock_st = MagicMock()
    mock_st.session_state.get = _session_state_get

    with patch('services.invoice_service.st', mock_st), \
         patch('services.invoice_service.xmltodict', real_xmltodict), \
         patch('services.ai_service.carica_memoria_completa', return_value=None), \
         patch('services.ai_service.categorizza_con_memoria',
               return_value='🧀 LATTICINI E FORMAGGI'):
        return estrai_dati_da_xml(file_mock)


class TestTD04NotaDiCredito:

    def test_td04_totale_riga_negativo(self):
        """Una nota di credito TD04 deve produrre Totale_Riga negativo."""
        righe = _run_estrai_xml(_xml_td04_minimal())
        assert len(righe) >= 1, "Attesa almeno una riga estratta"
        totale = righe[0]['Totale_Riga']
        assert totale < 0, f"TD04 deve avere Totale_Riga negativo, trovato: {totale}"

    def test_td04_tipo_documento_conservato(self):
        """Il campo tipo_documento deve essere 'TD04' nella riga estratta."""
        righe = _run_estrai_xml(_xml_td04_minimal())
        assert len(righe) >= 1
        assert righe[0]['tipo_documento'] == 'TD04'

    def test_td04_valore_corretto(self):
        """Totale_Riga deve essere -20.00 per PrezzoTotale=20 in una TD04."""
        righe = _run_estrai_xml(_xml_td04_minimal())
        assert len(righe) >= 1
        assert abs(righe[0]['Totale_Riga'] - (-20.0)) < 0.01, \
            f"Atteso -20.0, trovato: {righe[0]['Totale_Riga']}"

    def test_td04_gia_negativo_non_cambia_segno(self):
        """Se il PrezzoTotale è già negativo in una TD04, non deve essere ri-negato."""
        xml_gia_negativo = _xml_td04_minimal().replace(
            b'<PrezzoTotale>20.00</PrezzoTotale>',
            b'<PrezzoTotale>-20.00</PrezzoTotale>'
        )
        righe = _run_estrai_xml(xml_gia_negativo)
        assert len(righe) >= 1
        assert righe[0]['Totale_Riga'] < 0, \
            "Un valore già negativo in TD04 deve rimanere negativo (non doppia negazione)"


class TestRighePrezzoZero:

    def test_riga_zero_con_descrizione_valida_restera_in_review(self):
        righe = _run_estrai_xml(_xml_td01_zero_price_with_description())
        assert len(righe) == 1
        assert righe[0]['Descrizione'] == 'OMAGGIO PRODOTTO TEST'
        assert righe[0]['Prezzo_Unitario'] == 0.0
        assert righe[0]['needs_review'] is True

    def test_riga_fantasma_tutto_zero_viene_scartata(self):
        righe = _run_estrai_xml(_xml_td01_zero_price_blank_row())
        assert righe == []
