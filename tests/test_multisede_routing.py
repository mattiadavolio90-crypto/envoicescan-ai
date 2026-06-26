"""Unit dello smistamento multi-sede (services/multisede_routing.py).

Gemelli 1:1 di `supabase/functions/invoicetronic-webhook/routing_test.ts`: gli
output sono hardcodati IDENTICI al TS, cosi' un drift fra le tre implementazioni
(Python / TypeScript / SQL) rompe il test. Include lo scenario reale OFFSIDE
(2 sedi, stessa P.IVA) con gli indirizzo_match presi dal DB.
"""
import sys
import importlib
from unittest.mock import MagicMock

# conftest.py mocka xmltodict globalmente (modulo "pesante"). Qui ci serve quello
# VERO per parsare gli XML di esempio: lo ripristiniamo dal pacchetto installato.
if isinstance(sys.modules.get("xmltodict"), MagicMock):
    del sys.modules["xmltodict"]
import xmltodict  # noqa: E402
if isinstance(xmltodict, MagicMock):  # difensivo: se non installato, ricarica
    xmltodict = importlib.import_module("xmltodict")

from services.multisede_routing import (  # noqa: E402
    normalizza_indirizzo,
    estrai_indirizzo_destinatario,
    indirizzo_similarity,
    decidi_sede,
    MIN_SCORE,
    MIN_GAP,
)


def _parse(xml: str) -> dict:
    """Replica come estrai_dati_da_xml ottiene il dict 'fattura' (senza root)."""
    doc = xmltodict.parse(xml)
    keys = list(doc.keys())
    if not keys:
        return {}
    val = doc[keys[0]]
    return val if isinstance(val, dict) else {}


# ─── normalizza_indirizzo: allineata a normalizeIndirizzo (TS) e alla SQL ──────

def test_normalizza_lowercase_alfanumerici_spazi():
    assert normalizza_indirizzo("Via Roma 1") == "via roma 1"
    assert normalizza_indirizzo("VIA ROMA 1/A") == "via roma 1 a"
    assert normalizza_indirizzo("Corso Italia 22,  20100   Milano") == "corso italia 22 20100 milano"


def test_normalizza_espande_abbreviazioni():
    assert normalizza_indirizzo("V.le Roma 1") == "viale roma 1"
    assert normalizza_indirizzo("C.so Buenos Aires 5") == "corso buenos aires 5"
    assert normalizza_indirizzo("P.zza Duomo") == "piazza duomo"
    assert normalizza_indirizzo("V. Verdi 3") == "via verdi 3"


def test_normalizza_vuoto():
    assert normalizza_indirizzo("") == ""
    assert normalizza_indirizzo(None) == ""


# ─── indirizzo_similarity: Dice sui token ─────────────────────────────────────

def test_similarity_identici_uno():
    assert indirizzo_similarity("via roma 1 20100 milano", "via roma 1 20100 milano") == 1.0


def test_similarity_varianti_stessa_via_alto():
    a = normalizza_indirizzo("Via Roma 1 20100 Milano")
    b = normalizza_indirizzo("V.le Roma, 1 - 20100 Milano")
    assert indirizzo_similarity(a, b) >= 0.6


def test_similarity_sedi_diverse_basso():
    a = normalizza_indirizzo("Via Garibaldi 10 20100 Milano")
    b = normalizza_indirizzo("Corso Francia 250 10100 Torino")
    assert indirizzo_similarity(a, b) < 0.2


def test_similarity_vuoto_zero():
    assert indirizzo_similarity("", "via roma 1") == 0.0
    assert indirizzo_similarity("via roma 1", "") == 0.0


# ─── estrai_indirizzo_destinatario: Sede del Cessionario, non del Cedente ──────

XML_SAMPLE = """<?xml version="1.0"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" versione="FPR12">
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <Sede>
        <Indirizzo>Via del Fornitore</Indirizzo>
        <NumeroCivico>99</NumeroCivico>
        <CAP>00100</CAP>
        <Comune>Roma</Comune>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>07863990961</IdCodice></IdFiscaleIVA>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Garibaldi</Indirizzo>
        <NumeroCivico>10</NumeroCivico>
        <CAP>20100</CAP>
        <Comune>Milano</Comune>
        <Provincia>MI</Provincia>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
</p:FatturaElettronica>"""


def test_estrai_prende_cessionario_non_cedente():
    ind = estrai_indirizzo_destinatario(_parse(XML_SAMPLE))
    assert ind is not None
    assert "Garibaldi" in ind
    assert "Milano" in ind
    assert "Fornitore" not in ind  # mai l'indirizzo del cedente
    assert "Roma" not in ind


def test_estrai_senza_cessionario_none():
    assert estrai_indirizzo_destinatario(_parse("<x>niente</x>")) is None


# ─── decidi_sede: scenario reale OFFSIDE (2 sedi, stessa P.IVA) ────────────────
# indirizzo_match presi dal DB (calcolati dal trigger SQL).
SEDI_OFFSIDE = [
    {"id": "pub", "nome_ristorante": "OFFSIDE SPORTS PUB", "indirizzo_match": "via losanna 46 20154 milano"},
    {"id": "ov", "nome_ristorante": "OVERTIME", "indirizzo_match": "via luigi settembrini 36 20124 milano"},
]


def test_offside_fattura_losanna_va_al_pub():
    d = decidi_sede("Via Losanna 46 20154 Milano", SEDI_OFFSIDE)
    assert d["mode"] == "auto"
    assert d["ristorante_id"] == "pub"
    assert d["gap"] >= MIN_GAP


def test_offside_fattura_settembrini_va_a_overtime():
    d = decidi_sede("VIA LUIGI SETTEMBRINI, 36 - 20124 MILANO (MI)", SEDI_OFFSIDE)
    assert d["mode"] == "auto"
    assert d["ristorante_id"] == "ov"
    assert d["gap"] >= MIN_GAP


def test_offside_indirizzo_generico_ambiguo():
    # Indirizzo che non somiglia a nessuna delle due sedi -> sotto MIN_SCORE.
    d = decidi_sede("Via Mazzini 1 20100 Milano", SEDI_OFFSIDE)
    assert d["mode"] == "ambiguo"


def test_offside_indirizzo_assente_ambiguo():
    d = decidi_sede(None, SEDI_OFFSIDE)
    assert d["mode"] == "ambiguo"


def test_decidi_best_sotto_soglia_ambiguo():
    # Solo "milano" in comune -> score basso < MIN_SCORE.
    sedi = [{"id": "a", "nome_ristorante": "A", "indirizzo_match": "via losanna 46 20154 milano"}]
    d = decidi_sede("Milano", sedi)
    assert d["mode"] == "ambiguo"
    assert d["best_score"] < MIN_SCORE


def test_decidi_gap_insufficiente_ambiguo():
    # Due sedi con indirizzo_match quasi identico -> gap < MIN_GAP anche se score alto.
    sedi = [
        {"id": "a", "nome_ristorante": "A", "indirizzo_match": "via roma 1 20100 milano"},
        {"id": "b", "nome_ristorante": "B", "indirizzo_match": "via roma 1 20100 milano"},
    ]
    d = decidi_sede("Via Roma 1 20100 Milano", sedi)
    assert d["mode"] == "ambiguo"
    assert d["gap"] < MIN_GAP
