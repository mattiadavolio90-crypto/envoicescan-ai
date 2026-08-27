#!/usr/bin/env python3
"""Ripara i riparti costi di gruppo incoerenti: note di credito contate come costo
e header senza quote.

Due classi, entrambe esposte da `v_riparto_incoerenze` (migration 20260827214500):

1. `riparto_segno_incoerente` — una nota di credito (TD04) è stata ripartita col
   LORDO POSITIVO provvisorio dei metadati di coda (`ImportoTotaleDocumento` non
   porta il segno) e nessuno ha mai riportato l'header al netto reale, che è
   negativo. Risultato: il gruppo PAGA la nota di credito invece di riceverla.
   Su OFFSIDE: 6 casi, ~2.086 € di costo di troppo su feb/mar/giu 2026.

   Riparazione: `esplodi_quote_per_categoria(forza=True)`. Dal fix del 27/8/2026
   ricostruisce header e quote dal netto reale col segno giusto, e la NC si netta
   nel mese come in un conto mono-sede. NON si eliminano i riparti (né quello
   della NC né quello della fattura di costo gemella): entrambi i documenti sono
   veri e devono restare, esattamente come restano in un conto a sede singola.

2. `riparto_senza_quote` — l'header esiste ma non ha alcuna riga quota: il costo
   non arriva a nessuna sede, né nel MOL né in Analisi Fatture. Su OFFSIDE:
   AUTOSTRADE luglio, 96,80 € netti mai distribuiti.

   Riparazione: si ricreano le quote in parti uguali sulle sedi operative della
   catena (`_quote_equa`), poi `esplodi_quote_per_categoria(forza=True)` le spezza
   per categoria.

Dopo ogni riparazione si ricalcolano le quote mensili (RPC `riparto_quote_mensili`)
per ogni (anno, mese) toccato: è ciò che aggiorna `margini_mensili` e quindi il MOL.

Idempotente: un riparto già coerente non compare più nella view e viene saltato.

Uso:
  python scripts/pulizia_riparti_note_credito.py                      # dry-run, tutti
  python scripts/pulizia_riparti_note_credito.py --user x@y.it        # dry-run, un account
  python scripts/pulizia_riparti_note_credito.py --user x@y.it --apply  # scrive

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
from services.riparto_service import (  # noqa: E402
    _pesi_e_netto_categoria_fattura,
    esplodi_quote_per_categoria,
)
from services.routers.riparto import _carica_sedi_attive, _quote_equa  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", help="email dell'account da riparare (default: tutti)")
    ap.add_argument("--apply", action="store_true", help="scrive le correzioni (senza: dry-run)")
    args = ap.parse_args()

    sb = get_supabase_client()

    filtro_uid: str | None = None
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

    q = sb.table("v_riparto_incoerenze").select("*")
    if filtro_uid:
        q = q.eq("user_id", filtro_uid)
    incoerenze = q.execute().data or []

    da_riparare = [
        r for r in incoerenze
        if r.get("tipo_incoerenza") in ("riparto_segno_incoerente", "riparto_senza_quote")
    ]
    altre = [r for r in incoerenze if r not in da_riparare]

    if not da_riparare:
        print("Nessun riparto da riparare (segno incoerente / senza quote).")
    if altre:
        print(
            f"\n{len(altre)} incoerenze di ALTRO tipo (orfano / senza documento): "
            "non toccate da questo script, richiedono il recupero del documento."
        )
        for r in altre:
            print(f"  - {r.get('tipo_incoerenza'):26} {r.get('file_origine') or r.get('riparto_id')}")

    mesi_da_ricalcolare: set[tuple[str, int, int]] = set()
    n_ok = n_ko = 0

    for r in da_riparare:
        uid = str(r["user_id"])
        rid = str(r["riparto_id"])
        tipo = r["tipo_incoerenza"]

        padre = (
            sb.table("riparto_costi_catena")
            .select("id, anno, mese, fornitore, descrizione, importo_totale, file_origine, origine")
            .eq("id", rid).limit(1).execute()
        ).data
        if not padre:
            print(f"  riparto {rid} non più esistente, salto")
            continue
        p = padre[0]
        fo = p.get("file_origine")
        etichetta = (
            f"[{p['anno']}-{p['mese']:02d}] {(p.get('fornitore') or '?'):<14} "
            f"{(p.get('descrizione') or '')[:34]:<34}"
        )

        if not fo:
            print(f"  {etichetta} SALTATO — nessun file_origine (costo manuale)")
            n_ko += 1
            continue

        netto_res = _pesi_e_netto_categoria_fattura(sb, uid, fo)
        if netto_res is None:
            print(
                f"  {etichetta} SALTATO — netto ~0 o nessuna riga categorizzata: "
                "il riparto non ha più un importo da distribuire, va valutato a mano"
            )
            n_ko += 1
            continue
        _, netto = netto_res

        if tipo == "riparto_senza_quote":
            sedi = [str(s["id"]) for s in _carica_sedi_attive(uid, sb)]
            if len(sedi) < 2:
                print(f"  {etichetta} SALTATO — meno di 2 sedi operative, non è una catena")
                n_ko += 1
                continue
            quote = _quote_equa(netto, sedi)
            print(
                f"  {etichetta} quote assenti → ricreo {len(quote)} quote "
                f"su netto {netto:>9.2f} (era header {float(p['importo_totale']):.2f})"
            )
            if args.apply:
                sb.rpc("sostituisci_quote_riparto", {
                    "p_riparto_id": rid,
                    "p_user_id": uid,
                    "p_tipo": "generale",
                    "p_regola": "equa",
                    "p_importo_totale": round(netto, 2),
                    "p_quote": quote,
                }).execute()
        else:
            print(
                f"  {etichetta} segno errato: header {float(p['importo_totale']):>9.2f} "
                f"→ netto reale {netto:>9.2f} (nota di credito)"
            )

        if args.apply:
            esplodi_quote_per_categoria(sb, uid, rid, fo, forza=True)
        n_ok += 1
        mesi_da_ricalcolare.add((uid, int(p["anno"]), int(p["mese"])))

    if args.apply and mesi_da_ricalcolare:
        for uid, anno, mese in sorted(mesi_da_ricalcolare):
            sb.rpc("riparto_quote_mensili", {
                "p_user_id": uid, "p_anno": anno, "p_mese": mese,
            }).execute()
        print(f"\n→ quote mensili ricalcolate per {len(mesi_da_ricalcolare)} (account, mese)")

    modo = "APPLICATO" if args.apply else "DRY-RUN (nessuna scrittura)"
    print(f"\n{modo}: {n_ok} riparti riparati, {n_ko} saltati.")
    if not args.apply and n_ok:
        print("Rilancia con --apply per scrivere. Ricordati: fuori orario cliente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
