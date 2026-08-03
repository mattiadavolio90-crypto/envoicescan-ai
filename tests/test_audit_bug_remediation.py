"""Remediation audit Bug (3/8/2026), passata 1: upload → parsing → categorizzazione AI.

Copre i due findings HIGH, che sono quelli che toccano dati reali dei clienti:

HIGH#1 — le correzioni admin alla memoria globale non si propagavano piu' alle fatture
storiche: `salva_correzione_in_memoria_globale` era rimasta senza chiamanti vivi e i due
endpoint admin scrivevano `prodotti_master` in diretta. Qui si verifica lo SCOPING della
propagazione riattivata, perche' e' una scrittura di massa su dati storici veri.

HIGH#2 — fatture oltre i 500 record venivano scritte a chunk senza transazione: un
fallimento a meta' lasciava righe nel DB ma loggava `FAILED rows_saved=0`, cioe' il log
sottostimava il danno.
"""
import pytest

from services.ai_service import _propaga_global_override_a_fatture_storiche


class _HTTPError(Exception):
    """Sta al posto di requests.HTTPError: in questa suite `requests` è sostituito
    da un mock del conftest che non è un package e non espone eccezioni vere."""


# ─── Fake client Supabase (sottoinsieme PostgREST usato dalla propagazione) ────

class _FakeQuery:
    def __init__(self, table, rows, recorder):
        self._table = table
        self._rows = rows
        self._rec = recorder
        self._ids_filter = None
        self._payload = None
        self._mode = "select"

    # --- costruzione query (no-op sui filtri gia' garantiti a monte) ---
    def select(self, *_a, **_k):
        return self

    def is_(self, col, val):
        # deleted_at IS NULL: soft delete rispettato
        if col == "deleted_at" and val == "null":
            self._rows = [r for r in self._rows if r.get("deleted_at") is None]
        return self

    def neq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) != val]
        return self

    def ilike(self, col, pattern):
        needle = pattern.strip("%").upper()
        self._rows = [r for r in self._rows if needle in str(r.get(col, "")).upper()]
        return self

    def range(self, start, end):
        self._rows = self._rows[start:end + 1]
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def in_(self, col, values):
        self._ids_filter = (col, list(values))
        return self

    def execute(self):
        if self._mode == "update":
            col, values = self._ids_filter
            for r in self._rec["store"][self._table]:
                if r.get(col) in values:
                    r.update(self._payload)
                    self._rec["updated_ids"].append(r.get("id"))
            return type("R", (), {"data": []})()
        return type("R", (), {"data": list(self._rows)})()


class _FakeClient:
    def __init__(self, fatture, prodotti_utente):
        self.store = {"fatture": fatture, "prodotti_utente": prodotti_utente}
        self.rec = {"store": self.store, "updated_ids": []}

    def table(self, name):
        return _FakeQuery(name, list(self.store.get(name, [])), self.rec)


@pytest.fixture
def scenario(monkeypatch):
    """Una descrizione globale corretta dall'admin, quattro righe storiche."""
    fatture = [
        # cliente A: da aggiornare
        {"id": 1, "user_id": "A", "descrizione": "MOZZARELLA FIORDILATTE",
         "categoria": "SERVIZI E CONSULENZE", "deleted_at": None},
        # cliente B: ha un override Manuale -> NON toccare
        {"id": 2, "user_id": "B", "descrizione": "MOZZARELLA FIORDILATTE",
         "categoria": "SERVIZI E CONSULENZE", "deleted_at": None},
        # cliente C: riga cestinata -> NON toccare
        {"id": 3, "user_id": "C", "descrizione": "MOZZARELLA FIORDILATTE",
         "categoria": "SERVIZI E CONSULENZE", "deleted_at": "2026-07-01T00:00:00Z"},
        # cliente D: descrizione diversa -> NON toccare
        {"id": 4, "user_id": "D", "descrizione": "MOZZARELLA AFFUMICATA",
         "categoria": "SERVIZI E CONSULENZE", "deleted_at": None},
    ]
    prodotti_utente = [
        {"user_id": "B", "descrizione": "MOZZARELLA FIORDILATTE",
         "classificato_da": "Manuale (cliente-b@test.it)"},
        # override non-Manuale: e' un'auto-categorizzazione, va aggiornata
        {"user_id": "A", "descrizione": "MOZZARELLA FIORDILATTE",
         "classificato_da": "keyword-auto"},
    ]
    client = _FakeClient(fatture, prodotti_utente)

    # _fetch_all_rows pagina su prodotti_utente: qui basta restituirle tutte.
    monkeypatch.setattr(
        "services.ai_service._fetch_all_rows",
        lambda _c, table, _cols: list(client.store.get(table, [])),
    )
    return client


