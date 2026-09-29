"""Quali rotte del worker puo' chiamare un sotto-utente, e con quali pagine.

Il controllo e' CHIUSO PER DEFAULT: una rotta che non compare qui risponde 403 a
un sotto-utente. Una rotta nuova dimenticata e' quindi un rifiuto a un
responsabile legittimo, mai una falla. Il presidio (tests/test_permessi_rotte.py)
pretende che ogni rotta dell'app sia dichiarata in uno degli insiemi sotto, e che
non ne resti dichiarata una che non esiste piu'.

Come scatta. `registra_rotta` e' una dipendenza GLOBALE dell'app: prima di ogni
endpoint mette la rotta risolta in un ContextVar. `verifica_sessione_da_cookie`
(services/auth_service.py), quando la sessione e' di un sotto-utente, chiama
`verifica_rotta_corrente`. Il controllo sta quindi DENTRO ogni risoluzione di
sessione, non in una lettura separata che potrebbe fallire da sola e lasciar
passare. Una sessione di sotto-utente risolta fuori da una richiesta (nessuna
rotta registrata) e' rifiutata.

Per il titolare non cambia niente: la dipendenza scrive solo il ContextVar, e il
controllo non scatta. Il blocco lato server delle pagine vale per i sotto-utenti.

La mappa segue le pagine che CHIAMANO la rotta (misurato il 28-29/09/2026 sul
frontend), non il file del router: diario, spese e personale stanno in
routers/workspace.py ma sono della pagina Agenda; la scheda «Scadenze» di
/catena/fatture riusa lo scadenziario, quindi le sue rotte valgono con
`scadenziario` OPPURE `catena`. `/m/turni` e `/m/diario` sono Agenda.

Le chiamate interne ereditano la rotta d'ingresso: gli strumenti della chat e il
briefing leggono i dati chiamando funzioni di altri endpoint, e valgono come
`/api/chat` o `/api/home/*`. E' la «Home completa»; i tool della chat restano
limitati alle pagine dal loro gate (`_CHAT_TOOL_FLAG`).

La pagina la controlla questo modulo. La SEDE la controllano gli endpoint (la sede
attiva viene dalla sessione, gia' vincolata alle sedi del sotto-utente; le rotte
che prendono una sede esplicita la verificano con
`sotto_utenti_service.verifica_sede_consentita`).
"""

from contextvars import ContextVar
from typing import Dict, FrozenSet, Optional, Set, Tuple

from fastapi import HTTPException, Request

from services import sotto_utenti_service as _su

Rotta = Tuple[str, str]

F = "analisi_fatture"
M = "margini"
T = "analisi_e_tag"
P = "prezzi"
S = "scadenziario"
A = "agenda"
W = "workspace"
H = _su.PAGINA_HOME
C = _su.PAGINA_CATENA


def _p(*pagine: str) -> FrozenSet[str]:
    return frozenset(pagine)


