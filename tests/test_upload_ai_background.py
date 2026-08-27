"""Upload sopra soglia: la categorizzazione AI esce dal ciclo di risposta (fase 3.1).

STORICO: l'upload eseguiva _run_post_upload_ai_categorization IN LINEA prima di
rispondere. Su una fattura grande l'AI non sta nei 30s dell'abort di Next.js
(apps/web/src/app/api/upload/invoice/route.ts): il cliente vedeva "Errore di rete"
su una fattura in realta' salvata, e l'AI continuava a girare per un client andato via.

Ora sopra _UPLOAD_AI_SYNC_MAX_ROWS si risponde subito con ai_pending=True e la
categorizzazione prosegue in BackgroundTasks.

PUNTO CRITICO (il motivo per cui questa fase e' stata progettata, non solo scritta):
i ContextVar NON sopravvivono al passaggio in BackgroundTasks. Il task gira DOPO il
`finally` dell'endpoint, che li ha gia' azzerati — quindi force_local_worker_path e
set_ai_context vanno RI-IMPOSTATI dentro il task. Se non lo fossero:
  - senza force_local_worker_path: su Railway il worker fa una POST HTTP verso se
    stesso -> fallback "Da Classificare" silenzioso (cert. 24/08, 795 righe);
  - senza set_ai_context: ai_usage_events resta vuoto, costo non tracciato.
Questi test bloccano entrambe le regressioni.
"""
import inspect
import threading
import time
from contextvars import ContextVar

import pytest

from services import fastapi_worker as fw


# ─── soglia e contratto della response ───────────────────────────────────────

def test_soglia_esiste_ed_e_sensata():
    assert fw._UPLOAD_AI_SYNC_MAX_ROWS > 0
    # Sopra qualche centinaio di righe la soglia non proteggerebbe piu' nulla:
    # l'AI a chunk da 30 sforerebbe comunque i 30s del proxy.
    assert fw._UPLOAD_AI_SYNC_MAX_ROWS <= 300


def test_response_espone_ai_pending():
    """Il campo resta nel contratto anche se il modale non lo usa piu': segnala
    a qualsiasi consumatore (test, integrazioni, un domani il modale stesso) che
    la categorizzazione di quella fattura non e' ancora definitiva."""
    campi = fw.UploadInvoiceResponse.model_fields
    assert "ai_pending" in campi


def test_ai_pending_default_false():
    """Il default non deve cambiare il significato delle response esistenti."""
    r = fw.UploadInvoiceResponse(success=True, filename="f.xml", righe_salvate=1)
    assert r.ai_pending is False


def test_sotto_soglia_niente_background():
    """(a) del piano: sotto soglia il comportamento sincrono resta invariato."""
    assert fw._ai_va_in_background(1) is False
    assert fw._ai_va_in_background(fw._UPLOAD_AI_SYNC_MAX_ROWS - 1) is False


def test_esattamente_alla_soglia_resta_sincrono():
    """Il confine e' `>`, non `>=`: alla soglia esatta si resta sincroni."""
    assert fw._ai_va_in_background(fw._UPLOAD_AI_SYNC_MAX_ROWS) is False


def test_sopra_soglia_va_in_background():
    """(b) del piano: sopra soglia si risponde subito e l'AI prosegue dopo."""
    assert fw._ai_va_in_background(fw._UPLOAD_AI_SYNC_MAX_ROWS + 1) is True
    assert fw._ai_va_in_background(fw._UPLOAD_AI_SYNC_MAX_ROWS * 10) is True


def test_fattura_vuota_non_va_in_background():
    assert fw._ai_va_in_background(0) is False


# ─── budget AI del ramo sincrono: il VALORE, non solo la presenza ────────────

def test_budget_upload_sincrono_scala_col_tempo_gia_speso():
    """Meno tempo resta dei 27s, meno budget: ma sempre > 0."""
    from services.ai_service import AI_BUDGET_DEFAULT_SECONDS
    # Nulla speso: budget pieno (capped al default)
    assert fw._budget_ai_upload_sincrono(0) == min(AI_BUDGET_DEFAULT_SECONDS, 27.0)
    # 10s spesi: 17s residui, sotto il default -> 17
    assert fw._budget_ai_upload_sincrono(10_000) == pytest.approx(17.0)


