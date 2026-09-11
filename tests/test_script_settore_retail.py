"""Gli script manuali non classificano un negozio come un ristorante.

Quattro residui dichiarati dal reviewer alle Fasi 1 e 2, spostati qui perche' la
Fase 4 e' il momento in cui questi script verrebbero rilanciati davvero — per
misurare la qualita' della categorizzazione di un cliente retail.

Il buco NON era solo il prompt. Misurato eseguendo:

- `/api/classify` risolve il settore da `user_id`, e anche il fallback locale di
  `classifica_via_worker_con_confidenza` faceva lo stesso. `ricategorizza_sede_ai.py`
  passa `user_id=None` e solo `ristorante_id`: cadeva quindi sul percorso
  ristorazione per costruzione, non per caso;
- `ricategorizza_sede.py` non usa affatto l'AI: chiama dizionario e regole forti
  DIRETTAMENTE, saltando il chokepoint `categorizza_con_memoria` dove la Fase 1
  aveva messo il filtro d'uscita. E' la stessa famiglia dei sette buchi della
  Fase 1 — un gate a monte che non copre il punto a valle.

Gli script `catscan_*` sono di sola lettura: il danno sarebbe una diagnosi
sbagliata a video, non dati sporchi. Restano comunque corretti: una diagnosi che
accusa righe giuste fa perdere tempo a chi la legge.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

from config.constants import CATEGORIE_FOOD_BEVERAGE, SETTORE_RETAIL, SETTORE_RISTORAZIONE

RADICE = Path(__file__).resolve().parent.parent
SCRIPT_DET = RADICE / "scripts" / "ricategorizza_sede.py"


@pytest.fixture
def script_det():
    spec = importlib.util.spec_from_file_location("_ricat_sede_settore_test", SCRIPT_DET)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _riga(descrizione, categoria="Da Classificare", **extra):
    base = {
        "id": 1, "descrizione": descrizione, "fornitore": "FORNITORE X",
        "categoria": categoria, "categoria_fonte": None, "reviewed_at": None,
        "prezzo_unitario": 10.0, "totale_riga": 10.0, "iva_percentuale": 10.0,
    }
    base.update(extra)
    return base


# ── ricategorizza_sede.py: il filtro d'uscita che mancava ────────────────

def test_la_pipeline_non_da_una_categoria_food_a_un_negozio(script_det):
    """Il caso reale: il dizionario riconosce una descrizione alimentare e la
    manderebbe in una categoria che per un negozio non esiste."""
    cat = script_det.pipeline_deterministica(
        "MOZZARELLA FIORDILATTE 1KG", "Da Classificare", "FORNITORE X",
        SETTORE_RETAIL,
    )
    assert cat not in CATEGORIE_FOOD_BEVERAGE
    assert cat == "Da Classificare"


def test_la_stessa_riga_resta_food_per_un_ristorante(script_det):
    """Se fosse 'Da Classificare' anche qui, il test sopra non misurerebbe il
    settore ma solo che il dizionario non riconosce la descrizione."""
    cat = script_det.pipeline_deterministica(
        "MOZZARELLA FIORDILATTE 1KG", "Da Classificare", "FORNITORE X",
        SETTORE_RISTORAZIONE,
    )
    assert cat in CATEGORIE_FOOD_BEVERAGE, (
        f"il dizionario non riconosce piu' questa descrizione (da' {cat!r}): "
        "il test del retail diventerebbe vacuo"
    )


@pytest.mark.parametrize("settore", [SETTORE_RISTORAZIONE, None, "", "valore_ignoto"])
def test_il_ramo_ristorazione_della_pipeline_e_quello_di_ieri(script_det, settore):
    """Compreso il default `settore=None`, che e' come la chiamano i test
    esistenti e ogni chiamante che non e' stato aggiornato."""
    atteso = script_det.pipeline_deterministica(
        "MOZZARELLA FIORDILATTE 1KG", "Da Classificare", "FORNITORE X", SETTORE_RISTORAZIONE,
    )
    assert script_det.pipeline_deterministica(
        "MOZZARELLA FIORDILATTE 1KG", "Da Classificare", "FORNITORE X", settore,
    ) == atteso


def test_le_categorie_generiche_passano_anche_per_un_negozio(script_det):
    """Utenze e simili sono giuste per entrambi: filtrarle avrebbe mandato in
    coda righe che il sistema sa classificare."""
    cat = script_det.pipeline_deterministica(
        "CANONE LINEA TELEFONICA", "Da Classificare", "TIM S.P.A.", SETTORE_RETAIL,
    )
    assert cat != "Da Classificare"
    assert cat not in CATEGORIE_FOOD_BEVERAGE


