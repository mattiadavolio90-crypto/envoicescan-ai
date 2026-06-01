"""Rigenera le notifiche operative di UN singolo utente col codice corrente.

Uso operativo/manutentivo (NON runtime). Cancella le notifiche stale dei topic
operativi e le ricrea coi generatori aggiornati (finestra scaduto 90gg, mese
corretto). Pensato per allineare un utente di test senza aspettare il giro
automatico. NON tocca altri utenti.

    python scripts/regen_notifiche_utente.py <user_id> <ristorante_id>
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import get_supabase_client
from services.notification_service import (
    build_monthly_data_notifications,
    build_scadenza_documents_notifications,
)
from services.notification_inbox_service import (
    build_notification_record,
    upsert_inbox_notifications,
)

# Stessa mappa prefisso-id → topic usata da components/notifications_panel.py
_PREFIX_TOPIC = {
    "missing-revenue-": ("fatturato_mancante", "warning"),
    "missing-labor-cost-": ("costo_personale_mancante", "warning"),
    "scaduti-": ("scadenza_superata", "warning"),
    "imminenti-": ("scadenza_imminente", "info"),
}
_TOPIC_DA_PULIRE = sorted({t for t, _ in _PREFIX_TOPIC.values()})


def regen(user_id: str, ristorante_id: str) -> None:
    sb = get_supabase_client()

    # 1) Cancella le notifiche stale dei topic operativi per QUESTO utente.
    del_resp = (
        sb.table("notification_inbox")
        .delete()
        .eq("user_id", user_id)
        .eq("ristorante_id", ristorante_id)
        .in_("topic_key", _TOPIC_DA_PULIRE)
        .execute()
    )
    print(f"[regen] cancellate {len(del_resp.data or [])} notifiche stale")

    # 2) Rigenera coi generatori aggiornati.
    now = datetime.now(timezone.utc)
    grezze = build_monthly_data_notifications(
        user_id=user_id, ristorante_id=ristorante_id, reference_dt=now
    )
    grezze.extend(
        build_scadenza_documents_notifications(
            user_id=user_id, ristorante_id=ristorante_id
        )
    )
    print(f"[regen] generate {len(grezze)} notifiche grezze")

    # 3) Mappa e upsert nell'inbox.
    records = []
    for n in grezze:
        nid = str(n.get("id") or "")
        topic = sev = None
        for prefix, (t, s) in _PREFIX_TOPIC.items():
            if nid.startswith(prefix):
                topic, sev = t, s
                break
        if not topic:
            continue
        severity = str(n.get("level") or "") or sev
        records.append(build_notification_record(
            user_id=user_id,
            ristorante_id=ristorante_id,
            topic_key=topic,
            source_type="operativa",
            severity=severity,
            title=str(n.get("title") or ""),
            body=str(n.get("body") or ""),
            payload=n.get("payload_data") or {},
            action_page=str(n.get("action_page") or ""),
        ))

    if records:
        upsert_inbox_notifications(records, supabase_client=sb)
        print(f"[regen] upsert {len(records)} notifiche aggiornate")
        for r in records:
            print(f"   - {r.get('topic_key')}: {r.get('title')}")
    else:
        print("[regen] nessuna notifica da inserire (tutto a posto)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python scripts/regen_notifiche_utente.py <user_id> <ristorante_id>")
        sys.exit(1)
    regen(sys.argv[1], sys.argv[2])
