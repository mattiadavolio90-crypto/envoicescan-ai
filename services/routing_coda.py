"""Il cliente di una fattura SDI, deciso dall'XML: il gemello Python del webhook.

Perche' esiste: quando la GET a Invoicetronic fallisce nel webhook (saldo
esaurito, 404 transitorio, timeout) la riga di `fatture_queue` nasce senza
cliente (`user_id` NULL, `piva_raw` 'UNKNOWN'). Il worker riscarica l'XML ma
fino al 25/09/2026 si fermava a «Tenant non risolto» e la riga moriva `dead`:
«Riprova» la rimetteva in coda e lei moriva di nuovo.

Qui si decide il cliente come fa `supabase/functions/invoicetronic-webhook/
index.ts` (extractPivaDestinatario, normalizePivaForMatch, extractIndirizzo*,
extractDocMeta, lo smistamento fra sedi con i candidati di ripiego): le funzioni
sono un porting riga per riga, e `routing_parita.json` accanto al webhook le
tiene allineate — lo leggono sia i test Python sia quelli Deno.

Due scarti VOLUTI dal webhook, entrambi verso il non assegnare:
  - la P.IVA si legge due volte, con la regex del webhook e con un parser XML
    vero: si assegna solo se coincidono (la regex prende il primo IdCodice del
    blocco, anche quello del RappresentanteFiscale o di un commento);
  - se le sedi con quella P.IVA stanno su piu' account non si assegna niente
    (il webhook prende l'utente della sede piu' recente e la sede dal punteggio,
    che puo' essere di un altro utente).

`services/multisede_routing.py` resta quello dell'upload manuale: non ha i
candidati di ripiego e normalizza la P.IVA in un altro modo.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

MIN_SCORE = 0.40
MIN_GAP = 0.20

_BLOCCO_CESSIONARIO = re.compile(r"<CessionarioCommittente\b[^>]*>([\s\S]*?)</CessionarioCommittente>")
_BLOCCO_SEDE = re.compile(r"<Sede\b[^>]*>([\s\S]*?)</Sede>")
_BLOCCO_BODY = re.compile(r"<FatturaElettronicaBody\b[^>]*>([\s\S]*?)</FatturaElettronicaBody>")
_BLOCCO_CEDENTE = re.compile(r"<CedentePrestatore\b[^>]*>([\s\S]*?)</CedentePrestatore>")
_ID_CODICE = re.compile(r"<IdCodice>\s*([A-Z0-9\s]{1,28})\s*</IdCodice>", re.I)
_CODICE_FISCALE = re.compile(r"<CodiceFiscale>\s*([A-Z0-9]{11,16})\s*</CodiceFiscale>", re.I)
_ID_CODICE_CEDENTE = re.compile(r"<IdCodice>\s*([A-Z0-9]{1,28})\s*</IdCodice>")
_NUMERO_INIZIALE = re.compile(r"^\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")

# `\b` di JavaScript senza flag `u` e' solo ASCII: re.ASCII lo riproduce («Vò»).
_ABBREVIAZIONI = (
    (re.compile(r"\bv\.?le\b", re.ASCII), "viale"),
    (re.compile(r"\bc\.?so\b", re.ASCII), "corso"),
    (re.compile(r"\bp\.?(zza|za)\b", re.ASCII), "piazza"),
    (re.compile(r"\bv\.?\b", re.ASCII), "via"),
    (re.compile(r"\bstr\.?\b", re.ASCII), "strada"),
)


def _tag_foglia(nome: str, testo: str, maiuscole: bool = False) -> Optional[str]:
    flag = 0 if maiuscole else re.I
    m = re.search(rf"<{nome}>\s*([^<]+?)\s*</{nome}>", testo, flag)
    return m.group(1) if m else None


def normalizza_piva_per_match(raw: str) -> str:
    """normalizePivaForMatch: le cifre se sono esattamente 11, altrimenti il
    valore com'era."""
    ripulita = re.sub(r"[^0-9A-Za-z]", "", re.sub(r"^IT", "", raw, flags=re.I))
    cifre = re.sub(r"[^0-9]", "", ripulita)
    return cifre if len(cifre) == 11 else raw


def estrai_piva_destinatario(xml: str) -> Optional[str]:
    """extractPivaDestinatario: primo IdCodice del blocco CessionarioCommittente,
    altrimenti il CodiceFiscale com'e' scritto."""
    blocco = _BLOCCO_CESSIONARIO.search(xml)
    if not blocco:
        return None
    m = _ID_CODICE.search(blocco.group(1))
    id_codice = m.group(1).strip() if m else ""
    if id_codice:
        return normalizza_piva_per_match(id_codice)
    m = _CODICE_FISCALE.search(blocco.group(1))
    cf = m.group(1).strip() if m else ""
    return cf or None


