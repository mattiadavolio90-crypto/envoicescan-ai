"""Estrazione data_consegna dalle fatture differite TD24 — sulla funzione VERA.

Perche' questo file esiste (audit §3, 10/8/2026)
------------------------------------------------
`tests/test_td24.py` copriva questa logica **replicandola**: dichiarava nel
proprio docstring "We replicate the extraction algorithm from
invoice_service.estrai_dati_da_xml" e testava la copia, non il codice di
produzione. Restava verde anche rompendo `estrai_dati_da_xml`.

Non e' un dettaglio: misurato sul DB live il 10/8/2026, TD24 vale
**11.773 righe attive su 34.000 (35%)** distribuite su 669 documenti, e
`data_consegna` e' valorizzata su **11.771 di quelle righe (99,98%)**. La data
di consegna alimenta la competenza economica: se la mappa
`RiferimentoNumeroLinea -> DataDDT` si rompe, quelle righe prendono la data
sbagliata e i costi finiscono nel mese sbagliato, senza che nulla sollevi.

Qui si esercita `estrai_dati_da_xml` reale su XML sintetici, uno per schema
osservato in produzione.

Mutazioni verificate rosse (M1-M4 del piano):
- `:1222` `.get(_num_linea_xml) or .get(idx)` -> solo `.get(idx)`  [schema PARTESA]
- `:1224` rimozione del fallback `_ddt_global_date`
- `:1233` rimozione del range anno 2020..2030
- `:1209` `if is_td24:` -> `if True:`

M1 va scritta rimuovendo il PRIMO termine dell'`or`, non sostituendolo: i due
lookup coincidono su ogni fattura che numera le righe 1,2,3..., quindi una
mutazione del primo termine resterebbe verde ovunque tranne che sullo schema
PARTESA (righe 10/20/30), che e' esattamente la fixture che lo distingue.
"""
import io
from unittest.mock import MagicMock, patch

import pytest


def _run_estrai_xml(xml_bytes, user_id='user_test', categoria='🧀 LATTICINI E FORMAGGI'):
    """Esegue estrai_dati_da_xml con gli esterni mockati, xmltodict REALE.

    `xmltodict` e' mockato globalmente da tests/conftest.py: senza la
    ri-iniezione del modulo vero il parse restituirebbe un MagicMock e ogni
    assert confronterebbe oggetti fantasma, passando per il motivo sbagliato.

    `carica_memoria_completa` / `categorizza_con_memoria` sono import LOCALI
    dentro estrai_dati_da_xml: vanno patchati sul modulo sorgente
    (`services.ai_service`), non su `services.invoice_service`.
    """
    from services.invoice_service import estrai_dati_da_xml

    file_mock = io.BytesIO(xml_bytes)
    file_mock.name = 'test_td24.xml'

    def _session_state_get(key, default=None):
        if key == 'user_data':
            return {'id': user_id}
        return default

    mock_st = MagicMock()
    mock_st.session_state.get = _session_state_get

    with patch('services.invoice_service.st', mock_st), \
         patch('services.ai_service.carica_memoria_completa', return_value=None), \
         patch('services.ai_service.categorizza_con_memoria',
               return_value=(categoria, False)):
        return estrai_dati_da_xml(file_mock)


