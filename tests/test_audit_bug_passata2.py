"""Test di regressione per l'audit Bug — passata 2 (3/8/2026).

Perimetro: margini / briefing / chat. Ogni test qui e' stato verificato fallire
col codice pre-fix: un test verde al primo colpo non prova nulla (lezione 9 del
documento di stato).
"""
import asyncio
from unittest.mock import patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# HIGH — agent notturno: create_task su funzione sincrona
# ─────────────────────────────────────────────────────────────────────────────

def test_create_task_su_funzione_sincrona_esplode():
    """Documenta PERCHE' serve to_thread: passare una funzione sync a create_task
    la esegue inline (bloccando) e poi solleva TypeError sul valore di ritorno.
    Se un domani qualcuno "semplifica" il fix, questo test spiega il danno."""
    eseguita = []

    def _sync():
        eseguita.append(True)
        return {"ok": 1}

    async def _main():
        with pytest.raises(TypeError):
            asyncio.create_task(_sync(), name="t")

    asyncio.run(_main())
    # Il corpo E' stato eseguito: il bug non era "non parte mai", era "parte
    # bloccando l'event loop e poi fallisce".
    assert eseguita == [True]


def test_agent_notturno_schedulato_via_to_thread():
    """Il loop notturno deve passare la funzione a to_thread, non chiamarla."""
    import services.fastapi_worker as fw
    import inspect

    src = inspect.getsource(fw._agent_notturno_loop)
    assert "asyncio.to_thread(_run_agent_notturno)" in src, (
        "il loop deve usare to_thread: _run_agent_notturno e' sincrona e fa I/O"
    )
    assert "create_task(_run_agent_notturno()" not in src


def test_endpoint_esegui_ora_usa_thread_non_asyncio():
    """La route admin e' `def` sincrona: asyncio.create_task darebbe RuntimeError
    (no running event loop) dopo aver gia' eseguito tutto il lavoro."""
    import services.routers.admin as adm
    import inspect

    src = inspect.getsource(adm.admin_agent_notturno_esegui_ora)
    assert "threading.Thread" in src
    assert "asyncio.create_task" not in src.replace("# asyncio.create_task", "")


# ─────────────────────────────────────────────────────────────────────────────
# HIGH — chat: alert su colonna inesistente
# ─────────────────────────────────────────────────────────────────────────────

def test_alert_ricavi_usa_colonne_reali_di_margini_mensili():
    """margini_mensili non ha una colonna `fatturato`: la query falliva con 42703
    e l'except silenzioso rendeva l'alert inerte da sempre."""
    import services.fastapi_worker as fw
    import inspect

    src = inspect.getsource(fw._build_chat_system_prompt)
    assert '.select("fatturato")' not in src
    assert "fatturato_iva10" in src and "fatturato_iva22" in src


def test_alert_spese_non_usa_ilike_spese():
    """Nessuna categoria reale contiene la parola 'SPESE': ilike('%SPESE%')
    matchava 0 righe su 5827, facendo scattare un falso allarme."""
    import services.fastapi_worker as fw
    import inspect

    src = inspect.getsource(fw._build_chat_system_prompt)
    assert 'ilike("categoria", "%SPESE%")' not in src


def test_alert_chat_non_hanno_except_muti():
    """Un `except: pass` ha nascosto per mesi una query rotta: ogni alert deve
    almeno loggare."""
    import services.fastapi_worker as fw
    import inspect

    src = inspect.getsource(fw._build_chat_system_prompt)
    # nessun "except Exception:" seguito da "pass" nudo
    righe = [r.strip() for r in src.splitlines()]
    for i, r in enumerate(righe[:-1]):
        if r == "except Exception:":
            assert righe[i + 1] != "pass", (
                f"except muto alla riga {i} di _build_chat_system_prompt"
            )


# ─────────────────────────────────────────────────────────────────────────────
# MEDIUM — margini: riparto e note
# ─────────────────────────────────────────────────────────────────────────────

def test_costi_auto_escludono_fatture_ripartite():
    """Le fatture ripartite arrivano gia' come quote_riparto_* sui PV: contarle
    anche negli aggregatori le sottrarrebbe due volte dal MOL."""
    import services.fastapi_worker as fw
    import inspect

    for fn in (fw._calcola_costi_auto_per_mese, fw._calcola_costi_auto_per_periodo):
        src = inspect.getsource(fn)
        assert '.neq("ripartita_su_gruppo", True)' in src, (
            f"{fn.__name__} non filtra le fatture ripartite"
        )


