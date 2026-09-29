"""Sotto-utenti: credenziali in piu' sopra lo STESSO account, limitate a pagine e sedi.

Il principio e' uno: il tenant non cambia. La sessione di un sotto-utente si
risolve nel dict del TITOLARE (stesso `id`, quindi tutti i filtri multi-tenant
restano quelli di prima) con sopra uno strato di restrizione:

- `pagine_abilitate` diventa il dict EFFETTIVO: pagine del titolare ∩ pagine del
  sotto-utente, con tutte le chiavi-pagina esplicite. I lettori che gia' esistono
  (menu, chat, briefing, policy upload) applicano l'intersezione senza saperlo;
- `ristorante_id` e' la sede attiva del sotto-utente, sempre fra quelle assegnate;
- `email` e' la SUA: l'admin si riconosce per email, e un titolare admin non deve
  trasmettere l'accesso a chi lavora nel suo account;
- `_sotto_utente` porta chi sta agendo e le sue sedi, per i controlli espliciti.

Per un titolare `_sotto_utente` non c'e', e ogni helper di questo modulo risponde
"nessuna restrizione": e' la garanzia che chi non ha sotto-utenti non cambia.

Schema: supabase/migrations/20260928215000_sotto_utenti.sql.
"""

from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import HTTPException

from config.logger_setup import get_logger

logger = get_logger("sotto_utenti")

# Le chiavi-pagina dell'account: sono quelle di `_PAGINE_FLAG` in
# services/fastapi_worker.py (un test le tiene allineate).
PAGINE_ACCOUNT = frozenset({
    "analisi_fatture", "margini", "analisi_e_tag", "prezzi",
    "scadenziario", "agenda", "workspace",
})

# Home e Catena non sono pagine dell'account (per il titolare sono sempre
# accese): esistono solo per i sotto-utenti. Home = accesso all'AI.
PAGINA_HOME = "home"
PAGINA_CATENA = "catena"
PAGINE_SOTTO_UTENTE = PAGINE_ACCOUNT | {PAGINA_HOME, PAGINA_CATENA}

CHIAVE_CONTESTO = "_sotto_utente"

_COLONNE_SOTTO_UTENTE = (
    "id, titolare_id, email, nome, attivo, pagine, ultimo_ristorante_id, "
    "tema, vista_fatture, privacy_accepted_at"
)


def _pagine_account_del_titolare(raw) -> Optional[Set[str]]:
    """Pagine accese sull'account del titolare. None = tutte (nessuna restrizione).

    Stessa semantica di `_normalize_pagine`: NULL e un dict senza chiavi-pagina
    (caso OFFSIDE) sono "tutto aperto"; in un dict con chiavi-pagina, assente =
    spenta.
    """
    if raw is None:
        return None
    if isinstance(raw, list):
        return {str(p) for p in raw if str(p) in PAGINE_ACCOUNT}
    if isinstance(raw, dict):
        if not any(k in PAGINE_ACCOUNT for k in raw):
            return None
        return {k for k, v in raw.items() if v and k in PAGINE_ACCOUNT}
    return None


def pagine_effettive(raw_titolare, pagine_sotto_utente, catena_consentita: bool) -> Dict[str, Any]:
    """Il dict `pagine_abilitate` che vede un sotto-utente.

    Ogni chiave-pagina e' ESPLICITA (True/False): cosi' `_normalize_pagine` non
    puo' ricadere nel "tutto aperto" del caso OFFSIDE. Le chiavi non-pagina del
    titolare (`tab_off_*`, `blocco_mesi_precedenti`, `trigger_servizi_off`)
    restano sue: sono impostazioni dell'account, non permessi della persona.

    Una pagina e' accesa solo se `True` nel dict del sotto-utente: qualunque altro
    valore (assente, "true", 1) e' spenta. La Catena richiede anche tutte le sedi.
    """
    su = pagine_sotto_utente if isinstance(pagine_sotto_utente, dict) else {}
    del_titolare = _pagine_account_del_titolare(raw_titolare)

    effettive: Dict[str, Any] = {}
    if isinstance(raw_titolare, dict):
        effettive.update({k: v for k, v in raw_titolare.items() if k not in PAGINE_SOTTO_UTENTE})
    for pagina in sorted(PAGINE_ACCOUNT):
        del_titolare_ok = del_titolare is None or pagina in del_titolare
        effettive[pagina] = bool(del_titolare_ok and su.get(pagina) is True)
    effettive[PAGINA_HOME] = su.get(PAGINA_HOME) is True
    effettive[PAGINA_CATENA] = su.get(PAGINA_CATENA) is True and bool(catena_consentita)
    return effettive


