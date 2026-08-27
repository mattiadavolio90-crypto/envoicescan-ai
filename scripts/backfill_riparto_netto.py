#!/usr/bin/env python3
"""Riporta al NETTO i riparti costi di gruppo registrati LORDO (IVA inclusa).

Causa radice: `POST /api/riparto/da-coda` (dal 15/7/2026) registra
`riparto_costi_catena.importo_totale` = `ImportoTotaleDocumento` dei metadati di
coda, cioè IVA inclusa, perché al momento della ripartizione le righe non erano
ancora atterrate. `esplodi_quote_per_categoria` poi spezzava quel lordo per
categoria usando pesi calcolati sulle righe nette → `quota_importo` e quindi
`margini_mensili.quote_riparto_*` gonfiati ~+22%. Effetto visibile: la pagina
Ricavi e Margini mostra costi/MOL più alti di Analisi Fatture (cert. OFFSIDE
27/8/2026: Δ luglio ≈ 5.100 €, Δ 2026 ≈ 14.300 €).

Il fix di runtime è in `esplodi_quote_per_categoria` (riporta al netto
all'atterraggio). Questo script applica la stessa correzione ai riparti STORICI:
per ogni `riparto_costi_catena` con `origine='fattura'` e righe sorgente vive dove
`importo_totale` diverge dal netto reale, chiama
`esplodi_quote_per_categoria(..., forza=True)` e poi ricalcola le quote mensili
(RPC `riparto_quote_mensili`) per ogni (anno, mese) toccato.

Idempotente: un riparto già al netto non viene modificato.

Uso:
  python scripts/backfill_riparto_netto.py                       # dry-run, tutti gli account
  python scripts/backfill_riparto_netto.py --user offsidesp@gmail.com   # dry-run, un account
  python scripts/backfill_riparto_netto.py --user offsidesp@gmail.com --apply   # scrive

⚠️  Punta al DB cloud reale. Eseguire FUORI orario cliente.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
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
from services.riparto_service import (  # noqa: E402
    _pesi_e_netto_categoria_fattura,
    esplodi_quote_per_categoria,
)

SOGLIA = 0.02  # scarto lordo/netto oltre il quale il riparto va corretto


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", help="email dell'account da correggere (default: tutti)")
    ap.add_argument("--apply", action="store_true", help="scrive le correzioni (senza: dry-run)")
    args = ap.parse_args()

    sb = get_supabase_client()

    user_ids: list[str] = []
    if args.user:
        u = (
            sb.table("users").select("id, email")
            .ilike("email", args.user.strip()).limit(1).execute()
        ).data
        if not u:
            print(f"Nessun utente con email {args.user!r}")
            return 1
        user_ids = [str(u[0]["id"])]
        print(f"Account: {u[0]['email']} ({user_ids[0]})")
    else:
        rip_users = (
            sb.table("riparto_costi_catena").select("user_id").eq("origine", "fattura").execute()
        ).data or []
        user_ids = sorted({str(r["user_id"]) for r in rip_users})
        print(f"Account con riparti da fattura: {len(user_ids)}")

    tot_corretti = 0
    tot_delta = 0.0

    for uid in user_ids:
        riparti = (
            sb.table("riparto_costi_catena")
            .select("id, anno, mese, file_origine, fornitore, descrizione, importo_totale")
            .eq("user_id", uid).eq("origine", "fattura")
            .execute()
        ).data or []

        mesi_da_ricalcolare: set[tuple[int, int]] = set()
        for rip in riparti:
            fo = rip.get("file_origine")
            if not fo:
                continue
            res = _pesi_e_netto_categoria_fattura(sb, uid, fo)
            if res is None:
                continue  # storico purgato / nessuna riga categorizzata: resta legacy
            _, netto = res
            lordo = round(float(rip["importo_totale"] or 0), 2)
            delta = round(lordo - netto, 2)
            if abs(delta) <= SOGLIA:
                continue

            print(
                f"  [{rip['anno']}-{rip['mese']:02d}] {rip.get('fornitore') or '?':<14} "
                f"{(rip.get('descrizione') or '')[:38]:<38} "
                f"lordo {lordo:>10.2f} → netto {netto:>10.2f}  (Δ {delta:+.2f})"
            )
            tot_corretti += 1
            tot_delta += delta
            mesi_da_ricalcolare.add((int(rip["anno"]), int(rip["mese"])))

            if args.apply:
                esplodi_quote_per_categoria(sb, uid, str(rip["id"]), fo, forza=True)

        if args.apply and mesi_da_ricalcolare:
            for anno, mese in sorted(mesi_da_ricalcolare):
                sb.rpc("riparto_quote_mensili", {
                    "p_user_id": uid, "p_anno": anno, "p_mese": mese,
                }).execute()
            print(f"  → quote mensili ricalcolate per {len(mesi_da_ricalcolare)} mesi")

    modo = "APPLICATO" if args.apply else "DRY-RUN (nessuna scrittura)"
    print(
        f"\n{modo}: {tot_corretti} riparti da correggere, "
        f"sovra-distribuzione totale {tot_delta:+.2f} €"
    )
    if not args.apply and tot_corretti:
        print("Rilancia con --apply per scrivere. Ricordati: fuori orario cliente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