def test_costi_auto_escludono_entrambe_le_grafie_note():
    import services.fastapi_worker as fw
    import inspect

    for fn in (fw._calcola_costi_auto_per_mese, fw._calcola_costi_auto_per_periodo):
        src = inspect.getsource(fn)
        assert "CATEGORIE_NOTE_WORKER" in src, (
            f"{fn.__name__} confronta la sola stringa con emoji"
        )


def test_costanti_spese_derivano_da_una_sola_fonte():
    """Tre elenchi hardcoded nello stesso file erano tre fonti di verita'."""
    import services.fastapi_worker as fw
    from config.constants import CATEGORIE_SPESE_GENERALI

    attese = set(CATEGORIE_SPESE_GENERALI)
    assert set(fw.CATEGORIE_SPESE_GENERALI_WORKER) == attese
    assert set(fw._CATEGORIE_SPESE_M) == attese


# ─────────────────────────────────────────────────────────────────────────────
# MEDIUM — foodcost: "Da Classificare" fuori dagli ingredienti
# ─────────────────────────────────────────────────────────────────────────────

class _FakeQ:
    def __init__(self, sink):
        self._sink = sink

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def is_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, *_a, **_k):
        return self

    @property
    def not_(self):
        return self

    def in_(self, col, valori):
        self._sink["not_in"] = (col, list(valori))
        return self

    def execute(self):
        class _R:
            data = []
        return _R()


class _FakeSB:
    def __init__(self, sink):
        self._sink = sink

    def table(self, _nome):
        return _FakeQ(self._sink)


def test_ingredienti_escludono_le_righe_da_classificare():
    """Una riga ancora in coda di revisione non deve poter entrare nel foodcost
    di una ricetta (CLAUDE.md §1)."""
    from services.foodcost_service import get_articoli_da_fatture
    from config.constants import CATEGORIA_NON_CLASSIFICATA

    sink: dict = {}
    get_articoli_da_fatture(_FakeSB(sink), "u1", "r1")

    col, valori = sink["not_in"]
    assert col == "categoria"
    assert CATEGORIA_NON_CLASSIFICATA in valori, (
        "le righe Da Classificare finivano fra gli ingredienti selezionabili"
    )


# ─────────────────────────────────────────────────────────────────────────────
# MEDIUM — chat: mese parziale e Da Classificare dichiarati
# ─────────────────────────────────────────────────────────────────────────────

def test_query_margini_marca_il_mese_in_corso():
    import services.fastapi_worker as fw
    import inspect

    src = inspect.getsource(fw._chat_query_margini)
    assert '"parziale"' in src, (
        "senza il flag l'AI confronta il mese in corso coi mesi chiusi"
    )


def test_query_costi_dichiara_le_righe_da_classificare():
    import services.fastapi_worker as fw
    import inspect

    src = inspect.getsource(fw._chat_query_costi)
    assert "incluso_da_classificare" in src


# ─────────────────────────────────────────────────────────────────────────────
# MEDIUM — briefing: bullet vuoti e invalidazione su topic spenti
# ─────────────────────────────────────────────────────────────────────────────

def test_bullet_vuoti_non_finiscono_nel_prompt_ai():
    """Un bullet vuoto diventa un '- ' nudo che invita l'AI a inventare."""
    import services.daily_briefing_service as dbs
    import inspect

    src = inspect.getsource(dbs._build_snapshot)
    assert "if b]" in src, "le stringhe vuote non vengono filtrate da aperture_bullets"


def test_briefing_code_version_bumpata():
    """Il filtro dei bullet vuoti cambia l'output visibile: senza bump, chi ha
    gia' lo snapshot di oggi continua a vedere il '- ' nudo fino al TTL."""
    from services.daily_briefing_service import _BRIEFING_CODE_VERSION

    assert _BRIEFING_CODE_VERSION >= 13, (
        "logica briefing modificata senza bumpare _BRIEFING_CODE_VERSION"
    )


def test_streak_gemello_non_azzera_la_promozione():
    """Il ramo gemello deve replicare la logica dell'altro ramo: scrivere sempre
    streak=1 impedirebbe l'auto-promozione a confidence='alta'."""
    import services.ai_service as ais
    import inspect

    src = inspect.getsource(ais.aggiorna_streak_classificazione)
    assert "consecutive_correct_classifications" in src.split("_gemello = None")[1], (
        "il lookup del gemello non legge lo streak esistente"
    )


def test_ricavi_modalita_invalida_le_cache():
    """Dopo 'Carica Ricavi' mensile, Home e briefing devono rigenerarsi."""
    import services.routers.ricavi as ric
    import inspect

    src = inspect.getsource(ric.upsert_ricavi_modalita)
    assert "_invalidate_home_kpi_cache" in src
    assert "invalidate_today_briefing" in src