def _nome_locale(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def _figlio(elemento, nome: str):
    for f in list(elemento):
        if _nome_locale(f.tag) == nome:
            return f
    return None


def estrai_piva_destinatario_strutturata(xml: str) -> Optional[str]:
    """La stessa P.IVA letta con un parser XML vero, dal percorso che la
    FatturaPA prescrive: CessionarioCommittente/DatiAnagrafici/IdFiscaleIVA/
    IdCodice, poi DatiAnagrafici/CodiceFiscale. None se l'XML non si legge."""
    from defusedxml import ElementTree

    # Un BOM o degli spazi prima di <?xml fanno fallire expat, non il webhook
    # (TextDecoder toglie il BOM e la regex non guarda l'inizio).
    testo = xml.lstrip().lstrip("\ufeff").lstrip()
    try:
        radice = ElementTree.fromstring(testo, forbid_dtd=True)
    except Exception:
        try:
            radice = ElementTree.fromstring(testo.encode("utf-8"), forbid_dtd=True)
        except Exception:
            return None
    cessionario = next((e for e in radice.iter() if _nome_locale(e.tag) == "CessionarioCommittente"), None)
    if cessionario is None:
        return None
    anagrafici = _figlio(cessionario, "DatiAnagrafici")
    if anagrafici is None:
        return None
    fiscale = _figlio(anagrafici, "IdFiscaleIVA")
    codice = _figlio(fiscale, "IdCodice") if fiscale is not None else None
    if codice is not None and (codice.text or "").strip():
        return normalizza_piva_per_match(codice.text.strip())
    cf = _figlio(anagrafici, "CodiceFiscale")
    testo = (cf.text or "").strip() if cf is not None else ""
    return testo if re.fullmatch(r"[A-Z0-9]{11,16}", testo, re.I) else None


def piva_destinatario_verificata(xml: str) -> Optional[str]:
    """La P.IVA su cui smistare, solo se la regex del webhook e il parser XML
    dicono la stessa cosa. Una fattura che si legge in due modi diversi non si
    assegna a nessuno: meglio ferma che dal cliente sbagliato."""
    a = estrai_piva_destinatario(xml)
    b = estrai_piva_destinatario_strutturata(xml)
    return a if a is not None and a == b else None


def estrai_indirizzo_destinatario(xml: str) -> Optional[str]:
    """extractIndirizzoDestinatario: Indirizzo, NumeroCivico, CAP e Comune della
    Sede del destinatario (o dell'intero blocco se la Sede manca)."""
    blocco = _BLOCCO_CESSIONARIO.search(xml)
    if not blocco:
        return None
    m = _BLOCCO_SEDE.search(blocco.group(1))
    sede = m.group(1) if m else blocco.group(1)
    parti = [(_tag_foglia(n, sede) or "").strip() for n in ("Indirizzo", "NumeroCivico", "CAP", "Comune")]
    unito = " ".join(p for p in parti if p).strip()
    return unito or None


def estrai_indirizzo_candidati(xml: str) -> List[str]:
    """extractIndirizzoCandidati: la Sede, poi RiferimentoTesto, Causale e
    Descrizione del primo body, senza doppioni e senza testi sotto i 4 caratteri."""
    candidati: List[str] = []

    def aggiungi(testo: Optional[str]) -> None:
        v = (testo or "").strip()
        if len(v) >= 4 and v not in candidati:
            candidati.append(v)

    aggiungi(estrai_indirizzo_destinatario(xml))
    m = _BLOCCO_BODY.search(xml)
    body = m.group(1) if m else xml
    for nome in ("RiferimentoTesto", "Causale", "Descrizione"):
        for t in re.finditer(rf"<{nome}>\s*([^<]+?)\s*</{nome}>", body, re.I):
            aggiungi(t.group(1).strip())
    return candidati


def normalizza_indirizzo(raw: str) -> str:
    """normalizeIndirizzo."""
    testo = raw.lower()
    for regola, sostituto in _ABBREVIAZIONI:
        testo = regola.sub(sostituto, testo)
    testo = re.sub(r"[^a-z0-9 ]", " ", testo)
    return re.sub(r"\s+", " ", testo).strip()


def indirizzo_similarity(a: str, b: str) -> float:
    """indirizzoSimilarity: indice di Dice sui token."""
    ta = {t for t in a.split(" ") if t}
    tb = {t for t in b.split(" ") if t}
    if not ta or not tb:
        return 0.0
    return (2 * len(ta & tb)) / (len(ta) + len(tb))


def _parse_float_js(testo: str) -> Optional[float]:
    m = _NUMERO_INIZIALE.match(testo)
    return float(m.group(0)) if m else None


def estrai_meta_documento(xml: str) -> Dict[str, Any]:
    """extractDocMeta. Le chiavi che in TypeScript restano `undefined` qui non
    ci sono; un importo non numerico (NaN, che JSON scrive null) e' None."""
    blocco = _BLOCCO_CEDENTE.search(xml)
    m = _ID_CODICE_CEDENTE.search(blocco.group(1) if blocco else "")
    valori: Dict[str, Any] = {
        "tipo_documento": _tag_foglia("TipoDocumento", xml, maiuscole=True),
        "data_fattura": _tag_foglia("Data", xml, maiuscole=True),
        "numero_fattura": _tag_foglia("Numero", xml, maiuscole=True),
        "piva_cedente": m.group(1).strip() if m else None,
    }
    meta = {k: v for k, v in valori.items() if v is not None}
    importo = _tag_foglia("ImportoTotaleDocumento", xml, maiuscole=True)
    if importo is not None:
        meta["importo_totale"] = _parse_float_js(importo)
    return meta


def _punteggio(candidato: str, sedi: List[Dict[str, Any]]) -> Dict[str, Any]:
    bersaglio = normalizza_indirizzo(candidato) if candidato else ""
    ordinate = sorted(
        (
            {
                "id": s["id"],
                "score": indirizzo_similarity(bersaglio, s["indirizzo_match"])
                if bersaglio and s.get("indirizzo_match") else 0,
            }
            for s in sedi
        ),
        key=lambda x: -x["score"],
    )
    migliore = ordinate[0]
    secondo = ordinate[1]["score"] if len(ordinate) > 1 else 0
    return {"migliore": migliore, "gap": migliore["score"] - secondo}


def _passa(decisione: Dict[str, Any]) -> bool:
    return decisione["migliore"]["score"] >= MIN_SCORE and decisione["gap"] >= MIN_GAP


def decidi_cliente(xml: str, sedi: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Lo smistamento del webhook sulle sedi attive con quella P.IVA, ordinate
    dalla piu' recente. `sedi` sono righe di `ristoranti` con almeno user_id,
    id e indirizzo_match.

    Esiti:
      - `sconosciuta`: nessuna sede → la riga va in unknown_tenant;
      - `piu_account`: le sedi stanno su piu' utenti → non si assegna (scarto voluto);
      - `assegnata`: user_id + ristorante_id (+ routing se le sedi erano piu' d'una);
      - `da_assegnare`: piu' sedi e nessun indirizzo decisivo → sceglie il cliente.
    """
    if not sedi:
        return {"esito": "sconosciuta"}
    utenti = {str(s["user_id"]) for s in sedi}
    if len(utenti) > 1:
        return {"esito": "piu_account", "sedi_count": len(sedi)}
    user_id = str(sedi[0]["user_id"])
    if len(sedi) == 1:
        return {"esito": "assegnata", "user_id": user_id, "ristorante_id": str(sedi[0]["id"])}

    sede = _punteggio(estrai_indirizzo_destinatario(xml) or "", sedi)
    if _passa(sede):
        return {
            "esito": "assegnata", "user_id": user_id, "ristorante_id": str(sede["migliore"]["id"]),
            "routing": {"mode": "auto", "source": "sede", "score": sede["migliore"]["score"], "gap": sede["gap"]},
        }
    candidati = estrai_indirizzo_candidati(xml)
    for candidato in candidati:
        d = _punteggio(candidato, sedi)
        if _passa(d):
            return {
                "esito": "assegnata", "user_id": user_id, "ristorante_id": str(d["migliore"]["id"]),
                "routing": {"mode": "auto", "source": "fallback", "score": d["migliore"]["score"], "gap": d["gap"]},
                "indirizzo_fallback": candidato,
            }
    return {
        "esito": "da_assegnare", "user_id": user_id,
        "routing": {
            "mode": "manual", "best_score": sede["migliore"]["score"], "gap": sede["gap"],
            "sedi_count": len(sedi), "fallback_tried": len(candidati),
        },
    }