def _xml(tipo_documento='TD24', dati_ddt='', linee=None):
    """Costruisce una FatturaPA minimale col blocco DatiDDT richiesto."""
    if linee is None:
        linee = [(1, 'MOZZARELLA FIORDILATTE', '10.00')]
    linee_xml = "".join(
        f"""
      <DettaglioLinee>
        <NumeroLinea>{num}</NumeroLinea>
        <Descrizione>{desc}</Descrizione>
        <Quantita>1.00</Quantita>
        <UnitaMisura>KG</UnitaMisura>
        <PrezzoUnitario>{prezzo}</PrezzoUnitario>
        <PrezzoTotale>{prezzo}</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
      </DettaglioLinee>"""
        for num, desc, prezzo in linee
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA>
        <Anagrafica><Denominazione>FORNITORE TEST SRL</Denominazione></Anagrafica>
      </DatiAnagrafici>
    </CedentePrestatore>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>{tipo_documento}</TipoDocumento>
        <Data>2026-03-31</Data>
        <Numero>DIFF-1</Numero>
        <ImportoTotaleDocumento>10.00</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>{dati_ddt}
    </DatiGenerali>
    <DatiBeniServizi>{linee_xml}
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>""".encode('utf-8')


def _ddt(numero_ddt, data_ddt, rif_linee=None):
    """Blocco DatiDDT; rif_linee=None => nessun RiferimentoNumeroLinea (data globale)."""
    rif = "".join(
        f"\n        <RiferimentoNumeroLinea>{r}</RiferimentoNumeroLinea>"
        for r in (rif_linee or [])
    )
    return f"""
      <DatiDDT>
        <NumeroDDT>{numero_ddt}</NumeroDDT>
        <DataDDT>{data_ddt}</DataDDT>{rif}
      </DatiDDT>"""


def _consegne(righe):
    return [r.get('data_consegna') for r in righe]


class TestDatiDDTPerRiga:
    """Schema A: DatiDDT con RiferimentoNumeroLinea esplicito."""

    def test_ddt_singolo_mappa_la_riga_riferita(self):
        righe = _run_estrai_xml(_xml(dati_ddt=_ddt('DDT1', '2026-03-10', [1])))
        assert len(righe) == 1
        assert righe[0]['data_consegna'] == '2026-03-10'

    def test_ddt_multipli_ogni_riga_prende_la_sua_data(self):
        """Due DDT distinti, due righe: ognuna deve prendere la propria data."""
        xml = _xml(
            dati_ddt=_ddt('DDT1', '2026-03-10', [1]) + _ddt('DDT2', '2026-03-20', [2]),
            linee=[(1, 'MOZZARELLA', '10.00'), (2, 'BURRATA', '12.00')],
        )
        righe = _run_estrai_xml(xml)
        assert len(righe) == 2
        assert _consegne(righe) == ['2026-03-10', '2026-03-20']

    def test_un_ddt_con_piu_riferimenti_mappa_tutte_le_righe_elencate(self):
        xml = _xml(
            dati_ddt=_ddt('DDT1', '2026-03-15', [1, 2]),
            linee=[(1, 'MOZZARELLA', '10.00'), (2, 'BURRATA', '12.00')],
        )
        righe = _run_estrai_xml(xml)
        assert _consegne(righe) == ['2026-03-15', '2026-03-15']

    def test_riga_non_riferita_da_nessun_ddt_resta_senza_data(self):
        """Senza data globale, una riga non citata non deve ereditare nulla."""
        xml = _xml(
            dati_ddt=_ddt('DDT1', '2026-03-10', [1]),
            linee=[(1, 'MOZZARELLA', '10.00'), (2, 'BURRATA', '12.00')],
        )
        righe = _run_estrai_xml(xml)
        assert _consegne(righe) == ['2026-03-10', None]

    def test_schema_partesa_numerolinea_non_e_l_indice(self):
        """M1 — il lookup deve usare NumeroLinea dell'XML, non l'indice del loop.

        Alcuni fornitori (PARTESA) numerano le righe 10, 20, 30 e i
        RiferimentoNumeroLinea puntano a QUEI valori. Se il codice cercasse
        l'indice del loop (1, 2, 3) non troverebbe nulla e 11.771 righe di
        produzione perderebbero la data di consegna.

        E' la fixture che rende osservabile M1: qui NumeroLinea e indice
        divergono, in tutti gli altri test coincidono.
        """
        xml = _xml(
            dati_ddt=(
                _ddt('DDT1', '2026-03-10', [10])
                + _ddt('DDT2', '2026-03-11', [20])
                + _ddt('DDT3', '2026-03-12', [30])
            ),
            linee=[(10, 'MOZZARELLA', '10.00'), (20, 'BURRATA', '12.00'), (30, 'STRACCIATELLA', '14.00')],
        )
        righe = _run_estrai_xml(xml)
        assert _consegne(righe) == ['2026-03-10', '2026-03-11', '2026-03-12']

    def test_riferimento_non_numerico_non_scarta_la_riga(self):
        """Un RiferimentoNumeroLinea non intero degrada a "nessuna data",
        non fa sparire la riga dal totale documento."""
        xml = _xml(dati_ddt=_ddt('DDT1', '2026-03-10', ['ABC']))
        righe = _run_estrai_xml(xml)
        assert len(righe) == 1, "La riga deve sopravvivere"
        assert righe[0]['data_consegna'] is None


class TestDataGlobaleDDT:
    """Schema C: DatiDDT senza RiferimentoNumeroLinea => vale per tutte le righe."""

    def test_ddt_senza_riferimenti_vale_per_tutte_le_righe(self):
        """M2 — se cade questo fallback, le fatture con DDT unico perdono la data."""
        xml = _xml(
            dati_ddt=_ddt('DDT1', '2026-03-05'),
            linee=[(1, 'MOZZARELLA', '10.00'), (2, 'BURRATA', '12.00')],
        )
        righe = _run_estrai_xml(xml)
        assert _consegne(righe) == ['2026-03-05', '2026-03-05']

    def test_riferimento_puntuale_vince_sulla_data_globale(self):
        """La mappa per riga ha priorita': il globale e' il fallback, non il default."""
        xml = _xml(
            dati_ddt=_ddt('DDT_GLOB', '2026-03-05') + _ddt('DDT1', '2026-03-10', [1]),
            linee=[(1, 'MOZZARELLA', '10.00'), (2, 'BURRATA', '12.00')],
        )
        righe = _run_estrai_xml(xml)
        assert _consegne(righe) == ['2026-03-10', '2026-03-05']

    def test_ddt_con_data_vuota_ignorato(self):
        xml = _xml(dati_ddt=_ddt('DDT1', ''))
        righe = _run_estrai_xml(xml)
        assert righe[0]['data_consegna'] is None


class TestFallbackRegexDescrizione:
    """Schema D: nessun DatiDDT, data GG/MM/AAAA dentro la descrizione."""

    def test_data_nella_descrizione_viene_estratta(self):
        xml = _xml(linee=[(1, 'CONSEGNA DEL 12/03/2026 MERCE VARIA', '10.00')])
        righe = _run_estrai_xml(xml)
        assert righe[0]['data_consegna'] == '2026-03-12'

    @pytest.mark.parametrize('anno', ['2019', '2031'])
    def test_anno_fuori_range_rifiutato(self, anno):
        """M3 — il range 2020..2030 esiste per non raccogliere numeri che
        somigliano a date (lotti, codici). Senza, una descrizione qualunque
        contamina la competenza economica."""
        xml = _xml(linee=[(1, f'LOTTO 12/03/{anno} MERCE VARIA', '10.00')])
        righe = _run_estrai_xml(xml)
        assert righe[0]['data_consegna'] is None

    def test_data_impossibile_non_solleva(self):
        xml = _xml(linee=[(1, 'CONSEGNA 32/13/2026 MERCE', '10.00')])
        righe = _run_estrai_xml(xml)
        assert len(righe) == 1
        assert righe[0]['data_consegna'] is None

    def test_ddt_esplicito_vince_sulla_regex(self):
        xml = _xml(
            dati_ddt=_ddt('DDT1', '2026-03-10', [1]),
            linee=[(1, 'CONSEGNA DEL 12/03/2026 MERCE', '10.00')],
        )
        righe = _run_estrai_xml(xml)
        assert righe[0]['data_consegna'] == '2026-03-10'


class TestSoloTD24:
    """Il blocco data_consegna e' gatato su TipoDocumento == TD24.

    Nota di metodo (mutazione M4, verificata il 10/8/2026). Il gate e' DOPPIO:
    `:887` decide se popolare la mappa DDT, `:1209` decide se usarla. Rompendo
    un gate solo, i test restano VERDI e sembrano deboli — non lo sono: e' una
    difesa in profondita', l'altro gate copre. La mutazione osservabile e'
    disattivarli ENTRAMBI, e in quel caso cadono i due test qui sotto.
    Chi in futuro muta un gate solo e lo trova verde, sta guardando questo.
    """

    def test_td01_con_datiddt_non_produce_data_consegna(self):
        """M4 — una fattura immediata non ha data di consegna, anche se il
        gestionale ha lasciato un DatiDDT nel corpo. Se il gate cade, le
        21.800 righe TD01 iniziano a esporre una data che non significa nulla.
        """
        xml = _xml(tipo_documento='TD01', dati_ddt=_ddt('DDT1', '2026-03-10', [1]))
        righe = _run_estrai_xml(xml)
        assert len(righe) == 1
        assert righe[0]['data_consegna'] is None

    def test_td01_non_usa_nemmeno_la_regex_in_descrizione(self):
        xml = _xml(tipo_documento='TD01', linee=[(1, 'CONSEGNA DEL 12/03/2026', '10.00')])
        righe = _run_estrai_xml(xml)
        assert righe[0]['data_consegna'] is None

    def test_td24_senza_alcun_ddt_ne_data_resta_none(self):
        righe = _run_estrai_xml(_xml())
        assert len(righe) == 1
        assert righe[0]['data_consegna'] is None
