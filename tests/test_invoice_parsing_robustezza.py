"""Robustezza del parsing in ingresso: encoding, XXE, pagamenti, P7M, helper numerici.

Audit §3, 10/8/2026. Copre i punti da cui passano le 34.000 righe attive:
31.298 arrivate come XML e 2.702 come P7M (misurato sul DB live).

Aree e mutazioni verificate rosse:
- `decodifica_xml_sicuro` — guard XXE (M15), cascata encoding (M16)
- `_estrai_info_pagamento_xml` — precedenza scadenza/giorni (M17), max (M18)
- `_to_int_safe` (M20), `_normalizza_piva_cedente` (M21)
- `estrai_xml_da_p7m` — cap dimensione (M24), validazione FatturaElettronica

Il P7M di prova e' costruito con `asn1crypto` (gia' in requirements.txt:14):
un `cms.ContentInfo` con l'XML dentro l'OCTET STRING incapsulato. Niente
dipendenza da `openssl` (renderebbe il test ambiente-dipendente) e soprattutto
nessun file reale di `data/backfill_fatture/`, che contiene dati dei clienti.
"""
import importlib
import io
import sys

import pytest


@pytest.fixture(autouse=True)
def _xmltodict_reale():
    """`xmltodict` e' mockato globalmente dal conftest: senza il modulo vero il
    parse restituisce un MagicMock e ogni assert diventa vacuo."""
    sys.modules.pop('xmltodict', None)
    importlib.import_module('xmltodict')
    yield


# ─── decodifica_xml_sicuro ────────────────────────────────────────────────────

class TestDecodificaXmlSicuro:

    def test_utf8_semplice(self):
        from services.invoice_service import decodifica_xml_sicuro
        out = decodifica_xml_sicuro('<a>ciao</a>'.encode('utf-8'))
        assert '<a>ciao</a>' in out

    def test_encoding_dichiarato_nel_prolog_viene_usato(self):
        """M16 — il prolog ha la priorita' sulla cascata.

        Un fornitore che dichiara GB2312 (caso reale: fornitori cinesi) va
        decodificato con quello. Se si prova UTF-8 per primo il testo passa
        comunque ma i caratteri escono sbagliati, il dict resta monco e il
        routing multi-sede ricade sul fallback — bug gia' pagato, vedi il
        docstring della funzione.
        """
        from services.invoice_service import decodifica_xml_sicuro
        testo = "<?xml version='1.0' encoding='GB2312'?><a>你好</a>"
        out = decodifica_xml_sicuro(testo.encode('gb2312'))
        assert '你好' in out

    def test_cp1252_con_accenti_italiani(self):
        """L'assert e' sull'accento RECUPERATO, non su 'caff': quest'ultimo
        passerebbe anche con l'accento corrotto, che e' proprio il difetto che
        il test deve intercettare."""
        from services.invoice_service import decodifica_xml_sicuro
        out = decodifica_xml_sicuro('<a>caffè</a>'.encode('cp1252'))
        assert 'caffè' in out

    def test_stringa_passa_dritta(self):
        from services.invoice_service import decodifica_xml_sicuro
        assert decodifica_xml_sicuro('<a>x</a>') == '<a>x</a>'

    def test_entita_esterna_xxe_rifiutata(self):
        """M15 — il guard XXE e' l'unica difesa contro un XML che prova a
        leggere file locali. Deve sollevare, non ripulire e proseguire."""
        from services.invoice_service import decodifica_xml_sicuro
        xxe = (
            b'<?xml version="1.0"?>'
            b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b'<foo>&xxe;</foo>'
        )
        with pytest.raises(ValueError):
            decodifica_xml_sicuro(xxe)

    def test_xml_malformato_solleva_valueerror(self):
        from services.invoice_service import decodifica_xml_sicuro
        with pytest.raises(ValueError):
            decodifica_xml_sicuro(b'<a><b></a>')


# ─── _estrai_info_pagamento_xml ───────────────────────────────────────────────

def _fattura_pagamento(dettagli, in_dati_generali=False):
    blocco = {'DatiPagamento': {'DettaglioPagamento': dettagli}}
    if in_dati_generali:
        return {'FatturaElettronicaBody': {'DatiGenerali': blocco}}
    return {'FatturaElettronicaBody': blocco}