# ─── HIGH#1: scoping della propagazione ───────────────────────────────────────

def test_propagazione_aggiorna_solo_le_righe_legittime(scenario):
    aggiornate = _propaga_global_override_a_fatture_storiche(
        "MOZZARELLA FIORDILATTE", "LATTICINI E FORMAGGI", scenario
    )

    assert aggiornate == 1
    assert scenario.rec["updated_ids"] == [1]

    per_id = {r["id"]: r for r in scenario.store["fatture"]}
    assert per_id[1]["categoria"] == "LATTICINI E FORMAGGI"
    assert per_id[1]["classificato_da"] == "admin-global-propagation"


def test_propagazione_non_tocca_override_manuale_del_cliente(scenario):
    _propaga_global_override_a_fatture_storiche(
        "MOZZARELLA FIORDILATTE", "LATTICINI E FORMAGGI", scenario
    )
    riga_b = next(r for r in scenario.store["fatture"] if r["id"] == 2)
    assert riga_b["categoria"] == "SERVIZI E CONSULENZE"


def test_propagazione_non_tocca_righe_cestinate(scenario):
    _propaga_global_override_a_fatture_storiche(
        "MOZZARELLA FIORDILATTE", "LATTICINI E FORMAGGI", scenario
    )
    riga_c = next(r for r in scenario.store["fatture"] if r["id"] == 3)
    assert riga_c["categoria"] == "SERVIZI E CONSULENZE"


def test_propagazione_non_tocca_descrizioni_diverse(scenario):
    _propaga_global_override_a_fatture_storiche(
        "MOZZARELLA FIORDILATTE", "LATTICINI E FORMAGGI", scenario
    )
    riga_d = next(r for r in scenario.store["fatture"] if r["id"] == 4)
    assert riga_d["categoria"] == "SERVIZI E CONSULENZE"


def test_propagazione_no_op_su_input_vuoto(scenario):
    assert _propaga_global_override_a_fatture_storiche("", "LATTICINI E FORMAGGI", scenario) == 0
    assert _propaga_global_override_a_fatture_storiche("X", "", scenario) == 0
    assert scenario.rec["updated_ids"] == []


# ─── HIGH#1: gli endpoint admin richiamano davvero la propagazione ────────────

def test_endpoint_admin_promuovi_passa_da_salva_correzione(monkeypatch):
    """L'azione 'promuovi' non deve piu' fare un upsert secco su prodotti_master:
    e' esattamente lo scenario per cui la propagazione era stata scritta."""
    from services.routers import admin as admin_router

    chiamate = []
    monkeypatch.setattr(
        "services.ai_service.salva_correzione_in_memoria_globale",
        lambda **kw: chiamate.append(kw) or True,
    )

    class _Q:
        def __init__(self, rows=None):
            self._rows = rows or []

        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def update(self, *_a, **_k):
            return self

        def execute(self):
            return type("R", (), {"data": self._rows})()

    class _SB:
        def table(self, name):
            if name == "prodotti_utente":
                return _Q([{"descrizione": "PANE CARASAU", "categoria": "PRODOTTI DA FORNO"}])
            if name == "prodotti_master":
                return _Q([{"categoria": "Da Classificare"}])
            return _Q([])

    monkeypatch.setattr(admin_router, "get_supabase_client", lambda: _SB())
    monkeypatch.setattr(admin_router, "_log_review_action", lambda *a, **k: None)

    body = admin_router.RisolviConflittoBody(local_id="loc-1", azione="promuovi")
    out = admin_router.admin_qualita_risolvi_conflitto(body, admin_user={"email": "md@oneflux.it"})

    assert out == {"ok": True}
    assert len(chiamate) == 1
    assert chiamate[0]["is_admin"] is True
    assert chiamate[0]["nuova_categoria"] == "PRODOTTI DA FORNO"
    assert chiamate[0]["vecchia_categoria"] == "Da Classificare"


