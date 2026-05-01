"""
Backfill one-shot: normalizza la colonna `descrizione` di `prodotti_utente` per uniformare
la chiave di lookup con quella usata da `salva_correzione_in_memoria_locale`
e dalle auto-categorizzazioni (keyword-auto, AI auto-upload).

Idempotente. Per ogni `(user_id, descrizione)`:
  - calcola `desc_norm = get_descrizione_normalizzata_e_originale(descrizione)[0]`
  - se `desc_norm == descrizione` → no-op
  - altrimenti raccoglie tutte le righe dello stesso `user_id` che dopo
    normalizzazione collidono e mantiene UNA riga con priorità:
        Manuale > AI (auto-upload) > keyword-auto > altro
    sommando `volte_visto`. Le altre vengono cancellate.

Uso:
    python -m scripts.backfill_prodotti_utente_normalize          # dry-run
    python -m scripts.backfill_prodotti_utente_normalize --apply  # esegue UPDATE/DELETE
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="esegue le UPDATE/DELETE (default: dry-run)")
    args = ap.parse_args()

    sb = get_supabase_client()
    rows = _fetch_all(sb)
    print(f"Totale righe prodotti_utente: {len(rows)}")

    # raggruppa per (user_id, desc_norm)
    groups: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for r in rows:
        desc = r.get("descrizione") or ""
        try:
            desc_norm, _ = get_descrizione_normalizzata_e_originale(desc.strip())
        except Exception:
            desc_norm = desc.strip()
        desc_norm = (desc_norm or "").strip()
        if not desc_norm:
            continue
        groups[(r["user_id"], desc_norm)].append(r)

    to_update: List[dict] = []   # (id, new_descrizione, new_volte_visto)
    to_delete: List[int] = []
    collisions = 0
    only_renames = 0

    for (uid, desc_norm), members in groups.items():
        if len(members) == 1:
            r = members[0]
            current_desc = (r.get("descrizione") or "").strip()
            if current_desc != desc_norm:
                only_renames += 1
                to_update.append({
                    "id": r["id"],
                    "descrizione": desc_norm,
                    "volte_visto": r.get("volte_visto") or 1,
                })
        else:
            collisions += 1
            members_sorted = sorted(
                members,
                key=lambda r: (
                    _priority_of(r.get("classificato_da") or ""),
                    -((r.get("updated_at") or r.get("created_at") or "") and 1),
                    -(r.get("volte_visto") or 0),
                ),
            )
            keeper = members_sorted[0]
            tot_volte = sum((m.get("volte_visto") or 0) for m in members) or 1
            to_update.append({
                "id": keeper["id"],
                "descrizione": desc_norm,
                "volte_visto": tot_volte,
            })
            for losing in members_sorted[1:]:
                to_delete.append(losing["id"])

    print(f"Rinomine semplici (solo normalizzazione descrizione): {only_renames}")
    print(f"Collisioni dopo normalizzazione (merge in 1 keeper): {collisions}")
    print(f"Righe da aggiornare: {len(to_update)} | Righe da cancellare: {len(to_delete)}")

    if not args.apply:
        print("DRY-RUN: nessuna scrittura su DB. Riesegui con --apply per applicare.")
        return 0

    # Applica DELETE prima per evitare conflitti UNIQUE(user_id,descrizione) durante UPDATE
    if to_delete:
        for i in range(0, len(to_delete), 500):
            chunk = to_delete[i:i + 500]
            sb.table("prodotti_utente").delete().in_("id", chunk).execute()
        print(f"DELETE eseguite: {len(to_delete)}")

    # UPDATE descrizione + volte_visto
    for u in to_update:
        sb.table("prodotti_utente").update({
            "descrizione": u["descrizione"],
            "volte_visto": u["volte_visto"],
        }).eq("id", u["id"]).execute()
    print(f"UPDATE eseguite: {len(to_update)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
