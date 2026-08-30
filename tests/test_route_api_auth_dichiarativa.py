"""Rete strutturale sull'auth degli endpoint del worker (audit route API, 30/8/2026).

Il difetto che questo file esiste per impedire non e' un endpoint sbagliato oggi:
e' che il default sia APERTO. Dei 238 endpoint, 228 risolvono l'identita' del
chiamante, ma lo fanno IMPERATIVAMENTE nel corpo dell'handler
(`user = _resolve_user_from_token(authorization)`), e tutti e 12 gli APIRouter
sono nudi — nessun `dependencies=[...]` a livello di router. Un endpoint nuovo
che dimentica quella riga e' esposto e niente lo segnala: non un tipo, non un
lint, non un test. La copertura odierna e' disciplina, non struttura.

Qui la struttura: chi aggiunge un endpoint senza identita' deve AGGIUNGERSI
all'allowlist qui sotto motivando. E' il punto in cui il default passa da
aperto a chiuso.

PERCHE' PER INTROSPEZIONE E NON PER GREP
Il grep di `_resolve_user_from_token` conta 187 occorrenze contro 179 endpoint
che lo usano: alcune funzioni la chiamano piu' volte, altre occorrenze sono
wrapper e import. Un test costruito su regex del sorgente misura il proprio
pattern, non l'app (lezione del punto 9: un mutante che non matcha il sorgente
non prova niente). Si parte quindi da `app.routes`, che e' la lista vera e
completa degli endpoint montati.

ATTENZIONE A UNA TRAPPOLA GIA' PAGATA IN FASE DI STESURA
Il gate admin esiste in DUE forme (documentate in services/routers/admin.py:7-8):
`dependencies=[Depends(_verify_admin)]` nel decoratore, e
`admin_user: dict = Depends(_verify_admin)` come parametro di funzione. Una
prima stesura di questo controllo guardava solo `route.dependencies` e
dichiarava 44 endpoint "senza identita'", di cui 34 falsi positivi tutti admin.
`_dipendenze()` sotto guarda entrambe le forme (piu' Annotated[], oggi non
usata nel repo): se la si semplifica a una sola, il test torna a mentire.
Resta fuori la sub-dependency annidata — un Depends(wrapper) che dipende a sua
volta dal gate non viene riconosciuto. E' fail-safe (falso positivo), ma va
saputo.
"""

import inspect

import pytest
from fastapi import params as fastapi_params
from fastapi.routing import APIRoute


# ── Gli unici endpoint che possono non risolvere l'identita' del chiamante ────
# Ogni voce porta la ragione. Aggiungerne una e' una decisione di sicurezza
# esplicita, non un adempimento: se ti trovi qui per far passare la CI, quasi
# sicuramente all'endpoint manca `authorization: Optional[str] = Header(None)`
# e la chiamata a _resolve_user_from_token.
SENZA_IDENTITA_MOTIVATI = {
    # Pubblici per necessita'
    ("GET", "/health"): "Healthcheck Railway: deve rispondere senza credenziali.",
    ("POST", "/webhook"): "410 hard-coded, corpo di 3 righe. Zero superficie.",
    # Flusso di autenticazione: l'identita' e' cio' che stanno stabilendo
    ("POST", "/api/auth/login"): "Stabilisce la sessione. Gate: X-Worker-Key + rate-limit IP.",
    ("POST", "/api/auth/reset-request"): (
        "Reset password da email: per definizione senza sessione. Rate-limit IP e "
        "risposta generica anti-enumerazione (fastapi_worker.py:8368-8370)."
    ),
    ("POST", "/api/auth/reset-confirm"): "Reset password col token via email, non con la sessione.",
    # Server-to-server: nessun utente, gate = chiave macchina
    ("POST", "/api/classify"): "Chiamato dal queue-worker, non dal browser. Gate: X-Worker-Key + rate-limit IP.",
    ("POST", "/api/parse"): (
        "Chiamato dal queue-worker (services/worker_client.py:234), non dal browser. "
        "Gate: X-Worker-Key + rate-limit IP. NOTA: accetta user_id via Form non "
        "verificato (fastapi_worker.py:847) — read-only, precarica la memoria "
        "classificazioni e non scrive; registrato nell'audit del 30/8/2026."
    ),
    ("GET", "/api/admin/riparto/incoerenze"): (
        "Consumatore dichiarato: workflow GitHub Actions riparto_coerenza_check.yml, "
        "non un admin che naviga /admin. Scelta argomentata in riparto.py:1004-1010, "
        "che avverte: per esporlo alla pagina admin servirebbe _verify_admin."
    ),
    ("POST", "/api/admin/riparto/auto-pulisci"): (
        "Stesso gate macchina di /incoerenze (riparto.py:1069-1070). Con ?apply=true "
        "SCRIVE su qualunque account: rischio noto e accettato, non una dimenticanza."
    ),
    ("GET", "/api/admin/sistema/invoicetronic-eventi-sconosciuti"): (
        "Diagnostica consumata da automazione, gate X-Worker-Key (admin.py:2291)."
    ),
}

