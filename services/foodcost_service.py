"""
Foodcost service — calcolo ricette e ingredienti.
Tutta la matematica foodcost vive qui (regola #1: il backend calcola, l'AI racconta).
"""

import json
import re
import logging
from typing import Optional

from config.constants import CATEGORIE_SPESE_GENERALI

logger = logging.getLogger("foodcost_service")

CATEGORIE_RICETTE = [
    "ANTIPASTI", "BRACE", "CARNE", "CONTORNI", "CRUDI", "DOLCI",
    "FOCACCE", "FRITTI", "GRIGLIA", "INSALATE", "PANINI", "PESCE",
    "PIADINE", "PINZE", "PIZZE", "POKE", "PRIMI", "RISOTTI",
    "SALTATI", "SECONDI", "SEMILAVORATI", "SUSHI", "TEMPURA",
    "VAPORE", "VERDURE",
]

IVA_RISTORAZIONE = 0.10

# Soglie incidenza% food cost per colore
FC_SOGLIA_VERDE = 30.0
FC_SOGLIA_AMBRA = 40.0


def _estrai_grammatura(nome: str) -> Optional[dict]:
    """Estrae grammatura/volume dalla descrizione prodotto."""
    nome_upper = nome.upper()
    patterns = [
        (r"KG[\s\.]*(\d+(?:[.,]\d+)?)", "KG"),
        (r"(\d+(?:[.,]\d+)?)[\s]*KG", "KG"),
        (r"GR[\s\.]*(\d+)", "G"),
        (r"(\d+)[\s]*GR\b", "G"),
        (r"(\d+)[\s]*GRAMM", "G"),
        (r"LT[\s\.]*(\d+(?:[.,]\d+)?)", "LT"),
        (r"(\d+(?:[.,]\d+)?)[\s]*LT", "LT"),
        (r"(\d+(?:[.,]\d+)?)[\s]*LITR", "LT"),
        (r"ML[\s\.]*(\d+)", "ML"),
        (r"(\d+)[\s]*ML", "ML"),
        (r"CL[\s\.]*(\d+)", "CL"),
        (r"(\d+)[\s]*CL", "CL"),
    ]
    for pattern, um_tipo in patterns:
        m = re.search(pattern, nome_upper)
        if m:
            try:
                val = float(m.group(1).replace(",", "."))
                if um_tipo == "KG":
                    return {"valore": val * 1000, "um": "G", "originale": f"{val}KG"}
                if um_tipo == "G":
                    return {"valore": val, "um": "G", "originale": f"{val}G"}
                if um_tipo == "LT":
                    return {"valore": val * 1000, "um": "ML", "originale": f"{val}LT"}
                if um_tipo == "ML":
                    return {"valore": val, "um": "ML", "originale": f"{val}ML"}
                if um_tipo == "CL":
                    return {"valore": val * 10, "um": "ML", "originale": f"{val}CL"}
            except (ValueError, AttributeError):
                continue
    return None


def _converti_um(quantita: float, um_src: str, prezzo_per_unita_base: float) -> float:
    """Converte quantità+UM in costo. Prezzi base sono per kg/lt/pz."""
    um = um_src.lower().strip()
    if um in ("g", "gr", "grammi"):
        return (quantita / 1000) * prezzo_per_unita_base
    if um in ("kg", "kilogrammi", "kilo"):
        return quantita * prezzo_per_unita_base
    if um in ("ml", "millilitri"):
        return (quantita / 1000) * prezzo_per_unita_base
    if um in ("cl", "centilitri"):
        return (quantita / 100) * prezzo_per_unita_base
    if um in ("lt", "l", "litri"):
        return quantita * prezzo_per_unita_base
    return quantita * prezzo_per_unita_base


