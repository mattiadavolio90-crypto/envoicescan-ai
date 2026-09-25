"""La guardia dell'invio al commercialista (fase B): mai una fattura di un
cliente al commercialista di un altro.

Una sola violazione blocca tutto l'invio. Qui i casi che i critici del disegno
hanno usato per provare a farla passare: rappresentante fiscale, paese estero
con le nostre 11 cifre, codice fiscale, due destinatari, commento ingannevole,
DTD, busta annidata o «a pezzi», etichetta di codifica che mente, nomi di file
con percorsi. Le buste P7M si firmano al volo (nessuna chiave nel repo), tranne
quella a pezzi, che la libreria non produce (fixture generata con openssl).
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pytest

from services import invio_commercialista_guardia as g

PIVA = "07863990961"
AZIENDA = 1756
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "invio_commercialista"


@lru_cache(maxsize=1)
def _firmatario():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    chiave = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "prova")])
    cert = (
        x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chiave.public_key())
        .serial_number(1).not_valid_before(datetime(2026, 1, 1)).not_valid_after(datetime(2027, 1, 1))
        .sign(chiave, hashes.SHA256())
    )
    return cert, chiave


def _busta(dati: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs7

    cert, chiave = _firmatario()
    return (
        pkcs7.PKCS7SignatureBuilder().set_data(dati).add_signer(cert, chiave, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
    )


def _fattura(cessionario=None, testata_extra="", body="", radice="p:FatturaElettronica", prologo='<?xml version="1.0" encoding="UTF-8"?>'):
    if cessionario is None:
        cessionario = (
            "<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese>"
            f"<IdCodice>{PIVA}</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>Caffè Rossi</Denominazione>"
            "</Anagrafica></DatiAnagrafici><Sede><Indirizzo>Via Roma</Indirizzo></Sede></CessionarioCommittente>"
        )
    ns = ' xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"' if radice.startswith("p:") else ""
    return (
        f'{prologo}<{radice}{ns} versione="FPR12"><FatturaElettronicaHeader>'
        "<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice>"
        f"</IdFiscaleIVA></DatiAnagrafici></CedentePrestatore>{cessionario}{testata_extra}</FatturaElettronicaHeader>"
        f"<FatturaElettronicaBody>{body}</FatturaElettronicaBody></{radice}>"
    )


def _anagrafici(paese="IT", codice=PIVA, cf=None):
    fiscale = f"<IdFiscaleIVA><IdPaese>{paese}</IdPaese><IdCodice>{codice}</IdCodice></IdFiscaleIVA>" if codice else ""
    cf_xml = f"<CodiceFiscale>{cf}</CodiceFiscale>" if cf else ""
    return f"<CessionarioCommittente><DatiAnagrafici>{fiscale}{cf_xml}</DatiAnagrafici></CessionarioCommittente>"


def _doc(contenuto: bytes, encoding="Base64", id_=42, **extra):
    payload = base64.b64encode(contenuto).decode() if encoding == "Base64" else contenuto.decode("utf-8")
    return {"id": id_, "company_id": AZIENDA, "committente": PIVA, "encoding": encoding, "payload": payload,
            "file_name": "IT01234567890_abc12.xml", **extra}


# ─── Azienda ed elenco ───────────────────────────────────────────────────────

def test_azienda_giusta_passa():
    g.controlla_azienda({"id": AZIENDA, "vat": "IT07863990961"}, AZIENDA, PIVA)


@pytest.mark.parametrize("azienda,codice", [
    (None, "azienda_assente_su_invoicetronic"),
    ({"id": 9, "vat": "IT07863990961"}, "azienda_diversa_su_invoicetronic"),
    ({"id": AZIENDA, "vat": "IT12345678903"}, "azienda_diversa_su_invoicetronic"),
    ({"id": AZIENDA, "vat": "07863990961"}, "azienda_diversa_su_invoicetronic"),
])
def test_azienda_sbagliata_blocca(azienda, codice):
    with pytest.raises(g.GuardiaViolata) as e:
        g.controlla_azienda(azienda, AZIENDA, PIVA)
    assert e.value.codice == codice


@pytest.mark.parametrize("committente", [PIVA, f"IT{PIVA}", f"it{PIVA}"])
def test_elenco_del_cliente_passa(committente):
    g.controlla_elenco([{"company_id": AZIENDA, "committente": committente}], AZIENDA, PIVA)


@pytest.mark.parametrize("doc,codice", [
    ({"company_id": 9, "committente": PIVA}, "documento_di_un_altra_azienda"),
    ({"company_id": AZIENDA, "committente": "12345678903"}, "documento_con_altro_destinatario"),
    ({"company_id": AZIENDA, "committente": f"DE{PIVA}"}, "documento_con_altro_destinatario"),
    ({"company_id": AZIENDA, "committente": None}, "documento_con_altro_destinatario"),
    ({"company_id": str(AZIENDA), "committente": PIVA}, "documento_di_un_altra_azienda"),
])
def test_un_solo_documento_estraneo_blocca_tutto_l_elenco(doc, codice):
    buoni = [{"company_id": AZIENDA, "committente": PIVA}] * 5
    with pytest.raises(g.GuardiaViolata) as e:
        g.controlla_elenco([*buoni, doc, *buoni], AZIENDA, PIVA)
    assert e.value.codice == codice


# ─── Byte e buste ────────────────────────────────────────────────────────────

def test_base64_con_spazi_si_decodifica():
    xml = _fattura().encode()
    doc = _doc(xml)
    doc["payload"] = "\n".join(doc["payload"][i:i + 60] for i in range(0, len(doc["payload"]), 60))
    assert g.byte_originali(doc) == xml


def test_base64_con_caratteri_estranei_blocca():
    with pytest.raises(g.GuardiaViolata, match="base64"):
        g.byte_originali({"payload": "PD94bWwg!!", "encoding": "Base64"})


def test_testo_dichiarato_iso_8859_1_resta_nella_sua_codifica():
    xml = _fattura(prologo='<?xml version="1.0" encoding="ISO-8859-1"?>')
    dati = g.byte_originali({"payload": xml, "encoding": "Xml"})
    assert dati == xml.encode("iso-8859-1") and "Caffè".encode("iso-8859-1") in dati


def test_testo_con_codifica_inesistente_blocca():
    with pytest.raises(g.GuardiaViolata, match="codificabile"):
        g.byte_originali({"payload": '<?xml version="1.0" encoding="x-inventata"?><a/>', "encoding": "Xml"})


def test_busta_riconosciuta_dai_byte_anche_se_annunciata_come_xml():
    xml = _fattura().encode()
    busta = _busta(xml)
    assert g.contenuto_xml(busta) == (xml, True)
    assert g.contenuto_xml(base64.b64encode(busta)) == (xml, True), "busta in base64 dentro un payload «Xml»"


def test_busta_annidata_si_apre_fino_all_xml():
    xml = _fattura().encode()
    assert g.estrai_xml_da_busta(_busta(_busta(xml))) == xml


def test_busta_a_pezzi_da_l_xml_identico_all_originale():
    busta = (FIXTURE / "busta_a_pezzi.p7m").read_bytes()
    xml = g.estrai_xml_da_busta(busta)
    assert hashlib.sha256(xml).hexdigest() == "1eb8e20d264e72f02fa4bf2ab32360d130572ea21a61524996a44526aadb836e"


def test_troppe_buste_annidate_bloccano():
    xml = _fattura().encode()
    with pytest.raises(g.GuardiaViolata, match="annidata"):
        g.estrai_xml_da_busta(_busta(_busta(_busta(_busta(xml)))))


@pytest.mark.parametrize("dati", [b"\x30\x03\x02\x01\x01", b"%PDF-1.4 ...", b"", b"\x00\x01\x02"])
def test_contenuto_non_riconosciuto_blocca(dati):
    with pytest.raises(g.GuardiaViolata):
        g.contenuto_xml(dati)


def test_bom_e_spazi_davanti_all_xml_sono_xml():
    xml = b"\xef\xbb\xbf\n" + _fattura().encode()
    assert g.contenuto_xml(xml) == (xml, False)
    g.controlla_documento(xml, PIVA)


# ─── Il documento: struttura severa ──────────────────────────────────────────

def test_fattura_ordinaria_del_cliente_passa():
    g.controlla_documento(_fattura().encode(), PIVA)


def test_fattura_semplificata_del_cliente_passa():
    cess = ("<CessionarioCommittente><IdentificativiFiscali><IdFiscaleIVA><IdPaese>IT</IdPaese>"
            f"<IdCodice>{PIVA}</IdCodice></IdFiscaleIVA></IdentificativiFiscali></CessionarioCommittente>")
    g.controlla_documento(_fattura(cess, radice="FatturaElettronicaSemplificata").encode(), PIVA)


@pytest.mark.parametrize("nome,xml,codice", [
    ("altra partita iva", _fattura(_anagrafici(codice="12345678903")), "destinatario_con_altra_partita_iva"),
    ("paese estero con le nostre cifre", _fattura(_anagrafici(paese="DE")), "destinatario_con_altra_partita_iva"),
    ("prefisso nel codice", _fattura(_anagrafici(codice=f"IT{PIVA}")), "destinatario_con_altra_partita_iva"),
    ("10 cifre", _fattura(_anagrafici(codice=PIVA[:10])), "destinatario_con_altra_partita_iva"),
    ("solo codice fiscale", _fattura(_anagrafici(codice=None, cf=PIVA)), "destinatario_senza_partita_iva"),
    ("rappresentante fiscale col nostro numero",
     _fattura("<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>12345678903</IdCodice>"
              f"</IdFiscaleIVA></DatiAnagrafici><RappresentanteFiscale><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{PIVA}"
              "</IdCodice></IdFiscaleIVA></RappresentanteFiscale></CessionarioCommittente>"),
     "destinatario_con_altra_partita_iva"),
    ("due destinatari nella testata", _fattura(_anagrafici() + _anagrafici(codice="12345678903")), "destinatario_non_unico"),
    ("un destinatario anche nel corpo", _fattura(body=_anagrafici(codice="12345678903")), "destinatario_non_unico"),
    ("commento ingannevole", _fattura(testata_extra=f"<!-- <CessionarioCommittente><IdCodice>{PIVA}</IdCodice></CessionarioCommittente> -->",
                                      cessionario=_anagrafici(codice="12345678903")), "destinatario_con_altra_partita_iva"),
    ("radice sbagliata", _fattura(radice="AltroDocumento"), "non_e_una_fattura_elettronica"),
    ("senza destinatario", _fattura(cessionario=""), "destinatario_non_unico"),
    ("con DTD", _fattura(prologo='<?xml version="1.0"?><!DOCTYPE p:FatturaElettronica>'), "xml_non_leggibile"),
    ("xml rotto", _fattura()[:-20], "xml_non_leggibile"),
])
def test_documento_non_del_cliente_blocca(nome, xml, codice):
    with pytest.raises(g.GuardiaViolata) as e:
        g.controlla_documento(xml.encode(), PIVA)
    assert e.value.codice == codice, nome


def test_regex_e_struttura_devono_dire_la_stessa_cosa():
    """Un commento PRIMA del blocco vero inganna la regex del webhook: la
    struttura legge la nostra P.IVA, la regex quella del commento → blocco."""
    xml = _fattura(testata_extra="").replace(
        "<FatturaElettronicaHeader>",
        "<FatturaElettronicaHeader><!-- <CessionarioCommittente><IdCodice>12345678903</IdCodice></CessionarioCommittente> -->",
    )
    with pytest.raises(g.GuardiaViolata) as e:
        g.controlla_documento(xml.encode(), PIVA)
    assert e.value.codice == "destinatario_letto_in_due_modi"


# ─── Nomi nello ZIP e doppioni ───────────────────────────────────────────────

@pytest.mark.parametrize("nome,busta,atteso", [
    ("IT01234567890_abc12.xml.p7m", True, "IT01234567890_abc12.xml.p7m"),
    ("IT01234567890_abc12.xml", False, "IT01234567890_abc12.xml"),
    ("IT01234567890_abc12.xml", True, "IT01234567890_abc12.xml.p7m"),
    ("IT01234567890_abc12.xml.p7m", False, "IT01234567890_abc12.xml"),
    ("..\\..\\Windows\\evil.xml", False, "evil.xml"),
    ("../../etc/passwd", False, "passwd.xml"),
    ("fattura<>:\"|?*.xml", False, "fattura.xml"),
    (None, False, "42.xml"),
    ("", True, "42.xml.p7m"),
    ("....", False, "42.xml"),
])
def test_nome_nello_zip(nome, busta, atteso):
    assert g.nome_nello_zip(42, nome, busta) == atteso


def test_nome_troppo_lungo_si_accorcia():
    assert len(g.nome_nello_zip(42, "a" * 500 + ".xml", False)) <= 160


def _v(nome, contenuto, sdi=None, id_=1):
    return g.DocumentoVerificato(receive_id=id_, nome=nome, contenuto=contenuto, identificativo=sdi)


def test_doppioni_identici_una_volta_sola():
    docs = [_v("a.xml", b"1", "S1", 1), _v("a.xml", b"1", None, 2), _v("b.xml", b"1", "S1", 3), _v("c.xml", b"2", "S2", 4)]
    assert [d.receive_id for d in g.senza_doppioni(docs)] == [1, 4]


@pytest.mark.parametrize("docs,codice", [
    ([_v("a.xml", b"1", "S1", 1), _v("b.xml", b"2", "S1", 2)], "stesso_identificativo_sdi_contenuto_diverso"),
    ([_v("a.xml", b"1", None, 1), _v("A.XML", b"2", None, 2)], "stesso_nome_contenuto_diverso"),
])
def test_stesso_file_con_contenuto_diverso_blocca(docs, codice):
    with pytest.raises(g.GuardiaViolata) as e:
        g.senza_doppioni(docs)
    assert e.value.codice == codice


# ─── Tutto insieme ───────────────────────────────────────────────────────────

def test_verifica_documento_busta_del_cliente():
    xml = _fattura().encode()
    busta = _busta(xml)
    v = g.verifica_documento(_doc(busta, file_name="IT01234567890_abc12.xml.p7m", identifier="SDI1"), AZIENDA, PIVA)
    assert v.contenuto == busta, "nello ZIP va la busta originale, non l'XML estratto"
    assert v.nome == "IT01234567890_abc12.xml.p7m" and v.receive_id == 42 and v.identificativo == "SDI1"


def test_verifica_documento_ricontrolla_il_record_scaricato():
    xml = _fattura().encode()
    with pytest.raises(g.GuardiaViolata, match="altra_azienda"):
        g.verifica_documento(_doc(xml, company_id=9), AZIENDA, PIVA)


def test_verifica_documento_busta_di_un_altro_cliente():
    busta = _busta(_fattura(_anagrafici(codice="12345678903")).encode())
    with pytest.raises(g.GuardiaViolata, match="altra_partita_iva"):
        g.verifica_documento(_doc(busta), AZIENDA, PIVA)