# ─── HIGH#1 (B4): il PATCH resta ancorato all'id scelto dall'admin ────────────

def _patch_env(monkeypatch, master_rows):
    """Fake client per admin_qualita_memoria_update: registra update e propagazioni."""
    from services.routers import admin as admin_router

    rec = {"updates": [], "propagazioni": []}

    class _Q:
        def __init__(self, rows):
            self._rows = rows
            self._payload = None
            self._id = None

        def select(self, *_a, **_k):
            return self

        def eq(self, col, val):
            if col == "id":
                self._id = val
                self._rows = [r for r in self._rows if r.get("id") == val]
            return self

        def limit(self, *_a, **_k):
            return self

        def update(self, payload):
            self._payload = payload
            return self

        def execute(self):
            if self._payload is not None:
                rec["updates"].append((self._id, dict(self._payload)))
                return type("R", (), {"data": []})()
            return type("R", (), {"data": list(self._rows)})()

    class _SB:
        def table(self, _name):
            return _Q(list(master_rows))

    monkeypatch.setattr(admin_router, "get_supabase_client", lambda: _SB())
    monkeypatch.setattr(
        "services.ai_service._propaga_global_override_a_fatture_storiche",
        lambda desc, cat, _c: rec["propagazioni"].append((desc, cat)) or 3,
    )
    return admin_router, rec


def test_patch_admin_scrive_sul_record_scelto_non_su_quello_normalizzato(monkeypatch):
    """In prodotti_master convivono varianti non normalizzate: '(I)100 COP EST. X DW
    280CC' normalizza su '( )COP EST X DW 280CC', che è un ALTRO record esistente.
    L'update deve colpire l'id passato dall'admin, non il gemello normalizzato."""
    rows = [
        {"id": "id-4799", "descrizione": "(I)100 COP EST. X DW 280CC", "categoria": "MATERIALE DI CONSUMO"},
        {"id": "id-17195", "descrizione": "( )COP EST X DW 280CC", "categoria": "MATERIALE DI CONSUMO"},
    ]
    admin_router, rec = _patch_env(monkeypatch, rows)

    body = admin_router.MemoriaUpdateBody(categoria="SHOP")
    out = admin_router.admin_qualita_memoria_update(
        "id-4799", body, admin_user={"email": "md@oneflux.it"}
    )

    assert out["ok"] is True
    assert len(rec["updates"]) == 1, "una sola scrittura, non due"
    target_id, payload = rec["updates"][0]
    assert target_id == "id-4799", "deve aggiornare il record scelto dall'admin"
    assert payload["categoria"] == "SHOP"


def test_patch_admin_verified_false_non_viene_sovrascritto(monkeypatch):
    """verified esplicito nel body deve sopravvivere: prima una seconda UPDATE poteva
    rimetterlo a False DOPO che la propagazione di massa era già partita."""
    rows = [{"id": "id-1", "descrizione": "PANE CARASAU", "categoria": "Da Classificare"}]
    admin_router, rec = _patch_env(monkeypatch, rows)

    body = admin_router.MemoriaUpdateBody(categoria="PRODOTTI DA FORNO", verified=False)
    admin_router.admin_qualita_memoria_update("id-1", body, admin_user={"email": "md@oneflux.it"})

    assert len(rec["updates"]) == 1
    _, payload = rec["updates"][0]
    assert payload["verified"] is False, "lo stato finale deve essere quello richiesto"


def test_patch_admin_propaga_solo_se_categoria_cambia(monkeypatch):
    rows = [{"id": "id-1", "descrizione": "PANE CARASAU", "categoria": "PRODOTTI DA FORNO"}]
    admin_router, rec = _patch_env(monkeypatch, rows)

    # stessa categoria -> nessuna scrittura di massa
    body = admin_router.MemoriaUpdateBody(categoria="PRODOTTI DA FORNO")
    out = admin_router.admin_qualita_memoria_update("id-1", body, admin_user={"email": "md@oneflux.it"})
    assert rec["propagazioni"] == []
    assert out["righe_propagate"] == 0

    # categoria diversa -> propaga sulla descrizione normalizzata
    body2 = admin_router.MemoriaUpdateBody(categoria="SHOP")
    out2 = admin_router.admin_qualita_memoria_update("id-1", body2, admin_user={"email": "md@oneflux.it"})
    assert len(rec["propagazioni"]) == 1
    assert rec["propagazioni"][0][1] == "SHOP"
    assert out2["righe_propagate"] == 3