# Validano il bearer inline invece di passare da _resolve_user_from_token.
# Sono autenticati — e' duplicazione, non un buco — ma il fatto che siano solo
# questi tre e' cio' che rende il parametro `authorization` un segnale
# affidabile di "risolve l'identita'". Se la lista cresce, il segnale si sta
# sfaldando e questo file va ripensato prima di allargare l'atteso.
AUTENTICATI_INLINE = {
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/accetta-privacy"),
    ("POST", "/api/auth/logout"),
}


def _app():
    import services.fastapi_worker as fw

    return fw.app


def _dipendenze(route):
    """Nomi delle dipendenze FastAPI, in ENTRAMBE le forme in cui il repo le usa."""
    nomi = []
    for dep in route.dependencies:
        fn = getattr(dep, "dependency", None)
        if fn is not None:
            nomi.append(getattr(fn, "__name__", str(fn)))
    for par in inspect.signature(route.endpoint).parameters.values():
        if isinstance(par.default, fastapi_params.Depends) and par.default.dependency is not None:
            nomi.append(getattr(par.default.dependency, "__name__", str(par.default.dependency)))
        # Terza forma, oggi assente dal repo (0 occorrenze al 30/8/2026) ma
        # legale in FastAPI: Annotated[dict, Depends(_verify_admin)]. Qui il
        # Depends sta in __metadata__, non nel default — senza questo ramo un
        # endpoint gatato cosi' risulterebbe scoperto. E' un falso positivo
        # (rompe la CI, non apre l'app), ma un test che sbaglia insegna a
        # ignorarlo.
        for meta in getattr(par.annotation, "__metadata__", ()):
            if isinstance(meta, fastapi_params.Depends) and meta.dependency is not None:
                nomi.append(getattr(meta.dependency, "__name__", str(meta.dependency)))
    return nomi


def _chiavi(route):
    """(METODO, path) per ogni metodo esposto. HEAD e' generato da FastAPI sui GET."""
    return [(m, route.path) for m in sorted(route.methods - {"HEAD", "OPTIONS"})]


def _rotte():
    return [r for r in _app().routes if isinstance(r, APIRoute)]


def _risolve_identita(route):
    """L'endpoint stabilisce CHI sta chiamando?

    Due modi, entrambi verificati sull'app reale il 30/8/2026:
      - Depends(_verify_admin), che include gia' bearer + X-Worker-Key + allowlist email;
      - un parametro `authorization`, la firma invariante di _resolve_user_from_token.
    """
    if "_verify_admin" in _dipendenze(route):
        return True
    return "authorization" in inspect.signature(route.endpoint).parameters


def test_ogni_endpoint_risolve_l_identita_o_e_motivato():
    """Il test centrale: nessun endpoint sprovvisto di identita' fuori dall'allowlist.

    Fallisce quando qualcuno aggiunge un endpoint dimenticando l'auth — che e'
    esattamente il modo in cui la falla si riformerebbe.
    """
    scoperti = []
    for route in _rotte():
        if _risolve_identita(route):
            continue
        for chiave in _chiavi(route):
            if chiave not in SENZA_IDENTITA_MOTIVATI:
                scoperti.append(f"{chiave[0]} {chiave[1]}  ({route.endpoint.__name__})")

    assert not scoperti, (
        "Endpoint senza identita' del chiamante e non motivati:\n  "
        + "\n  ".join(sorted(scoperti))
        + "\n\nManca `authorization: Optional[str] = Header(None)` + "
        "`_resolve_user_from_token(authorization)`, oppure Depends(_verify_admin).\n"
        "Se l'endpoint deve davvero essere senza identita', aggiungilo a "
        "SENZA_IDENTITA_MOTIVATI in questo file scrivendo PERCHE'."
    )


def test_l_allowlist_non_contiene_voci_morte():
    """Un'allowlist che elenca endpoint inesistenti e' una lista che non guarda piu'
    l'app: da' l'impressione di autorizzare qualcosa e in realta' non misura niente.
    Se un endpoint viene rinominato o rimosso, la sua deroga va tolta con lui."""
    esistenti = {c for r in _rotte() for c in _chiavi(r)}
    fantasmi = sorted(k for k in SENZA_IDENTITA_MOTIVATI if k not in esistenti)
    assert not fantasmi, (
        "Voci in SENZA_IDENTITA_MOTIVATI che non corrispondono a nessun endpoint: "
        f"{fantasmi}. Rimuovile o correggi il percorso."
    )


def test_le_deroghe_sono_motivate_per_iscritto():
    """La deroga vale se dice perche'. Una stringa vuota o simbolica renderebbe
    l'allowlist un timbro."""
    povere = sorted(k for k, v in SENZA_IDENTITA_MOTIVATI.items() if len(v.strip()) < 25)
    assert not povere, f"Deroghe senza motivazione leggibile: {povere}"


