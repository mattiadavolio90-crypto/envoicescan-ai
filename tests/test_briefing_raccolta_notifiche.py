"""Test audit §3 — `_briefing_raccogli_notifiche` e `_scontrino_medio_significativo`
(`services/fastapi_worker.py`, 10/8/2026).

E' cio' che il cliente LEGGE in Home. `_briefing_raccogli_notifiche` era finora
sempre e solo mockata (`tests/test_home_briefing_cache_first.py:114,142,164`):
nessun test la eseguiva, quindi nessuno difendeva i suoi invarianti dichiarati a
commento. `_scontrino_medio_significativo` non compariva in tutta la suite.

REGOLA ANTI-VACUITA' seguita qui. Si stubbano solo i sotto-helper che NON
producono la notifica sotto esame, e mai con un `MagicMock()` nudo: un MagicMock
e' truthy e, restituito da un sotto-helper, entrerebbe nella lista superando
qualunque assert di presenza. I default sono `None`/`[]`; dove il test osserva la
posizione si usano dict-sentinella espliciti.

NON sono mai stubbati (sono il corpo della funzione, non una dipendenza): la
query su `notification_inbox`, il blocco upload-ricavi-falliti, i filtri di
rimozione delle notifiche legacy, l'ordine degli `insert(0, ...)`, la gestione
del timeout dell'alert prezzi. Stubbarli renderebbe verde un test che non guarda
piu' nulla.
"""
import os
from datetime import date, datetime, timedelta, timezone

import pytest

os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import services.fastapi_worker as fw  # noqa: E402
from tests.test_costi_auto_fatture_mol import _FakeQuery  # noqa: E402

USER = "user-test"
RID = "rid-test"
ALTRO_RID = "rid-altro"

# I sotto-helper che il briefing chiama e che NON sono l'oggetto di questi test:
# ognuno ha gia' i suoi file di test dedicati. Default neutri, mai MagicMock.
_STUB_NEUTRI = {
    "_briefing_dati_mensili_mancanti": [],
    "_briefing_righe_da_classificare": None,
    "_briefing_fatture_mancanti": None,
    "_briefing_appuntamenti_oggi": [],
    "_briefing_buona_notizia": None,
    "_briefing_rientro_assenza": None,
    "_briefing_onboarding": None,
}


class _FakeSB:
    """Client fake con routing per tabella, una query NUOVA a ogni `table()`."""

    def __init__(self, notifiche=None, mappa_ricavi=None, giornalieri=None, recorder=None):
        self._notifiche = notifiche or []
        self._mappa = mappa_ricavi or []
        self._giornalieri = giornalieri or []
        self._rec = recorder if recorder is not None else {}

    def table(self, name):
        self._rec.setdefault("tables", []).append(name)
        src = {
            "notification_inbox": self._notifiche,
            "ricavi_ragione_sociale_map": self._mappa,
            "ricavi_giornalieri": self._giornalieri,
        }.get(name, [])
        return _FakeQuery(src, recorder=self._rec, table=name)


def _notifica(topic_key="scadenza_superata", user_id=USER, ristorante_id=RID,
              dismissed_at=None, expires_at=None, **extra):
    row = {
        "id": f"n-{topic_key}", "topic_key": topic_key, "source_type": "inbox",
        "severity": "info", "title": topic_key, "body": "", "action_page": "/",
        "payload": {}, "dismissed_at": dismissed_at, "expires_at": expires_at,
        "created_at": "2026-08-10T08:00:00+00:00", "source_event_at": None,
        "dedupe_key": topic_key, "user_id": user_id, "ristorante_id": ristorante_id,
    }
    row.update(extra)
    return row


@pytest.fixture
def stub(monkeypatch):
    """Applica gli stub neutri e restituisce un helper per sovrascriverli."""
    for nome, valore in _STUB_NEUTRI.items():
        monkeypatch.setattr(fw, nome, lambda *a, _v=valore, **k: _v)
    monkeypatch.setattr(fw, "_briefing_aggiorna_last_seen", lambda *a, **k: None)
    monkeypatch.setattr(fw, "_get_assistant_preferences", lambda *a, **k: {})

    def _override(nome, fn):
        monkeypatch.setattr(fw, nome, fn)
    return _override


