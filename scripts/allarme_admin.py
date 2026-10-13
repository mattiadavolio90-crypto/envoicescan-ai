"""Allarme Telegram con memoria, per i controlli di GitHub Actions.

Chi chiama dice solo se il problema c'e' ADESSO (`--problema 1|0`); la memoria
nel DB (RPC `admin_allarme_segnala`, migration 20261013140000) decide se
scrivere: una volta all'apertura, un critico di nuovo ogni 6 ore finche' dura,
«✅ Risolto» quando rientra, silenzio in tutti gli altri giri.

Solo libreria standard: gira sul runner di GitHub con il Python di sistema,
senza installare le dipendenze del repo.

Se la memoria non risponde (Supabase giu', chiave scaduta) e il problema c'e',
il messaggio parte lo stesso: meglio un doppione che un allarme muto. Ritorna 1
solo se un messaggio dovuto non e' partito, cosi' il run diventa rosso e GitHub
manda la sua email.

Ambiente: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, TG_TOKEN, TG_CHAT_ID.
Scrive `azione=<...>` in $GITHUB_OUTPUT se presente.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Optional, Tuple

GRAVITA = ("critico", "oggi")


def azione_di_ripiego(problema: bool) -> str:
    """Memoria irraggiungibile: si avvisa se c'e' un problema, si tace se no."""
    return "invia" if problema else "niente"


def componi(azione: str, gravita: str, testo: str, link: Optional[str],
            testo_risolto: Optional[str], memoria_ok: bool = True) -> Tuple[Optional[str], bool]:
    """Il messaggio da mandare per un'azione, e se va mandato senza suono.

    Ritorna (None, _) quando non c'e' niente da dire.
    """
    coda = f"\n{link}" if link else ""
    if azione in ("invia", "ripeti"):
        icona = "🔴" if gravita == "critico" else "🟠"
        prefisso = "Ancora: " if azione == "ripeti" else ""
        nota = "" if memoria_ok else "\n(Memoria allarmi non raggiungibile: potresti riceverlo piu' volte.)"
        return f"{icona} {prefisso}{testo}{coda}{nota}", gravita != "critico"
    if azione == "risolto":
        return f"✅ Risolto: {testo_risolto or testo}", True
    return None, True


def chiedi_azione(url: str, chiave_api: str, chiave: str, gravita: str, problema: bool,
                  testo: str, link: Optional[str]) -> Optional[str]:
    corpo = json.dumps({
        "p_chiave": chiave, "p_gravita": gravita, "p_problema": problema,
        "p_testo": testo, "p_link": link,
    }).encode()
    req = urllib.request.Request(
        f"{url.rstrip('/')}/rest/v1/rpc/admin_allarme_segnala",
        data=corpo, method="POST",
        headers={"apikey": chiave_api, "Authorization": f"Bearer {chiave_api}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            valore = json.loads(r.read().decode() or "null")
    except Exception as exc:  # rete, 401, 5xx: la memoria non ha risposto
        print(f"::warning::memoria allarmi non raggiungibile: {exc}")
        return None
    return valore if isinstance(valore, str) else None


def invia_telegram(token: str, chat_id: str, testo: str, silenzioso: bool) -> bool:
    corpo = json.dumps({"chat_id": chat_id, "text": testo[:4096],
                        "disable_notification": silenzioso}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=corpo, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as exc:
        print(f"::error::Telegram non ha accettato il messaggio: {exc}")
        return False


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--chiave", required=True)
    p.add_argument("--gravita", choices=GRAVITA, default="critico")
    p.add_argument("--problema", choices=("0", "1"), required=True)
    p.add_argument("--testo", required=True)
    p.add_argument("--link")
    p.add_argument("--risolto", help="testo del messaggio di rientro")
    a = p.parse_args(argv)
    problema = a.problema == "1"

    url, chiave_api = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    azione = chiedi_azione(url, chiave_api, a.chiave, a.gravita, problema, a.testo, a.link) if url and chiave_api else None
    memoria_ok = azione is not None
    if azione is None:
        azione = azione_di_ripiego(problema)
    print(f"{a.chiave}: azione={azione}")
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write(f"azione={azione}\n")

    testo, silenzioso = componi(azione, a.gravita, a.testo, a.link, a.risolto, memoria_ok)
    if testo is None:
        return 0
    token, chat = os.getenv("TG_TOKEN", ""), os.getenv("TG_CHAT_ID", "")
    if not token or not chat:
        print("::error::TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID mancanti: allarme dovuto ma non inviato")
        return 1
    return 0 if invia_telegram(token, chat, testo, silenzioso) else 1


if __name__ == "__main__":
    sys.exit(main())