def calcola_costo_riga(
    tipo: str,
    prezzo_unitario: float,
    um_db: str,
    quantita: float,
    um_richiesta: str,
    grammatura_confezione: Optional[float] = None,
    grammatura_um: Optional[str] = None,
    prezzo_override: Optional[float] = None,
    foodcost_ricetta: Optional[float] = None,
) -> float:
    """
    Calcola il costo di una riga ingrediente.

    tipo: 'articolo' | 'manuale' | 'semilavorato'
    """
    if tipo == "semilavorato":
        # Il foodcost del semilavorato è già normalizzato per porzione
        fc = foodcost_ricetta or 0.0
        return _converti_um(quantita, um_richiesta, fc)

    prezzo = prezzo_override if prezzo_override is not None else prezzo_unitario

    if grammatura_confezione and grammatura_confezione > 0:
        gum = (grammatura_um or "G").upper()
        if gum in ("G", "GR"):
            prezzo_base = (prezzo / grammatura_confezione) * 1000  # €/kg
        elif gum == "ML":
            prezzo_base = (prezzo / grammatura_confezione) * 1000  # €/lt
        else:
            prezzo_base = (prezzo / grammatura_confezione) * 1000
        return _converti_um(quantita, um_richiesta, prezzo_base)

    # Fallback: converti UM del DB in prezzo base
    um = um_db.upper()
    if um in ("G", "GR", "GRAMMI"):
        prezzo_base = prezzo * 1000
    elif um in ("KG", "KILOGRAMMI", "KILO"):
        prezzo_base = prezzo
    elif um in ("ML", "MILLILITRI"):
        prezzo_base = prezzo * 1000
    elif um in ("CL", "CENTILITRI"):
        prezzo_base = prezzo * 100
    elif um in ("LT", "L", "LITRI", "LITRO"):
        prezzo_base = prezzo
    else:
        prezzo_base = prezzo
    return _converti_um(quantita, um_richiesta, prezzo_base)


def calcola_ricetta(righe: list[dict]) -> float:
    """Ricalcola foodcost_totale da una lista di righe ingrediente."""
    totale = 0.0
    for r in righe:
        try:
            totale += calcola_costo_riga(
                tipo=r.get("tipo", "articolo"),
                prezzo_unitario=float(r.get("prezzo_unitario", 0) or 0),
                um_db=r.get("um_db", "KG"),
                quantita=float(r.get("quantita", 0) or 0),
                um_richiesta=r.get("um", "KG"),
                grammatura_confezione=r.get("grammatura_confezione"),
                grammatura_um=r.get("grammatura_um"),
                prezzo_override=r.get("prezzo_override"),
                foodcost_ricetta=r.get("foodcost_ricetta"),
            )
        except Exception:
            logger.exception("Errore calcolo riga foodcost: %s", r)
    return round(totale, 4)


def arricchisci_ricetta(r: dict) -> dict:
    """Aggiunge margine, incidenza% e colore a una ricetta dal DB."""
    fc = float(r.get("foodcost_totale") or 0)
    prezzo_ivainc = r.get("prezzo_vendita_ivainc")
    prezzo_netto = (float(prezzo_ivainc) / (1 + IVA_RISTORAZIONE)) if prezzo_ivainc else None

    margine = round(prezzo_netto - fc, 2) if prezzo_netto is not None else None
    incidenza = round((fc / prezzo_netto) * 100, 1) if (prezzo_netto and prezzo_netto > 0) else None

    if incidenza is None:
        colore = "grigio"
    elif incidenza <= FC_SOGLIA_VERDE:
        colore = "verde"
    elif incidenza <= FC_SOGLIA_AMBRA:
        colore = "ambra"
    else:
        colore = "rosso"

    return {
        **r,
        "prezzo_netto": round(prezzo_netto, 2) if prezzo_netto is not None else None,
        "margine": margine,
        "incidenza_pct": incidenza,
        "colore_fc": colore,
    }


def get_articoli_da_fatture(supabase, user_id: str, ristorante_id: str) -> list[dict]:
    """
    Carica articoli unici dalle fatture (descrizione, ultimo prezzo, UM).
    Filtra spese generali e cestino.
    """
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        q = (
            supabase.table("fatture")
            .select("descrizione,prezzo_unitario,unita_misura,data_documento")
            .eq("user_id", user_id)
            .eq("ristorante_id", ristorante_id)
            .is_("deleted_at", "null")
            .not_.in_("categoria", CATEGORIE_SPESE_GENERALI)
            .order("data_documento", desc=True)
            .range(offset, offset + page_size - 1)
        )
        resp = q.execute()
        if not resp.data:
            break
        all_rows.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size

    articoli_map: dict[str, dict] = {}
    for row in all_rows:
        desc = (row.get("descrizione") or "").strip()
        if not desc or desc in articoli_map:
            continue
        gram = _estrai_grammatura(desc)
        articoli_map[desc] = {
            "nome": desc,
            "prezzo_unitario": float(row.get("prezzo_unitario") or 0),
            "um": (row.get("unita_misura") or "PZ").upper(),
            "grammatura_confezione": gram["valore"] if gram else None,
            "grammatura_um": gram["um"] if gram else None,
            "grammatura_str": gram["originale"] if gram else None,
        }
    return list(articoli_map.values())
