"""Deadline condivisa fra i 3 livelli di retry della categorizzazione (fase 3.2).

STORICO: i 3 livelli di retry erano indipendenti e contavano solo i TENTATIVI, mai
il tempo — tenacity in _chiama_gpt_classificazione (3 tentativi, backoff fino a 30s),
il retry applicativo di classifica_con_ai (2 giri su chunk da 20), il retry chunk in
worker/queue_processor (3 tentativi, backoff 2/4/8s). Nel caso peggiore si moltiplicano
e superano di gran lunga il vincolo vero: Next.js abortisce l'upload a 30s
(apps/web/src/app/api/upload/invoice/route.ts). Oltre quella soglia i retry bruciano
quota OpenAI per un client che non ascolta piu'.

Ora una deadline assoluta su time.monotonic() viaggia in un ContextVar e ferma tutti
e tre i livelli. Regola di dominio: a deadline scaduta NON si solleva mai — subentra
il fallback deterministico esistente (regole forti + dizionario, residuo
"Da Classificare"), nessuna categoria inventata.
"""
import inspect
import time

import pytest

from services import ai_service
from worker import queue_processor as qp


@pytest.fixture(autouse=True)
def _pulisci_deadline():
    """Nessun test deve lasciare una deadline attiva agli altri."""
    ai_service.clear_ai_deadline()
    yield
    ai_service.clear_ai_deadline()


# ─── helper di contesto ──────────────────────────────────────────────────────

def test_senza_deadline_nessun_limite():
    """Default = nessun budget: i percorsi in background restano invariati."""
    assert ai_service.ai_budget_rimanente() is None
    assert ai_service.ai_deadline_scaduta() is False


def test_set_ai_deadline_fissa_un_budget():
    ai_service.set_ai_deadline(5)
    rimanente = ai_service.ai_budget_rimanente()
    assert rimanente is not None
    assert 4.5 < rimanente <= 5.0
    assert ai_service.ai_deadline_scaduta() is False


def test_budget_nullo_o_negativo_rimuove_la_deadline():
    """None/<=0 significa "nessun limite", non "scaduta subito": altrimenti un
    chiamante senza budget bloccherebbe l'AI invece di lasciarla lavorare."""
    for valore in (None, 0, -1):
        ai_service.set_ai_deadline(valore)
        assert ai_service.ai_budget_rimanente() is None
        assert ai_service.ai_deadline_scaduta() is False


def test_deadline_passata_e_scaduta():
    ai_service._ai_ctx_deadline.set(time.monotonic() - 1)
    assert ai_service.ai_deadline_scaduta() is True
    assert ai_service.ai_budget_rimanente() < 0


def test_clear_rimuove_la_deadline():
    ai_service.set_ai_deadline(10)
    ai_service.clear_ai_deadline()
    assert ai_service.ai_deadline_scaduta() is False


def test_worker_legge_la_stessa_deadline():
    """queue_processor importa gli helper da ai_service: stesso ContextVar, non una
    copia. Se l'import fallisse e restasse il fallback, il guard sarebbe inerte."""
    ai_service._ai_ctx_deadline.set(time.monotonic() - 1)
    assert qp.ai_deadline_scaduta() is True
    assert qp.ai_budget_rimanente() < 0


# ─── livello 1: tenacity in _chiama_gpt_classificazione ──────────────────────

def _esegui_chunk_sempre_fallito(contatore):
    """Simula un chunk che fallisce sempre, con lo STESSO stop/wait usato in
    produzione da _chiama_gpt_classificazione. Ritorna la durata totale.

    Usa lo stop/wait veri di ai_service: dal 28/8/2026 tenacity non e' piu'
    mockato nel conftest, quindi non serve sostituire nulla.
    """
    import tenacity

    if True:
        @tenacity.retry(
            stop=ai_service._stop_su_tentativi_o_deadline,
            wait=ai_service._wait_entro_deadline,
            retry=tenacity.retry_if_exception_type(ValueError),
        )
        def _f():
            contatore["n"] += 1
            raise ValueError("errore ritentabile simulato")

        t0 = time.monotonic()
        with pytest.raises(Exception):
            _f()
        return time.monotonic() - t0


def test_tenacity_senza_deadline_fa_tutti_i_tentativi():
    """Path felice invariato: senza budget restano i 3 tentativi storici."""
    contatore = {"n": 0}
    _esegui_chunk_sempre_fallito(contatore)
    assert contatore["n"] == 3


def test_tenacity_si_ferma_subito_se_deadline_gia_scaduta():
    contatore = {"n": 0}
    ai_service._ai_ctx_deadline.set(time.monotonic() - 1)
    durata = _esegui_chunk_sempre_fallito(contatore)
    assert contatore["n"] == 1, "ha ritentato nonostante il budget esaurito"
    assert durata < 1.0