def test_budget_upload_sincrono_ha_un_floor_positivo():
    """Il bug che questo test blocca: con >=27s gia' spesi il calcolo grezzo
    darebbe 0, che set_ai_deadline interpreta come 'nessun limite' — l'opposto
    di quel che serve nel ramo sincrono. Il floor deve tenere il budget > 0."""
    assert fw._budget_ai_upload_sincrono(27_000) >= 3.0
    assert fw._budget_ai_upload_sincrono(60_000) >= 3.0
    assert fw._budget_ai_upload_sincrono(10 ** 9) >= 3.0


def test_budget_upload_sincrono_impone_davvero_una_deadline():
    """End-to-end sul contratto con set_ai_deadline: anche nel caso peggiore
    (tempo esaurito) la deadline risulta ATTIVA, non None."""
    from services import ai_service
    try:
        ai_service.set_ai_deadline(fw._budget_ai_upload_sincrono(120_000))
        assert ai_service.ai_budget_rimanente() is not None
        assert ai_service.ai_budget_rimanente() > 0
    finally:
        ai_service.clear_ai_deadline()


def test_endpoint_decide_sulla_soglia():
    src = inspect.getsource(fw.upload_invoice)
    assert "_ai_va_in_background(" in src, "la soglia non e' usata dall'endpoint"
    assert "background_tasks.add_task(" in src, (
        "sopra soglia l'AI non viene rimandata: la richiesta scadrebbe di nuovo"
    )
    assert "ai_pending=True" in src


def test_sotto_soglia_resta_sincrono():
    """Il path esistente (fatture piccole) non deve cambiare comportamento."""
    src = inspect.getsource(fw.upload_invoice)
    assert "_run_post_upload_ai_categorization" in src, (
        "il ramo sincrono e' sparito: le fatture piccole non verrebbero piu' "
        "categorizzate durante l'upload"
    )


# ─── il punto critico: ContextVar in BackgroundTasks ─────────────────────────

def test_il_task_async_reimposta_il_proprio_contesto():
    """I ContextVar sono azzerati dal finally dell'endpoint prima che il task giri."""
    src = inspect.getsource(fw._upload_ai_categorizzazione_async)
    assert "set_ai_context(" in src, (
        "senza set_ai_context ai_usage_events resta vuoto: il costo non e' tracciato"
    )
    assert "force_local_worker_path(False)" in src, "il finally non ripristina il path"
    # `force_local_worker_path(True)` va cercato come ATTIVAZIONE reale, non come
    # semplice occorrenza nel sorgente: il `(False)` del finally basterebbe a far
    # passare un `in src` generico anche se l'attivazione fosse sparita.
    import ast
    chiamate = [
        n for n in ast.walk(ast.parse(inspect.cleandoc(src)))
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "force_local_worker_path"
        and n.args and getattr(n.args[0], "value", None) is True
    ]
    assert chiamate, (
        "senza force_local_worker_path(True) il worker chiama se stesso via HTTP "
        "e l'AI degrada in silenzio (cert. 24/08)"
    )


def test_il_task_async_non_propaga_eccezioni():
    """Non c'e' una request da rompere: un errore deve restare confinato."""
    src = inspect.getsource(fw._upload_ai_categorizzazione_async)
    assert "except Exception" in src


def test_contextvar_non_sopravvive_a_backgroundtasks():
    """La premessa del design, verificata invece che assunta.

    Se un giorno FastAPI/anyio propagassero il contesto anche ai BackgroundTasks,
    questo test lo direbbe subito — e le due `set_` nel task diventerebbero
    ridondanti invece che indispensabili.
    """
    from fastapi import BackgroundTasks, FastAPI
    from fastapi.testclient import TestClient

    cv: ContextVar = ContextVar("cv_prova", default=None)
    visto = []

    def _task(nome):
        visto.append((nome, cv.get()))

    app = FastAPI()

    @app.get("/prova")
    def _prova(background_tasks: BackgroundTasks, nome: str):
        cv.set(nome)
        try:
            background_tasks.add_task(_task, nome)
            return {"ok": True}
        finally:
            cv.set(None)          # come il finally dell'endpoint upload

    TestClient(app).get("/prova?nome=tenantA")
    assert visto == [("tenantA", None)], (
        f"il ContextVar e' arrivato al task ({visto}): rivedere il commento in "
        "_upload_ai_categorizzazione_async, la premessa e' cambiata"
    )


