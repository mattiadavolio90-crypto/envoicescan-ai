"""Cosa deve fare l'admin oggi: la lista della pagina Admin → Oggi e del
riepilogo Telegram del mattino (riordino del 13/10/2026).

Logica PURA: riceve i dati gia' letti (le stesse strutture che ritornano gli
endpoint di salute in routers/admin.py) e li trasforma in voci ordinate. La
pagina e il messaggio del mattino leggono la stessa funzione, cosi' non possono
dire due cose diverse.

Una voce:
    chiave     identifica la voce (per React e per contare quelle di un cliente)
    gravita    "critico" (qualcosa non entra o e' rotto) | "oggi" (da sbrigare)
    titolo     una frase che dice cosa succede
    dettaglio  il contesto (numero, importo, da quanto), o None
    da         ISO del momento in cui e' iniziato, o None
    cliente_id / cliente   a chi si riferisce, o None
    ristorante_id          la sede, quando la voce e' di una sede sola (la Mappa
                           dei clienti colora quel nodo), o None
    link       dove si risolve nell'admin, o None
    azione     il pulsante da mostrare sulla voce, o None
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

ROMA = ZoneInfo("Europe/Rome")

GIORNI_ATTIVAZIONE = 3
GIORNI_SDI_MUTO = 14
GIORNI_FINE_PROVA = 2
ORA_RIEPILOGO = 8
MAX_RIGHE_RIEPILOGO = 8

_ORDINE = {"critico": 0, "oggi": 1}


def _voce(chiave, gravita, titolo, *, dettaglio=None, da=None, cliente_id=None,
          cliente=None, link=None, azione=None, ristorante_id=None) -> Dict[str, Any]:
    return {
        "chiave": chiave, "gravita": gravita, "titolo": titolo, "dettaglio": dettaglio,
        "da": da, "cliente_id": cliente_id, "cliente": cliente, "link": link, "azione": azione,
        "ristorante_id": ristorante_id,
    }


def _euro(v) -> Optional[str]:
    try:
        return f"€ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return None


def _dettaglio_fattura(p: Dict[str, Any]) -> str:
    parti = []
    if p.get("numero"):
        parti.append(f"n. {p['numero']}")
    importo = _euro(p.get("importo")) if p.get("importo") not in (None, "") else None
    if importo:
        parti.append(importo)
    # Da smistare: la P.IVA e' quella del cliente (comune alle sue sedi), e'
    # l'indirizzo di consegna a dire quale sede. Negli altri casi la P.IVA e'
    # proprio cio' che non torna.
    if p.get("status") == "da_assegnare":
        if p.get("indirizzo"):
            parti.append(f"consegna: {p['indirizzo']}")
    elif p.get("piva_raw"):
        parti.append(f"P.IVA {p['piva_raw']}")
    return " · ".join(parti) or "fattura senza dati"


def _voci_fattura(p: Dict[str, Any], cliente_id: Optional[str], cliente: Optional[str]) -> Optional[Dict[str, Any]]:
    stato = p.get("status")
    qid = p.get("queue_id")
    base = dict(dettaglio=_dettaglio_fattura(p), da=p.get("created_at"),
                cliente_id=cliente_id, cliente=cliente)
    if stato == "da_assegnare":
        return _voce(f"fattura:{qid}", "oggi", "Fattura da assegnare a una sede",
                     azione={"tipo": "assegna_sede", "queue_id": qid, "user_id": cliente_id}, **base)
    if stato == "unknown_tenant":
        return _voce(f"fattura:{qid}", "critico", "Fattura con P.IVA di nessun cliente",
                     azione={"tipo": "assegna_piva", "queue_id": qid, "piva": p.get("piva_raw")}, **base)
    if stato in ("failed", "dead"):
        titolo = "Fattura bloccata dopo i tentativi" if stato == "dead" else "Fattura non ancora scaricata"
        if p.get("last_error"):
            base["dettaglio"] = f"{base['dettaglio']} · {p['last_error'][:120]}"
        return _voce(f"fattura:{qid}", "critico", titolo,
                     azione={"tipo": "riprova", "queue_id": qid}, **base)
    return None


def _voci_ricavi(it: Dict[str, Any], sede_cliente: Dict[str, Dict[str, str]]) -> Optional[Dict[str, Any]]:
    stato = it.get("stato")
    if stato not in ("critico", "warning"):
        return None
    rid = str(it.get("ristorante_id") or "")
    chi = sede_cliente.get(rid, {})
    silenzio = it.get("giorni_silenzio")
    if silenzio is None:
        titolo = "Nessun ricavo mai arrivato dal gestionale"
    elif stato == "critico" and it.get("coda_problemi"):
        titolo = "Import dei ricavi bloccato"
    elif stato == "critico":
        titolo = f"Ricavi fermi da {silenzio} giorni"
    else:
        n = int(it.get("n_buchi") or 0)
        titolo = f"Mancano i ricavi di {n} giorn{'o' if n == 1 else 'i'}"
    dettaglio = it.get("nome_ristorante") or None
    if it.get("ultima_data"):
        dettaglio = f"{dettaglio} · ultimo dato {it['ultima_data']}" if dettaglio else f"ultimo dato {it['ultima_data']}"
    return _voce(f"ricavi:{rid}", "critico" if stato == "critico" else "oggi", titolo,
                 dettaglio=dettaglio, cliente_id=chi.get("user_id"), cliente=chi.get("cliente"),
                 link=f"/admin/clienti/{chi['user_id']}?tab=sedi" if chi.get("user_id") else None,
                 ristorante_id=rid or None)


_IMPORT = {
    "unknown_sender": ("oggi", "Email dei ricavi da un mittente sconosciuto"),
    "failed": ("oggi", "Email dei ricavi in nuovo tentativo"),
    "dead": ("critico", "Email dei ricavi bloccata"),
}


def _voce_import(it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    stato = it.get("status")
    if stato not in _IMPORT:
        return None
    gravita, titolo = _IMPORT[stato]
    parti = [x for x in (it.get("email_sender"), it.get("attachment_name"), (it.get("last_error") or "")[:120]) if x]
    azione = {"tipo": "collega_mittente"} if stato == "unknown_sender" else None
    return _voce(f"import:{it.get('id')}", gravita, titolo, dettaglio=" · ".join(parti) or None,
                 da=it.get("created_at"), azione=azione)


def _giorni(iso: Optional[str], adesso: datetime) -> Optional[int]:
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:  # una data senza ora (sdi_attivo_dal): mezzanotte UTC
        t = t.replace(tzinfo=adesso.tzinfo)
    return max(0, (adesso - t).days)


def componi_voci(
    *,
    adesso: datetime,
    fatture: Optional[Dict[str, Any]] = None,
    ricavi: Optional[Dict[str, Any]] = None,
    ricavi_import: Optional[Dict[str, Any]] = None,
    consumi: Optional[Dict[str, Any]] = None,
    n_categorie: int = 0,
    clienti: Iterable[Dict[str, Any]] = (),
    richieste: Iterable[Dict[str, Any]] = (),
    allarmi: Iterable[Dict[str, Any]] = (),
) -> List[Dict[str, Any]]:
    """Le voci da fare, i critici prima, ognuna dalla piu' vecchia."""
    clienti = list(clienti)
    nome = {str(c["id"]): (c.get("nome_gruppo") or c.get("nome_ristorante") or c.get("email") or "—") for c in clienti}
    sede_cliente: Dict[str, Dict[str, str]] = {}
    for c in clienti:
        for s in c.get("sedi") or []:
            sede_cliente[str(s["id"])] = {"user_id": str(c["id"]), "cliente": nome[str(c["id"])]}

    voci: List[Dict[str, Any]] = []

    for a in allarmi:
        voci.append(_voce(f"allarme:{a.get('chiave')}", a.get("gravita") or "critico",
                          a.get("testo") or a.get("chiave"), da=a.get("aperto_at"), link=a.get("link")))

    for it in (fatture or {}).get("items") or []:
        uid = str(it.get("user_id") or "") or None
        for p in it.get("problemi") or []:
            v = _voci_fattura(p, uid, it.get("nome") or (nome.get(uid) if uid else None))
            if v:
                voci.append(v)
    for p in (fatture or {}).get("orfane") or []:
        v = _voci_fattura(p, None, None)
        if v:
            voci.append(v)

    for it in (ricavi or {}).get("items") or []:
        v = _voci_ricavi(it, sede_cliente)
        if v:
            voci.append(v)

    for it in (ricavi_import or {}).get("items") or []:
        v = _voce_import(it)
        if v:
            voci.append(v)

    mesi = set((consumi or {}).get("mesi_avviso") or [])
    sopra_visto = set()
    for r in (consumi or {}).get("righe") or []:
        rid = str(r.get("ristorante_id"))
        if r.get("mese") in mesi and r.get("sopra_soglia") and rid not in sopra_visto:
            sopra_visto.add(rid)
            chi = sede_cliente.get(rid, {})
            voci.append(_voce(
                f"soglia:{rid}", "oggi", "Sopra le fatture incluse nel piano",
                dettaglio=f"{r.get('sede') or '—'} · {r.get('totale')} su {r.get('limite')} a {r.get('mese')}",
                cliente_id=chi.get("user_id"), cliente=chi.get("cliente"),
                link=f"/admin/clienti/{chi['user_id']}" if chi.get("user_id") else None,
                ristorante_id=rid,
            ))

    if n_categorie > 0:
        voci.append(_voce("categorie", "oggi",
                          f"{n_categorie} descrizion{'e' if n_categorie == 1 else 'i'} da classificare",
                          link="/admin/categorie"))

    for c in clienti:
        cid = str(c["id"])
        # SDI acceso ma nessuna fattura dallo SDI: la ricezione di quella sede si
        # e' interrotta (o non e' mai partita), e la coda fatture resta pulita
        # perche' non le arriva niente. Si misura sugli arrivi dallo SDI
        # (`ultimo_sdi_at`), non sui caricamenti: un upload a mano non dice che
        # lo SDI funziona. Niente voce se gli arrivi non si sono letti (un dato
        # assente non e' un «mai»), per una sede spenta, o nei primi 14 giorni
        # dall'accensione (`sdi_attivo_dal`).
        if c.get("attivo"):
            for s in c.get("sedi") or []:
                if not s.get("sdi_attivo") or s.get("attivo") is False or not s.get("sdi_letto"):
                    continue
                acceso = _giorni(s.get("sdi_attivo_dal"), adesso)
                if acceso is not None and acceso < GIORNI_SDI_MUTO:
                    continue
                g = _giorni(s.get("ultimo_sdi_at"), adesso)
                if g is not None and g < GIORNI_SDI_MUTO:
                    continue
                titolo = ("SDI attivo ma non e' mai arrivata una fattura" if g is None
                          else f"Nessuna fattura dallo SDI da {g} giorni")
                voci.append(_voce(f"sdi:{s['id']}", "oggi", titolo, dettaglio=s.get("nome_ristorante"),
                                  da=s.get("ultimo_sdi_at"), cliente_id=cid, cliente=nome[cid],
                                  link=f"/admin/clienti/{cid}?tab=sedi", ristorante_id=str(s["id"])))
        if not c.get("attivo") and c.get("last_seen_at") is None:
            g = _giorni(c.get("created_at"), adesso)
            if g is not None and g >= GIORNI_ATTIVAZIONE:
                voci.append(_voce(f"attivazione:{cid}", "oggi", "Non ha ancora attivato l'account",
                                  dettaglio=f"creato {g} giorni fa", da=c.get("created_at"),
                                  cliente_id=cid, cliente=nome[cid], link=f"/admin/clienti/{cid}?tab=account"))
        trial = c.get("trial") or {}
        if trial.get("active") and trial.get("days_remaining") is not None and trial["days_remaining"] <= GIORNI_FINE_PROVA:
            g = int(trial["days_remaining"])
            quando = "oggi" if g == 0 else ("domani" if g == 1 else f"fra {g} giorni")
            voci.append(_voce(f"prova:{cid}", "oggi", f"La prova finisce {quando}",
                              dettaglio="poi l'account si disattiva da solo", cliente_id=cid,
                              cliente=nome[cid], link=f"/admin/clienti/{cid}"))

    for r in richieste:
        if r.get("stato") != "nuovo":
            continue
        dettaglio = " · ".join(x for x in (r.get("ristorante_nome"), r.get("contatto_email"), (r.get("messaggio") or "")[:140]) if x)
        voci.append(_voce(f"richiesta:{r.get('id')}", "oggi",
                          f"Richiesta servizio: {r.get('servizio_label') or r.get('servizio_key') or '—'}",
                          dettaglio=dettaglio or None, da=r.get("created_at"),
                          azione={"tipo": "richiesta", "id": r.get("id")}))

    voci.sort(key=lambda v: (_ORDINE.get(v["gravita"], 9), v["da"] or "9999"))
    return voci


