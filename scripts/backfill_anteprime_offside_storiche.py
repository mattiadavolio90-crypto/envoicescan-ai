"""Backfill di anteprima_righe per le fatture storiche OFFSIDE (gen-giu 2026)
il cui xml_content era stato purgato in coda 'da_assegnare' prima che la cache
anteprima venisse popolata (vedi migration 20260723210000).

Usa l'output gia' generato da scripts/_recupera_anteprime_offside_storiche.py
(un JSON {sha256: anteprima_righe}, ottenuto ri-parsando gli XML originali
trovati su disco in "OFFSIDE GENNAIO-GIUGNO 2026/**/XML/*.xml") e lo scrive nel
DB facendo il join lato server su fatture_queue.xml_hash: nessun id viene mai
trascritto a mano, il rischio di errore e' zero.

Scrive SOLO righe che sono ancora 'da_assegnare' e con anteprima_righe NULL:
non tocca nulla che sia gia' stato assegnato o gia' recuperato in questa
sessione.

Uso:
    set SUPABASE_URL=https://vthikmfpywilukizputn.supabase.co
    set SUPABASE_SERVICE_ROLE_KEY=<service_role_key da Supabase dashboard>
    python scripts/backfill_anteprime_offside_storiche.py <anteprime_by_hash.json>

La service_role_key si trova su https://supabase.com/dashboard/project/vthikmfpywilukizputn
in Project Settings > API > service_role (secret).
"""
import json
import os
import sys
from datetime import datetime, timezone

USER_ID = "2f3f93a1-c1f4-4804-858e-a161e6f36f3f"
STATUS = "da_assegnare"


def main(json_path: str) -> int:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("ERRORE: imposta SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY prima di lanciare lo script.")
        return 2

    from supabase import create_client

    client = create_client(url, key)

    with open(json_path, "r", encoding="utf-8") as fh:
        by_hash = json.load(fh)
    print(f"Hash disponibili nel file: {len(by_hash)}")

    rows = (
        client.table("fatture_queue")
        .select("id, xml_hash")
        .eq("user_id", USER_ID)
        .eq("status", STATUS)
        .is_("anteprima_righe", "null")
        .execute()
    ).data
    print(f"Righe in coda da_assegnare senza anteprima: {len(rows)}")

    da_scrivere = [(r["id"], by_hash[r["xml_hash"]]) for r in rows if r["xml_hash"] in by_hash]
    print(f"Match trovati (hash presente anche nel JSON): {len(da_scrivere)}")

    if not da_scrivere:
        print("Niente da scrivere. Fine.")
        return 0

    risposta = input(f"Procedo a scrivere anteprima_righe su {len(da_scrivere)} righe? [s/N]: ").strip().lower()
    if risposta != "s":
        print("Annullato.")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    ok = fail = 0
    for i, (queue_id, righe) in enumerate(da_scrivere, 1):
        try:
            client.table("fatture_queue").update(
                {"anteprima_righe": righe, "anteprima_at": now_iso}
            ).eq("id", queue_id).execute()
            ok += 1
        except Exception as exc:
            fail += 1
            print(f"  FALLITO id={queue_id}: {exc}")
        if i % 25 == 0:
            print(f"  ...{i}/{len(da_scrivere)}")

    print("-" * 60)
    print(f"scritte ok: {ok}")
    print(f"fallite:    {fail}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/backfill_anteprime_offside_storiche.py <anteprime_by_hash.json>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
