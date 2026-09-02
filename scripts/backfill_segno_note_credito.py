#!/usr/bin/env python3
"""Corregge il segno delle note di credito (TD04) contate come costo.

PROBLEMA
    Una nota di credito deve RIDURRE i costi: il netto delle sue righe deve
    essere negativo. Il parser, fino al fix in services/invoice_service.py,
    lasciava intatto qualunque documento contenente almeno una riga gia'
    negativa — anche marginale (es. RIVALSA BOLLO N.C da -2,00 euro accanto a un
    premio da +791,49). Risultato: note di credito col netto POSITIVO, sommate
    ai costi invece che sottratte.

CRITERIO (identico a quello del parser corretto)
    Un documento TD04 e' da correggere se la somma dei suoi totale_riga e'
    POSITIVA. La correzione inverte il segno di TUTTE le sue righe, il che
    preserva i rapporti interni (una nota +2174.67/-2072.47 diventa
    -2174.67/+2072.47, netto -102.20 e non -4247).

USO
    python scripts/backfill_segno_note_credito.py              # dry-run (default)
    python scripts/backfill_segno_note_credito.py --apply      # scrive davvero
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
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


def _carica_righe_td04(supabase):
    """Tutte le righe TD04 attive, paginate (il client tronca a 1000)."""
    righe, offset, page = [], 0, 1000
    while True:
        resp = (
            supabase.table("fatture")
            .select("id,file_origine,fornitore,data_documento,descrizione,"
                    "totale_riga,prezzo_unitario,totale_imponibile,ristorante_id")
            .eq("tipo_documento", "TD04")
            .is_("deleted_at", "null")
            .order("id")
            .range(offset, offset + page - 1)
            .execute()
        )
        blocco = resp.data or []
        righe.extend(blocco)
        if len(blocco) < page:
            break
        offset += page
    return righe


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="Esegue la scrittura. Senza questo flag e' un dry-run.")
    args = ap.parse_args()

    supabase = get_supabase_client()
    righe = _carica_righe_td04(supabase)

    documenti: dict[str, list] = {}
    for r in righe:
        documenti.setdefault(r.get("file_origine") or "(senza file)", []).append(r)

    da_correggere = {
        f: rr for f, rr in documenti.items()
        if sum(float(x.get("totale_riga") or 0) for x in rr) > 0
    }

    print(f"TD04 attive: {len(righe)} righe in {len(documenti)} documenti")
    print(f"Da correggere (netto positivo): {len(da_correggere)} documenti\n")

    if not da_correggere:
        print("Nessun documento da correggere.")
        return 0

    tot_righe = 0
    tot_scarto = 0.0
    for f, rr in sorted(da_correggere.items(),
                        key=lambda kv: -sum(float(x.get("totale_riga") or 0) for x in kv[1])):
        netto = sum(float(x.get("totale_riga") or 0) for x in rr)
        imp = rr[0].get("totale_imponibile")
        print(f"── {f}")
        print(f"   {rr[0].get('fornitore')} · {rr[0].get('data_documento')} · "
              f"{len(rr)} righe · netto {netto:+.2f} → {-netto:+.2f} "
              f"(imponibile testata: {imp})")
        for x in rr:
            att = float(x.get("totale_riga") or 0)
            desc = (x.get("descrizione") or "")[:52]
            print(f"     id={x['id']:<10} {att:>12.2f} → {-att:>12.2f}   {desc}")
        tot_righe += len(rr)
        tot_scarto += netto * 2
        print()

    print(f"TOTALE: {len(da_correggere)} documenti, {tot_righe} righe")
    print(f"Effetto sui costi: {-tot_scarto:+.2f} EUR\n")

    if not args.apply:
        print("DRY-RUN — nessuna scrittura. Rilancia con --apply per applicare.")
        return 0

    print("Scrittura in corso...")
    aggiornate, errori = 0, 0
    for f, rr in da_correggere.items():
        for x in rr:
            att = float(x.get("totale_riga") or 0)
            pu = x.get("prezzo_unitario")
            patch = {"totale_riga": round(-att, 2)}
            if pu is not None:
                patch["prezzo_unitario"] = round(-float(pu), 2)
            try:
                supabase.table("fatture").update(patch).eq("id", x["id"]).execute()
                aggiornate += 1
            except Exception as e:
                errori += 1
                print(f"   ERRORE id={x['id']}: {e}")

    print(f"\nRighe aggiornate: {aggiornate} · errori: {errori}")
    return 1 if errori else 0


if __name__ == "__main__":
    raise SystemExit(main())