@pytest.fixture
def prezzi(monkeypatch):
    """Sostituisce il motore alert prezzi e REGISTRA se e' stato chiamato.

    Il toggle-gating (fastapi_worker.py:5989) dice che un topic spento non deve
    far girare la sua funzione: senza registrare le chiamate, un test che guarda
    solo l'output passerebbe anche con un filtro applicato a valle.
    """
    import services.price_impact_service as pis
    chiamate = []

    def _installa(risultato=None, solleva=None, lento=False):
        def _fn(*a, **k):
            chiamate.append(True)
            if lento:
                import time
                time.sleep(0.6)
            if solleva is not None:
                raise solleva
            return risultato or {"count": 0, "top": None}
        monkeypatch.setattr(pis, "calcola_alert_prezzi_impatto", _fn)
        return chiamate

    _installa.chiamate = chiamate
    return _installa


def _topics(*keys):
    return {"topics_disabled": list(keys), "giorni_chiusura_settimanali": 0}


# ─────────────────────────────────────────────────────────────────────────────
# Alert prezzi — il legacy va rimosso SEMPRE, anche se il motore fallisce
# ─────────────────────────────────────────────────────────────────────────────

def test_price_alert_legacy_rimosso_anche_se_il_motore_va_in_timeout(stub, prezzi, monkeypatch):
    """Il commento a :6039-6045 dichiara che la rimozione sta FUORI dal try
    proprio perche' su un timeout il legacy resterebbe.

    Il legacy non ha filtro di peso: segnala qualsiasi rincaro, anche su prodotti
    marginali. Meglio nessun alert prezzi che un alert sbagliato.
    """
    monkeypatch.setattr(fw, "_ALERT_PREZZI_TIMEOUT_SEC", 0.05)
    prezzi(lento=True)
    sb = _FakeSB(notifiche=[_notifica("price_alert"), _notifica("scadenza_superata")])
    out = fw._briefing_raccogli_notifiche(USER, RID, sb)
    assert [n["topic_key"] for n in out if n["topic_key"] == "price_alert"] == []
    assert any(n["topic_key"] == "scadenza_superata" for n in out)


def test_price_alert_legacy_rimosso_anche_se_il_motore_solleva(stub, prezzi):
    prezzi(solleva=RuntimeError("boom"))
    sb = _FakeSB(notifiche=[_notifica("price_alert")])
    out = fw._briefing_raccogli_notifiche(USER, RID, sb)
    assert all(n["topic_key"] != "price_alert" for n in out)


def test_alert_prezzi_live_sostituisce_il_legacy(stub, prezzi):
    prezzi({"count": 3, "top": {"nome": "CAFFE", "aumento_pct": 20,
                                "impatto_mese": 150, "tipo": "tag"}})
    sb = _FakeSB(notifiche=[_notifica("price_alert")])
    out = fw._briefing_raccogli_notifiche(USER, RID, sb)
    alert = [n for n in out if n["topic_key"] == "price_alert"]
    assert len(alert) == 1
    assert alert[0]["id"] == "price-alert-live"
    # 'top_tipo' distingue prodotto da tag: senza, un alert su un TAG veniva
    # raccontato come se fosse un prodotto.
    assert alert[0]["payload"]["top_tipo"] == "tag"
    assert alert[0]["payload"]["count"] == 3


def test_alert_prezzi_non_calcolato_se_il_topic_e_spento(stub, prezzi):
    """Toggle-gating: la funzione non deve GIRARE, non basta filtrarne l'esito."""
    chiamate = prezzi({"count": 3, "top": {"nome": "X", "aumento_pct": 9}})
    stub("_get_assistant_preferences", lambda *a, **k: _topics("price_alert"))
    out = fw._briefing_raccogli_notifiche(USER, RID, _FakeSB())
    assert chiamate == []
    assert all(n["topic_key"] != "price_alert" for n in out)


def test_includi_alert_prezzi_false_salta_solo_i_prezzi(stub, prezzi):
    """Fast-path 2: niente 4s di alert prezzi, ma gli altri segnali live restano
    (o la Home mostrerebbe un falso 'tutto in ordine')."""
    chiamate = prezzi({"count": 1, "top": {"nome": "X", "aumento_pct": 9}})
    visti = []
    stub("_briefing_righe_da_classificare",
         lambda *a, **k: visti.append("righe") or _notifica("uncategorized_rows"))
    out = fw._briefing_raccogli_notifiche(USER, RID, _FakeSB(), includi_alert_prezzi=False)
    assert chiamate == []
    assert visti == ["righe"]
    assert any(n["topic_key"] == "uncategorized_rows" for n in out)


