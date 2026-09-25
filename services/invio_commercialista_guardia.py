"""La guardia dell'invio al commercialista: mai una fattura di un cliente al
commercialista di un altro (fase B del piano, 25/09/2026).

Una sola violazione blocca l'INTERO invio di quel cliente: niente «salto il
documento sospetto e mando il resto». I motivi (`GuardiaViolata.codice`) non
contengono dati personali: finiscono nel registro e negli avvisi.

L'ordine, dal database ai byte:
  1. la P.IVA della configurazione e' solo di quel cliente, su `ristoranti` E su
     `piva_ristoranti` (il trigger che tiene la seconda non segue lo spostamento di
     una sede fra account);
  2. l'azienda su Invoicetronic ha quell'id e quella P.IVA (con la chiave in uso);
  3. OGNI documento dell'elenco — prima di scegliere il periodo — e' di
     quell'azienda e ha quel destinatario;
  4. la coda locale torna con l'elenco: ogni fattura SDI gia' arrivata a OneFlux
     per questa P.IVA c'e', e nessuna riga di quell'azienda e' di un altro cliente;
  5. per ogni documento scaricato: XML o busta P7M riconosciuti dai BYTE (Invoicetronic
     annuncia a volte P7M come «Xml»), busta aperta solo con asn1crypto e senza
     ripieghi (quelli di invoice_service possono alterare l'XML), struttura della
     FatturaPA con UN solo CessionarioCommittente, IdPaese IT e IdCodice di
     esattamente 11 cifre uguale alla P.IVA, e la stessa P.IVA letta dalla regex del
     webhook. Nello ZIP va il file originale, non l'XML estratto.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from services import routing_coda

FORMATI = {"FatturaElettronica": ("DatiAnagrafici",), "FatturaElettronicaSemplificata": ("IdentificativiFiscali",)}
_PROLOGO_ENCODING = re.compile(r"""^\s*<\?xml[^>]*?encoding\s*=\s*["']([A-Za-z0-9._-]+)["']""")
_SOLO_BASE64 = re.compile(rb"[A-Za-z0-9+/=\s]+")
_INIZIO_VUOTO = re.compile(rb"^(?:\xef\xbb\xbf|[ \t\r\n])+")


class GuardiaViolata(Exception):
    """L'invio non si fa. `codice` e' breve e senza dati personali."""

    def __init__(self, codice: str) -> None:
        super().__init__(codice)
        self.codice = codice


@dataclass(frozen=True)
class DocumentoVerificato:
    receive_id: int
    nome: str
    contenuto: bytes
    identificativo: Optional[str]


def controlla_proprieta_piva(sb, piva: str, user_id: str) -> None:
    from utils.supabase_paging import fetch_all

    sedi = fetch_all(sb.table("ristoranti").select("id,user_id").eq("partita_iva", piva).order("id"))
    registrate = fetch_all(sb.table("piva_ristoranti").select("id,user_id").eq("piva", piva).order("id"))
    utenti = {str(r.get("user_id")) for r in [*sedi, *registrate]}
    if not sedi or utenti != {str(user_id)}:
        raise GuardiaViolata("piva_non_solo_del_cliente")


def controlla_azienda(azienda: Optional[Dict[str, Any]], company_id: int, piva: str) -> None:
    if azienda is None:
        raise GuardiaViolata("azienda_assente_su_invoicetronic")
    if azienda.get("id") != company_id or str(azienda.get("vat") or "").upper() != f"IT{piva}":
        raise GuardiaViolata("azienda_diversa_su_invoicetronic")


def _committente_ok(committente: Any, piva: str) -> bool:
    return isinstance(committente, str) and committente.strip().upper() in {piva, f"IT{piva}"}


def controlla_elenco(documenti: Iterable[Dict[str, Any]], company_id: int, piva: str) -> None:
    for doc in documenti:
        if doc.get("company_id") != company_id:
            raise GuardiaViolata("documento_di_un_altra_azienda")
        if not _committente_ok(doc.get("committente"), piva):
            raise GuardiaViolata("documento_con_altro_destinatario")


def controlla_coda(sb, user_id: str, piva: str, company_id: int, ids_elenco: Set[int],
                   adesso: Optional[datetime] = None) -> None:
    """La coda locale conferma l'elenco: una lista che non contiene fatture che
    OneFlux ha gia' visto arrivare vuol dire chiave, ambiente o azienda sbagliati."""
    from utils.supabase_paging import fetch_all

    adesso = adesso or datetime.now(timezone.utc)
    da = (adesso - timedelta(days=700)).isoformat()
    righe = fetch_all(
        sb.table("fatture_queue")
        .select("id,user_id,piva_raw,payload_meta,created_at")
        .eq("source", "invoicetronic")
        .gte("created_at", da)
        .order("id")
    )
    for riga in righe:
        meta = riga.get("payload_meta") or {}
        azienda = meta.get("invoicetronic_company_id")
        nostra = azienda == company_id or (
            str(riga.get("user_id")) == str(user_id) and riga.get("piva_raw") == piva
        )
        if not nostra:
            continue
        if riga.get("user_id") is not None and str(riga.get("user_id")) != str(user_id):
            raise GuardiaViolata("azienda_con_fatture_di_un_altro_cliente")
        if azienda is not None and azienda != company_id:
            raise GuardiaViolata("fatture_del_cliente_su_un_altra_azienda")
        risorsa = meta.get("resource_id")
        if isinstance(risorsa, int) and not isinstance(risorsa, bool) and risorsa not in ids_elenco:
            raise GuardiaViolata("elenco_senza_fatture_gia_arrivate")


def byte_originali(documento: Dict[str, Any]) -> bytes:
    payload = documento.get("payload")
    if not isinstance(payload, str) or not payload:
        raise GuardiaViolata("documento_vuoto")
    if str(documento.get("encoding") or "").lower() == "base64":
        try:
            return base64.b64decode(re.sub(r"\s+", "", payload), validate=True)
        except (binascii.Error, ValueError):
            raise GuardiaViolata("base64_non_valido") from None
    m = _PROLOGO_ENCODING.match(payload)
    try:
        return payload.encode(m.group(1) if m else "utf-8")
    except (LookupError, UnicodeEncodeError):
        raise GuardiaViolata("testo_non_codificabile") from None


def estrai_xml_da_busta(dati: bytes, livelli: int = 3) -> bytes:
    """Il contenuto di una busta CAdES, anche annidata, anche a pezzi. Solo
    asn1crypto: niente ricerche di pattern ne' pulizie di byte."""
    from asn1crypto import cms

    for _ in range(livelli):
        try:
            info = cms.ContentInfo.load(dati)
            if info["content_type"].native != "signed_data":
                raise ValueError
            contenuto = info["content"]["encap_content_info"]["content"].native
        except Exception:
            raise GuardiaViolata("busta_p7m_non_leggibile") from None
        if not contenuto:
            raise GuardiaViolata("busta_p7m_senza_contenuto")
        if contenuto[:1] != b"\x30":
            return contenuto
        dati = contenuto
    raise GuardiaViolata("busta_p7m_troppo_annidata")


def contenuto_xml(dati: bytes) -> tuple[bytes, bool]:
    """(XML, e' una busta P7M), deciso dai byte e non dall'etichetta."""
    testa = dati.lstrip(b"\xef\xbb\xbf \t\r\n")[:1]
    if testa == b"<":
        return dati, False
    if dati[:1] == b"\x30":
        return estrai_xml_da_busta(dati), True
    if dati and _SOLO_BASE64.fullmatch(dati):
        try:
            interno = base64.b64decode(re.sub(rb"\s+", b"", dati), validate=True)
        except (binascii.Error, ValueError):
            raise GuardiaViolata("formato_sconosciuto") from None
        if interno[:1] == b"\x30":
            return estrai_xml_da_busta(interno), True
    raise GuardiaViolata("formato_sconosciuto")


def _locale(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1].split(":")[-1]


def _figli(elemento, nome: str) -> List[Any]:
    return [f for f in list(elemento) if _locale(f.tag) == nome]


def _unico(elemento, nome: str, codice: str):
    trovati = _figli(elemento, nome) if elemento is not None else []
    if len(trovati) != 1:
        raise GuardiaViolata(codice)
    return trovati[0]


def controlla_documento(xml: bytes, piva: str) -> None:
    from defusedxml import ElementTree

    try:
        radice = ElementTree.fromstring(_INIZIO_VUOTO.sub(b"", xml), forbid_dtd=True)
    except Exception:
        raise GuardiaViolata("xml_non_leggibile") from None
    formato = _locale(radice.tag)
    if formato not in FORMATI:
        raise GuardiaViolata("non_e_una_fattura_elettronica")
    testata = _unico(radice, "FatturaElettronicaHeader", "testata_non_unica")
    cessionario = _unico(testata, "CessionarioCommittente", "destinatario_non_unico")
    if sum(1 for e in radice.iter() if _locale(e.tag) == "CessionarioCommittente") != 1:
        raise GuardiaViolata("destinatario_non_unico")
    (contenitore,) = FORMATI[formato]
    fiscale = _unico(_unico(cessionario, contenitore, "destinatario_senza_dati_fiscali"),
                     "IdFiscaleIVA", "destinatario_senza_partita_iva")
    paese = (_unico(fiscale, "IdPaese", "destinatario_senza_paese").text or "").strip()
    codice = (_unico(fiscale, "IdCodice", "destinatario_senza_codice").text or "").strip()
    if paese != "IT" or not re.fullmatch(r"[0-9]{11}", codice) or codice != piva:
        raise GuardiaViolata("destinatario_con_altra_partita_iva")
    testo = xml.decode(_codifica(xml), errors="strict")
    if routing_coda.estrai_piva_destinatario(testo) != piva:
        raise GuardiaViolata("destinatario_letto_in_due_modi")


def _codifica(xml: bytes) -> str:
    if xml.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    m = _PROLOGO_ENCODING.match(xml[:200].decode("latin-1"))
    return m.group(1) if m else "utf-8"


_NOME_PULITO = re.compile(r"[^A-Za-z0-9._-]")


def nome_nello_zip(receive_id: int, file_name: Any, busta: bool) -> str:
    nome = re.split(r"[\\/]", str(file_name or ""))[-1]
    nome = _NOME_PULITO.sub("", nome).lstrip(".")[:150]
    if not nome:
        nome = f"{receive_id}.xml"
    minuscolo = nome.lower()
    if busta and not minuscolo.endswith(".p7m"):
        nome += ".p7m"
    elif not busta and minuscolo.endswith(".p7m"):
        nome = nome[:-4]
    if not nome.lower().endswith((".xml", ".xml.p7m")):
        nome = nome[:-4] + ".xml.p7m" if busta else nome + ".xml"
    return nome


def verifica_documento(documento: Dict[str, Any], company_id: int, piva: str) -> DocumentoVerificato:
    """Livelli 3 e 5 su un documento scaricato: il record scaricato si ricontrolla
    (potrebbe non essere quello dell'elenco), poi i byte."""
    controlla_elenco([documento], company_id, piva)
    dati = byte_originali(documento)
    xml, busta = contenuto_xml(dati)
    controlla_documento(xml, piva)
    return DocumentoVerificato(
        receive_id=documento["id"],
        nome=nome_nello_zip(documento["id"], documento.get("file_name"), busta),
        contenuto=dati,
        identificativo=documento.get("identifier"),
    )


class FiltroDoppioni:
    """Lo stesso file SDI una volta sola, un documento alla volta (l'arretrato di
    due anni non sta in memoria): ricorda solo l'impronta di cio' che ha tenuto.
    Stesso identificativo SDI o stesso nome con contenuto identico: e' un doppione
    e si tiene il primo. Stesso nome o identificativo con contenuto diverso:
    blocco (il commercialista non deve scegliere lui)."""

    def __init__(self) -> None:
        self._per_nome: Dict[str, bytes] = {}
        self._per_id_sdi: Dict[str, bytes] = {}

    def ammetti(self, doc: DocumentoVerificato) -> bool:
        impronta = hashlib.sha256(doc.contenuto).digest()
        if doc.identificativo and doc.identificativo in self._per_id_sdi:
            if self._per_id_sdi[doc.identificativo] != impronta:
                raise GuardiaViolata("stesso_identificativo_sdi_contenuto_diverso")
            return False
        gia = self._per_nome.get(doc.nome.lower())
        if gia is not None:
            if gia != impronta:
                raise GuardiaViolata("stesso_nome_contenuto_diverso")
            return False
        self._per_nome[doc.nome.lower()] = impronta
        if doc.identificativo:
            self._per_id_sdi[doc.identificativo] = impronta
        return True


def senza_doppioni(documenti: Iterable[DocumentoVerificato]) -> List[DocumentoVerificato]:
    filtro = FiltroDoppioni()
    return [doc for doc in documenti if filtro.ammetti(doc)]