def test_seleziona_aggiornamenti_propaga_il_settore(script_det):
    """Il gate sta in `pipeline_deterministica`, ma e' `seleziona_aggiornamenti`
    la funzione che lo script chiama: se non glielo passasse, il filtro non
    scatterebbe mai in esecuzione reale."""
    righe = [_riga("MOZZARELLA FIORDILATTE 1KG")]
    updates_retail, _, _ = script_det.seleziona_aggiornamenti(righe, SETTORE_RETAIL)
    updates_risto, _, _ = script_det.seleziona_aggiornamenti(righe, SETTORE_RISTORAZIONE)

    assert not any(
        cat in CATEGORIE_FOOD_BEVERAGE for cat, _nr in updates_retail.values()
    ), "una categoria food e' passata dal selettore per un negozio"
    assert any(
        cat in CATEGORIE_FOOD_BEVERAGE for cat, _nr in updates_risto.values()
    ), "il ristorante non ha ricevuto la categoria food: il test e' vacuo"


# ── worker_client: il fallback sulla sede ────────────────────────────────

def test_il_client_risolve_il_settore_dalla_sede_se_manca_l_utente(monkeypatch):
    """Il buco di `ricategorizza_sede_ai.py`: passa `user_id=None` e solo la
    sede, quindi senza questo fallback riceveva il prompt dei ristoranti."""
    import services.ai_service as ai
    import services.settore_service as ss
    import services.worker_client as wc

    ricevuti: list = []

    def _finta(descrizioni, **kw):
        ricevuti.append(kw)
        return ["ARTICOLO DI VENDITA"] * len(descrizioni), ["alta"] * len(descrizioni)

    monkeypatch.setattr(ai, "classifica_con_ai", _finta)
    monkeypatch.setattr(ss, "settore_sede", lambda rid, supabase_client=None: (
        SETTORE_RETAIL if rid == "rid-retail" else SETTORE_RISTORAZIONE
    ))
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: SETTORE_RISTORAZIONE)

    wc.force_local_worker_path(True)
    try:
        wc.classifica_via_worker_con_confidenza(["MARTELLO"], ristorante_id="rid-retail")
        wc.classifica_via_worker_con_confidenza(["MARTELLO"], ristorante_id="rid-risto")
        wc.classifica_via_worker_con_confidenza(["MARTELLO"])
    finally:
        wc.force_local_worker_path(False)

    assert [r["settore"] for r in ricevuti] == [SETTORE_RETAIL, SETTORE_RISTORAZIONE, None]


def test_l_utente_vince_sulla_sede(monkeypatch):
    """L'account e' la fonte autorevole: la sede e' il ripiego di chi non ce
    l'ha. Se vincesse la sede, un chiamante corretto perderebbe la risoluzione
    piu' precisa."""
    import services.ai_service as ai
    import services.settore_service as ss
    import services.worker_client as wc

    ricevuti: list = []
    monkeypatch.setattr(ai, "classifica_con_ai", lambda d, **kw: (
        ricevuti.append(kw) or (["X"] * len(d), ["alta"] * len(d))
    ))
    monkeypatch.setattr(ss, "settore_utente", lambda uid, supabase_client=None: SETTORE_RETAIL)
    monkeypatch.setattr(ss, "settore_sede", lambda rid, supabase_client=None: SETTORE_RISTORAZIONE)

    wc.force_local_worker_path(True)
    try:
        wc.classifica_via_worker_con_confidenza(["X"], user_id="u-1", ristorante_id="rid-1")
    finally:
        wc.force_local_worker_path(False)

    assert ricevuti[0]["settore"] == SETTORE_RETAIL


# ── I due catscan: il settore arriva al prompt ───────────────────────────

@pytest.mark.parametrize("nome", ["catscan_arbitro.py", "catscan_senza_segnale.py"])
def test_i_catscan_passano_il_settore(nome):
    """Sola lettura, ma una diagnosi sbagliata fa perdere tempo a chi la legge.

    Entrambi gli script eseguono a import time e non sono importabili, quindi il
    presidio parte dal sorgente — ma NON cercando `settore=` in una finestra di
    testo: la prima stesura lo faceva, e un mutante che TOGLIEVA l'argomento e'
    sopravvissuto, perche' la finestra pescava il `settore=` della chiamata
    dopo. Qui si analizza l'AST e si guarda la singola CHIAMATA.
    """
    import ast as _ast

    src = (RADICE / "scripts" / nome).read_text(encoding="utf-8")
    assert "settore_utente" in src, f"{nome} non risolve il settore"

    chiamate = [
        nodo for nodo in _ast.walk(_ast.parse(src))
        if isinstance(nodo, _ast.Call)
        and getattr(nodo.func, "id", getattr(nodo.func, "attr", None)) == "classifica_con_ai"
    ]
    assert chiamate, f"{nome} non chiama piu' classifica_con_ai: presidio da rivedere"
    for c in chiamate:
        kw = {k.arg for k in c.keywords}
        assert "settore" in kw, (
            f"{nome} riga {c.lineno}: chiamata a classifica_con_ai senza "
            f"`settore` (argomenti: {sorted(kw)}) — un negozio riceverebbe il "
            "prompt dei ristoranti"
        )