def test_budget_generoso_usa_il_timeout_async(stub, prezzi, monkeypatch):
    """Dal path async nessuno aspetta: 25s invece di 4s, cosi' su clienti grossi
    l'alert non viene piu' saltato in silenzio."""
    prezzi()
    budget = []

    class _FakeFut:
        def result(self, timeout=None):
            budget.append(timeout)
            return {"count": 0, "top": None}

    class _FakeEx:
        def submit(self, fn, *a, **k):
            return _FakeFut()

    monkeypatch.setattr(fw, "_ALERT_PREZZI_EXECUTOR", _FakeEx())
    fw._briefing_raccogli_notifiche(USER, RID, _FakeSB(), alert_prezzi_budget_generoso=True)
    fw._briefing_raccogli_notifiche(USER, RID, _FakeSB(), alert_prezzi_budget_generoso=False)
    assert budget == [fw._ALERT_PREZZI_TIMEOUT_ASYNC_SEC, fw._ALERT_PREZZI_TIMEOUT_SEC]


# ─────────────────────────────────────────────────────────────────────────────
# Lettura delle notifiche persistite
# ─────────────────────────────────────────────────────────────────────────────

def test_notifiche_dismissed_escluse(stub, prezzi):
    prezzi()
    sb = _FakeSB(notifiche=[
        _notifica("scadenza_superata"),
        _notifica("credit_note", dismissed_at="2026-08-09T10:00:00+00:00"),
    ])
    out = fw._briefing_raccogli_notifiche(USER, RID, sb)
    keys = [n["topic_key"] for n in out]
    assert "scadenza_superata" in keys and "credit_note" not in keys


def test_notifiche_scadute_escluse(stub, prezzi):
    """Esercita la `.or_("expires_at.is.null,expires_at.gt.<now>")`: una notifica
    scaduta non deve piu' comparire in Home."""
    prezzi()
    passato = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    futuro = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    sb = _FakeSB(notifiche=[
        _notifica("scadenza_superata", expires_at=passato),
        _notifica("credit_note", expires_at=futuro),
        _notifica("quality_check_failed", expires_at=None),
    ])
    keys = [n["topic_key"] for n in fw._briefing_raccogli_notifiche(USER, RID, sb)]
    assert "scadenza_superata" not in keys
    assert "credit_note" in keys and "quality_check_failed" in keys


def test_filtro_per_sede(stub, prezzi):
    """Multi-sede: il briefing di una sede non include le notifiche di un'altra."""
    prezzi()
    sb = _FakeSB(notifiche=[
        _notifica("scadenza_superata", ristorante_id=RID),
        _notifica("credit_note", ristorante_id=ALTRO_RID),
    ])
    keys = [n["topic_key"] for n in fw._briefing_raccogli_notifiche(USER, RID, sb)]
    assert "scadenza_superata" in keys and "credit_note" not in keys


def test_filtro_per_utente(stub, prezzi):
    prezzi()
    sb = _FakeSB(notifiche=[
        _notifica("scadenza_superata", user_id=USER),
        _notifica("credit_note", user_id="altro-user"),
    ])
    keys = [n["topic_key"] for n in fw._briefing_raccogli_notifiche(USER, RID, sb)]
    assert "scadenza_superata" in keys and "credit_note" not in keys


def test_lettura_notifiche_in_errore_non_blocca_il_briefing(stub, prezzi):
    """Fail-open: se l'inbox non si legge, il briefing esce lo stesso coi segnali
    live invece di sparire dalla Home."""
    prezzi()

    class _SbRotto(_FakeSB):
        def table(self, name):
            if name == "notification_inbox":
                raise RuntimeError("inbox giu'")
            return super().table(name)

    stub("_briefing_fatture_mancanti", lambda *a, **k: _notifica("fatture_mancanti"))
    out = fw._briefing_raccogli_notifiche(USER, RID, _SbRotto())
    assert [n["topic_key"] for n in out] == ["fatture_mancanti"]


