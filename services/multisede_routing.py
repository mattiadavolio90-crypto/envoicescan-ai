"""Smistamento fatture per indirizzo fra sedi con la STESSA P.IVA.

Gemella Python della logica del webhook SDI. Tre implementazioni DEVONO restare
allineate (stesse abbreviazioni toponomastiche, stesse soglie, stessa similarità):

  1. TypeScript — `supabase/functions/invoicetronic-webhook/index.ts`
       extractIndirizzoDestinatario / normalizeIndirizzo / indirizzoSimilarity
       + decisione MIN_SCORE=0.40, MIN_GAP=0.20.
  2. SQL — `supabase/migrations/20260611140000_multi_sede_routing.sql`
       normalizza_indirizzo_match() + trigger che popola ristoranti.indirizzo_match.
  3. Questo modulo — usato dall'upload MANUALE (browser→worker), che a differenza
       del webhook non passa dalla coda ma salva diretto in `fatture`.

Spec di riferimento (mantenere verdi): la suite Deno `routing_test.ts`. I test
Python `tests/test_multisede_routing.py` ne replicano gli scenari con output
hardcodati per intercettare qualsiasi drift fra le tre implementazioni.

Il confronto avviene fra l'indirizzo del CessionarioCommittente normalizzato e
`ristoranti.indirizzo_match` (gia' normalizzato dal trigger SQL). Se quel campo
fosse popolato a mano in forma NON normalizzata, il match degrada: deve sempre
essere output di normalizza_indirizzo_match().
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from utils.formatters import safe_get

# Soglie identiche al webhook (index.ts 611-612):
#   - il match migliore deve superare MIN_SCORE (somiglianza minima)
#   - e distanziare il secondo di almeno MIN_GAP (nessuna ambiguita')
MIN_SCORE = 0.40
MIN_GAP = 0.20


def normalizza_indirizzo(raw: str) -> str:
    """Forma confrontabile di un indirizzo. Gemella di normalizeIndirizzo (TS).

    Ordine critico: le abbreviazioni specifiche (v.le, c.so, p.zza) vanno espanse
    PRIMA di `v.→via`, altrimenti `v.le` diventerebbe `viae`. Identico al TS e
    alla SQL normalizza_indirizzo_match.
    """
    if not raw:
        return ""
    s = raw.lower()
    s = re.sub(r"\bv\.?le\b", "viale", s)
    s = re.sub(r"\bc\.?so\b", "corso", s)
    s = re.sub(r"\bp\.?(zza|za)\b", "piazza", s)
    s = re.sub(r"\bv\.?\b", "via", s)
    s = re.sub(r"\bstr\.?\b", "strada", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def estrai_indirizzo_destinatario(fattura: Dict[str, Any]) -> Optional[str]:
    """Indirizzo del CessionarioCommittente (chi RICEVE), mai del Cedente.

    Gemella di extractIndirizzoDestinatario (TS), ma su dict xmltodict. Concatena
    Indirizzo + NumeroCivico + CAP + Comune della <Sede> del destinatario.
    Ritorna None se non c'e' un CessionarioCommittente con Sede valorizzata.
    """
    sede = safe_get(
        fattura,
        ["FatturaElettronicaHeader", "CessionarioCommittente", "Sede"],
        default=None,
        keep_list=False,
    )
    if not isinstance(sede, dict):
        # Fallback: alcuni XML annidano diversamente (senza Header esplicito).
        sede = safe_get(
            fattura,
            ["CessionarioCommittente", "Sede"],
            default=None,
            keep_list=False,
        )
    if not isinstance(sede, dict):
        return None

    def _f(chiave: str) -> str:
        v = sede.get(chiave)
        return str(v).strip() if v is not None else ""

    parti = [_f("Indirizzo"), _f("NumeroCivico"), _f("CAP"), _f("Comune")]
    joined = " ".join(p for p in parti if p).strip()
    return joined or None


def indirizzo_similarity(a: str, b: str) -> float:
    """Similarita' di Dice sui token (parole): 2*|inter| / (|A|+|B|). [0..1].

    Robusta a parole in piu'/in meno e all'ordine. Scelta su token (non bigrammi
    di caratteri) perche' le sedi hanno indirizzi completamente diversi: il
    segnale forte e' quante parole-chiave coincidono. Gemella di indirizzoSimilarity (TS).
    """
    ta = {t for t in a.split(" ") if t}
    tb = {t for t in b.split(" ") if t}
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return (2 * inter) / (len(ta) + len(tb))


def decidi_sede(indirizzo_raw: Optional[str], sedi: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sceglie la sede di destinazione dall'indirizzo in fattura. Gemella della
    decisione del webhook (index.ts 614-643).

    sedi: lista di dict con almeno {id, nome_ristorante, indirizzo_match}.

    Ritorna:
      {mode: 'auto', ristorante_id, nome, best_score, gap}  se match univoco
      {mode: 'ambiguo', best_score, gap}                    altrimenti
    """
    target = normalizza_indirizzo(indirizzo_raw or "")
    scored = sorted(
        (
            {
                "id": s.get("id"),
                "nome": s.get("nome_ristorante"),
                "score": indirizzo_similarity(target, str(s.get("indirizzo_match") or "")),
            }
            for s in sedi
        ),
        key=lambda r: r["score"],
        reverse=True,
    )

    best = scored[0] if scored else {"score": 0.0}
    second = scored[1] if len(scored) > 1 else {"score": 0.0}
    best_score = best["score"]
    gap = best_score - second["score"]

    if best_score >= MIN_SCORE and gap >= MIN_GAP:
        return {
            "mode": "auto",
            "ristorante_id": best["id"],
            "nome": best["nome"],
            "best_score": round(best_score, 4),
            "gap": round(gap, 4),
        }
    return {"mode": "ambiguo", "best_score": round(best_score, 4), "gap": round(gap, 4)}


