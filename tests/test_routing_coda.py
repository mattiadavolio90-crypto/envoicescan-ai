"""Il cliente di una fattura SDI deciso dal worker, come lo decide il webhook (passo 0-bis).

`services/routing_coda.py` e' il porting Python del routing di
`supabase/functions/invoicetronic-webhook/index.ts`. Qui:
  - la PARITA': gli stessi esempi di `routing_parita.json`, che il test Deno
    `routing_parita_test.ts` ancora al TypeScript;
  - la DOPPIA LETTURA della P.IVA: si assegna solo se regex e parser XML
    coincidono (il file di parita' mostra che la regex del webhook si fa
    ingannare da un commento e dal RappresentanteFiscale);
  - lo SMISTAMENTO fra sedi, compresi i due scarti voluti dal webhook.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services import routing_coda as rc

PARITA = json.loads(
    (Path(__file__).resolve().parents[1] / "supabase" / "functions" / "invoicetronic-webhook" / "routing_parita.json")
    .read_text(encoding="utf-8")
)


def _casi(sezione, chiave="nome"):
    return pytest.mark.parametrize("caso", PARITA[sezione], ids=[str(c.get(chiave, c.get("input"))) for c in PARITA[sezione]])


# ─── Parita' col webhook ─────────────────────────────────────────────────────

@_casi("normalizza_piva", "input")
def test_parita_normalizza_piva(caso):
    assert rc.normalizza_piva_per_match(caso["input"]) == caso["atteso"]


@_casi("piva_destinatario")
def test_parita_piva_destinatario(caso):
    assert rc.estrai_piva_destinatario(caso["xml"]) == caso["atteso"]


@_casi("indirizzo_destinatario")
def test_parita_indirizzo_destinatario(caso):
    assert rc.estrai_indirizzo_destinatario(caso["xml"]) == caso["atteso"]


@_casi("indirizzo_candidati")
def test_parita_indirizzo_candidati(caso):
    assert rc.estrai_indirizzo_candidati(caso["xml"]) == caso["atteso"]


@_casi("normalizza_indirizzo", "input")
def test_parita_normalizza_indirizzo(caso):
    assert rc.normalizza_indirizzo(caso["input"]) == caso["atteso"]


@pytest.mark.parametrize("caso", PARITA["similarita"], ids=[f"{c['a']}|{c['b']}" for c in PARITA["similarita"]])
def test_parita_similarita(caso):
    assert rc.indirizzo_similarity(caso["a"], caso["b"]) == caso["atteso"]


@_casi("meta_documento")
def test_parita_meta_documento(caso):
    assert rc.estrai_meta_documento(caso["xml"]) == caso["atteso"]


def test_il_file_di_parita_copre_i_casi_che_contano():
    nomi = {c["nome"] for c in PARITA["piva_destinatario"]}
    assert {"commento_ingannevole", "trattino_e_rappresentante", "cdata", "solo_cf_persona", "estera_corta"} <= nomi
    assert any(c["atteso"] == [] or len(c["atteso"]) > 1 for c in PARITA["indirizzo_candidati"])


# ─── Doppia lettura della P.IVA ──────────────────────────────────────────────

def _xml(nome):
    return next(c["xml"] for c in PARITA["piva_destinatario"] if c["nome"] == nome)


@pytest.mark.parametrize("nome,atteso", [
    ("standard", "07863990961"),
    ("prefisso_e_spazi", "07863990961"),
    ("solo_cf_persona", "AAABBB00C11D222E"),
    ("solo_cf_numerico", "07863990961"),
    ("estera_corta", "DE123456789"),
])
def test_regex_e_parser_concordi_danno_la_piva(nome, atteso):
    assert rc.piva_destinatario_verificata(_xml(nome)) == atteso


@pytest.mark.parametrize("nome,regex,parser", [
    ("commento_ingannevole", "33333333333", "07863990961"),
    ("trattino_e_rappresentante", "11111111111", "07863990961"),
    ("cdata", None, "07863990961"),
    ("prefisso_namespace", None, None),
])
def test_regex_e_parser_discordi_non_assegnano(nome, regex, parser):
    xml = _xml(nome)
    assert rc.estrai_piva_destinatario(xml) == regex
    assert rc.estrai_piva_destinatario_strutturata(xml) == parser
    assert rc.piva_destinatario_verificata(xml) is None


@pytest.mark.parametrize("xml", ["", "non e' xml", "\x00\x01<FatturaElettronica", "<a><b></a>"])
def test_xml_illeggibile_non_assegna(xml):
    assert rc.estrai_piva_destinatario_strutturata(xml) is None
    assert rc.piva_destinatario_verificata(xml) is None


def test_senza_cessionario_nessuna_piva():
    xml = _xml("senza_cessionario")
    assert rc.estrai_piva_destinatario_strutturata(xml) is None
    assert rc.piva_destinatario_verificata(xml) is None


# ─── Smistamento fra sedi ────────────────────────────────────────────────────

U1 = "2f3f93a1-c1f4-4804-858e-a161e6f36f3f"
U2 = "9b9b9b9b-1111-4222-8333-444444444444"
SEDE_A = {"id": "aaaaaaaa-0000-4000-8000-000000000001", "user_id": U1, "indirizzo_match": "via roma 5 20100 milano"}
SEDE_B = {"id": "bbbbbbbb-0000-4000-8000-000000000002", "user_id": U1, "indirizzo_match": "viale monza 10 20127 milano"}
TECNICA = {"id": "cccccccc-0000-4000-8000-000000000003", "user_id": U1, "indirizzo_match": None}


def _fattura(sede_xml, body=""):
    return (
        '<?xml version="1.0" encoding="UTF-8"?><p:FatturaElettronica xmlns:p="x" versione="FPR12">'
        "<FatturaElettronicaHeader><CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese>"
        f"<IdCodice>07863990961</IdCodice></IdFiscaleIVA></DatiAnagrafici>{sede_xml}</CessionarioCommittente>"
        f"</FatturaElettronicaHeader><FatturaElettronicaBody>{body}</FatturaElettronicaBody></p:FatturaElettronica>"
    )


def _sede(indirizzo):
    return f"<Sede><Indirizzo>{indirizzo}</Indirizzo><CAP>00000</CAP><Comune>Luogo</Comune></Sede>"


def test_nessuna_sede_e_piva_sconosciuta():
    assert rc.decidi_cliente(_fattura(_sede("Via Roma 5")), []) == {"esito": "sconosciuta"}


def test_una_sede_si_assegna_senza_routing():
    d = rc.decidi_cliente(_fattura(_sede("Via Qualunque 1")), [SEDE_A])
    assert d == {"esito": "assegnata", "user_id": U1, "ristorante_id": SEDE_A["id"]}


def test_piu_sedi_la_sede_in_fattura_decide():
    xml = _fattura("<Sede><Indirizzo>Via Roma</Indirizzo><NumeroCivico>5</NumeroCivico><CAP>20100</CAP><Comune>Milano</Comune></Sede>")
    d = rc.decidi_cliente(xml, [TECNICA, SEDE_B, SEDE_A])
    assert d["esito"] == "assegnata" and d["ristorante_id"] == SEDE_A["id"] and d["user_id"] == U1
    assert d["routing"]["mode"] == "auto" and d["routing"]["source"] == "sede"
    assert d["routing"]["score"] == 1.0


def test_piu_sedi_sede_legale_in_fattura_decide_il_ripiego():
    xml = _fattura(_sede("Via Sede Legale 99"), "<DatiGenerali><DatiGeneraliDocumento><Causale>Consegna Viale Monza 10 20127 Milano</Causale></DatiGeneraliDocumento></DatiGenerali>")
    d = rc.decidi_cliente(xml, [SEDE_A, SEDE_B])
    assert d["esito"] == "assegnata" and d["ristorante_id"] == SEDE_B["id"]
    assert d["routing"]["source"] == "fallback"
    assert d["indirizzo_fallback"] == "Consegna Viale Monza 10 20127 Milano"


def test_vince_il_primo_candidato_che_passa_non_il_migliore():
    # RiferimentoTesto viene prima di Descrizione: passa con un punteggio
    # piu' basso e vince comunque, come col `break` del webhook.
    body = (
        "<DatiBeniServizi><DettaglioLinee><Descrizione>via roma 5 20100 milano</Descrizione>"
        "<AltriDatiGestionali><RiferimentoTesto>presso viale monza 10 20127 milano ingresso b piano terra</RiferimentoTesto>"
        "</AltriDatiGestionali></DettaglioLinee></DatiBeniServizi>"
    )
    d = rc.decidi_cliente(_fattura(_sede("Via Sede Legale 99"), body), [SEDE_A, SEDE_B])
    assert d["ristorante_id"] == SEDE_B["id"]
    assert d["routing"]["score"] < 1.0


def test_piu_sedi_nessun_indirizzo_decisivo_va_da_assegnare():
    d = rc.decidi_cliente(_fattura(_sede("Via Altrove 1"), "<Causale>Birra</Causale>"), [SEDE_A, SEDE_B])
    assert d["esito"] == "da_assegnare" and d["user_id"] == U1 and "ristorante_id" not in d
    assert d["routing"]["mode"] == "manual" and d["routing"]["sedi_count"] == 2
    assert d["routing"]["fallback_tried"] == 2, "la Sede e' il primo candidato, poi la Causale"


def test_sedi_di_piu_account_non_si_assegnano_mai():
    """Scarto voluto dal webhook: la stessa P.IVA su due utenti. Anche con un
    indirizzo che combacia perfettamente non si sceglie un cliente."""
    altra = {**SEDE_B, "user_id": U2}
    xml = _fattura("<Sede><Indirizzo>Viale Monza</Indirizzo><NumeroCivico>10</NumeroCivico><CAP>20127</CAP><Comune>Milano</Comune></Sede>")
    d = rc.decidi_cliente(xml, [SEDE_A, altra])
    assert d == {"esito": "piu_account", "sedi_count": 2}


def test_distacco_di_0_20_esatto_e_ambiguo_come_nel_webhook():
    """0.6 - 0.4 in virgola mobile e' 0.19999999999999996: il webhook non
    assegna, e nemmeno il porting."""
    sede_1 = {"id": "s1", "user_id": U1, "indirizzo_match": "a b c x y"}
    sede_2 = {"id": "s2", "user_id": U1, "indirizzo_match": "a b p q r"}
    xml = _fattura("<Sede><Indirizzo>a b c d e</Indirizzo></Sede>")
    punteggi = sorted(rc.indirizzo_similarity("a b c d e", s["indirizzo_match"]) for s in (sede_1, sede_2))
    assert punteggi == [0.4, 0.6]
    assert punteggi[1] - punteggi[0] < rc.MIN_GAP
    assert rc.decidi_cliente(xml, [sede_1, sede_2])["esito"] == "da_assegnare"


def test_punteggio_esattamente_0_40_basta_come_nel_webhook():
    """Il webhook confronta con >=: 2 token comuni su 5+5 danno 0.40 esatto, e
    col distacco pieno dalla seconda sede la fattura si assegna."""
    sede_1 = {"id": "s1", "user_id": U1, "indirizzo_match": "a b x y z"}
    sede_2 = {"id": "s2", "user_id": U1, "indirizzo_match": "q r s t u"}
    xml = _fattura("<Sede><Indirizzo>a b c d e</Indirizzo></Sede>")
    assert rc.indirizzo_similarity("a b c d e", "a b x y z") == rc.MIN_SCORE
    d = rc.decidi_cliente(xml, [sede_1, sede_2])
    assert d["esito"] == "assegnata" and d["ristorante_id"] == "s1"


@pytest.mark.parametrize("prefisso", ["﻿", "  \n", "﻿\n  ", "\n﻿"])
def test_bom_e_spazi_prima_della_dichiarazione_non_fermano_la_lettura(prefisso):
    """Expat rifiuta un BOM o degli spazi prima di <?xml; il webhook no
    (TextDecoder toglie il BOM, la regex non guarda l'inizio). Senza questa
    tolleranza la riga resterebbe in retry con la P.IVA giusta."""
    xml = prefisso + _xml("standard")
    assert rc.estrai_piva_destinatario_strutturata(xml) == "07863990961"
    assert rc.piva_destinatario_verificata(xml) == "07863990961"


def test_un_dtd_nell_xml_non_si_legge():
    xml = _xml("standard").replace('<?xml version="1.0" encoding="UTF-8"?>', '<?xml version="1.0"?><!DOCTYPE FatturaElettronica>')
    assert rc.estrai_piva_destinatario_strutturata(xml) is None
    assert rc.piva_destinatario_verificata(xml) is None