def test_patch_admin_404_se_record_inesistente(monkeypatch):
    from fastapi import HTTPException
    admin_router, _ = _patch_env(monkeypatch, [])
    body = admin_router.MemoriaUpdateBody(categoria="SHOP")
    with pytest.raises(HTTPException) as exc:
        admin_router.admin_qualita_memoria_update("mancante", body, admin_user={"email": "md@oneflux.it"})
    assert exc.value.status_code == 404


# ─── MEDIUM#1: claim compare-and-swap ─────────────────────────────────────────

def _fake_queue_client(locked_by, boom=False):
    class _Q:
        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def execute(self):
            if boom:
                raise RuntimeError("rete giu'")
            return type("R", (), {"data": [{"locked_by": locked_by}]})()

    return type("C", (), {"table": lambda _s, _n: _Q()})()


def test_claim_valido_quando_lock_e_nostro():
    from worker.queue_processor import _claim_ancora_valido
    assert _claim_ancora_valido(_fake_queue_client("w-1"), 1, "w-1") is True


def test_claim_perso_quando_altro_worker_ha_riclamato():
    """È il caso che protegge dal doppio addebito AI dopo il JOB_TIMEOUT."""
    from worker.queue_processor import _claim_ancora_valido
    assert _claim_ancora_valido(_fake_queue_client("w-2"), 1, "w-1") is False


def test_claim_fail_open_su_errore_di_rete():
    """Il controllo è accessorio: se il DB non risponde si prosegue, non si blocca."""
    from worker.queue_processor import _claim_ancora_valido
    assert _claim_ancora_valido(_fake_queue_client("w-1", boom=True), 1, "w-1") is True


def test_claim_senza_worker_id_non_blocca():
    from worker.queue_processor import _claim_ancora_valido
    assert _claim_ancora_valido(_fake_queue_client("w-9"), 1, None) is True


# ─── MEDIUM#2: quota AI distinguibile da errore di rete ───────────────────────

class _Resp429:
    """Risposta 429 realistica: raise_for_status alza come farebbe requests, così il
    test non passa per un AttributeError accidentale sul mock."""

    def __init__(self, scope=None, detail=""):
        self.status_code = 429
        self.headers = {"X-RateLimit-Scope": scope} if scope else {}
        self._detail = detail

    def json(self):
        return {"detail": self._detail}

    def raise_for_status(self):
        raise _HTTPError("429 Too Many Requests")


def _resp_429(scope=None, detail=""):
    return _Resp429(scope=scope, detail=detail)


def test_429_quota_ai_diventa_eccezione_tipizzata(monkeypatch):
    """Prima il 429 finiva nell'except generico e degradava a fallback locale,
    mascherando 'quota finita' dietro 'worker non disponibile'."""
    import services.worker_client as wc
    from services.ai_service import AIDailyLimitExceededError

    monkeypatch.setattr(wc, "_worker_base_url", lambda: "http://worker.test")
    monkeypatch.setattr(wc.requests, "post", lambda *_a, **_k: _resp_429(scope="ai-daily-quota"))

    with pytest.raises(AIDailyLimitExceededError):
        wc.classifica_via_worker_con_confidenza(["PANE"], ristorante_id="rid-1")


def test_429_quota_ai_riconosciuta_anche_senza_header(monkeypatch):
    """Fallback sul testo: durante un rollout il worker può non mandare ancora l'header."""
    import services.worker_client as wc
    from services.ai_service import AIDailyLimitExceededError

    monkeypatch.setattr(wc, "_worker_base_url", lambda: "http://worker.test")
    monkeypatch.setattr(
        wc.requests, "post",
        lambda *_a, **_k: _resp_429(detail="Limite giornaliero categorizzazioni AI raggiunto (1000 chiamate/giorno)."),
    )

    with pytest.raises(AIDailyLimitExceededError):
        wc.classifica_via_worker_con_confidenza(["PANE"], ristorante_id="rid-1")


