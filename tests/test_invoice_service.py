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
      <DatiRiepilogo>
        <AliquotaIVA>10.00</AliquotaIVA>
        <ImponibileImporto>20.00</ImponibileImporto>
        <Imposta>2.00</Imposta>
      </DatiRiepilogo>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""


def _xml_td04_segni_misti():
    """TD04 a SEGNI MISTI (caso reale LODI): un riaddebito positivo e uno storno
    negativo, netto righe +102.20 = imponibile di testata.

    E' una nota di credito che AUMENTA i costi: va invertita in blocco, cosi'
    il netto diventa -102.20. L'inversione in blocco preserva i rapporti interni
    (non produce -4247, che sarebbe la somma dei moduli)."""
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
        <Data>2026-04-27</Data>
        <Numero>1/3997</Numero>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione>SALMONE LEROY 5/6 FRESCHI</Descrizione>
        <Quantita>283.90</Quantita>
        <UnitaMisura>KG</UnitaMisura>
        <PrezzoUnitario>7.66</PrezzoUnitario>
        <PrezzoTotale>2174.67</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>2</NumeroLinea>
        <Descrizione>SALMONE LEROY 5/6 FRESCHI</Descrizione>
        <Quantita>283.90</Quantita>
        <UnitaMisura>KG</UnitaMisura>
        <PrezzoUnitario>-7.30</PrezzoUnitario>
        <PrezzoTotale>-2072.47</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
      </DettaglioLinee>
      <DatiRiepilogo>
        <AliquotaIVA>10.00</AliquotaIVA>
        <ImponibileImporto>102.20</ImponibileImporto>
        <Imposta>10.22</Imposta>
      </DatiRiepilogo>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""


def _xml_td04_premio_con_bollo():
    """TD04 caso reale PARTESA: un premio positivo e una rivalsa bollo negativa
    marginale (0,25% del documento). Netto righe +789.49 = imponibile di testata.

    E' il caso che il criterio storico sbagliava: la riga da -2,00 bastava a
    disattivare l'inversione sull'intero documento."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <DatiAnagrafici>
        <Anagrafica><Denominazione>PARTESA TEST SRL</Denominazione></Anagrafica>
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
        <Data>2026-04-10</Data>
        <Numero>NC/PREMIO/1</Numero>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione>PREMIO POSTICIPATO FINE PERIODO</Descrizione>
        <Quantita>1.00</Quantita>
        <PrezzoUnitario>791.49</PrezzoUnitario>
        <PrezzoTotale>791.49</PrezzoTotale>
        <AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>2</NumeroLinea>
        <Descrizione>RIVALSA BOLLO N.C</Descrizione>
        <Quantita>1.00</Quantita>
        <PrezzoUnitario>-2.00</PrezzoUnitario>
        <PrezzoTotale>-2.00</PrezzoTotale>
        <AliquotaIVA>0.00</AliquotaIVA>
      </DettaglioLinee>
      <DatiRiepilogo>
        <AliquotaIVA>22.00</AliquotaIVA>
        <ImponibileImporto>789.49</ImponibileImporto>
        <Imposta>173.69</Imposta>
      </DatiRiepilogo>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""


def _xml_td04_tutta_negativa():
    """TD04 gia' corretta: solo righe negative, netto -150.00 concorde con la
    testata. E' la forma delle 130 note sane in produzione — non va toccata."""
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
        <Data>2026-03-11</Data>
        <Numero>NC/RESO/1</Numero>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione>RESO MERCE NON CONFORME</Descrizione>
        <Quantita>10.00</Quantita>
        <PrezzoUnitario>-10.00</PrezzoUnitario>
        <PrezzoTotale>-100.00</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee>
        <NumeroLinea>2</NumeroLinea>
        <Descrizione>RESO IMBALLI</Descrizione>
        <Quantita>5.00</Quantita>
        <PrezzoUnitario>-10.00</PrezzoUnitario>
        <PrezzoTotale>-50.00</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
      </DettaglioLinee>
      <DatiRiepilogo>
        <AliquotaIVA>10.00</AliquotaIVA>
        <ImponibileImporto>150.00</ImponibileImporto>
        <Imposta>15.00</Imposta>
      </DatiRiepilogo>
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