def test_config_invalida_briefing_solo_se_i_topic_cambiano():
    """topics_disabled ha default [] (non None): invalidare su 'is not None'
    rigenererebbe il briefing a ogni salvataggio, anche solo del nome."""
    import services.fastapi_worker as fw
    import inspect

    src = inspect.getsource(fw.home_config_post)
    assert "_topics_cambiati" in src
    assert "body.topics_disabled is not None" not in src


# ─────────────────────────────────────────────────────────────────────────────
# LOW — codice morto
# ─────────────────────────────────────────────────────────────────────────────

def test_rami_morti_rimossi_dalla_narrativa():
    import services.daily_briefing_service as dbs
    import inspect

    src = inspect.getsource(dbs._narrative_phrase_for)
    assert src.count("if topic == 'coperti_anomalia':") == 1, (
        "il secondo blocco coperti_anomalia era irraggiungibile"
    )


def test_badge_inbox_rimosso():
    import services.notification_inbox_service as nis

    assert not hasattr(nis, "get_inbox_badge_count")
    assert not hasattr(nis, "_get_inbox_badge_cached")


# ─────────────────────────────────────────────────────────────────────────────
# HIGH — prodotti_master: niente doppioni per grafia
# ─────────────────────────────────────────────────────────────────────────────

class _StreakSB:
    """Simula prodotti_master: nessun match esatto, ma esiste il normalizzato."""

    def __init__(self, esistente_normalizzato: str, categoria="MATERIALE DI CONSUMO", streak=0):
        self._norm = esistente_normalizzato
        self._cat = categoria
        self._streak = streak
        self.upsert_chiamato = False
        self.update_payload = None

    def table(self, _n):
        return self

    def select(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._eq = (col, val)
        return self

    def execute(self):
        class _R:
            pass

        r = _R()
        col, val = getattr(self, "_eq", (None, None))
        if col == "descrizione" and val == self._norm:
            r.data = [{
                "id": 42, "verified": False, "confidence": "media",
                "categoria": self._cat,
                "consecutive_correct_classifications": self._streak,
            }]
        else:
            r.data = []
        return r

    def upsert(self, *_a, **_k):
        self.upsert_chiamato = True
        return self

    def update(self, payload):
        self.update_payload = payload
        return self


def test_streak_non_crea_doppione_se_esiste_il_normalizzato():
    """aggiorna_streak_classificazione riceve descrizioni GREZZE dalla coda:
    senza il lookup normalizzato nascevano due record per lo stesso prodotto,
    che poi insegnavano categorie diverse."""
    from utils.text_utils import normalizza_descrizione
    from services.ai_service import aggiorna_streak_classificazione

    grezza = "(I)100 COP EST. X DW 280CC"
    norm = normalizza_descrizione(grezza)
    assert norm != grezza, "prerequisito del test: la grafia deve normalizzare diversa"

    sb = _StreakSB(esistente_normalizzato=norm)
    aggiorna_streak_classificazione(grezza, "MATERIALE DI CONSUMO", sb)

    assert sb.upsert_chiamato is False, (
        "ha inserito un doppione invece di aggiornare il record normalizzato"
    )


def test_streak_gemello_incrementa_e_promuove():
    """Se la categoria coincide, lo streak deve crescere e promuovere a 'alta'
    a quota 3 — come fa il ramo match-esatto."""
    from utils.text_utils import normalizza_descrizione
    from services.ai_service import aggiorna_streak_classificazione

    grezza = "(I)100 COP EST. X DW 280CC"
    norm = normalizza_descrizione(grezza)
    cat = "MATERIALE DI CONSUMO"

    # streak 2 + stessa categoria -> 3 -> promozione
    sb = _StreakSB(esistente_normalizzato=norm, categoria=cat, streak=2)
    aggiorna_streak_classificazione(grezza, cat, sb)
    assert sb.update_payload["consecutive_correct_classifications"] == 3
    assert sb.update_payload.get("confidence") == "alta"

    # categoria diversa -> reset a 1, nessuna promozione
    sb2 = _StreakSB(esistente_normalizzato=norm, categoria="PESCE", streak=2)
    aggiorna_streak_classificazione(grezza, cat, sb2)
    assert sb2.update_payload["consecutive_correct_classifications"] == 1


class _StreakSBContaSelect:
    """Come _StreakSB ma conta i SELECT: serve a dimostrare che passare
    record_precaricato evita il lookup (audit Performance, N+1 queue-worker)."""

    def __init__(self, categoria="MATERIALE DI CONSUMO", streak=0):
        self._cat = categoria
        self._streak = streak
        self.select_calls = 0
        self.update_payload = None

    def table(self, _n):
        return self

    def select(self, *_a, **_k):
        self.select_calls += 1
        return self

    def limit(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._eq = (col, val)
        return self

    def execute(self):
        class _R:
            pass
        r = _R()
        r.data = [{
            "id": 7, "verified": False, "confidence": "media",
            "categoria": self._cat,
            "consecutive_correct_classifications": self._streak,
        }]
        return r

    def update(self, payload):
        self.update_payload = payload
        return self


def test_streak_con_record_precaricato_non_fa_select():
    """record_precaricato deve far saltare il SELECT di lookup: e' il batching
    che rimpiazza 1 round-trip per descrizione con 1 solo per l'intero chunk."""
    from services.ai_service import aggiorna_streak_classificazione

    sb = _StreakSBContaSelect(categoria="PESCE", streak=2)
    aggiorna_streak_classificazione(
        "MERLUZZO FILETTO", "PESCE", sb,
        record_precaricato={
            "id": 7, "verified": False, "confidence": "media",
            "categoria": "PESCE", "consecutive_correct_classifications": 2,
        },
    )
    assert sb.select_calls == 0, "record_precaricato deve evitare il SELECT"
    assert sb.update_payload["consecutive_correct_classifications"] == 3
    assert sb.update_payload.get("confidence") == "alta"


def test_streak_senza_record_precaricato_fa_select_come_prima():
    """Senza il parametro (default), il comportamento pre-esistente non cambia:
    nessuna call-site fuori dal queue-worker deve essere toccata da questo fix."""
    from services.ai_service import aggiorna_streak_classificazione

    sb = _StreakSBContaSelect(categoria="PESCE", streak=2)
    aggiorna_streak_classificazione("MERLUZZO FILETTO", "PESCE", sb)
    assert sb.select_calls == 1


def test_streak_record_precaricato_none_significa_prodotto_assente():
    """record_precaricato=None e' 'precaricato ma vuoto' (non nel batch), non va
    confuso col default (sentinella) che invece fa il SELECT di lookup. Deve
    trattarlo come prodotto nuovo e inserirlo, non fare l'UPDATE del ramo
    match-esatto.

    NB: l'invariante NON e' "zero SELECT" — col ramo gemello una descrizione che
    normalizza diversa fa comunque il suo lookup normalizzato. L'invariante e'
    che il SELECT *di lookup per match esatto* sia stato saltato, cioe' che si
    finisca nel ramo prodotto-nuovo."""
    from services.ai_service import aggiorna_streak_classificazione

    class _SBUpsert(_StreakSBContaSelect):
        """Nessun record in tabella: ne' per match esatto ne' per normalizzato.
        Cosi' l'unico esito possibile e' il ramo prodotto-nuovo."""

        def __init__(self):
            super().__init__()
            self.upsert_chiamato = False

        def execute(self):
            class _R:
                pass
            r = _R()
            r.data = []
            return r

        def upsert(self, *_a, **_k):
            self.upsert_chiamato = True
            return self

    # Descrizione che NORMALIZZA DIVERSA: cosi' il test esercita davvero il ramo
    # gemello invece di passare per caso su una grafia gia' normalizzata.
    from utils.text_utils import normalizza_descrizione
    grezza = "Pane  Casereccio 1KG"
    assert normalizza_descrizione(grezza) != grezza, (
        "prerequisito del test: serve una grafia che normalizzi diversa"
    )

    sb = _SBUpsert()
    aggiorna_streak_classificazione(grezza, "CARNE", sb, record_precaricato=None)
    assert sb.upsert_chiamato is True, (
        "record_precaricato=None deve portare al ramo prodotto-nuovo (upsert), "
        "non all'UPDATE del ramo match-esatto"
    )
    assert sb.update_payload is None, (
        "non deve aggiornare un record per match esatto: quel record non esiste"
    )


def test_prefetch_fallito_non_azzera_lo_streak():
    """Se il pre-fetch del chunk fallisce, il worker NON deve passare un dict
    vuoto: 'assente dal batch' significa 'prodotto nuovo' e farebbe saltare il
    guard `verified`, azzerando lo streak di un prodotto gia' noto (e
    sovrascrivendo un prodotto verificato a mano dall'admin). Deve invece
    ricadere sul SELECT per riga, cioe' il comportamento pre-fix."""
    import inspect
    import worker.queue_processor as qp

    src = inspect.getsource(qp._auto_classify_saved_rows)
    assert "_streak_precaricati = None" in src, (
        "il ramo except del pre-fetch deve annullare il batch (None), non "
        "passare un dict vuoto che verrebbe letto come 'prodotto assente'"
    )
    assert "_STREAK_NON_PRECARICATO if _streak_precaricati is None" in src, (
        "col batch annullato va passata la sentinella, non None: None significa "
        "'precaricato ma assente' e salta il guard verified"
    )
