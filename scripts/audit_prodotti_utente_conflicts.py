"""
Audit pre-apply per backfill prodotti_utente.

Obiettivo:
- identificare collisioni su (user_id, descrizione_normalizzata)
- evidenziare i casi in cui le categorie in collisione sono diverse
- mostrare quale record verrebbe tenuto dal criterio di priorita

Output:
- exports/prodotti_utente_conflicts_<timestamp>.csv
- exports/prodotti_utente_collisions_<timestamp>.csv
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from services import get_supabase_client
from utils.text_utils import get_descrizione_normalizzata_e_originale

_PRIORITY = {
    "Manuale": 0,
    "AI (auto-upload)": 1,
    "keyword-auto": 2,
}


def _priority_of(classificato_da: str) -> int:
    cd = classificato_da or ""
    if cd.startswith("Manuale"):
        return _PRIORITY["Manuale"]
    if cd.startswith("AI"):
        return _PRIORITY["AI (auto-upload)"]
    if cd.startswith("keyword"):
        return _PRIORITY["keyword-auto"]
    return 99


def _fetch_all(sb) -> List[dict]:
    rows: List[dict] = []
    page = 0
    page_size = 1000
    while page < 1000:
        resp = (
            sb.table("prodotti_utente")
            .select("id,user_id,descrizione,categoria,classificato_da,volte_visto,updated_at,created_at")
            .range(page * page_size, page * page_size + page_size - 1)
            .execute()
        )
        chunk = resp.data or []
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        page += 1
    return rows


def main() -> int:
    sb = get_supabase_client()
    rows = _fetch_all(sb)

    groups: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for r in rows:
        desc = (r.get("descrizione") or "").strip()
        if not desc:
            continue
        try:
            desc_norm, _ = get_descrizione_normalizzata_e_originale(desc)
        except Exception:
            desc_norm = desc
        desc_norm = (desc_norm or "").strip()
        if not desc_norm:
            continue
        groups[(r["user_id"], desc_norm)].append(r)

    collisions = []
    conflicts = []
    for (uid, desc_norm), members in groups.items():
        if len(members) <= 1:
            continue

        cats = sorted({(m.get("categoria") or "").strip() for m in members})
        members_sorted = sorted(
            members,
            key=lambda r: (
                _priority_of(r.get("classificato_da") or ""),
                -(r.get("volte_visto") or 0),
                str(r.get("updated_at") or r.get("created_at") or ""),
            ),
        )
        keeper = members_sorted[0]

        collisions.append(
            {
                "user_id": uid,
                "descrizione_normalizzata": desc_norm,
                "num_records": len(members),
                "categorie_distinte": " | ".join(cats),
                "keeper_id": keeper.get("id"),
                "keeper_categoria": keeper.get("categoria"),
                "keeper_classificato_da": keeper.get("classificato_da"),
                "keeper_volte_visto": keeper.get("volte_visto") or 0,
            }
        )

        if len(cats) > 1:
            for m in members_sorted:
                conflicts.append(
                    {
                        "user_id": uid,
                        "descrizione_normalizzata": desc_norm,
                        "id": m.get("id"),
                        "descrizione_raw": (m.get("descrizione") or "").strip(),
                        "categoria": (m.get("categoria") or "").strip(),
                        "classificato_da": m.get("classificato_da") or "",
                        "volte_visto": m.get("volte_visto") or 0,
                        "is_keeper": "1" if m.get("id") == keeper.get("id") else "0",
                        "keeper_categoria": keeper.get("categoria") or "",
                        "keeper_classificato_da": keeper.get("classificato_da") or "",
                    }
                )

    out_dir = Path("exports")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    collisions_csv = out_dir / f"prodotti_utente_collisions_{ts}.csv"
    conflicts_csv = out_dir / f"prodotti_utente_conflicts_{ts}.csv"

    with collisions_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "user_id",
                "descrizione_normalizzata",
                "num_records",
                "categorie_distinte",
                "keeper_id",
                "keeper_categoria",
                "keeper_classificato_da",
                "keeper_volte_visto",
            ],
        )
        writer.writeheader()
        writer.writerows(collisions)

    with conflicts_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "user_id",
                "descrizione_normalizzata",
                "id",
                "descrizione_raw",
                "categoria",
                "classificato_da",
                "volte_visto",
                "is_keeper",
                "keeper_categoria",
                "keeper_classificato_da",
            ],
        )
        writer.writeheader()
        writer.writerows(conflicts)

    print(f"Totale righe prodotti_utente: {len(rows)}")
    print(f"Collisioni post-normalizzazione: {len(collisions)}")
    print(f"Conflitti categoria (rischiosi): {len(conflicts)} righe in dettaglio")
    print(f"CSV collisioni: {collisions_csv}")
    print(f"CSV conflitti: {conflicts_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
