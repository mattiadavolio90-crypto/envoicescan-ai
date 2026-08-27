#!/usr/bin/env python3
"""Rimette in coda le fatture archiviate `done` senza aver mai prodotto righe.

CAUSA (fix del 27/8/2026): quando lo sbustamento P7M falliva, la Edge Function
salvava la busta binaria come `xml_content`; il parser esplodeva, ritornava `[]`,
e il worker interpretava `[]` come "fattura valida senza righe" chiudendo l'item
`done` e PURGANDO l'XML. Il documento spariva senza errore: nessun `last_error`,
nessun retry, solo un riparto di gruppo rimasto orfano a reggere il costo.

Su OFFSIDE: 2 fatture TOYOTA di agosto 2026 (resource_id 95089 e 96551),
+531,76 € di costo fantasma.

Il codice nuovo non ricrea più questa situazione (`estrai_dati_da_xml` ritorna
None, il worker va in retry e conserva l'XML). Restano i record già archiviati:
questo script li riporta in `pending`. Con `xml_content` ormai purgato, il worker
li recupera via `_fetch_xml_via_api(resource_id)` — la chiave INVOICETRONIC_API_KEY
vive su Railway, quindi il recupero avviene lì, non da questa macchina.

Come si riconosce un item perso, senza falsi positivi:
  - status='done'                    → archiviato come riuscito
  - nessuna riga in `fatture` per quel nome_file
  - payload_meta.resource_id presente → recuperabile via API
  - payload_meta.payload_sanitized valorizzato OPPURE p7m_extract_failed
    → l'XML era stato manipolato/marcato: è la firma del bug

Una fattura legittimamente senza DettaglioLinee NON ha payload_sanitized, quindi
non viene toccata.

Uso:
  python scripts/riaccoda_fatture_perse.py                     # dry-run, tutti
  python scripts/riaccoda_fatture_perse.py --user x@y.it       # dry-run, un account
  python scripts/riaccoda_fatture_perse.py --user x@y.it --apply
  python scripts/riaccoda_fatture_perse.py --queue-id 673 676 --apply

⚠️  Punta al DB cloud reale. Eseguire FUORI orario cliente.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # py < 3.11
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _bootstrap_supabase_env_from_secrets() -> None:
    secrets_path = ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return
    try:
        with secrets_path.open("rb") as f:
            secrets = tomllib.load(f)
    except Exception:
        return
    cfg = secrets.get("supabase", {})
    if cfg.get("url"):
        os.environ["SUPABASE_URL"] = cfg["url"]
    if cfg.get("service_role_key"):
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = cfg["service_role_key"]
    if cfg.get("key"):
        os.environ.setdefault("SUPABASE_KEY", cfg["key"])


_bootstrap_supabase_env_from_secrets()

from services import get_supabase_client  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", help="email dell'account (default: tutti)")
    ap.add_argument("--queue-id", nargs="*", type=int, help="id specifici di fatture_queue")
    ap.add_argument("--apply", action="store_true", help="riaccoda (senza: dry-run)")
    args = ap.parse_args()

    sb = get_supabase_client()

    filtro_uid = None
    if args.user:
        u = (
            sb.table("users").select("id, email")
            .ilike("email", args.user.strip()).limit(1).execute()
        ).data
        if not u:
            print(f"Nessun utente con email {args.user!r}")
            return 1
        filtro_uid = str(u[0]["id"])
        print(f"Account: {u[0]['email']} ({filtro_uid})")

    q = sb.table("fatture_queue").select(
        "id, user_id, status, payload_meta, xml_content, created_at"
    ).eq("status", "done")
    if filtro_uid:
        q = q.eq("user_id", filtro_uid)
    if args.queue_id:
        q = q.in_("id", args.queue_id)
    items = q.execute().data or []

    candidati = []
    for it in items:
        meta = it.get("payload_meta") or {}
        resource_id = meta.get("resource_id")
        nome_file = meta.get("nome_file")
        # Senza resource_id il worker non ha da dove riscaricare: riaccodarlo
        # produrrebbe solo retry destinati a morire in `dead`.
        if resource_id is None or not nome_file:
            continue
        # La firma del bug. Un documento valido senza righe non ha questi marker.
        if not (meta.get("payload_sanitized") or meta.get("p7m_extract_failed")):
            continue
        # Se le righe ci sono, l'item ha funzionato: non toccarlo.
        righe = (
            sb.table("fatture").select("id")
            .eq("user_id", it["user_id"]).eq("file_origine", nome_file)
            .is_("deleted_at", "null").limit(1).execute()
        ).data
        if righe:
            continue
        candidati.append({**it, "_resource_id": resource_id, "_nome_file": nome_file})

    if not candidati:
        print("Nessuna fattura persa da riaccodare.")
        return 0

    print(f"\n{len(candidati)} fatture archiviate done senza righe e senza errore:\n")
    for c in candidati:
        meta = c.get("payload_meta") or {}
        print(
            f"  queue_id={c['id']:<6} resource_id={c['_resource_id']:<8} "
            f"{c['_nome_file']:<34} xml={'purgato' if not c.get('xml_content') else 'presente'} "
            f"sanitized={meta.get('payload_sanitized')}"
        )

    if args.apply:
        for c in candidati:
            # attempt_count a 0: l'item riparte con l'intero budget di tentativi.
            # xml_content resta NULL — è voluto: il worker cade sul fallback API
            # via resource_id e riscarica il documento originale, invece di
            # riprovare a parsare la busta corrotta che aveva causato il problema.
            sb.table("fatture_queue").update({
                "status": "pending",
                "attempt_count": 0,
                "last_error": "riaccodata: archiviata done senza righe (bug sbustamento P7M)",
                "locked_at": None,
                "locked_by": None,
                "next_retry_at": "now()",
            }).eq("id", c["id"]).execute()
        print(f"\nAPPLICATO: {len(candidati)} item riportati in pending.")
        print("Il worker Railway li riprenderà al prossimo ciclo e li recupererà")
        print("via API Invoicetronic (INVOICETRONIC_API_KEY vive lì).")
        print("\nDopo che le righe sono atterrate, ricalcolare il riparto:")
        print("  python scripts/pulizia_riparti_note_credito.py --user <email> --apply")
    else:
        print("\nDRY-RUN: nessuna scrittura. Rilancia con --apply.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
