"""Che un endpoint nuovo non possa nascere aperto (R5).

**Cosa NON era.** Al 3/9/2026 tutti i 216 endpoint dei 12 router erano gia'
protetti uno per uno: `dependencies=[Depends(...)]` nel decoratore oppure un
`Depends` nella firma. **Zero endpoint scoperti** — misurato, non dedotto. R5
non chiudeva una falla.

**Cosa e'.** La protezione stava su ogni singolo endpoint: il 217esimo nasceva
aperto se chi lo scriveva si dimenticava la riga. Con `dependencies` sul
`APIRouter` la guardia e' ereditata, e dimenticarsene non basta piu' per
esporre un endpoint.

**Perche' e' additivo e non sostitutivo** (misurato il 3/9 con un'app di prova):
FastAPI esegue **prima** la dependency del router e **poi** quella
dell'endpoint. Le protezioni piu' strette restano intatte — `_verify_admin`
controlla la worker key *e* il token admin, quindi resta piu' restrittivo del
gate di router che lo precede.

**Prova che non ha rotto niente**: 95 rotte GET senza path-param, con e senza
`X-Worker-Key`, danno **gli stessi identici status code** di prima (snapshot
confrontati sullo stesso albero, con e senza la modifica).
"""
import pathlib
import re

import pytest

_ROUTERS = pathlib.Path(__file__).resolve().parents[1] / "services" / "routers"
_FILE = sorted(f for f in _ROUTERS.glob("*.py") if f.name != "__init__.py")


def _codice_vivo(percorso: pathlib.Path) -> str:
    return "\n".join(
        r for r in percorso.read_text(encoding="utf-8").splitlines()
        if not r.lstrip().startswith("#")
    )


def test_ci_sono_dodici_router():
    """Se ne nasce uno nuovo il test sotto deve girare anche su quello."""
    assert len(_FILE) == 12, (
        f"i router sono {len(_FILE)}, non 12: aggiorna il test invece di "
        "cancellarlo — un router nuovo senza guardia e' il caso che R5 previene"
    )


@pytest.mark.parametrize("f", _FILE, ids=lambda f: f.stem)
def test_ogni_router_dichiara_la_guardia_alla_creazione(f):
    """La forma esatta, non una sottostringa.

    `APIRouter(dependencies=[])` conterrebbe comunque la parola `dependencies`:
    il confronto e' sulla riga normalizzata (lezione del 3/9, `? false : false`).
    """
    righe = [" ".join(r.split()) for r in _codice_vivo(f).splitlines()]
    atteso = "router = APIRouter(dependencies=[Depends(_verify_worker_key)])"
    assert atteso in righe, (
        f"{f.name}: il router non dichiara piu' la guardia alla creazione.\n"
        "Senza, un endpoint nuovo che dimentica `dependencies=[...]` nasce "
        "APERTO: e' esattamente il rischio che R5 chiude."
    )


@pytest.mark.parametrize("f", _FILE, ids=lambda f: f.stem)
def test_nessun_endpoint_resta_senza_protezione_esplicita(f):
    """La rete di prima non si smonta: ogni endpoint tiene ANCHE la sua.

    Il gate di router e' una seconda linea, non un permesso di togliere le
    guardie esistenti: se una sparisce e domani qualcuno rimuove il
    `dependencies` del router, l'endpoint resta scoperto.
    """
    righe = _codice_vivo(f).splitlines()
    scoperti = []
    i = 0
    while i < len(righe):
        if re.match(r"^@router\.(get|post|put|patch|delete)\(", righe[i]):
            blocco, j = [], i
            while j < len(righe) and not re.match(r"^(async )?def ", righe[j]):
                blocco.append(righe[j])
                j += 1
            nome = righe[j] if j < len(righe) else "?"
            firma = []
            while j < len(righe):
                firma.append(righe[j])
                if righe[j].rstrip().endswith(":"):
                    break
                j += 1
            dec, fir = "\n".join(blocco), "\n".join(firma)
            if "dependencies=[" not in dec and "Depends(" not in fir:
                scoperti.append((i + 1, nome.strip()[:60]))
            i = j
        i += 1
    assert scoperti == [], (
        f"{f.name}: {len(scoperti)} endpoint senza protezione propria "
        f"(riga, def): {scoperti}"
    )


