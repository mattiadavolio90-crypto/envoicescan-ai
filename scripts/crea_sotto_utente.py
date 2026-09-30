"""
Crea, elenca o disattiva i sotto-utenti di un titolare, finche' non c'e' il
pannello Admin (Fase 2 del piano sotto-utenti).

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
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.sotto_utenti_service import (  # noqa: E402
    PAGINA_CATENA, PAGINE_ACCOUNT, PAGINE_SOTTO_UTENTE, _pagine_account_del_titolare,
)


def valida_richiesta(
    pagine: List[str], sedi_richieste: List[str], sedi_account: List[Dict[str, Any]],
    pagine_titolare: Any = None,
) -> Tuple[Dict[str, bool], List[str], List[str]]:
    """(pagine come dict esplicito, id delle sedi, errori). Nessun accesso al DB.

    `sedi_account`: le sedi attive NON tecniche del titolare (`id`, `nome_ristorante`).
    `pagine_titolare`: `users.pagine_abilitate` del titolare.
    Meglio un errore adesso che un flag acceso che non fa niente: la Catena senza
    tutte le sedi e una pagina che il titolare non ha il worker le spegnerebbe in
    silenzio.
    """
    errori: List[str] = []
    richieste = [p.strip().lower() for p in pagine if p.strip()]
    sconosciute = sorted(set(richieste) - PAGINE_SOTTO_UTENTE)
    if sconosciute:
        errori.append(f"pagine sconosciute: {', '.join(sconosciute)}")
    if not richieste:
        errori.append("serve almeno una pagina")
    del_titolare = _pagine_account_del_titolare(pagine_titolare)
    if del_titolare is not None:
        spente = sorted(p for p in set(richieste) & PAGINE_ACCOUNT if p not in del_titolare)
        if spente:
            errori.append(f"pagine che il titolare non ha: {', '.join(spente)}")
    dict_pagine = {p: (p in richieste) for p in sorted(PAGINE_SOTTO_UTENTE)}

    per_id = {str(s["id"]): str(s["id"]) for s in sedi_account}
    per_nome: Dict[str, str] = {}
    omonime = set()
    for s in sedi_account:
        nome = str(s.get("nome_ristorante") or "").strip().lower()
        if nome in per_nome:
            omonime.add(nome)
        per_nome[nome] = str(s["id"])
    voci = [s.strip() for s in sedi_richieste if s.strip()]
    if [v.lower() for v in voci] == ["tutte"]:
        ids = list(per_id)
    else:
        ids = []
        for v in voci:
            if v not in per_id and v.lower() in omonime:
                errori.append(f"piu' sedi si chiamano {v!r}: indicala per id")
                continue
            rid = per_id.get(v) or per_nome.get(v.lower())
            if rid is None:
                errori.append(f"sede non trovata fra quelle attive del titolare: {v!r}")
            elif rid not in ids:
                ids.append(rid)
    if not ids and not errori:
        errori.append("serve almeno una sede")
    if dict_pagine[PAGINA_CATENA] and set(ids) != set(per_id):
        errori.append("la Catena si puo' dare solo con TUTTE le sedi")
    return dict_pagine, ids, errori


def _titolare(sb, email: str) -> Dict[str, Any]:
    r = (
        sb.table("users").select("id, email, nome_ristorante, pagine_abilitate")
        .eq("email", email.strip().lower()).limit(1).execute()
    )
    if not r.data:
        sys.exit(f"Titolare non trovato: {email}")
    return r.data[0]


def _sedi_operative(sb, titolare_id: str) -> List[Dict[str, Any]]:
    r = (
        sb.table("ristoranti").select("id, nome_ristorante")
        .eq("user_id", titolare_id).eq("attivo", True).eq("sede_tecnica", False)
        .order("created_at").execute()
    )
    return r.data or []


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
