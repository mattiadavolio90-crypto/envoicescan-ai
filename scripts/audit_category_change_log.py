"""Audit cronologico modifiche categoria (old/new) da category_change_log.

Uso tipico:
  python scripts/audit_category_change_log.py --user-id <UUID>
  python scripts/audit_category_change_log.py --user-id <UUID> --since-id 1200
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services import get_supabase_client  # noqa: E402


def _fetch_changes(client, user_id: str, since_id: int | None, limit: int):
    page_size = min(max(limit, 1), 1000)
    rows = []
    offset = 0

    while len(rows) < limit:
        query = (
            client.table("category_change_log")
            .select(
                "id, changed_at, table_name, target_id, descrizione, "
                "file_origine, numero_riga, old_categoria, new_categoria, "
                "actor_email, source, batch_id"
            )
            .eq("user_id", user_id)
            .order("id", desc=False)
            .range(offset, offset + page_size - 1)
        )
        if since_id is not None:
            query = query.gt("id", since_id)

        resp = query.execute()
        chunk = resp.data or []
        if not chunk:
            break

        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size

    return rows[:limit]


def _print_rows(rows):
    if not rows:
        print("Nessuna modifica trovata per i filtri indicati.")
        return

    print("=" * 120)
    print(f"MODIFICHE TROVATE: {len(rows)}")
    print("=" * 120)
    for r in rows:
        rid = r.get("id")
        ts = (r.get("changed_at") or "")[:19]
        table_name = r.get("table_name") or "?"
        target_id = r.get("target_id") or "?"
        desc = (r.get("descrizione") or "").strip()
        old_cat = r.get("old_categoria") or "<NULL>"
        new_cat = r.get("new_categoria") or "<NULL>"
        src = r.get("source") or "db_trigger"
        actor = r.get("actor_email") or "n/d"
        file_origine = r.get("file_origine") or ""
        numero_riga = r.get("numero_riga")

        print(f"[{rid}] {ts} | {table_name}:{target_id} | {old_cat} -> {new_cat}")
        print(f"      desc: {desc[:120]}")
        if file_origine or numero_riga is not None:
            print(f"      file/riga: {file_origine} / {numero_riga}")
        print(f"      actor: {actor} | source: {src}")

    print("-" * 120)
    print(f"CHECKPOINT CONSIGLIATO (since-id): {rows[-1].get('id')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit log modifiche categoria")
    parser.add_argument("--user-id", required=True, help="UUID utente da analizzare")
    parser.add_argument("--since-id", type=int, default=None, help="Mostra solo record con id > since_id")
    parser.add_argument("--limit", type=int, default=500, help="Numero massimo record da stampare")
    args = parser.parse_args()

    supabase = get_supabase_client()
    rows = _fetch_changes(supabase, args.user_id, args.since_id, args.limit)
    _print_rows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