# ─────────────────────────────────────────────────────────────────────────────
# Rimozione delle notifiche legacy stantie
# ─────────────────────────────────────────────────────────────────────────────

def test_dati_mensili_legacy_rimossi_prima_dei_live(stub, prezzi):
    """`_build_snapshot` tiene la PRIMA occorrenza per topic_key: una legacy
    stantia vincerebbe sulla versione live e il briefing continuerebbe a dire
    'manca il fatturato' anche dopo che il cliente l'ha inserito."""
    prezzi()
    live = _notifica("fatturato_mancante", id="live", payload={"fonte": "live"})
    stub("_briefing_dati_mensili_mancanti", lambda *a, **k: [live])
    sb = _FakeSB(notifiche=[_notifica("fatturato_mancante", id="legacy")])
    out = fw._briefing_raccogli_notifiche(USER, RID, sb)
    fm = [n for n in out if n["topic_key"] == "fatturato_mancante"]
    assert len(fm) == 1 and fm[0]["id"] == "live"


def test_uncategorized_rows_legacy_sostituita_dal_conteggio_live(stub, prezzi):
    prezzi()
    stub("_briefing_righe_da_classificare",
         lambda *a, **k: _notifica("uncategorized_rows", id="live"))
    sb = _FakeSB(notifiche=[_notifica("uncategorized_rows", id="legacy")])
    out = fw._briefing_raccogli_notifiche(USER, RID, sb)
    ur = [n for n in out if n["topic_key"] == "uncategorized_rows"]
    assert len(ur) == 1 and ur[0]["id"] == "live"


def test_uncategorized_rows_spento_lascia_la_legacy(stub, prezzi):
    """Comportamento ATTUALE, fissato non perche' sia desiderabile ma perche'
    cambi involontari siano visibili.

    Con il topic spento il blocco intero e' saltato, quindi la legacy stantia
    NON viene rimossa — asimmetrico rispetto al price_alert, dove la rimozione e'
    deliberatamente fuori dal gate. Verificato sul DB live il 10/8/2026: zero
    righe 'uncategorized_rows' in `notification_inbox`, quindi oggi e' latente.
    Se un domani si decide di allineare i due comportamenti, questo test cade e
    va aggiornato di proposito.
    """
    prezzi()
    stub("_get_assistant_preferences", lambda *a, **k: _topics("uncategorized_rows"))
    sb = _FakeSB(notifiche=[_notifica("uncategorized_rows", id="legacy")])
    out = fw._briefing_raccogli_notifiche(USER, RID, sb)
    assert [n["id"] for n in out if n["topic_key"] == "uncategorized_rows"] == ["legacy"]


# ─────────────────────────────────────────────────────────────────────────────
# Ricavi automatici assenti
# ─────────────────────────────────────────────────────────────────────────────

def test_upload_ricavi_solo_per_clienti_mappati(stub, prezzi):
    """Senza riga in `ricavi_ragione_sociale_map` il cliente inserisce a mano:
    segnalargli 'ricavi automatici assenti' sarebbe un falso allarme."""
    prezzi()
    out = fw._briefing_raccogli_notifiche(USER, RID, _FakeSB(mappa_ricavi=[], giornalieri=[]))
    assert all(n["topic_key"] != "upload_ricavi_failed" for n in out)


def test_upload_ricavi_assenti_segnalati_al_cliente_mappato(stub, prezzi):
    prezzi()
    vecchio = (date.today() - timedelta(days=10)).isoformat()
    sb = _FakeSB(mappa_ricavi=[{"ristorante_id": RID}],
                 giornalieri=[{"ristorante_id": RID, "data": vecchio}])
    out = fw._briefing_raccogli_notifiche(USER, RID, sb)
    n = [x for x in out if x["topic_key"] == "upload_ricavi_failed"]
    assert len(n) == 1
    assert n[0]["payload"]["giorni_senza"] == 10


def test_upload_ricavi_recenti_non_segnalati(stub, prezzi):
    prezzi()
    ieri = (date.today() - timedelta(days=1)).isoformat()
    sb = _FakeSB(mappa_ricavi=[{"ristorante_id": RID}],
                 giornalieri=[{"ristorante_id": RID, "data": ieri}])
    out = fw._briefing_raccogli_notifiche(USER, RID, sb)
    assert all(n["topic_key"] != "upload_ricavi_failed" for n in out)