class TestInfoPagamento:

    def test_scadenza_singola(self):
        from services.invoice_service import _estrai_info_pagamento_xml
        out = _estrai_info_pagamento_xml(
            _fattura_pagamento({'DataScadenzaPagamento': '2026-04-30'}), 'TD01')
        assert out == {'scadenza_xml': '2026-04-30', 'giorni_termini_xml': None}

    def test_piu_scadenze_prende_la_piu_lontana(self):
        """M18 — con pagamento rateale la scadenza del documento e' l'ultima:
        prendere la minima anticiperebbe lo scadenziario di 1.905 documenti."""
        from services.invoice_service import _estrai_info_pagamento_xml
        out = _estrai_info_pagamento_xml(_fattura_pagamento([
            {'DataScadenzaPagamento': '2026-04-30'},
            {'DataScadenzaPagamento': '2026-06-30'},
            {'DataScadenzaPagamento': '2026-05-31'},
        ]), 'TD01')
        assert out['scadenza_xml'] == '2026-06-30'

    def test_scadenza_esplicita_vince_sui_giorni(self):
        """M17 — la data certa batte il calcolo per giorni: invertendo la
        precedenza lo scadenziario userebbe una stima al posto del dato."""
        from services.invoice_service import _estrai_info_pagamento_xml
        out = _estrai_info_pagamento_xml(_fattura_pagamento([
            {'DataScadenzaPagamento': '2026-04-30', 'GiorniTerminiPagamento': '60'},
        ]), 'TD01')
        assert out['scadenza_xml'] == '2026-04-30'
        assert out['giorni_termini_xml'] is None

    def test_solo_giorni_prende_il_massimo(self):
        from services.invoice_service import _estrai_info_pagamento_xml
        out = _estrai_info_pagamento_xml(_fattura_pagamento([
            {'GiorniTerminiPagamento': '30'}, {'GiorniTerminiPagamento': '60'},
        ]), 'TD01')
        assert out == {'scadenza_xml': None, 'giorni_termini_xml': 60}

    def test_dati_pagamento_annidati_in_dati_generali(self):
        from services.invoice_service import _estrai_info_pagamento_xml
        out = _estrai_info_pagamento_xml(
            _fattura_pagamento({'DataScadenzaPagamento': '2026-04-30'},
                               in_dati_generali=True), 'TD01')
        assert out['scadenza_xml'] == '2026-04-30'

    def test_tipo_documento_fuori_whitelist_non_estrae(self):
        from services.invoice_service import _estrai_info_pagamento_xml
        out = _estrai_info_pagamento_xml(
            _fattura_pagamento({'DataScadenzaPagamento': '2026-04-30'}), 'TD99')
        assert out == {'scadenza_xml': None, 'giorni_termini_xml': None}

    def test_data_non_parsabile_ignorata_senza_eccezione(self):
        from services.invoice_service import _estrai_info_pagamento_xml
        out = _estrai_info_pagamento_xml(
            _fattura_pagamento({'DataScadenzaPagamento': 'non-una-data'}), 'TD01')
        assert out == {'scadenza_xml': None, 'giorni_termini_xml': None}

    def test_senza_dati_pagamento(self):
        from services.invoice_service import _estrai_info_pagamento_xml
        out = _estrai_info_pagamento_xml({'FatturaElettronicaBody': {}}, 'TD01')
        assert out == {'scadenza_xml': None, 'giorni_termini_xml': None}


# ─── P.IVA cessionario ────────────────────────────────────────────────────────

class TestPivaCessionario:

    def _fattura(self, paese='IT', codice='01234567890'):
        return {'FatturaElettronicaHeader': {'CessionarioCommittente': {'DatiAnagrafici': {
            'IdFiscaleIVA': {'IdPaese': paese, 'IdCodice': codice}}}}}

    def test_piva_italiana_valida(self):
        from services.invoice_service import estrai_piva_cessionario_xml
        assert estrai_piva_cessionario_xml(self._fattura()) == '01234567890'

    def test_senza_header_restituisce_none(self):
        from services.invoice_service import estrai_piva_cessionario_xml
        assert estrai_piva_cessionario_xml({'FatturaElettronicaHeader': {}}) is None

    def test_input_malformato_non_solleva(self):
        from services.invoice_service import estrai_piva_cessionario_xml
        assert estrai_piva_cessionario_xml({'FatturaElettronicaHeader': 'stringa'}) is None


# ─── helper numerici ──────────────────────────────────────────────────────────

class TestHelperNumerici:

    def test_bool_non_diventa_intero(self):
        """M20 — `True` in Python e' anche `1`: senza il ramo esplicito un flag
        finirebbe silenziosamente in un campo numerico come quantita' 1."""
        from services.invoice_service import _to_int_safe
        assert _to_int_safe(True, default=None) is None
        assert _to_int_safe(False, default=None) is None

    @pytest.mark.parametrize('valore,atteso', [
        (5, 5), (3.9, 3), ('12', 12), ('12,7', 12), ('', None), (None, None),
        ('abc', None),
    ])
    def test_conversioni(self, valore, atteso):
        from services.invoice_service import _to_int_safe
        assert _to_int_safe(valore, default=None) == atteso

    @pytest.mark.parametrize('valore,atteso', [
        ('IT01234567890', '01234567890'),
        ('01234567890', '01234567890'),
        ('0123456789012345', '01234567890'),
        ('  01234 567890 ', '01234567890'),
        ('SOLOLETTERE', None),
        (None, None),
    ])
    def test_normalizza_piva(self, valore, atteso):
        """M21 — il troncamento a 11 cifre: una P.IVA piu' lunga (prefissi o
        errori del gestionale) non deve entrare nel DB come chiave diversa,
        o la guardia anti-doppione smette di riconoscere il documento."""
        from services.invoice_service import _normalizza_piva_cedente
        assert _normalizza_piva_cedente(valore) == atteso

    @pytest.mark.parametrize('valore,atteso', [
        ('2.174,67', 2174.67), ('5,00', 5.0), ('2174.67', 2174.67),
        (10, 10.0), ('', None), (None, None),
    ])
    def test_to_float_formato_italiano(self, valore, atteso):
        from services.invoice_service import _to_float_safe
        assert _to_float_safe(valore, default=None) == atteso


