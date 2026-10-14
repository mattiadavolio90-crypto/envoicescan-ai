"""Admin → Categorie, «Da sistemare» (14/10/2026): le righe su cui serve una
decisione dell'admin, raggruppate per descrizione e ordinate per euro.

Una riga e' da sistemare se e' `Da Classificare` o se il sistema l'ha marcata
`needs_review`. Storni, sconti e diciture che non hanno bisogno di revisione non
entrano: li gestisce il sistema da solo (nella vecchia coda erano 460 voci su
654). Le descrizioni scelte a mano da un cliente restano fuori: sono sue.

Logica pura: l'I/O sta nel router (`admin_categorie_da_sistemare`).
"""
from __future__ import annotations

from collections import Counter
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from utils.text_utils import pulisci_caratteri_corrotti

DA_CLASSIFICARE = "Da Classificare"
NOTE_E_DICITURE = "📝 NOTE E DICITURE"

Suggeritore = Callable[[str, str], Tuple[Optional[str], Optional[str]]]


def chiave_descrizione(descrizione) -> str:
    """La stessa normalizzazione di `_descrizioni_impronta_umana`: senza, una
    scelta del cliente con un carattere corrotto rientrerebbe in coda."""
    if not isinstance(descrizione, str):
        return ""
    return pulisci_caratteri_corrotti(descrizione).strip().upper()


def _euro(riga: dict) -> float:
    try:
        return abs(float(riga.get("totale_riga") or 0))
    except (TypeError, ValueError):
        return 0.0


def _ha_importo(riga: dict) -> bool:
    """Lo stesso criterio di `admin_qualita_classifica` per NOTE: il totale, o il
    prezzo se il totale e' zero."""
    for campo in ("totale_riga", "prezzo_unitario"):
        try:
            if float(riga.get(campo) or 0) != 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def componi_da_sistemare(
    righe: Iterable[dict],
    umane: Set[str],
    nomi_cliente: Dict[str, str],
    clienti_retail: Set[str],
    suggerisci: Suggeritore,
) -> List[dict]:
    """Un gruppo per descrizione, il piu' pesante in euro per primo.

    `categorie` elenca le categorie diverse del gruppo: con piu' d'una, «Giusta»
    non ha senso (quale delle due?) e il frontend chiede di scegliere. Un gruppo
    che contiene righe di un negozio non ha suggerimento: dizionario e regole
    sono dei ristoranti.
    """
    gruppi: Dict[str, List[dict]] = {}
    for r in righe:
        chiave = chiave_descrizione(r.get("descrizione"))
        if chiave in umane:
            continue
        gruppi.setdefault(chiave, []).append(r)

    out: List[dict] = []
    for chiave, membri in gruppi.items():
        membri.sort(key=lambda r: r.get("id") or 0)
        categorie = Counter(str(r.get("categoria") or DA_CLASSIFICARE) for r in membri)
        categoria = sorted(categorie.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        fornitori = Counter(str(r.get("fornitore") or "").strip() for r in membri if str(r.get("fornitore") or "").strip())
        uids = sorted({str(r.get("user_id")) for r in membri if r.get("user_id")})
        nomi = sorted({nomi_cliente.get(u) or u for u in uids})
        descrizione = pulisci_caratteri_corrotti(str(membri[0].get("descrizione") or "")).strip()

        suggerita, fonte = None, None
        if descrizione and not (set(uids) & clienti_retail):
            suggerita, fonte = suggerisci(descrizione, categoria)
            # Regola di dominio #2: NOTE solo sulle righe a importo zero. Proporla
            # a un gruppo con importi sarebbe proporre una scelta che il
            # salvataggio rifiuta (o applica a meta').
            if suggerita == categoria or (suggerita == NOTE_E_DICITURE and any(_ha_importo(r) for r in membri)):
                suggerita, fonte = None, None

        out.append({
            "chiave": chiave,
            "descrizione": descrizione or "—",
            "ids": [int(r["id"]) for r in membri],
            "righe": len(membri),
            "euro": round(sum(_euro(r) for r in membri), 2),
            # Con lo stesso criterio del salvataggio: NOTE non si conferma su un
            # gruppo con importi (regola di dominio #2).
            "con_importo": any(_ha_importo(r) for r in membri),
            "categoria": categoria,
            "categorie": sorted(categorie),
            "fornitore": fornitori.most_common(1)[0][0] if fornitori else None,
            "cliente_ids": uids,
            # Col filtro su un cliente si scrivono solo le sue righe: lo stesso
            # testo comprato da un altro cliente resta com'e'.
            "ids_per_cliente": {u: [int(r["id"]) for r in membri if str(r.get("user_id")) == u] for u in uids},
            "cliente": nomi[0] if len(nomi) == 1 else f"{len(nomi)} clienti",
            "suggerita": suggerita,
            "fonte": fonte,
        })

    out.sort(key=lambda g: (-g["euro"], -g["righe"], g["chiave"]))
    return out


def conta_da_sistemare(righe: Iterable[dict], umane: Set[str]) -> int:
    """Le descrizioni da decidere, cioe' i gruppi della pagina: Oggi e Categorie
    devono dire lo stesso numero."""
    return len({chiave_descrizione(r.get("descrizione")) for r in righe} - umane)