def test_finestra_ricavi_tollera_i_giorni_di_chiusura(stub, prezzi):
    """Finestra = giorni di chiusura + 1: una sede chiusa 2 giorni a settimana non
    deve ricevere un falso allarme nel suo giorno di chiusura."""
    prezzi()
    tre_giorni_fa = (date.today() - timedelta(days=3)).isoformat()
    sb_kwargs = dict(mappa_ricavi=[{"ristorante_id": RID}],
                     giornalieri=[{"ristorante_id": RID, "data": tre_giorni_fa}])

    stub("_get_assistant_preferences",
         lambda *a, **k: {"topics_disabled": [], "giorni_chiusura_settimanali": 3})
    out_tollerante = fw._briefing_raccogli_notifiche(USER, RID, _FakeSB(**sb_kwargs))
    assert all(n["topic_key"] != "upload_ricavi_failed" for n in out_tollerante)

    stub("_get_assistant_preferences",
         lambda *a, **k: {"topics_disabled": [], "giorni_chiusura_settimanali": 0})
    out_stretto = fw._briefing_raccogli_notifiche(USER, RID, _FakeSB(**sb_kwargs))
    assert any(n["topic_key"] == "upload_ricavi_failed" for n in out_stretto)


# ─────────────────────────────────────────────────────────────────────────────
# Aperture, ordine, fail-open
# ─────────────────────────────────────────────────────────────────────────────

def test_ordine_delle_aperture_in_testa(stub, prezzi):
    """Tre `insert(0, ...)` in sequenza (buona notizia, rientro, onboarding):
    l'ultimo inserito e' il primo della lista."""
    prezzi()
    stub("_briefing_buona_notizia", lambda *a, **k: _notifica("buona_notizia"))
    stub("_briefing_rientro_assenza", lambda *a, **k: _notifica("rientro_assenza"))
    stub("_briefing_onboarding", lambda *a, **k: _notifica("onboarding"))
    out = fw._briefing_raccogli_notifiche(USER, RID, _FakeSB(notifiche=[_notifica("credit_note")]))
    assert [n["topic_key"] for n in out[:3]] == ["onboarding", "rientro_assenza", "buona_notizia"]


def test_last_seen_aggiornato_dopo_la_lettura_del_rientro(stub, prezzi, monkeypatch):
    """L'ordine e' essenziale: aggiornare `last_briefing_seen` PRIMA di leggere il
    rientro azzererebbe per sempre il contatore di assenza."""
    prezzi()
    ordine = []
    stub("_briefing_rientro_assenza", lambda *a, **k: ordine.append("letto") or None)
    monkeypatch.setattr(fw, "_briefing_aggiorna_last_seen",
                        lambda *a, **k: ordine.append("scritto"))
    fw._briefing_raccogli_notifiche(USER, RID, _FakeSB())
    assert ordine == ["letto", "scritto"]


def test_last_seen_aggiornato_anche_senza_rientro(stub, prezzi, monkeypatch):
    prezzi()
    scritture = []
    monkeypatch.setattr(fw, "_briefing_aggiorna_last_seen",
                        lambda *a, **k: scritture.append(1))
    fw._briefing_raccogli_notifiche(USER, RID, _FakeSB())
    assert scritture == [1]


def test_preferenze_in_errore_non_spengono_nulla(stub, prezzi):
    """Fail-open: se la lettura delle preferenze fallisce non si spegne nulla —
    meglio un avviso di troppo che un cliente all'oscuro."""
    chiamate = prezzi({"count": 1, "top": {"nome": "X", "aumento_pct": 9,
                                           "impatto_mese": 10, "tipo": "prodotto"}})

    def _rotto(*a, **k):
        raise RuntimeError("preferenze giu'")

    stub("_get_assistant_preferences", _rotto)
    out = fw._briefing_raccogli_notifiche(USER, RID, _FakeSB())
    assert chiamate == [True]
    assert any(n["topic_key"] == "price_alert" for n in out)


