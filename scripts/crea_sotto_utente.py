"""
Crea, elenca o disattiva i sotto-utenti di un titolare da riga di comando. Il
modo normale e' il pannello Admin (scheda cliente → Sotto-utenti); lo script
resta per le prove e le emergenze. Le regole sono le stesse
(`services.sotto_utenti_service.valida_permessi`).

Un sotto-utente e' una credenziale in piu' sopra lo STESSO account: vede solo le
pagine e le sedi scelte qui, e i blocchi li applica il worker
(services/permessi_rotte.py, services/sotto_utenti_service.py).

Dry-run di default: senza --esegui stampa cosa farebbe e non scrive niente.
Richiede la migration supabase/migrations/20260928215000_sotto_utenti.sql
applicata al database.

USO
---
  # elenco dei sotto-utenti di un titolare
  python scripts/crea_sotto_utente.py --titolare titolare@esempio.it --elenca

  # prova a vuoto, poi davvero
  python scripts/crea_sotto_utente.py --titolare titolare@esempio.it \\
      --email sala@esempio.it --nome "Responsabile sala" \\
      --pagine home,margini,agenda --sedi "NAVIGLI,CASATI 14"
  python scripts/crea_sotto_utente.py ... --esegui

  # disattiva (e butta fuori dalle sessioni aperte)
  python scripts/crea_sotto_utente.py --disattiva sala@esempio.it --esegui

Pagine: analisi_fatture, margini, analisi_e_tag, prezzi, scadenziario, agenda,
workspace, home (= Home e assistente AI), catena (solo con TUTTE le sedi).
Sedi: nomi o id separati da virgola, oppure "tutte".
Senza --password ne genera una conforme e la stampa UNA volta (solo con --esegui):
e' il modo consigliato, perche' --password resta nella history della shell.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.sotto_utenti_service import (  # noqa: E402
    sedi_operative as _sedi_operative_svc,
    valida_permessi as valida_richiesta,
)


def _titolare(sb, email: str) -> Dict[str, Any]:
    r = (
        sb.table("users").select("id, email, nome_ristorante, pagine_abilitate")
        .eq("email", email.strip().lower()).limit(1).execute()
    )
    if not r.data:
        sys.exit(f"Titolare non trovato: {email}")
    return r.data[0]


def _sedi_operative(sb, titolare_id: str) -> List[Dict[str, Any]]:
    return _sedi_operative_svc(sb, titolare_id)


def elenca(sb, titolare_email: str) -> None:
    t = _titolare(sb, titolare_email)
    nomi = {str(s["id"]): s["nome_ristorante"] for s in _sedi_operative(sb, t["id"])}
    righe = sb.table("sotto_utenti").select("id, email, nome, attivo, pagine").eq("titolare_id", t["id"]).execute().data or []
    if not righe:
        print(f"{t['email']}: nessun sotto-utente")
        return
    for su in righe:
        sedi = sb.table("sotto_utenti_sedi").select("ristorante_id").eq("sotto_utente_id", su["id"]).execute().data or []
        pagine = [p for p, v in (su.get("pagine") or {}).items() if v is True]
        stato = "attivo" if su["attivo"] else "DISATTIVATO"
        print(f"- {su['email']} ({su.get('nome') or '-'}) {stato}")
        print(f"    pagine: {', '.join(sorted(pagine)) or 'nessuna'}")
        print(f"    sedi:   {', '.join(nomi.get(str(s['ristorante_id']), str(s['ristorante_id'])) for s in sedi)}")


def crea(sb, args) -> None:
    from services.auth_service import ph, valida_password_compliance

    t = _titolare(sb, args.titolare)
    sedi = _sedi_operative(sb, t["id"])
    pagine, ids, errori = valida_richiesta(
        args.pagine.split(","), args.sedi.split(","), sedi, t.get("pagine_abilitate"),
    )
    email = args.email.strip().lower()
    if sb.table("users").select("id").eq("email", email).limit(1).execute().data:
        errori.append(f"{email} e' gia' l'email di un account")
    if sb.table("sotto_utenti").select("id").eq("email", email).limit(1).execute().data:
        errori.append(f"{email} e' gia' l'email di un sotto-utente")
    password = args.password or (secrets.token_urlsafe(12) + "-Aa1!")
    errori += valida_password_compliance(password, email, t.get("nome_ristorante") or "")
    if errori:
        sys.exit("Non creato:\n  - " + "\n  - ".join(errori))

    nomi = {str(s["id"]): s["nome_ristorante"] for s in sedi}
    print(f"Titolare: {t['email']}")
    print(f"Sotto-utente: {email} ({args.nome or '-'})")
    print(f"Pagine: {', '.join(p for p, v in pagine.items() if v) or 'nessuna'}")
    print(f"Sedi: {', '.join(nomi[i] for i in ids)}")
    if not args.esegui:
        print("\nDRY-RUN: niente scritto. Rilancia con --esegui.")
        return

    riga = sb.table("sotto_utenti").insert({
        "titolare_id": t["id"], "email": email, "password_hash": ph.hash(password),
        "nome": args.nome or None, "attivo": True, "pagine": pagine,
    }).execute().data[0]
    try:
        sb.table("sotto_utenti_sedi").insert(
            [{"sotto_utente_id": riga["id"], "ristorante_id": i} for i in ids]
        ).execute()
    except Exception:
        # Senza sedi il sotto-utente non entrerebbe comunque: niente mezze righe.
        sb.table("sotto_utenti").delete().eq("id", riga["id"]).execute()
        raise
    print(f"\nCreato (id {riga['id']}).")
    if not args.password:
        print(f"Password generata (mostrata solo ora): {password}")


def disattiva(sb, email: str, esegui: bool) -> None:
    from services.session_service import revoca_sessioni_sotto_utente

    r = sb.table("sotto_utenti").select("id, email, attivo").eq("email", email.strip().lower()).limit(1).execute()
    if not r.data:
        sys.exit(f"Sotto-utente non trovato: {email}")
    su = r.data[0]
    print(f"Disattivo {su['email']} (ora {'attivo' if su['attivo'] else 'gia disattivato'}) e chiudo le sue sessioni.")
    if not esegui:
        print("DRY-RUN: niente scritto. Rilancia con --esegui.")
        return
    sb.table("sotto_utenti").update({"attivo": False}).eq("id", su["id"]).execute()
    print(f"Fatto: {revoca_sessioni_sotto_utente(su['id'], sb)} sessioni chiuse.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--titolare")
    ap.add_argument("--elenca", action="store_true")
    ap.add_argument("--email")
    ap.add_argument("--nome")
    ap.add_argument("--pagine", default="")
    ap.add_argument("--sedi", default="")
    ap.add_argument("--password")
    ap.add_argument("--disattiva", metavar="EMAIL")
    ap.add_argument("--esegui", action="store_true")
    args = ap.parse_args()

    from services import get_supabase_client

    sb = get_supabase_client()
    if args.disattiva:
        disattiva(sb, args.disattiva, args.esegui)
    elif args.titolare and args.elenca:
        elenca(sb, args.titolare)
    elif args.titolare and args.email:
        crea(sb, args)
    else:
        ap.error("serve --titolare con --elenca o --email, oppure --disattiva")


if __name__ == "__main__":
    main()