def test_tenacity_rispetta_il_budget_totale():
    """Un chunk sempre fallito non deve superare il budget configurato.

    Senza il troncamento del backoff, i soli sleep (2s + 4s) sforavano gia' un
    budget stretto prima ancora di ritentare.
    """
    contatore = {"n": 0}
    ai_service.set_ai_deadline(2)
    durata = _esegui_chunk_sempre_fallito(contatore)
    assert durata <= 3.0, f"budget 2s sforato: {durata:.1f}s"


def test_wait_mai_negativo(monkeypatch):
    """Con budget residuo negativo il wait deve valere 0, non un tempo negativo
    (tenacity rifiuta le attese negative con ValueError).

    `wait_exponential` in ai_service e' quello vero di tenacity: dal 28/8/2026
    il conftest non lo mocka piu', quindi si misura la libreria, non un mock.
    """
    ai_service._ai_ctx_deadline.set(time.monotonic() - 100)

    class _S:
        attempt_number = 2
        outcome = None
        idle_for = 0
        next_action = None

    assert ai_service._wait_entro_deadline(_S()) == 0.0


# ─── livello 2: retry applicativo in classifica_con_ai ───────────────────────

def test_classifica_con_ai_salta_i_retry_a_budget_esaurito(monkeypatch):
    """A deadline scaduta i retry non devono partire, ma la risposta deve
    comunque arrivare completa (fallback deterministico, nessuna eccezione)."""
    chiamate = {"n": 0}

    def _fake_gpt(descrizioni, *a, **k):
        chiamate["n"] += 1
        return (["Da Classificare"] * len(descrizioni), ["bassa"] * len(descrizioni))

    monkeypatch.setattr(ai_service, "_chiama_gpt_classificazione", _fake_gpt)
    monkeypatch.setattr(ai_service, "_get_openai_client", lambda *a, **k: object())

    ai_service._ai_ctx_deadline.set(time.monotonic() - 1)
    cats, confs = ai_service.classifica_con_ai(
        ["XKCD9931 ARTICOLO IGNOTO"], return_confidenze=True,
    )
    # una sola chiamata: la prima. I 2 giri di retry sono stati saltati.
    assert chiamate["n"] == 1, f"retry eseguiti a budget esaurito ({chiamate['n']} chiamate)"
    # contratto invariato: risposta allineata, nessuna eccezione propagata
    assert len(cats) == 1 and len(confs) == 1
    # regola di dominio #1: cio' che non si riconosce resta Da Classificare
    assert cats[0] == "Da Classificare"


def test_retry_si_interrompe_a_meta_pass_se_il_budget_scade(monkeypatch):
    """Il budget puo' scadere DENTRO un giro di retry, non solo prima.

    Con 60 descrizioni il retry le spezza in chunk da 20: se il budget finisce
    dopo il primo chunk, i due successivi non devono partire. Senza il guard nel
    loop dei chunk si continuerebbe fino in fondo al giro.
    """
    chiamate = {"n": 0}

    def _fake_gpt(descrizioni, *a, **k):
        chiamate["n"] += 1
        if chiamate["n"] == 2:
            # primo chunk del primo giro di retry: da qui il budget e' finito
            ai_service._ai_ctx_deadline.set(time.monotonic() - 1)
        return (["Da Classificare"] * len(descrizioni), ["bassa"] * len(descrizioni))

    monkeypatch.setattr(ai_service, "_chiama_gpt_classificazione", _fake_gpt)
    monkeypatch.setattr(ai_service, "_get_openai_client", lambda *a, **k: object())

    ai_service.set_ai_deadline(30)
    descrizioni = [f"XKCD99{i:02d} ARTICOLO IGNOTO" for i in range(60)]
    cats = ai_service.classifica_con_ai(descrizioni)

    # 1 prima chiamata + 1 solo chunk di retry: i chunk 2 e 3 sono stati saltati.
    assert chiamate["n"] == 2, (
        f"chunk di retry eseguiti oltre il budget ({chiamate['n']} chiamate)"
    )
    assert len(cats) == 60


def test_nessun_log_di_retry_avviato_se_il_budget_e_gia_finito(monkeypatch, caplog):
    """A budget gia' esaurito il giro di retry non deve nemmeno annunciarsi.

    Il guard interno (sui chunk) da solo basterebbe a non chiamare la GPT, ma il
    log direbbe "RETRY 1/2: N descrizioni... ritentando" per un lavoro mai fatto:
    a leggere i log di produzione sembrerebbe che i retry siano partiti.
    """
    def _fake_gpt(descrizioni, *a, **k):
        return (["Da Classificare"] * len(descrizioni), ["bassa"] * len(descrizioni))

    monkeypatch.setattr(ai_service, "_chiama_gpt_classificazione", _fake_gpt)
    monkeypatch.setattr(ai_service, "_get_openai_client", lambda *a, **k: object())

    ai_service._ai_ctx_deadline.set(time.monotonic() - 1)
    with caplog.at_level("INFO", logger="fci_app.ai"):
        ai_service.classifica_con_ai(["XKCD9931 ARTICOLO IGNOTO"])

    assert not any("ritentando" in r.message for r in caplog.records), (
        "log di retry avviato con budget gia' esaurito: i log mentono su cosa e' successo"
    )