def test_upload_concorrenti_non_si_contaminano():
    """Due upload paralleli di tenant diversi devono restare isolati.

    E' la ragione per cui il contesto si re-imposta DENTRO il task: se lo si
    facesse a livello di processo (os.environ), il secondo upload sovrascriverebbe
    il ristorante_id del primo a meta' categorizzazione.
    """
    from fastapi import BackgroundTasks, FastAPI
    from fastapi.testclient import TestClient

    cv: ContextVar = ContextVar("cv_tenant", default=None)
    visto = []
    lock = threading.Lock()

    def _task(nome):
        cv.set(nome)                       # come fa il task reale
        time.sleep(0.05)                   # finestra per una race
        with lock:
            visto.append((nome, cv.get()))

    app = FastAPI()

    @app.get("/prova")
    def _prova(background_tasks: BackgroundTasks, nome: str):
        cv.set(nome)
        try:
            background_tasks.add_task(_task, nome)
            return {"ok": True}
        finally:
            cv.set(None)

    client = TestClient(app)
    import concurrent.futures as cf
    tenants = [f"tenant{i}" for i in range(6)]
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(lambda n: client.get(f"/prova?nome={n}"), tenants))

    assert len(visto) == len(tenants)
    for nome, letto in visto:
        assert nome == letto, (
            f"contaminazione fra tenant concorrenti: {nome} ha letto {letto}"
        )


# ─── invalidazione cache dopo il lavoro in background ────────────────────────

def test_il_task_async_invalida_la_cache():
    """Senza invalidazione il cliente ricaricherebbe e vedrebbe ancora le righe
    pre-AI fino allo scadere del TTL, cioe' proprio il problema che ai_pending
    dice essere in via di risoluzione."""
    src = inspect.getsource(fw._upload_ai_categorizzazione_async)
    assert "_invalidate_fatture_rows_cache(" in src


def test_nessuna_deadline_nel_task_async():
    """In background nessuno aspetta: la deadline dell'upload non deve restare
    appiccicata al contesto, o l'AI si fermerebbe subito per un budget che non
    ha piu' senso qui."""
    src = inspect.getsource(fw._upload_ai_categorizzazione_async)
    assert "clear_ai_deadline()" in src


# ─── frontend ───────────────────────────────────────────────────────────────
# SCELTA (27/8, dopo test in produzione): il modale NON introduce un messaggio
# per ai_pending. Il flusso naturale e' "Chiudi e aggiorna" -> window.location
# .reload(), e su una fattura grande l'AI finisce in 10-20s, prima che il
# cliente abbia letto il modale e cliccato. Una frase "categorizzazione in
# corso, aggiorna fra poco" e' rumore che confonde tutti per proteggere un
# caso raro (fattura enorme + reload entro 5s). Il campo ai_pending resta nella
# response del worker per eventuali consumatori futuri, ma il modale mostra il
# conteggio needs_review come sempre.

def _upload_modal_src():
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "apps/web/src/app/(app)/analisi-fatture/upload-modal.tsx"
    return p.read_text(encoding="utf-8")


def test_modale_non_ha_messaggio_ai_pending():
    """Regressione della scelta di cui sopra: se un giorno si rimette una frase
    per ai_pending, questo test lo intercetta e obbliga a rileggere il perche'."""
    src = _upload_modal_src()
    assert "categorizzazione in corso" not in src
    assert "entry.ai_pending" not in src


def test_modale_mostra_sempre_needs_review():
    src = _upload_modal_src()
    assert "categoria da verificare" in src, (
        "il conteggio needs_review non e' piu' mostrato nel modale"
    )