PAGINE_PER_ROTTA: Dict[Rotta, FrozenSet[str]] = {
    # ── Analisi Fatture ──────────────────────────────────────────────────
    ("GET", "/api/fatture"): _p(F),
    ("GET", "/api/fatture/articoli-aggregati"): _p(F),
    ("GET", "/api/fatture/categorie"): _p(F),
    ("GET", "/api/fatture/fornitori"): _p(F),
    ("GET", "/api/fatture/kpi"): _p(F),
    ("GET", "/api/fatture/mesi-disponibili"): _p(F),
    ("GET", "/api/fatture/pivot"): _p(F),
    ("GET", "/api/fatture/righe-articolo"): _p(F),
    ("GET", "/api/fatture/trend"): _p(F),
    ("POST", "/api/fatture/righe-export"): _p(F),
    ("POST", "/api/fatture/categoria-batch"): _p(F),
    ("PATCH", "/api/fatture/{riga_id}/categoria"): _p(F),
    ("POST", "/api/upload/start-session"): _p(F),
    ("POST", "/api/upload/invoice"): _p(F),
    # ── Margini ──────────────────────────────────────────────────────────
    ("GET", "/api/margini"): _p(M),
    ("POST", "/api/margini"): _p(M),
    ("GET", "/api/margini/analisi"): _p(M),
    ("GET", "/api/margini/analisi-avanzata"): _p(M),
    ("GET", "/api/margini/analisi-centri"): _p(M),
    ("POST", "/api/margini/cella"): _p(M),
    ("GET", "/api/margini/costo-personale-turni"): _p(M),
    ("GET", "/api/margini/costo-spese-extra"): _p(M),
    ("GET", "/api/margini/fatturato-centri"): _p(M),
    ("POST", "/api/margini/fatturato-centri"): _p(M),
    ("GET", "/api/margini/fatturato-centri-giorni"): _p(M),
    ("GET", "/api/margini/kpi"): _p(M),
    ("POST", "/api/ricavi/batch"): _p(M),
    ("GET", "/api/ricavi/coperti-analisi"): _p(M),
    ("GET", "/api/ricavi/coperti-categorie"): _p(M),
    ("POST", "/api/ricavi/modalita"): _p(M),
    # La «Conferma» delle cifre dettate all'assistente (incasso, personale, fatturato).
    ("POST", "/api/assistente/registra"): _p(M),
    # Incassi del giorno: anche /m/turni (Agenda su mobile).
    ("GET", "/api/ricavi/giornalieri"): _p(M, A),
    ("POST", "/api/ricavi/giornalieri"): _p(M, A),
    ("DELETE", "/api/ricavi/giornalieri"): _p(M, A),
    ("GET", "/api/ricavi/modalita"): _p(M, A),
    # ── Analisi e Tag ────────────────────────────────────────────────────
    ("GET", "/api/tag"): _p(T),
    ("POST", "/api/tag"): _p(T),
    ("PUT", "/api/tag/{tag_id}"): _p(T),
    ("DELETE", "/api/tag/{tag_id}"): _p(T),
    ("GET", "/api/tag/descrizioni"): _p(T),
    ("GET", "/api/tag/{tag_id}/prodotti"): _p(T),
    ("POST", "/api/tag/{tag_id}/prodotti"): _p(T),
    ("DELETE", "/api/tag/prodotti/{assoc_id}"): _p(T),
    ("GET", "/api/tag/{tag_id}/analisi"): _p(T),
    ("GET", "/api/tag/{tag_id}/orfani"): _p(T),
    ("GET", "/api/tag/suggestions"): _p(T),
    ("POST", "/api/tag/suggestions/{sid}/accept"): _p(T),
    ("POST", "/api/tag/suggestions/{sid}/dismiss"): _p(T),
    ("POST", "/api/tag/suggestions/{sid}/snooze"): _p(T),
    # ── Prezzi ───────────────────────────────────────────────────────────
    ("GET", "/api/prezzi/variazioni"): _p(P),
    ("GET", "/api/prezzi/storico-prodotto"): _p(P),
    ("GET", "/api/prezzi/preferiti"): _p(P),
    ("POST", "/api/prezzi/preferiti"): _p(P),
    ("DELETE", "/api/prezzi/preferiti"): _p(P),
    ("GET", "/api/prezzi/note-credito"): _p(P),
    ("GET", "/api/prezzi/sconti-omaggi"): _p(P),
    ("GET", "/api/prezzi/score-fornitori"): _p(P),
    ("GET", "/api/prezzi/soglia-alert"): _p(P),
    # ── Scadenziario (e la scheda «Scadenze» di /catena/fatture) ─────────
    ("GET", "/api/scadenziario"): _p(S),
    ("GET", "/api/scadenziario/calendario"): _p(S),
    ("POST", "/api/scadenziario/notifica"): _p(S),
    ("GET", "/api/cestino"): _p(S),
    ("POST", "/api/fatture/sposta-sede"): _p(S),
    ("GET", "/api/scadenziario/anteprima"): _p(S, C, P),
    ("GET", "/api/scadenziario/fornitori"): _p(S, C),
    ("GET", "/api/scadenziario/regole"): _p(S, C),
    ("POST", "/api/scadenziario/regole"): _p(S, C),
    ("DELETE", "/api/scadenziario/regole/{regola_id}"): _p(S, C),
    ("POST", "/api/scadenziario/pagata"): _p(S, C),
    ("POST", "/api/scadenziario/scadenza"): _p(S, C),
    ("POST", "/api/fatture/elimina"): _p(S, C),
    ("POST", "/api/fatture/oscura"): _p(S, C),
    ("POST", "/api/cestino/ripristina"): _p(S, C),
    ("POST", "/api/cestino/elimina"): _p(S, C),
    ("POST", "/api/cestino/svuota"): _p(S, C),
    # ── Agenda (anche /m/diario e /m/turni) ──────────────────────────────
    ("GET", "/api/workspace/diario"): _p(A),
    ("POST", "/api/workspace/diario"): _p(A),
    ("PATCH", "/api/workspace/diario/{evento_id}"): _p(A),
    ("DELETE", "/api/workspace/diario/{evento_id}"): _p(A),
    ("GET", "/api/workspace/spese"): _p(A),
    ("POST", "/api/workspace/spese"): _p(A),
    ("PATCH", "/api/workspace/spese/{spesa_id}"): _p(A),
    ("DELETE", "/api/workspace/spese/{spesa_id}"): _p(A),
    ("GET", "/api/workspace/personale"): _p(A),
    ("POST", "/api/workspace/personale"): _p(A),
    ("PATCH", "/api/workspace/personale/{turno_id}"): _p(A),
    ("DELETE", "/api/workspace/personale/{turno_id}"): _p(A),
    ("PATCH", "/api/workspace/personale/{turno_id}/stato-giorno"): _p(A),
    ("POST", "/api/workspace/personale/stato-giorno-intervallo"): _p(A),
    ("POST", "/api/workspace/personale/mensile"): _p(A),
    ("PATCH", "/api/workspace/personale/mensile/{turno_id}"): _p(A),
    ("POST", "/api/workspace/personale/copia-mese"): _p(A),
    ("POST", "/api/workspace/personale/copia-settimana"): _p(A),
    ("GET", "/api/workspace/personale/export-mensile"): _p(A),
    ("GET", "/api/workspace/dipendenti"): _p(A),
    ("POST", "/api/workspace/dipendenti"): _p(A),
    ("PATCH", "/api/workspace/dipendenti/{dipendente_id}"): _p(A),
    ("DELETE", "/api/workspace/dipendenti/{dipendente_id}"): _p(A),
    ("PATCH", "/api/workspace/dipendenti/{dipendente_id}/disattiva"): _p(A),
    ("PATCH", "/api/workspace/dipendenti/{dipendente_id}/riattiva"): _p(A),
    ("POST", "/api/workspace/dipendenti/{dipendente_id}/merge-in/{target_id}"): _p(A),
    ("GET", "/api/workspace/regole-turni"): _p(A),
    ("POST", "/api/workspace/regole-turni"): _p(A),
    ("PATCH", "/api/workspace/regole-turni/{regola_id}"): _p(A),
    ("DELETE", "/api/workspace/regole-turni/{regola_id}"): _p(A),
    ("POST", "/api/workspace/regole-turni/genera"): _p(A),
    # ── Workspace ────────────────────────────────────────────────────────
    ("GET", "/api/workspace/foodcost/ingredienti"): _p(W),
    ("GET", "/api/workspace/foodcost/ingredienti-manuali"): _p(W),
    ("POST", "/api/workspace/foodcost/ingredienti-manuali"): _p(W),
    ("PATCH", "/api/workspace/foodcost/ingredienti-manuali/{ing_id}"): _p(W),
    ("DELETE", "/api/workspace/foodcost/ingredienti-manuali/{ing_id}"): _p(W),
    ("GET", "/api/workspace/foodcost/ricette"): _p(W),
    ("POST", "/api/workspace/foodcost/ricette"): _p(W),
    ("GET", "/api/workspace/foodcost/ricette/{ricetta_id}"): _p(W),
    ("PATCH", "/api/workspace/foodcost/ricette/{ricetta_id}"): _p(W),
    ("DELETE", "/api/workspace/foodcost/ricette/{ricetta_id}"): _p(W),
    ("POST", "/api/workspace/foodcost/ricette/riordina"): _p(W),
    ("POST", "/api/workspace/foodcost/calcola"): _p(W),
    ("GET", "/api/workspace/inventario"): _p(W),
    ("POST", "/api/workspace/inventario"): _p(W),
    ("DELETE", "/api/workspace/inventario"): _p(W),
    ("PATCH", "/api/workspace/inventario/{voce_id}"): _p(W),
    ("DELETE", "/api/workspace/inventario/{voce_id}"): _p(W),
    ("GET", "/api/workspace/inventario/articoli"): _p(W),
    ("POST", "/api/workspace/inventario/batch"): _p(W),
    ("POST", "/api/workspace/inventario/copia-snapshot"): _p(W),
    ("GET", "/api/workspace/inventario/snapshot-dates"): _p(W),
    # ── Home (= accesso all'AI) ──────────────────────────────────────────
    ("GET", "/api/home/briefing"): _p(H),
    ("GET", "/api/home/kpi"): _p(H),
    ("GET", "/api/home/salute"): _p(H),
    ("GET", "/api/home/alert-prezzi"): _p(H),
    ("GET", "/api/dashboard/stats"): _p(H),
    # Il contesto (sede/catena) lo ricontrolla chat_ai: sede → home, catena → catena.
    ("POST", "/api/chat"): _p(H, C),
    # ── Catena (sedi tutte assegnate: lo garantisce la sovrapposizione) ──
    ("GET", "/api/gruppo/overview"): _p(C),
    ("GET", "/api/gruppo/segnali"): _p(C),
    ("GET", "/api/gruppo/notifiche"): _p(C),
    ("GET", "/api/gruppo/chat-config"): _p(C),
    ("GET", "/api/gruppo/assistant-config"): _p(C),
    ("GET", "/api/gruppo/costi-comuni"): _p(C),
    ("GET", "/api/gruppo/margini-coperti"): _p(C),
    ("GET", "/api/gruppo/spreco-categorie"): _p(C),
    ("GET", "/api/gruppo/spesa-pivot"): _p(C),
    ("GET", "/api/gruppo/cestino"): _p(C),
    ("GET", "/api/gruppo/scadenziario"): _p(C),
    ("GET", "/api/gruppo/tag"): _p(C),
    ("POST", "/api/gruppo/tag"): _p(C),
    ("DELETE", "/api/gruppo/tag/{tag_id}"): _p(C),
    ("GET", "/api/gruppo/tag/descrizioni"): _p(C),
    ("GET", "/api/gruppo/tag/{tag_id}/analisi"): _p(C),
    ("GET", "/api/gruppo/tag/{tag_id}/prodotti"): _p(C),
    ("POST", "/api/gruppo/tag/{tag_id}/prodotti"): _p(C),
    ("DELETE", "/api/gruppo/tag/prodotti/{assoc_id}"): _p(C),
    ("GET", "/api/fatture/da-assegnare"): _p(C),
    ("POST", "/api/fatture/assegna-sede"): _p(C),
    ("POST", "/api/fatture/scarta-da-coda"): _p(C),
    # Il riparto agisce su TUTTE le sedi del gruppo: solo con la Catena, anche
    # quando parte da Analisi Fatture (riga ripartita) o dallo Scadenziario
    # («Ripartisci»). Lo ripete `_require_catena` nel router.
    ("PATCH", "/api/riparto/riga-categoria"): _p(C),
    ("POST", "/api/riparto/da-fattura"): _p(C),
    ("GET", "/api/riparto/regola-fornitore"): _p(C),
    ("POST", "/api/riparto/da-coda"): _p(C),
    ("GET", "/api/riparto/anteprima-coda"): _p(C),
    ("POST", "/api/riparto/manuale"): _p(C),
    ("PATCH", "/api/riparto/{riparto_id}"): _p(C),
    ("DELETE", "/api/riparto/{riparto_id}"): _p(C),
    ("POST", "/api/riparto/{riparto_id}/duplica"): _p(C),
}