def sovrapponi(
    titolare: Dict[str, Any],
    sotto_utente: Dict[str, Any],
    sedi_assegnate: Iterable[str],
    sedi_account: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Il dict utente di una sessione di sotto-utente. None = sessione non valida.

    `sedi_account`: le sedi ATTIVE del titolare (`id`, `sede_tecnica`), nell'ordine
    in cui `_resolve_ristorante_id` sceglie la sede di default (created_at).

    Le sedi consentite sono l'intersezione fra assegnate e attive dell'account,
    ricalcolata a ogni risoluzione: una sede disattivata o passata a un altro
    account smette di essere visibile anche se la riga di assegnazione resta.
    Senza nessuna sede consentita (non tecnica) il sotto-utente non ha niente da
    vedere: la sessione non vale.

    La sede tecnica («Costi comuni di gruppo») non e' un punto vendita: contiene i
    costi di tutta la catena, quindi e' consentita solo a chi ha la Catena, e mai
    per semplice assegnazione.
    """
    assegnate = {str(s) for s in sedi_assegnate}
    attive = [(str(r["id"]), bool(r.get("sede_tecnica"))) for r in sedi_account]
    operative = [rid for rid, tecnica in attive if rid in assegnate and not tecnica]
    if not operative:
        return None

    tutte_le_operative = {rid for rid, tecnica in attive if not tecnica}
    catena_consentita = tutte_le_operative.issubset(set(operative))
    tecniche = [rid for rid, tecnica in attive if tecnica]
    consentite = operative + (tecniche if catena_consentita else [])

    scelta = sotto_utente.get("ultimo_ristorante_id")
    sede_attiva = str(scelta) if scelta and str(scelta) in operative else operative[0]

    effettive = pagine_effettive(
        titolare.get("pagine_abilitate"), sotto_utente.get("pagine"), catena_consentita
    )

    utente = dict(titolare)
    utente["_titolare_email"] = titolare.get("email")
    utente["email"] = sotto_utente.get("email")
    utente["nome_referente"] = sotto_utente.get("nome")
    utente["tema"] = sotto_utente.get("tema") or "dark"
    utente["vista_fatture"] = sotto_utente.get("vista_fatture") or "agenda"
    utente["privacy_accepted_at"] = sotto_utente.get("privacy_accepted_at")
    utente["pagine_abilitate"] = effettive
    utente["ultimo_ristorante_id"] = sede_attiva
    utente["ristorante_id"] = sede_attiva
    utente[CHIAVE_CONTESTO] = {
        "id": str(sotto_utente["id"]),
        "email": sotto_utente.get("email"),
        "nome": sotto_utente.get("nome"),
        "sedi": consentite,
        "sedi_operative": operative,
        "home": effettive[PAGINA_HOME],
        "catena": effettive[PAGINA_CATENA],
    }
    return utente


def carica_e_sovrapponi(titolare: Dict[str, Any], sotto_utente_id: str, sb) -> Optional[Dict[str, Any]]:
    """Legge sotto-utente, sedi assegnate e sedi dell'account, e sovrappone.

    None se il sotto-utente non esiste, non e' attivo, non e' di questo titolare,
    o non ha sedi: in tutti questi casi la sessione non deve valere.
    """
    titolare_id = str(titolare["id"])
    su = (
        sb.table("sotto_utenti")
        .select(_COLONNE_SOTTO_UTENTE)
        .eq("id", str(sotto_utente_id))
        .eq("titolare_id", titolare_id)
        .eq("attivo", True)
        .limit(1)
        .execute()
    )
    if not su.data:
        return None
    assegnate = (
        sb.table("sotto_utenti_sedi")
        .select("ristorante_id")
        .eq("sotto_utente_id", str(sotto_utente_id))
        .execute()
    )
    sedi = (
        sb.table("ristoranti")
        .select("id, sede_tecnica")
        .eq("user_id", titolare_id)
        .eq("attivo", True)
        .order("created_at")
        .execute()
    )
    return sovrapponi(
        titolare,
        su.data[0],
        [r["ristorante_id"] for r in (assegnate.data or [])],
        sedi.data or [],
    )


# ─── Helper per gli endpoint ────────────────────────────────────────────────


def contesto(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Il contesto del sotto-utente, o None se chi agisce e' il titolare."""
    if not user:
        return None
    ctx = user.get(CHIAVE_CONTESTO)
    return ctx if isinstance(ctx, dict) else None


def e_sotto_utente(user: Optional[Dict[str, Any]]) -> bool:
    return contesto(user) is not None


def sotto_utente_id(user: Optional[Dict[str, Any]]) -> Optional[str]:
    ctx = contesto(user)
    return str(ctx["id"]) if ctx else None


def sedi_consentite(user: Optional[Dict[str, Any]]) -> Optional[Set[str]]:
    """None per il titolare (nessuna restrizione), l'insieme delle sedi per il sotto-utente."""
    ctx = contesto(user)
    if ctx is None:
        return None
    return {str(s) for s in ctx.get("sedi") or []}


def sede_consentita(user: Optional[Dict[str, Any]], ristorante_id: Optional[str]) -> bool:
    consentite = sedi_consentite(user)
    if consentite is None:
        return True
    return bool(ristorante_id) and str(ristorante_id) in consentite


def verifica_sede_consentita(user: Optional[Dict[str, Any]], ristorante_id: Optional[str]) -> None:
    """403 se chi agisce e' un sotto-utente e la sede non e' fra le sue."""
    if not sede_consentita(user, ristorante_id):
        raise HTTPException(status_code=403, detail="Sede non consentita per questo utente")


def filtra_sedi(user: Optional[Dict[str, Any]], ids: Iterable[str]) -> List[str]:
    """Tiene solo le sedi consentite (tutte, per il titolare), nell'ordine dato."""
    consentite = sedi_consentite(user)
    return [str(i) for i in ids if consentite is None or str(i) in consentite]


def ha_pagina(user: Optional[Dict[str, Any]], pagina: str) -> bool:
    """True se il sotto-utente ha la pagina (sempre True per il titolare).

    Per il titolare NON si guarda `pagine_abilitate`: il blocco lato server delle
    pagine vale solo per i sotto-utenti, e per il titolare resta il comportamento
    di oggi (menu e guardie del frontend).
    """
    if contesto(user) is None:
        return True
    pagine = user.get("pagine_abilitate") if user else None
    return isinstance(pagine, dict) and pagine.get(pagina) is True


def catena_consentita(user: Optional[Dict[str, Any]]) -> bool:
    ctx = contesto(user)
    return True if ctx is None else bool(ctx.get("catena"))


def verifica_catena(user: Optional[Dict[str, Any]]) -> None:
    """403 al sotto-utente senza Catena effettiva (flag acceso E tutte le sedi)."""
    if not catena_consentita(user):
        raise HTTPException(status_code=403, detail="Vista catena non consentita per questo utente")


def vieta_ai_sotto_utenti(user: Optional[Dict[str, Any]]) -> None:
    """403 per le azioni riservate al titolare (area Account, impostazioni di business)."""
    if e_sotto_utente(user):
        raise HTTPException(status_code=403, detail="Operazione riservata al titolare dell'account")


def pagine_per_client(user: Dict[str, Any], pagine_normalizzate: Optional[List[str]]) -> Optional[List[str]]:
    """La lista `pagine_abilitate` di UserPublic.

    Per il titolare e' quella di oggi, identica. Per il sotto-utente aggiunge
    `home`/`catena` quando accese: `_normalize_pagine` non le conosce, perche' non
    sono pagine dell'account.
    """
    ctx = contesto(user)
    if ctx is None:
        return pagine_normalizzate
    lista = list(pagine_normalizzate or [])
    for chiave in (PAGINA_HOME, PAGINA_CATENA):
        if ctx.get(chiave) and chiave not in lista:
            lista.append(chiave)
    return lista