def problemi_per_cliente(voci: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """Quante voci aperte ha ogni cliente: la colonna «Problemi» della lista."""
    conta: Dict[str, int] = {}
    for v in voci:
        if v.get("cliente_id"):
            conta[v["cliente_id"]] = conta.get(v["cliente_id"], 0) + 1
    return conta


# ─── Riepilogo Telegram del mattino ─────────────────────────────────────────

def adesso_roma() -> datetime:
    return datetime.now(ROMA)


def e_ora_del_riepilogo(adesso: datetime) -> bool:
    """Fra le 8 e le 9:59 a Roma. Il cron gira alle 06 e alle 07 UTC: almeno
    uno dei due cade nella finestra con l'ora legale e con quella solare, e il
    secondo lo ferma la memoria degli allarmi (una volta al giorno)."""
    locale = adesso.astimezone(ROMA)
    return ORA_RIEPILOGO <= locale.hour < ORA_RIEPILOGO + 2


def chiave_riepilogo(adesso: datetime) -> str:
    return f"riepilogo:{adesso.astimezone(ROMA).date().isoformat()}"


def testo_riepilogo(voci: List[Dict[str, Any]], numeri: Dict[str, Any], url_admin: str) -> str:
    critici = sum(1 for v in voci if v["gravita"] == "critico")
    if not voci:
        testa = "☀️ Buongiorno. Oggi nell'admin non c'e' niente da fare."
    else:
        n = len(voci)
        testa = f"☀️ Buongiorno. Oggi {n} {'cosa' if n == 1 else 'cose'} da fare"
        testa += f", {critici} urgent{'e' if critici == 1 else 'i'}." if critici else "."
    righe = [testa]
    for v in voci[:MAX_RIGHE_RIEPILOGO]:
        icona = "🔴" if v["gravita"] == "critico" else "🟠"
        chi = f"{v['cliente']}: " if v.get("cliente") else ""
        righe.append(f"{icona} {chi}{v['titolo']}")
    if len(voci) > MAX_RIGHE_RIEPILOGO:
        righe.append(f"… e altre {len(voci) - MAX_RIGHE_RIEPILOGO}")
    fatti = []
    if numeri.get("fatture_ieri") is not None:
        fatti.append(f"ieri {numeri['fatture_ieri']} fatture arrivate")
    if numeri.get("fatture_mese") is not None:
        fatti.append(f"{numeri['fatture_mese']} nel mese")
    if numeri.get("costo_ai_mese") is not None:
        fatti.append(f"costo AI del mese $ {float(numeri['costo_ai_mese']):.2f}")
    if fatti:
        righe.append("")
        frase = " · ".join(fatti)
        righe.append(frase[0].upper() + frase[1:])
    righe.append(url_admin)
    return "\n".join(righe)


def finestra_ieri(adesso: datetime) -> tuple:
    """Inizio e fine di ieri a Roma, in UTC ISO: «ieri» e' il giorno del cliente."""
    oggi = adesso.astimezone(ROMA).date()
    inizio = datetime.combine(oggi - timedelta(days=1), datetime.min.time(), ROMA)
    fine = datetime.combine(oggi, datetime.min.time(), ROMA)
    return inizio.isoformat(), fine.isoformat()


def inizio_mese(adesso: datetime) -> str:
    oggi: date = adesso.astimezone(ROMA).date()
    return datetime.combine(oggi.replace(day=1), datetime.min.time(), ROMA).isoformat()