# Ogni sotto-utente, qualunque pagina abbia: sessione, sedi, preferenze
# personali, notifiche (filtrate per sede dall'endpoint), privacy.
ROTTE_COMUNI: Set[Rotta] = {
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/accetta-privacy"),
    ("GET", "/api/account/me"),
    ("GET", "/api/account/sedi"),
    ("POST", "/api/account/cambia-sede"),
    ("POST", "/api/account/preferenze"),
    ("POST", "/api/account/cambia-password"),
    ("GET", "/api/notifiche"),
    ("POST", "/api/notifiche/{notifica_id}/dismiss"),
    # Legge se la chat e' accesa sulla sede: il layout di /m la chiede su ogni pagina.
    ("GET", "/api/home/config"),
    ("POST", "/api/assistenza/lead"),
}

# Mai a un sotto-utente: azioni sull'intero account e impostazioni di business.
# (Oltre a tutto /api/admin/*.)
ROTTE_VIETATE: Set[Rotta] = {
    ("POST", "/api/account/elimina"),
    ("GET", "/api/account/esporta-dati"),
    ("POST", "/api/account/svuota-dati"),
    ("POST", "/api/home/config"),
    ("POST", "/api/prezzi/soglia-alert"),
    ("POST", "/api/gruppo/assistant-config"),
    # Import multi-sede: smista righe su qualunque sede dell'account. Il frontend
    # non lo chiama (28/09/2026).
    ("POST", "/api/ricavi/import-xls"),
}

