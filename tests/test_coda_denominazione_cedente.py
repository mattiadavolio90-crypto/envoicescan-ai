"""Test guardia: la coda "da assegnare" deve mostrare il NOME del fornitore.

Contesto (16/07/2026): né il webhook SDI né l'upload manuale salvano la ragione
sociale in payload_meta — entrambi mettono solo `piva_cedente`. La coda diceva
quindi "Fornitore P.IVA 09806270154", che non dice niente a chi deve decidere in
quale locale va la fattura: proprio la decisione per cui la coda esiste.

Il nome è nell'XML, che per gli item da_assegnare è ancora in tabella. Verificato
su OFFSIDE: 20/20 item in coda risolti (PARTESA, METRO Italia, Amazon EU,
Ristopiù Lombardia, PIADASNACK di Tura Alessandro...).

La trappola coperta qui: <Denominazione> compare DUE volte in ogni fattura —
CedentePrestatore (il fornitore) e CessionarioCommittente (il cliente, cioè il
ristorante). Prendere la prima senza tagliare l'XML significherebbe mostrare al
cliente il suo stesso nome su ogni riga della coda.
"""
from services.routers.fatture import _denominazione_cedente


def _xml(cedente: str = "", cessionario: str = "OFFSIDE SRL") -> str:
    """Scheletro di fattura elettronica: cedente (fornitore) + cessionario (cliente)."""
    return f"""<?xml version="1.0"?>
<FatturaElettronica>
  <FatturaElettronicaHeader>
    <CedentePrestatore><DatiAnagrafici><Anagrafica>
      {cedente}
    </Anagrafica></DatiAnagrafici></CedentePrestatore>
    <CessionarioCommittente><DatiAnagrafici><Anagrafica>
      <Denominazione>{cessionario}</Denominazione>
    </Anagrafica></DatiAnagrafici></CessionarioCommittente>
  </FatturaElettronicaHeader>
</FatturaElettronica>"""


class TestPrendeIlFornitoreNonIlCliente:
    def test_ritorna_il_cedente_non_il_cessionario(self):
        xml = _xml(cedente="<Denominazione>PARTESA S.R.L.</Denominazione>", cessionario="OFFSIDE SRL")
        assert _denominazione_cedente(xml) == "PARTESA S.R.L."

    def test_ditta_individuale_senza_denominazione_usa_nome_e_cognome(self):
        # Caso reale in coda OFFSIDE: "PIADASNACK di Tura Alessandro".
        xml = _xml(cedente="<Nome>Alessandro</Nome><Cognome>Tura</Cognome>")
        assert _denominazione_cedente(xml) == "Alessandro Tura"

    def test_ditta_individuale_non_pesca_il_cliente_come_fallback(self):
        # Il cedente non ha Denominazione: il fallback Nome/Cognome non deve
        # sconfinare oltre il taglio e restituire la denominazione del CLIENTE.
        xml = _xml(cedente="<Nome>Alessandro</Nome><Cognome>Tura</Cognome>", cessionario="OFFSIDE SRL")
        assert "OFFSIDE" not in (_denominazione_cedente(xml) or "")


class TestCasiSporchi:
    def test_entita_html_decodificate(self):
        # I nomi con & arrivano come &amp;: mostrarli grezzi sarebbe un difetto visibile.
        xml = _xml(cedente="<Denominazione>GABRI &amp; MARCO S.R.L.</Denominazione>")
        assert _denominazione_cedente(xml) == "GABRI & MARCO S.R.L."

    def test_denominazione_vuota_ripiega_su_nome_cognome(self):
        xml = _xml(cedente="<Denominazione></Denominazione><Nome>Mario</Nome><Cognome>Rossi</Cognome>")
        assert _denominazione_cedente(xml) == "Mario Rossi"

    def test_solo_cognome(self):
        xml = _xml(cedente="<Cognome>Rossi</Cognome>")
        assert _denominazione_cedente(xml) == "Rossi"

    def test_spazi_ripuliti(self):
        xml = _xml(cedente="<Denominazione>  METRO Italia S.p.A.  </Denominazione>")
        assert _denominazione_cedente(xml) == "METRO Italia S.p.A."


class TestNessunNome:
    """Il nome è una comodità: quando manca la coda resta usabile con la P.IVA,
    non deve rompersi né inventare."""

    def test_xml_none(self):
        assert _denominazione_cedente(None) is None

    def test_xml_vuoto(self):
        assert _denominazione_cedente("") is None

    def test_xml_senza_anagrafica(self):
        assert _denominazione_cedente("<FatturaElettronica></FatturaElettronica>") is None

    def test_xml_spazzatura_non_esplode(self):
        assert _denominazione_cedente("non-xml <<< >>>") is None

    def test_p7m_binario_non_esplode(self):
        # Un p7m estratto male non è XML: deve tornare None, non sollevare.
        assert _denominazione_cedente("\x00\x04\x82\x01\x00binario") is None