# ─── P7M ──────────────────────────────────────────────────────────────────────

def _p7m_sintetico(xml_bytes):
    """Costruisce un CMS/PKCS#7 DER con l'XML nell'OCTET STRING incapsulato.

    E' la forma che il metodo 1 (`asn1crypto`) sa leggere, cioe' quella da cui
    sono passate le 2.702 righe P7M in produzione.
    """
    from asn1crypto import cms, core
    return cms.ContentInfo({
        'content_type': 'signed_data',
        'content': cms.SignedData({
            'version': 'v1',
            'digest_algorithms': [],
            'encap_content_info': {'content_type': 'data',
                                   'content': core.OctetString(xml_bytes)},
            'certificates': None, 'crls': None, 'signer_infos': [],
        }),
    }).dump()


def _file(contenuto, nome='FATT_001.xml.p7m'):
    f = io.BytesIO(contenuto)
    f.name = nome
    return f


class TestEstraiXmlDaP7m:

    XML = (b'<?xml version="1.0" encoding="UTF-8"?>'
           b'<p:FatturaElettronica xmlns:p="x"><Body>contenuto</Body></p:FatturaElettronica>')

    def test_estrazione_da_p7m_valido(self):
        from services.invoice_service import estrai_xml_da_p7m
        out = estrai_xml_da_p7m(_file(_p7m_sintetico(self.XML)))
        assert b'FatturaElettronica' in out.read()

    def test_nome_stream_derivato_dal_file(self):
        from services.invoice_service import estrai_xml_da_p7m
        out = estrai_xml_da_p7m(_file(_p7m_sintetico(self.XML), nome='FATT_001.p7m'))
        assert out.name == 'FATT_001.xml'

    def test_file_troppo_grande_rifiutato(self):
        """M24 — il cap protegge il worker da un payload che lo farebbe morire
        in memoria: e' un limite di servizio, non un dettaglio."""
        from config.constants import MAX_FILE_SIZE_P7M
        from services.invoice_service import estrai_xml_da_p7m
        with pytest.raises(ValueError, match='troppo grande'):
            estrai_xml_da_p7m(_file(b'\x30' + b'x' * (MAX_FILE_SIZE_P7M + 1)))

    def test_contenuto_senza_fattura_rifiutato(self):
        """Validazione finale: se dai cinque metodi esce qualcosa che non e'
        una fattura, meglio un errore esplicito che una fattura vuota nel DB."""
        from services.invoice_service import estrai_xml_da_p7m
        payload = _p7m_sintetico(b'<?xml version="1.0"?><AltroDocumento>x</AltroDocumento>')
        with pytest.raises(ValueError):
            estrai_xml_da_p7m(_file(payload))

    def test_p7m_illeggibile_solleva(self):
        from services.invoice_service import estrai_xml_da_p7m
        with pytest.raises(ValueError):
            estrai_xml_da_p7m(_file(b'\x30\x82\x00\x10' + b'\xff' * 200))

    def test_p7m_in_base64_pem_viene_decodificato(self):
        import base64
        from services.invoice_service import estrai_xml_da_p7m
        der = _p7m_sintetico(self.XML)
        pem = b'-----BEGIN PKCS7-----\n' + base64.encodebytes(der) + b'-----END PKCS7-----\n'
        out = estrai_xml_da_p7m(_file(pem))
        assert b'FatturaElettronica' in out.read()


class TestProvaDecodificaBase64:

    def test_pem_decodificato_in_der(self):
        import base64
        from services.invoice_service import _prova_decodifica_base64
        der = _p7m_sintetico(b'<x/>')
        pem = b'-----BEGIN PKCS7-----\n' + base64.encodebytes(der) + b'-----END PKCS7-----\n'
        assert _prova_decodifica_base64(pem) == der

    def test_input_non_base64_restituisce_none(self):
        from services.invoice_service import _prova_decodifica_base64
        assert _prova_decodifica_base64(b'\x30\x82 questo non e base64 \xff') is None