@pytest.mark.parametrize("helper", sorted(_STUB_NEUTRI))
def test_ogni_sezione_e_best_effort(stub, prezzi, helper):
    """Ogni sotto-helper e' avvolto nel suo try/except: se uno esplode, il
    briefing esce comunque con gli altri segnali. Nessuno di questi rami era
    coperto prima."""
    prezzi()

    def _rotto(*a, **k):
        raise RuntimeError(f"{helper} giu'")

    stub(helper, _rotto)
    out = fw._briefing_raccogli_notifiche(USER, RID, _FakeSB(notifiche=[_notifica("credit_note")]))
    assert any(n["topic_key"] == "credit_note" for n in out)


def test_senza_ristorante_id_niente_segnali_di_sede(stub, prezzi):
    """Path minimo: senza sede attiva restano solo le notifiche dell'utente."""
    chiamate = prezzi()
    visti = []
    stub("_briefing_fatture_mancanti", lambda *a, **k: visti.append(1) or None)
    out = fw._briefing_raccogli_notifiche(USER, None, _FakeSB(notifiche=[_notifica("credit_note")]))
    assert chiamate == [] and visti == []
    assert [n["topic_key"] for n in out] == ["credit_note"]


# ─────────────────────────────────────────────────────────────────────────────
# _scontrino_medio_significativo
# ─────────────────────────────────────────────────────────────────────────────

def _giorno(d, coperti, i10=0.0, i22=0.0, altri=0.0):
    return {"ristorante_id": RID, "data": d, "coperti": coperti,
            "fatturato_iva10": i10, "fatturato_iva22": i22, "altri_ricavi_noiva": altri}


def _baseline(n=6, netto_per_giorno=200.0, coperti=10, mese="2026-08"):
    """n giorni a 20 euro/coperto (netto/coperti), tutti nel mese in corso."""
    return [_giorno(f"{mese}-{i + 1:02d}", coperti, altri=netto_per_giorno) for i in range(n)]


IERI = date(2026, 8, 9)


def test_scostamento_sopra_soglia_ritorna_alert():
    """Baseline 20 euro/coperto, ieri 30: +50%, ben oltre il 10% di soglia."""
    sb = _FakeSB(giornalieri=_baseline())
    out = fw._scontrino_medio_significativo(RID, sb, IERI, 10, 300.0)
    assert out == {"scontrino_medio": 30.0, "scontrino_delta_pct": 50, "scontrino_su": True}


def test_scostamento_negativo_segnalato_in_giu():
    sb = _FakeSB(giornalieri=_baseline())
    out = fw._scontrino_medio_significativo(RID, sb, IERI, 10, 150.0)
    assert out["scontrino_su"] is False
    assert out["scontrino_delta_pct"] == 25


def test_scostamento_sotto_soglia_ritorna_none():
    """Zero rumore: uno scarto del 5% non e' una notizia."""
    sb = _FakeSB(giornalieri=_baseline())
    assert fw._scontrino_medio_significativo(RID, sb, IERI, 10, 210.0) is None


def test_ieri_escluso_dalla_baseline():
    """Se ieri entrasse nella propria baseline, si annullerebbe da solo.

    Qui la baseline vera e' 20 euro/coperto (+50% -> alert). Includendo ieri
    (40 euro/coperto su 6 giorni) la media salirebbe e il delta scenderebbe
    sotto soglia: il test cade se il `continue` viene rimosso.
    """
    giorni = _baseline(n=5) + [_giorno(IERI.isoformat(), 10, altri=400.0)]
    out = fw._scontrino_medio_significativo(RID, _FakeSB(giornalieri=giorni), IERI, 10, 400.0)
    assert out is not None
    assert out["scontrino_medio"] == 40.0
    assert out["scontrino_delta_pct"] == 100


def test_baseline_troppo_corta_ritorna_none():
    """Sotto `min_giorni_baseline` il dato non e' affidabile."""
    from config.constants import COPERTI_ALERT
    minimo = int(COPERTI_ALERT["min_giorni_baseline"])
    corta = _FakeSB(giornalieri=_baseline(n=minimo - 1))
    giusta = _FakeSB(giornalieri=_baseline(n=minimo))
    assert fw._scontrino_medio_significativo(RID, corta, IERI, 10, 300.0) is None
    assert fw._scontrino_medio_significativo(RID, giusta, IERI, 10, 300.0) is not None