def _piva_norm(v: Any) -> str:
    """Solo le cifre della P.IVA (toglie spazi, prefisso IT eventuale, punteggiatura)."""
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def decidi_destinazione_upload(
    piva_dest: Optional[str],
    indirizzo_dest: Optional[str],
    sedi_attive: List[Dict[str, Any]],
    sede_attiva_id: Optional[str],
    bypass_guardia: bool = False,
) -> Dict[str, Any]:
    """Decide la sede di destinazione di una fattura caricata a mano.

    Logica unica (guardia P.IVA + smistamento), gemella concettuale del webhook:
      - P.IVA destinatario assente -> fallback alla sede attiva (XML anomalo: non
        scartare una fattura valida). mode='fallback'.
      - nessuna sede del cliente con quella P.IVA -> 'piva_estranea' (scartata):
        la fattura non e' del cliente / sede non configurata.
      - 1 sede con quella P.IVA -> 'auto' su quella sede (caso P.IVA-per-sede).
      - >=2 sedi con quella P.IVA (stessa P.IVA) -> distingui per indirizzo via
        decidi_sede(); 'auto' o 'ambiguo' (scartata).

    cross_sede = True quando la sede dedotta != sede attiva selezionata.

    `bypass_guardia` (ambienti di TEST): se True, la guardia P.IVA non scarta mai.
    Una P.IVA estranea o un caso ambiguo finiscono in 'fallback' sulla sede attiva
    invece di essere respinti. NON usare per i clienti reali (default False): la
    guardia protegge dal caricare fatture sulla sede sbagliata.

    Ritorna un dict con 'mode' in {'auto','fallback','piva_estranea','ambiguo'},
    e per auto/fallback: ristorante_id, nome, cross_sede.
    """
    if not piva_dest:
        return {
            "mode": "fallback",
            "ristorante_id": sede_attiva_id,
            "nome": None,
            "cross_sede": None,
        }

    piva_dest_n = _piva_norm(piva_dest)
    sedi_match = [s for s in sedi_attive if _piva_norm(s.get("partita_iva")) == piva_dest_n]

    if not sedi_match:
        if bypass_guardia:
            # Ambiente test: accetta comunque, tutto sulla sede attiva.
            return {
                "mode": "fallback",
                "ristorante_id": sede_attiva_id,
                "nome": None,
                "cross_sede": None,
            }
        return {"mode": "piva_estranea", "piva_dest": piva_dest_n}

    if len(sedi_match) == 1:
        rid = sedi_match[0].get("id")
        nome = sedi_match[0].get("nome_ristorante")
    else:
        decision = decidi_sede(indirizzo_dest, sedi_match)
        if decision["mode"] != "auto":
            if bypass_guardia:
                return {
                    "mode": "fallback",
                    "ristorante_id": sede_attiva_id,
                    "nome": None,
                    "cross_sede": None,
                }
            return {
                "mode": "ambiguo",
                "best_score": decision["best_score"],
                "gap": decision["gap"],
            }
        rid = decision["ristorante_id"]
        nome = decision["nome"]

    cross = bool(sede_attiva_id and str(rid) != str(sede_attiva_id))
    return {"mode": "auto", "ristorante_id": rid, "nome": nome, "cross_sede": cross}