def _xml_td01_explicit_zero_total_with_discount():
    """XML con PrezzoTotale esplicitamente a zero: deve restare zero nel parser."""
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
        <Numero>F003</Numero>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione>CAUZIONE FUSTI VINO</Descrizione>
        <Quantita>11.00</Quantita>
        <UnitaMisura>NR</UnitaMisura>
        <PrezzoUnitario>30.98700000</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>100.00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>0.00000000</PrezzoTotale>
        <AliquotaIVA>0.00</AliquotaIVA>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""


def _xml_td01_discount_comma_decimal():
    """XML con Percentuale sconto in formato italiano (virgola): '5,00'.
    Regressione: float('5,00') solleva ValueError e fa crashare l'INTERO parsing
    della fattura (audit 19/06). Con _to_float_safe la riga viene estratta."""
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
        <Numero>F010</Numero>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione>OLIO EXTRAVERGINE</Descrizione>
        <Quantita>10.00</Quantita>
        <UnitaMisura>LT</UnitaMisura>
        <PrezzoUnitario>8.00</PrezzoUnitario>
        <ScontoMaggiorazione>
          <Tipo>SC</Tipo>
          <Percentuale>5,00</Percentuale>
        </ScontoMaggiorazione>
        <PrezzoTotale>76.00</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
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
    """
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
         patch('services.ai_service.carica_memoria_completa', return_value=None), \
         patch('services.ai_service.categorizza_con_memoria',
               return_value=('🧀 LATTICINI E FORMAGGI', False)):
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

    def test_td04_segni_misti_netto_positivo_viene_invertito(self):
        """REGRESSIONE LODI. Il criterio storico lasciava intatta questa nota
        perché conteneva una riga già negativa, e il netto restava +102.20: una
        nota di credito che AUMENTA i costi. Va invertita in blocco.

        L'inversione in blocco preserva i rapporti interni: netto -102.20, NON
        -4247.14 (che sarebbe la somma dei moduli, l'errore che il criterio
        storico voleva evitare)."""
        righe = _run_estrai_xml(_xml_td04_segni_misti())
        assert len(righe) == 2, f"Attese 2 righe, trovate {len(righe)}"
        per_tot = sorted(r['Totale_Riga'] for r in righe)
        assert per_tot[0] == pytest.approx(-2174.67, abs=0.01), \
            f"Il riaddebito invertito deve valere -2174.67, trovato {per_tot[0]}"
        assert per_tot[1] == pytest.approx(2072.47, abs=0.01), \
            f"Lo storno invertito deve valere +2072.47, trovato {per_tot[1]}"
        netto = sum(r['Totale_Riga'] for r in righe)
        assert netto == pytest.approx(-102.20, abs=0.02), \
            f"Netto deve essere -102.20 (riduce i costi), trovato {netto}"
        assert netto != pytest.approx(-4247.14, abs=1.0), \
            "L'inversione non deve sommare i moduli (-4247): romperebbe il documento"

    def test_td04_premio_con_bollo_marginale_viene_invertito(self):
        """REGRESSIONE PARTESA: premio +791.49 e rivalsa bollo -2.00.

        È il caso che il criterio storico sbagliava: due euro di bollo già
        negativi disattivavano la correzione su ottocento euro di premio, e la
        nota veniva contata come costo. Netto atteso -789.49."""
        righe = _run_estrai_xml(_xml_td04_premio_con_bollo())
        assert len(righe) == 2, f"Attese 2 righe, trovate {len(righe)}"
        netto = sum(r['Totale_Riga'] for r in righe)
        assert netto == pytest.approx(-789.49, abs=0.02), \
            f"Netto deve essere -789.49 (rimborso), trovato {netto}"
        per_tot = sorted(r['Totale_Riga'] for r in righe)
        assert per_tot[0] == pytest.approx(-791.49, abs=0.01), \
            f"Il premio invertito deve valere -791.49, trovato {per_tot[0]}"
        assert per_tot[1] == pytest.approx(2.00, abs=0.01), \
            f"Il bollo invertito deve valere +2.00, trovato {per_tot[1]}"

    def test_td04_gia_negativa_non_viene_reinvertita(self):
        """Una TD04 già corretta (solo righe negative, netto negativo) non va
        toccata: è la forma delle 130 note sane in produzione."""
        righe = _run_estrai_xml(_xml_td04_tutta_negativa())
        assert len(righe) == 2, f"Attese 2 righe, trovate {len(righe)}"
        netto = sum(r['Totale_Riga'] for r in righe)
        assert netto == pytest.approx(-150.00, abs=0.02), \
            f"Netto deve restare -150.00, trovato {netto}"
        assert all(r['Totale_Riga'] < 0 for r in righe), \
            "Nessuna riga deve tornare positiva"

    def test_td04_senza_imponibile_usa_criterio_storico(self):
        """Fallback: senza DatiRiepilogo non c'è ancora di testata, quindi vale
        il criterio storico (nessuna riga negativa → inverto in blocco). In
        produzione non capita (140 TD04 su 140 hanno l'imponibile), ma il codice
        non deve dipendere dalla sua presenza."""
        xml_senza_riepilogo = _xml_td04_minimal().replace(
            b"""      <DatiRiepilogo>
        <AliquotaIVA>10.00</AliquotaIVA>
        <ImponibileImporto>20.00</ImponibileImporto>
        <Imposta>2.00</Imposta>
      </DatiRiepilogo>
""",
            b""
        )
        assert b'DatiRiepilogo' not in xml_senza_riepilogo, "La fixture deve restare senza riepilogo"
        righe = _run_estrai_xml(xml_senza_riepilogo)
        assert len(righe) >= 1
        assert sum(r['Totale_Riga'] for r in righe) < 0, \
            "Senza imponibile, una TD04 tutta positiva va comunque invertita"

    def test_td04_segni_misti_senza_imponibile_resta_al_criterio_storico(self):
        """Il caso che separa davvero i due rami della guardia.

        Segni misti a netto positivo (LODI) ma SENZA DatiRiepilogo: senza ancora
        di testata non possiamo affermare che il netto vada ribaltato, quindi
        vale il criterio storico e il documento resta intatto (+102.20).
        Con l'imponibile presente lo stesso documento viene invece invertito
        (test_td04_segni_misti_netto_positivo_viene_invertito).

        Senza questo test la guardia `if totale_imponibile:` e' sostituibile con
        `if True:` senza che nulla fallisca."""
        xml_senza_riepilogo = _xml_td04_segni_misti().replace(
            b"""      <DatiRiepilogo>
        <AliquotaIVA>10.00</AliquotaIVA>
        <ImponibileImporto>102.20</ImponibileImporto>
        <Imposta>10.22</Imposta>
      </DatiRiepilogo>
""",
            b""
        )
        assert b'DatiRiepilogo' not in xml_senza_riepilogo
        righe = _run_estrai_xml(xml_senza_riepilogo)
        assert len(righe) == 2, f"Attese 2 righe, trovate {len(righe)}"
        netto = sum(r['Totale_Riga'] for r in righe)
        assert netto == pytest.approx(102.20, abs=0.02), \
            f"Senza imponibile vale il criterio storico: netto resta +102.20, trovato {netto}"

    def test_td04_tutto_positivo_inverte_in_blocco(self):
        """Contro-prova: una TD04 con TUTTE le righe positive (convenzione
        gestionale 'sempre positivo') deve essere invertita in blocco → netto
        negativo (riduce i costi)."""
        righe = _run_estrai_xml(_xml_td04_minimal())  # singola riga +20
        assert len(righe) >= 1
        assert sum(r['Totale_Riga'] for r in righe) < 0, \
            "TD04 tutta positiva deve diventare negativa in blocco"


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

    def test_prezzo_totale_zero_esplicito_non_viene_ricostruito(self):
      righe = _run_estrai_xml(_xml_td01_explicit_zero_total_with_discount())
      assert len(righe) == 1
      assert righe[0]['Totale_Riga'] == 0.0
      assert righe[0]['Prezzo_Unitario'] == 30.99

    def test_sconto_percentuale_con_virgola_non_crasha(self):
        """Percentuale sconto '5,00' (formato italiano): prima float() crashava
        l'intero parsing; ora la fattura viene estratta normalmente."""
        righe = _run_estrai_xml(_xml_td01_discount_comma_decimal())
        assert len(righe) == 1
        assert righe[0]['Totale_Riga'] == 76.0


class TestGuardrailNoteConImporto:
    """Il guardrail NOTE nel parser XML: una riga classificata
    '📝 NOTE E DICITURE' con importo != 0 NON può restare NOTE e NON deve finire
    in una categoria inventata (niente fallback travestito in SERVIZI E
    CONSULENZE). Deve tornare a 'Da Classificare' + needs_review, così resta in
    coda e fuori dai margini. Regressione del flusso onesto (CLAUDE.md regole #1/#2)."""

    def _run_con_categoria_note(self, xml_bytes, user_id='user_test'):
        """Come _run_estrai_xml ma forza categorizza_con_memoria a restituire NOTE."""
        from services.invoice_service import estrai_dati_da_xml

        file_mock = io.BytesIO(xml_bytes)
        file_mock.name = 'test_fattura.xml'

        def _session_state_get(key, default=None):
            if key == 'user_data':
                return {'id': user_id}
            return default

        mock_st = MagicMock()
        mock_st.session_state.get = _session_state_get

        with patch('services.invoice_service.st', mock_st), \
                 patch('services.ai_service.carica_memoria_completa', return_value=None), \
             patch('services.ai_service.categorizza_con_memoria',
                   return_value=('📝 NOTE E DICITURE', False)):
            return estrai_dati_da_xml(file_mock)

    def test_note_con_importo_non_resta_servizi(self):
        """Riga NOTE con importo != 0 NON deve diventare 'SERVIZI E CONSULENZE'."""
        righe = self._run_con_categoria_note(_xml_td04_minimal())  # importo -20.00
        assert len(righe) >= 1
        assert righe[0]['Categoria'] != 'SERVIZI E CONSULENZE', \
            "Il guardrail NON deve più inventare la categoria SERVIZI E CONSULENZE"

    def test_note_con_importo_torna_da_classificare(self):
        """Riga NOTE con importo != 0 deve tornare a 'Da Classificare' + needs_review."""
        righe = self._run_con_categoria_note(_xml_td04_minimal())  # importo -20.00
        assert len(righe) >= 1
        assert righe[0]['Categoria'] == 'Da Classificare', \
            f"Atteso 'Da Classificare', trovato {righe[0]['Categoria']!r}"
        assert righe[0]['needs_review'] is True, \
            "Una riga riportata a Da Classificare deve restare in coda (needs_review)"

    def test_note_con_importo_zero_resta_note(self):
        """Contro-prova: una dicitura a importo 0 resta legittimamente in NOTE."""
        righe = self._run_con_categoria_note(_xml_td01_zero_price_with_description())
        assert len(righe) == 1
        assert righe[0]['Categoria'] == '📝 NOTE E DICITURE', \
            "Una dicitura a importo zero deve poter restare in NOTE E DICITURE"


class TestDocumentoNonLetto:
    """`None` vs `[]`: la differenza fra "non l'ho letto" e "non ha righe".

    Regressione del bug che ha perso 2 fatture TOYOTA (agosto 2026): l'except
    finale ritornava `[]`, indistinguibile da una fattura valida senza
    DettaglioLinee. Il worker chiudeva l'item `done` e purgava l'XML dalla coda.
    Vedi tests/test_worker_p7m_non_perde_fatture.py per l'anello successivo.
    """

    def test_xml_corrotto_ritorna_none(self):
        busta = b'0\x82%\x06\t*\x86H\xde\xad\xbe\xef1\x0f'
        assert _run_estrai_xml(busta) is None, \
            "un documento illeggibile non è una fattura senza righe"

    def test_xml_troncato_ritorna_none(self):
        troncato = b'<?xml version="1.0"?><p:FatturaElettronica><rotto>'
        assert _run_estrai_xml(troncato) is None

    def test_xml_valido_senza_righe_ritorna_lista_vuota(self):
        """Guardia anti-regressione: il caso legittimo resta `[]`, non `None`."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" versione="FPR12">'
            '<FatturaElettronicaHeader><CedentePrestatore><DatiAnagrafici>'
            '<IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>12345678901</IdCodice></IdFiscaleIVA>'
            '<Anagrafica><Denominazione>FORNITORE SPA</Denominazione></Anagrafica>'
            '</DatiAnagrafici></CedentePrestatore></FatturaElettronicaHeader>'
            '<FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento>'
            '<TipoDocumento>TD01</TipoDocumento><Data>2026-08-01</Data><Numero>1</Numero>'
            '</DatiGeneraliDocumento></DatiGenerali>'
            '<DatiBeniServizi></DatiBeniServizi>'
            '</FatturaElettronicaBody></p:FatturaElettronica>'
        ).encode('utf-8')
        righe = _run_estrai_xml(xml)
        assert righe == [], f"fattura valida senza righe deve dare [], trovato {righe!r}"