def test_giorni_senza_coperti_esclusi_dalla_baseline():
    """Righe con coperti nulli o zero non hanno uno scontrino medio: se
    entrassero, la baseline sarebbe calcolata su meno giorni di quelli attesi."""
    giorni = _baseline(n=4) + [
        _giorno("2026-08-05", None, altri=500.0),
        _giorno("2026-08-06", 0, altri=500.0),
    ]
    out = fw._scontrino_medio_significativo(RID, _FakeSB(giornalieri=giorni), IERI, 10, 300.0)
    assert out is not None and out["scontrino_delta_pct"] == 50


def test_giorni_con_netto_zero_esclusi():
    giorni = _baseline(n=4) + [_giorno("2026-08-05", 10, altri=0.0)]
    out = fw._scontrino_medio_significativo(RID, _FakeSB(giornalieri=giorni), IERI, 10, 300.0)
    assert out is not None and out["scontrino_delta_pct"] == 50


def test_baseline_limitata_al_mese_in_corso():
    """I giorni del mese precedente non entrano: il confronto e' col mese in corso."""
    giorni = _baseline(n=4) + [_giorno("2026-07-15", 10, altri=2000.0)]
    out = fw._scontrino_medio_significativo(RID, _FakeSB(giornalieri=giorni), IERI, 10, 300.0)
    assert out is not None and out["scontrino_delta_pct"] == 50


@pytest.mark.parametrize("coperti", [None, 0, -1, "abc", ""])
def test_coperti_ieri_invalidi_ritornano_none(coperti):
    sb = _FakeSB(giornalieri=_baseline())
    assert fw._scontrino_medio_significativo(RID, sb, IERI, coperti, 300.0) is None


@pytest.mark.parametrize("netto", [0.0, -50.0])
def test_netto_ieri_non_positivo_ritorna_none(netto):
    sb = _FakeSB(giornalieri=_baseline())
    assert fw._scontrino_medio_significativo(RID, sb, IERI, 10, netto) is None


def test_giorni_con_netto_negativo_non_entrano_nella_baseline():
    """Un giorno a netto negativo (storni/note di credito) e' scartato dal filtro
    `n > 0`, quindi non abbassa la media.

    Nota: la guardia `base <= 0` subito a valle (riga 4650) e' di conseguenza
    IRRAGGIUNGIBILE — `valori` contiene solo positivi. Resta scoperta di
    proposito: e' difesa in profondita', non un ramo da esercitare con dati
    inventati che il filtro precedente non lascerebbe mai passare.
    """
    giorni = _baseline(n=6) + [_giorno("2026-08-07", 10, altri=-5000.0)]
    out = fw._scontrino_medio_significativo(RID, _FakeSB(giornalieri=giorni), IERI, 10, 300.0)
    assert out is not None
    assert out["scontrino_delta_pct"] == 50


def test_query_in_errore_ritorna_none():
    class _Rotto:
        def table(self, name):
            raise RuntimeError("db giu'")

    assert fw._scontrino_medio_significativo(RID, _Rotto(), IERI, 10, 300.0) is None


def test_netto_calcolato_scorporando_l_iva():
    """La baseline usa il netto (10% e 22% scorporati), non il lordo: con i
    divisori scambiati il valore atteso non torna."""
    giorni = [_giorno(f"2026-08-{i + 1:02d}", 10, i10=1100.0, i22=1220.0) for i in range(5)]
    # netto per giorno = 1100/1.10 + 1220/1.22 = 1000 + 1000 = 2000 -> 200/coperto
    out = fw._scontrino_medio_significativo(RID, _FakeSB(giornalieri=giorni), IERI, 10, 3000.0)
    assert out is not None and out["scontrino_medio"] == 300.0
    assert out["scontrino_delta_pct"] == 50


def test_soglia_letta_da_config_constants(monkeypatch):
    """La soglia non e' hardcoded: alzandola, un delta che prima era alert tace."""
    from config import constants
    sb = _FakeSB(giornalieri=_baseline())
    assert fw._scontrino_medio_significativo(RID, sb, IERI, 10, 300.0) is not None
    monkeypatch.setitem(constants.COPERTI_ALERT, "scontrino_medio_delta_pct", 0.90)
    assert fw._scontrino_medio_significativo(RID, _FakeSB(giornalieri=_baseline()),
                                             IERI, 10, 300.0) is None