def test_classifica_con_ai_esegue_i_retry_senza_deadline(monkeypatch):
    """Controprova: senza budget i retry storici devono ancora scattare."""
    chiamate = {"n": 0}

    def _fake_gpt(descrizioni, *a, **k):
        chiamate["n"] += 1
        return (["Da Classificare"] * len(descrizioni), ["bassa"] * len(descrizioni))

    monkeypatch.setattr(ai_service, "_chiama_gpt_classificazione", _fake_gpt)
    monkeypatch.setattr(ai_service, "_get_openai_client", lambda *a, **k: object())

    ai_service.clear_ai_deadline()
    ai_service.classifica_con_ai(["XKCD9931 ARTICOLO IGNOTO"], return_confidenze=True)
    # prima chiamata + MAX_RETRY (2) giri
    assert chiamate["n"] == 3, f"i retry non scattano piu' senza deadline ({chiamate['n']})"


def test_deadline_scaduta_non_propaga_mai_eccezioni(monkeypatch):
    """Anche se la GPT esplode a budget esaurito, il salvataggio non deve rompersi."""
    def _esplode(*a, **k):
        raise ValueError("boom")

    monkeypatch.setattr(ai_service, "_chiama_gpt_classificazione", _esplode)
    monkeypatch.setattr(ai_service, "_get_openai_client", lambda *a, **k: object())

    ai_service._ai_ctx_deadline.set(time.monotonic() - 1)
    cats = ai_service.classifica_con_ai(["MOZZARELLA FIORDILATTE KG 1"])
    assert len(cats) == 1


# ─── livello 3: retry chunk nel queue-worker ─────────────────────────────────

def test_worker_guard_deadline_nel_retry_chunk():
    src = inspect.getsource(qp._auto_classify_saved_rows)
    assert "ai_deadline_scaduta()" in src, (
        "il retry chunk del worker ignora il budget condiviso"
    )


def test_worker_non_dorme_oltre_il_budget():
    """I due time.sleep() diretti del backoff dovevano passare dal troncamento:
    da soli (2s+4s) potevano sforare il budget prima ancora di ritentare."""
    src = inspect.getsource(qp._auto_classify_saved_rows)
    assert "_sleep_backoff_entro_budget(" in src
    assert "time.sleep(_CLASSIFY_RETRY_BACKOFF" not in src, (
        "backoff non troncato: resta uno sleep che ignora la deadline"
    )


def test_sleep_backoff_troncato_al_budget():
    ai_service.set_ai_deadline(0.2)
    t0 = time.monotonic()
    qp._sleep_backoff_entro_budget(2)   # backoff nominale: 2.0 * 4 = 8s
    durata = time.monotonic() - t0
    assert durata < 1.0, f"ha dormito {durata:.1f}s ignorando il budget di 0.2s"


def test_sleep_backoff_non_dorme_a_budget_esaurito():
    ai_service._ai_ctx_deadline.set(time.monotonic() - 1)
    t0 = time.monotonic()
    qp._sleep_backoff_entro_budget(0)
    assert time.monotonic() - t0 < 0.5


def test_sleep_backoff_invariato_senza_deadline():
    """Senza budget il backoff storico resta intatto."""
    ai_service.clear_ai_deadline()
    t0 = time.monotonic()
    qp._sleep_backoff_entro_budget(0)   # _CLASSIFY_RETRY_BACKOFF = 2.0s
    durata = time.monotonic() - t0
    assert durata >= 1.5, f"backoff accorciato senza deadline attiva: {durata:.1f}s"


# ─── il chiamante che impone il budget ───────────────────────────────────────

def test_upload_imposta_e_pulisce_la_deadline():
    """L'endpoint upload e' l'unico con un client che abortisce a 30s: deve
    imporre il budget e rimuoverlo, altrimenti la deadline resterebbe appiccicata
    al contesto per le operazioni successive."""
    from services import fastapi_worker
    src = inspect.getsource(fastapi_worker)
    assert "set_ai_deadline(" in src, "l'upload non impone alcun budget AI"
    assert "clear_ai_deadline()" in src, (
        "la deadline non viene rimossa: resterebbe attiva oltre l'upload"
    )


def test_budget_default_sotto_il_timeout_del_proxy():
    """Il budget deve stare SOTTO i 30s dell'abort Next.js
    (apps/web/src/app/api/upload/invoice/route.ts), altrimenti e' inutile."""
    assert 0 < ai_service.AI_BUDGET_DEFAULT_SECONDS < 30