def test_gli_endpoint_admin_sono_gatati_da_verify_admin():
    """Chi sta sotto /api/admin/ dev'essere protetto dall'identita' admin.

    Le 3 eccezioni sono machine-gate documentati nel codice (X-Worker-Key,
    consumatori GitHub Actions) e stanno gia' in SENZA_IDENTITA_MOTIVATI.
    `_verify_admin` e' l'unico gate che verifica l'allowlist ADMIN_EMAILS:
    `authorization` da solo dice che sei un utente, non che sei admin.
    """
    non_gatati = []
    for route in _rotte():
        if not route.path.startswith("/api/admin/"):
            continue
        if "_verify_admin" in _dipendenze(route):
            continue
        for chiave in _chiavi(route):
            if chiave not in SENZA_IDENTITA_MOTIVATI:
                non_gatati.append(f"{chiave[0]} {chiave[1]}  ({route.endpoint.__name__})")

    assert not non_gatati, (
        "Endpoint sotto /api/admin/ senza Depends(_verify_admin):\n  "
        + "\n  ".join(sorted(non_gatati))
        + "\n\nUn utente autenticato qualunque potrebbe raggiungerli."
    )


def test_authorization_resta_un_segnale_affidabile():
    """Il test centrale si fida del parametro `authorization` come prova che
    l'endpoint risolva l'identita'. Regge finche' chi lo dichiara poi lo USA.

    Al 30/8/2026 gli unici che lo dichiarano senza passarlo a
    _resolve_user_from_token sono i 3 auth-flow che validano il bearer inline
    (fastapi_worker.py:1284-1293, 1350-1361, 1376-1383). Se ne comparissero
    altri, il segnale si starebbe sfaldando: un endpoint potrebbe dichiarare
    `authorization`, non guardarlo mai, e passare questo file. Meglio scoprirlo
    qui che in produzione.
    """
    sospetti = []
    illeggibili = []
    for route in _rotte():
        if "_verify_admin" in _dipendenze(route):
            continue
        if "authorization" not in inspect.signature(route.endpoint).parameters:
            continue
        try:
            sorgente = inspect.getsource(route.endpoint)
        except (OSError, TypeError):
            # Un endpoint di cui non si legge il sorgente NON va assolto in
            # silenzio: in una rete di sicurezza l'except che manda avanti e'
            # lo stesso meccanismo che ha gia' reso invisibile un difetto in
            # questo repo. Se non posso verificarlo, lo segnalo.
            illeggibili.append(f"{route.path}  ({route.endpoint.__name__})")
            continue
        if "_resolve_user_from_token" in sorgente or "_resolve_gruppo" in sorgente:
            continue
        for chiave in _chiavi(route):
            if chiave not in AUTENTICATI_INLINE:
                sospetti.append(f"{chiave[0]} {chiave[1]}  ({route.endpoint.__name__})")

    assert not sospetti, (
        "Endpoint che dichiarano `authorization` senza risolvere l'utente:\n  "
        + "\n  ".join(sorted(sospetti))
        + "\n\nDichiarare il parametro senza usarlo rende il segnale di questo "
        "file falso. Usa _resolve_user_from_token(authorization), oppure — se "
        "l'endpoint valida il bearer inline come i 3 di /api/auth/* — "
        "aggiungilo ad AUTENTICATI_INLINE spiegando perche'."
    )

    assert not illeggibili, (
        "Endpoint di cui non si e' potuto leggere il sorgente, quindi NON "
        "verificati:\n  " + "\n  ".join(sorted(illeggibili))
        + "\n\nQuesto controllo non sa dire se risolvono l'identita'. "
        "Verificali a mano prima di silenziare questa riga."
    )


def test_la_superficie_e_quella_misurata():
    """Guardia grossolana sul totale: se il numero di endpoint cambia di molto
    senza che nessuno tocchi questo file, e' il momento di rileggerlo. Non e'
    un numero da aggiornare meccanicamente per far tornare il verde."""
    rotte = _rotte()
    assert len(rotte) >= 230, (
        f"Solo {len(rotte)} endpoint montati: l'app potrebbe non essersi caricata "
        "per intero, e in quel caso i controlli qui sopra non stanno misurando niente."
    )


@pytest.mark.parametrize("chiave", sorted(AUTENTICATI_INLINE))
def test_gli_inline_auth_esistono_ancora(chiave):
    """AUTENTICATI_INLINE e' una deroga al segnale: se un endpoint sparisce o
    viene rinominato, la deroga va tolta invece di restare a coprire il nulla."""
    esistenti = {c for r in _rotte() for c in _chiavi(r)}
    assert chiave in esistenti, (
        f"{chiave[0]} {chiave[1]} non esiste piu': "
        "rimuovilo da AUTENTICATI_INLINE."
    )