def test_429_rate_limit_per_ip_non_e_quota_ai(monkeypatch):
    """Il worker limita anche a 30 req/60s per IP: un upload grosso lo raggiunge.
    Quel 429 è transitorio e deve ancora degradare a fallback locale, altrimenti
    il cliente vedrebbe 'quota esaurita' per un problema che si risolve da solo."""
    import services.worker_client as wc

    monkeypatch.setattr(wc, "_worker_base_url", lambda: "http://worker.test")
    monkeypatch.setattr(
        wc.requests, "post",
        lambda *_a, **_k: _resp_429(detail="Rate limit: max 30 richieste ogni 60s per IP."),
    )
    monkeypatch.setattr(
        "services.ai_service.classifica_con_ai",
        lambda *_a, **_k: (["SHOP"], ["alta"]),
    )

    cat, conf = wc.classifica_via_worker_con_confidenza(["PANE"], ristorante_id="rid-1")
    assert cat == ["SHOP"], "il rate limit per IP deve ancora fare fallback locale"


def test_errore_di_rete_continua_a_fare_fallback_locale(monkeypatch):
    """Retrocompatibilità: un guasto vero del worker deve ancora degradare in locale."""
    import services.worker_client as wc

    monkeypatch.setattr(wc, "_worker_base_url", lambda: "http://worker.test")

    def _boom(*_a, **_k):
        raise ConnectionError("worker irraggiungibile")

    monkeypatch.setattr(wc.requests, "post", _boom)
    monkeypatch.setattr(
        "services.ai_service.classifica_con_ai",
        lambda *_a, **_k: (["SHOP"], ["alta"]),
    )

    cat, conf = wc.classifica_via_worker_con_confidenza(["PANE"], ristorante_id="rid-1")
    assert cat == ["SHOP"] and conf == ["alta"]


def test_eccezione_quota_resta_un_runtimeerror():
    """fastapi_worker mappa RuntimeError su 429: la sottoclasse non deve rompere quel gancio."""
    from services.ai_service import AIDailyLimitExceededError
    assert issubclass(AIDailyLimitExceededError, RuntimeError)


# ─── HIGH#2: scrittura parziale osservabile ───────────────────────────────────

def test_cap_righe_per_fattura_e_2000():
    """Il cap viveva solo nel ramo Streamlit morto: ora e' nel percorso vivo."""
    from services.invoice_service import _MAX_RIGHE_PER_FATTURA
    assert _MAX_RIGHE_PER_FATTURA == 2000


def test_fallimento_a_meta_logga_le_righe_davvero_scritte(monkeypatch):
    """Prima loggava FAILED rows_saved=0 con 500 righe gia' nel DB."""
    import services.invoice_service as inv

    eventi = []
    monkeypatch.setattr(inv, "log_upload_event", lambda **kw: eventi.append(kw))
    monkeypatch.setattr(inv, "normalizza_data_consegna_td24", lambda *_a, **_k: None)

    class _Tab:
        def __init__(self, chiamate):
            self._chiamate = chiamate

        def upsert(self, chunk, **_k):
            self._chiamate.append(len(chunk))
            if len(self._chiamate) == 2:      # il secondo chunk fallisce
                raise RuntimeError("timeout di rete sul chunk 2")
            return self

        def execute(self):
            return type("R", (), {"data": []})()

    class _SB:
        def __init__(self):
            self.chiamate = []

        def table(self, _name):
            return _Tab(self.chiamate)

    sb = _SB()
    righe = [
        {"Descrizione": f"ART {i}", "Quantita": 1, "PrezzoUnitario": 1.0,
         "Totale_Riga": 1.0, "numero_riga": i}
        for i in range(600)
    ]

    esito = inv.salva_fattura_processata(
        nome_file="fattura-grande.xml",
        dati_prodotti=righe,
        supabase_client=sb,
        silent=True,
        ristoranteid="rid-1",
        user_id="uid-1",
    )

    assert esito["success"] is False
    assert eventi, "nessun upload_event registrato"
    ev = eventi[-1]
    assert ev["status"] == "SAVED_PARTIAL"
    assert ev["rows_saved"] == 500, "il log deve dire quante righe sono davvero nel DB"
    assert ev["details"].get("partial_write") is True