# Rotte senza sessione cliente (login, reset, webhook, chiamate interne).
# Dichiarate perche' il presidio sappia che non sono dimenticate. Non risolvono
# la sessione, quindi il controllo qui non scatta: le protegge la chiave del
# worker, o non espongono dati di un account.
ROTTE_SENZA_SESSIONE: Set[Rotta] = {
    ("GET", "/health"),
    ("POST", "/webhook"),
    ("POST", "/api/classify"),
    ("POST", "/api/parse"),
    ("POST", "/api/interno/email-settimanale"),
    ("POST", "/api/email/disiscrizione"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/reset-request"),
    ("POST", "/api/auth/reset-confirm"),
    # Admin «a gate macchina»: solo la chiave del worker, chiamate da script
    # schedulati (GitHub Actions), non da un browser; nessun proxy Next.
    ("GET", "/api/admin/riparto/incoerenze"),
    ("POST", "/api/admin/riparto/auto-pulisci"),
    ("GET", "/api/admin/sistema/invoicetronic-eventi-sconosciuti"),
    ("GET", "/api/admin/retail/categorie-incoerenti"),
}

PREFISSO_ADMIN = "/api/admin/"

_ROTTA_CORRENTE: ContextVar[Optional[Rotta]] = ContextVar("rotta_corrente", default=None)


async def registra_rotta(request: Request) -> None:
    """Dipendenza globale dell'app: la rotta di questa richiesta, per il controllo.

    `async` di proposito: gira nel contesto della richiesta, e l'endpoint (anche
    sincrono, nel threadpool) ne eredita una copia. Una dipendenza sincrona
    girerebbe in un thread e il valore andrebbe perso.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    _ROTTA_CORRENTE.set((request.method.upper(), path) if path else None)


def rotta_consentita(user: Optional[dict], rotta: Optional[Rotta]) -> bool:
    """True per il titolare; per il sotto-utente solo le rotte comuni o di una sua pagina."""
    if not _su.e_sotto_utente(user):
        return True
    if rotta is None:
        return False
    if rotta in ROTTE_COMUNI:
        return True
    pagine = PAGINE_PER_ROTTA.get(rotta)
    return bool(pagine) and any(_su.ha_pagina(user, p) for p in pagine)


def verifica_rotta_corrente(user: Optional[dict]) -> None:
    """403 se chi agisce e' un sotto-utente e la rotta di questa richiesta non gli e' consentita."""
    if not rotta_consentita(user, _ROTTA_CORRENTE.get()):
        raise HTTPException(status_code=403, detail="Pagina non consentita per questo utente")