# ─── Che la guardia FUNZIONI, non solo che sia scritta ─────────────────────


def test_un_endpoint_nuovo_senza_guardia_e_comunque_protetto(monkeypatch):
    """Il comportamento che R5 compra, eseguito.

    Simula il 217esimo endpoint: registrato sul router **senza** alcun
    `dependencies` e senza `Depends` in firma — cioe' la dimenticanza tipica.
    Con il gate a livello di router deve rispondere 401 lo stesso.

    Un test sul solo sorgente non lo proverebbe: direbbe che la riga c'e', non
    che protegge.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import services.fastapi_worker as fw
    from services.routers.tag import router

    # `WORKER_SECRET_KEY` e' letta a import-time nel worker: impostare la env
    # var qui non basta (misurato — il test falliva confrontando con il valore
    # gia' caricato). Si sostituisce la costante sul modulo.
    #
    # `monkeypatch` e non un try/finally: il modulo `fastapi_worker` e' condiviso
    # da tutta la suite, e `WORKER_DEV_MODE` in particolare e' letta da altri test
    # (test_normalize_pagine lo mette a "1" all'import). Un ripristino a mano che
    # non venisse eseguito lascerebbe lo stato sporco per i 12.000 test seguenti:
    # monkeypatch lo annulla comunque, anche se il test fallisce a meta'.
    monkeypatch.setattr(fw, "WORKER_SECRET_KEY", "chiave-di-prova")
    monkeypatch.setattr(fw, "WORKER_DEV_MODE", False)

    @router.get("/api/tag/_endpoint_di_prova_r5")
    def _endpoint_dimenticato():
        return {"segreto": "non deve uscire senza chiave"}

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    try:
        senza = client.get("/api/tag/_endpoint_di_prova_r5")
        assert senza.status_code == 401, (
            "un endpoint nuovo SENZA guardia propria e' risultato accessibile "
            f"({senza.status_code}): il gate a livello di router non protegge, "
            "e il 217esimo endpoint nasce aperto"
        )
        con = client.get(
            "/api/tag/_endpoint_di_prova_r5",
            headers={"X-Worker-Key": "chiave-di-prova"},
        )
        assert con.status_code == 200, (
            f"con la chiave giusta l'endpoint risponde {con.status_code}: il "
            "gate blocca anche chi ha diritto di passare"
        )
    finally:
        router.routes[:] = [
            r for r in router.routes
            if getattr(r, "path", None) != "/api/tag/_endpoint_di_prova_r5"
        ]


def test_la_guardia_del_router_non_sostituisce_quella_dell_endpoint():
    """Additiva, non sostitutiva — la ragione per cui `admin` e' unificabile.

    `_verify_admin` controlla la worker key E il token admin. Se il gate di
    router la sostituisse, gli endpoint admin scenderebbero al controllo piu'
    debole: bastarebbe la worker key per entrare nell'area amministrativa.
    """
    from fastapi import APIRouter, Depends, FastAPI, HTTPException
    from fastapi.testclient import TestClient

    eseguite = []

    def gate_router():
        eseguite.append("router")

    def gate_endpoint():
        eseguite.append("endpoint")
        raise HTTPException(status_code=403, detail="piu' stretto")

    r = APIRouter(dependencies=[Depends(gate_router)])

    @r.get("/doppia", dependencies=[Depends(gate_endpoint)])
    def _doppia():
        return {"ok": True}

    app = FastAPI()
    app.include_router(r)
    esito = TestClient(app).get("/doppia")

    assert eseguite == ["router", "endpoint"], (
        f"ordine/esecuzione inattesi: {eseguite}. Se quella dell'endpoint non "
        "gira, la protezione piu' stretta e' stata persa"
    )
    assert esito.status_code == 403, (
        "ha vinto il gate del router: la guardia piu' stretta dell'endpoint "
        "non e' piu' applicata"
    )
