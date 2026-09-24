"""Le osservazioni da consulente del PV (fase 4) arrivano anche in catena.

Fase 6 del piano consulente (24/09/2026). Il cliente piu' attivo e' una catena
e vive su `/catena`, dove fino a oggi non arrivava nessuno dei contenuti da
consulente. Nessuna regola nuova: calcolo e frase sono quelli del PV
(`_briefing_osservazioni` nel worker, `_osservazione_frase` nel briefing).
Qui si prova cio' che la catena AGGIUNGE:
- una sede per riga, col suo nome, ordinate per tema e poi per nome;
- i tre modi di spegnerle (configuratore della catena, `pv_esclusi`,
  configuratore DEL PV) e l'esclusione dei negozi dal food cost;
- che non sono segnali: lista a parte, fuori dal conteggio che spegne il
  «tutto in ordine»;
- che un calcolo fallito toglie solo se stesso (best-effort come nel PV), e che
  fuori dai giorni in cui possono parlare non si fa nessuna query per sede.

I calcoli girano sul codice vero del worker; si finge solo il database.
"""
from datetime import date, timedelta
from typing import Any, Dict, List

import pytest

import services.fastapi_worker as fw
from services.routers import gruppo

MARTEDI = date(2026, 9, 22)          # fuori dalla finestra del food cost
VENERDI_FINESTRA = date(2026, 10, 2)  # finestra del food cost (agosto), non martedi'
NOMI = {"a": "PV Alfa", "b": "PV Beta"}


class _Resp:
    def __init__(self, data):
        self.data = data
        self.count = len(data)


class _Query:
    def __init__(self, sb, nome):
        self._sb, self._nome, self._filtri = sb, nome, {}

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filtri[col] = val
        return self

    def gte(self, *_a):
        return self

    def lte(self, *_a):
        return self

    def in_(self, *_a):
        return self

    def limit(self, *_a):
        return self

    def order(self, *_a, **_k):
        return self

    def upsert(self, payload, **_k):
        self._sb.upsert.append(payload)
        return self

    def execute(self):
        if self._nome == "ricavi_giornalieri":
            return _Resp(self._sb.ricavi.get(self._filtri.get("ristorante_id"), []))
        return _Resp([])


class _FakeSB:
    def __init__(self, ricavi=None):
        self.ricavi: Dict[str, List[Dict[str, Any]]] = ricavi or {}
        self.upsert: List[Dict[str, Any]] = []

    def table(self, nome):
        return _Query(self, nome)


def _ricavi_in_crescita(giorno_martedi: date, prima=1000.0, dopo=1200.0):
    """8 settimane di incasso: le 4 prima a `prima`, le ultime 4 a `dopo`."""
    fine = giorno_martedi - timedelta(days=giorno_martedi.weekday() + 1)
    righe = []
    for i in range(56):
        g = fine - timedelta(days=i)
        righe.append({"data": g.isoformat(), "fatturato_iva10": dopo if i < 28 else prima,
                      "fatturato_iva22": 0, "altri_ricavi_noiva": 0, "coperti": 0})
    return righe


@pytest.fixture
def ambiente(monkeypatch):
    """Nessuna preferenza spenta nel PV, settore ristorazione, giorno impostabile."""
    stato = {"spenti_pv": {}, "settore": "ristorazione"}
    monkeypatch.setattr(
        fw, "_get_assistant_preferences",
        lambda rid, sb: {"topics_disabled": list(stato["spenti_pv"].get(rid, []))},
    )
    monkeypatch.setattr("services.settore_service.settore_sede",
                        lambda rid, sb: stato["settore"])

    def giorno(g):
        monkeypatch.setattr(fw, "_oggi_rome", lambda: g)

    stato["giorno"] = giorno
    return stato


def _calcola(sb, **kw):
    return gruppo._calcola_osservazioni(sb, ["a", "b"], NOMI, user_id="u1", **kw)


# ── Andamento incasso: il calcolo vero del PV, una sede per riga ────────────

def test_martedi_la_sede_che_si_e_mossa_ha_la_sua_riga(ambiente):
    ambiente["giorno"](MARTEDI)
    sb = _FakeSB({"a": _ricavi_in_crescita(MARTEDI)})
    oss = _calcola(sb)
    assert [(o["tipo"], o["ristorante_id"], o["pv_nome"]) for o in oss] == [
        ("andamento_incasso", "a", "PV Alfa"),
    ], "la sede b non ha ricavi: nessuna riga"
    testo = oss[0]["testo"]
    assert "il 20% in più" in testo and "€ 33.600" in testo and "€ 28.000" in testo, testo
    assert oss[0]["severity"] == "success"
    assert oss[0]["cta_page"] == "/margini"


def test_fuori_dal_martedi_tace(ambiente):
    ambiente["giorno"](MARTEDI + timedelta(days=1))
    sb = _FakeSB({"a": _ricavi_in_crescita(MARTEDI)})
    assert _calcola(sb) == []


def test_spenta_nel_configuratore_della_catena_tace(ambiente):
    ambiente["giorno"](MARTEDI)
    sb = _FakeSB({"a": _ricavi_in_crescita(MARTEDI)})
    assert _calcola(sb, segnali_off={"andamento_incasso"}) == []


def test_pv_escluso_dalla_catena_tace(ambiente):
    ambiente["giorno"](MARTEDI)
    sb = _FakeSB({"a": _ricavi_in_crescita(MARTEDI), "b": _ricavi_in_crescita(MARTEDI)})
    oss = _calcola(sb, pv_esclusi={"a"})
    assert [o["ristorante_id"] for o in oss] == ["b"]


def test_spenta_nel_configuratore_del_pv_tace_solo_per_quella_sede(ambiente):
    """Il cliente ha spento l'osservazione su una sede: la catena non gliela
    ripete, ma l'altra sede continua a parlare."""
    ambiente["giorno"](MARTEDI)
    ambiente["spenti_pv"] = {"a": ["andamento_incasso"]}
    sb = _FakeSB({"a": _ricavi_in_crescita(MARTEDI), "b": _ricavi_in_crescita(MARTEDI)})
    oss = _calcola(sb)
    assert [o["ristorante_id"] for o in oss] == ["b"]


def test_preferenze_del_pv_illeggibili_non_spengono_nulla(ambiente, monkeypatch):
    """Fail-open come il PV: senza preferenze non si spegne niente."""
    ambiente["giorno"](MARTEDI)

    def _rotta(rid, sb):
        raise RuntimeError("preferenze giu'")

    monkeypatch.setattr(fw, "_get_assistant_preferences", _rotta)
    sb = _FakeSB({"a": _ricavi_in_crescita(MARTEDI)})
    oss = _calcola(sb)
    assert [o["ristorante_id"] for o in oss] == ["a"]


# ── Food cost alto: finestra, negozi, ordine ────────────────────────────────

@pytest.fixture
def food_cost_alto(monkeypatch):
    """Agosto a food cost 45,8% su 10.000 € di netto, settembre gia' arrivato:
    i dati che `_briefing_food_cost_alto` legge, finti a livello di sorgente."""
    monkeypatch.setattr("services.margine_service.carica_margini_anno", lambda *a, **k: {})
    monkeypatch.setattr(fw, "_merge_override_mensile", lambda m, *a, **k: m)
    monkeypatch.setattr("services.margine_service.calcola_costi_automatici_per_anno_sql",
                        lambda *a, **k: ({8: 4580.0, 9: 100.0}, {}))
    monkeypatch.setattr(fw, "_kpi_periodo",
                        lambda *a, **k: {"food_cost_pct": 45.8, "netto": 10000.0})


def test_nella_finestra_il_food_cost_alto_ha_la_sua_riga(ambiente, food_cost_alto):
    ambiente["giorno"](VENERDI_FINESTRA)
    oss = _calcola(_FakeSB())
    assert [(o["tipo"], o["pv_nome"]) for o in oss] == [
        ("food_cost_alto", "PV Alfa"), ("food_cost_alto", "PV Beta"),
    ]
    assert "Ad agosto il food cost è stato del 45,8%" in oss[0]["testo"], oss[0]["testo"]
    assert "soglia critica del 38%" in oss[0]["testo"]


def test_ai_negozi_il_food_cost_non_si_dice(ambiente, food_cost_alto):
    ambiente["giorno"](VENERDI_FINESTRA)
    ambiente["settore"] = "retail"
    assert _calcola(_FakeSB()) == []


def test_food_cost_spento_in_catena_tace(ambiente, food_cost_alto):
    ambiente["giorno"](VENERDI_FINESTRA)
    assert _calcola(_FakeSB(), segnali_off={"food_cost_alto"}) == []


@pytest.mark.parametrize("off, atteso", [
    ({"food_cost_alto"}, ["andamento_incasso"]),
    ({"andamento_incasso"}, ["food_cost_alto"]),
])
def test_martedi_in_finestra_spento_in_catena_tace_solo_lui(ambiente, food_cost_alto, off, atteso):
    """Nel giorno in cui possono parlare entrambe, l'uscita anticipata non
    scatta: e' qui che lo spegnimento dal configuratore della catena deve
    arrivare fino al calcolo per sede. Gli altri test sullo spegnimento
    passavano gia' per l'uscita anticipata (review del 24/09, secondo giro)."""
    g = date(2026, 10, 6)
    ambiente["giorno"](g)
    sb = _FakeSB({"a": _ricavi_in_crescita(g)})
    oss = gruppo._calcola_osservazioni(sb, ["a"], NOMI, segnali_off=off, user_id="u1")
    assert [o["tipo"] for o in oss] == atteso


def test_ordine_prima_il_tema_poi_il_nome(ambiente, food_cost_alto, monkeypatch):
    """Un martedi' dentro la finestra parlano entrambe: prima l'incasso di tutte
    le sedi, poi il food cost, e dentro il tema per nome della sede."""
    martedi_in_finestra = date(2026, 10, 6)
    assert martedi_in_finestra.weekday() == 1
    ambiente["giorno"](martedi_in_finestra)
    # primi giorni di ottobre: il mese detto e' agosto, quello dopo settembre
    sb = _FakeSB({"b": _ricavi_in_crescita(martedi_in_finestra),
                  "a": _ricavi_in_crescita(martedi_in_finestra)})
    nomi = {"a": "Zeta", "b": "Alfa"}
    oss = gruppo._calcola_osservazioni(sb, ["a", "b"], nomi, user_id="u1")
    assert [(o["tipo"], o["pv_nome"]) for o in oss] == [
        ("andamento_incasso", "Alfa"), ("andamento_incasso", "Zeta"),
        ("food_cost_alto", "Alfa"), ("food_cost_alto", "Zeta"),
    ]


# ── Errore: best-effort, come nel PV ────────────────────────────────────────
#
# Una prima stesura marcava lo snapshot «degradato» (niente cache) quando
# un'osservazione falliva. La review del 24/09 ha mostrato il costo: un guasto
# persistente su una sede toglieva la cache a tutti i segnali e spegneva il
# «tutto in ordine» per l'intera giornata. Ora un'osservazione che fallisce
# manca, e basta — come nel briefing del PV.

def test_un_calcolo_fallito_toglie_solo_se_stesso(ambiente, monkeypatch):
    ambiente["giorno"](date(2026, 10, 6))   # martedi' dentro la finestra

    def _rotto(*a, **k):
        raise RuntimeError("DB giu'")

    monkeypatch.setattr(fw, "_briefing_andamento_incasso", _rotto)
    monkeypatch.setattr(fw, "_briefing_food_cost_alto",
                        lambda uid, rid, sb, oggi: {"topic_key": "food_cost_alto",
                                                    "severity": "warning",
                                                    "action_page": "/margini",
                                                    "payload": {"mese": "agosto",
                                                                "food_cost_pct": 40.0}})
    oss = gruppo._calcola_osservazioni(_FakeSB(), ["a"], NOMI, user_id="u1")
    assert [o["tipo"] for o in oss] == ["food_cost_alto"]


def test_una_sede_che_esplode_non_ferma_le_altre(ambiente, monkeypatch):
    """Il guasto fuori dai due calcoli resta della sua sede: le altre parlano."""
    ambiente["giorno"](MARTEDI)
    vero = fw._briefing_osservazioni

    def _esplode_su_a(user_id, rid, sb, spenti):
        if rid == "a":
            raise RuntimeError("guasto")
        return vero(user_id, rid, sb, spenti)

    monkeypatch.setattr(fw, "_briefing_osservazioni", _esplode_su_a)
    sb = _FakeSB({"a": _ricavi_in_crescita(MARTEDI), "b": _ricavi_in_crescita(MARTEDI)})
    assert [o["ristorante_id"] for o in _calcola(sb)] == ["b"]


def test_senza_utente_o_tutte_spente_non_calcola(ambiente, monkeypatch):
    ambiente["giorno"](MARTEDI)
    chiamate = []
    monkeypatch.setattr(fw, "_briefing_osservazioni",
                        lambda *a, **k: chiamate.append(1) or [])
    sb = _FakeSB()
    assert gruppo._calcola_osservazioni(sb, ["a"], NOMI, user_id=None) == []
    assert _calcola(sb, segnali_off=set(gruppo._OSSERVAZIONI_CATENA)) == []
    assert chiamate == [], "spente tutte, non si fanno le query per sede"


def _conta_letture(monkeypatch):
    letture = []
    monkeypatch.setattr(fw, "_get_assistant_preferences",
                        lambda rid, sb: letture.append(rid) or {"topics_disabled": []})
    return letture


@pytest.mark.parametrize("giorno, off, parla", [
    (date(2026, 9, 23), set(), False),                       # mercoledi', fuori finestra
    (MARTEDI, set(), True),                                  # martedi'
    (MARTEDI, {"andamento_incasso"}, False),                 # martedi' ma incasso spento
    (VENERDI_FINESTRA, set(), True),                         # finestra food cost
    (VENERDI_FINESTRA, {"food_cost_alto"}, False),           # finestra ma food cost spento
])
def test_fuori_dai_giorni_utili_nessuna_query_per_sede(ambiente, monkeypatch, giorno, off, parla):
    """La prima apertura del giorno legge le preferenze di ogni sede solo se
    oggi almeno un'osservazione attiva puo' parlare."""
    ambiente["giorno"](giorno)
    letture = _conta_letture(monkeypatch)
    monkeypatch.setattr(fw, "_briefing_osservazioni", lambda *a, **k: [])
    _calcola(_FakeSB(), segnali_off=off)
    assert (letture == ["a", "b"]) is parla, letture


# ── Endpoint: lista a parte, cache, conteggio ───────────────────────────────

OSS = {"tipo": "andamento_incasso", "severity": "success", "ristorante_id": "a",
       "pv_nome": "PV Alfa", "testo": "📊 Nelle ultime 4 settimane…", "cta_page": "/margini"}


def _endpoint(monkeypatch, osservazioni, segnali=None, snapshot=None, config=(set(), set())):
    sb = _FakeSB()
    if snapshot is not None:
        sb.table = lambda nome: (_QueryConSnapshot(sb, snapshot) if nome == "gruppo_segnali_state"
                                 else _Query(sb, nome))
    monkeypatch.setattr(gruppo, "_resolve_gruppo",
                        lambda auth: (sb, "u1", [{"id": "a"}], "G", {"a": "PV Alfa"}, ["a"]))
    monkeypatch.setattr(gruppo, "_get_gruppo_config", lambda sb, uid: config)
    monkeypatch.setattr(gruppo, "_calcola_segnali", lambda *a, **k: list(segnali or []))
    argomenti = []

    def _oss(*a, **k):
        argomenti.append((a, k))
        if isinstance(osservazioni, Exception):
            raise osservazioni
        return [dict(o) for o in osservazioni]

    monkeypatch.setattr(gruppo, "_calcola_osservazioni", _oss)
    sb.argomenti = argomenti
    return sb, gruppo.gruppo_segnali(authorization="Bearer t")


class _QueryConSnapshot(_Query):
    def __init__(self, sb, snapshot):
        super().__init__(sb, "gruppo_segnali_state")
        self._snapshot = snapshot

    def execute(self):
        return _Resp([{"snapshot": self._snapshot}])


def test_endpoint_le_osservazioni_sono_una_lista_a_parte_e_vanno_in_cache(monkeypatch):
    sb, resp = _endpoint(monkeypatch, [OSS])
    assert resp.segnali == []
    assert [o.model_dump() for o in resp.osservazioni] == [OSS]
    assert len(sb.upsert) == 1
    snap = sb.upsert[0]["snapshot"]
    assert snap["osservazioni"] == [OSS] and snap["segnali"] == []


def test_endpoint_un_errore_delle_osservazioni_non_rompe_la_card(monkeypatch):
    """Card dei segnali e tool della chat leggono lo stesso endpoint: un errore
    imprevisto delle osservazioni le toglie, non toglie i segnali."""
    seg = {"tipo": "ricavi_mancanti", "severity": "warning", "ristorante_id": "a",
           "pv_nome": "PV Alfa", "testo": "Nessun ricavo", "cta_page": "/margini"}
    sb, resp = _endpoint(monkeypatch, RuntimeError("imprevisto"), segnali=[seg])
    assert [s.tipo for s in resp.segnali] == ["ricavi_mancanti"]
    assert resp.osservazioni == []
    assert len(sb.upsert) == 1, "i segnali sani vanno in cache come sempre"


def test_endpoint_passa_alle_osservazioni_la_config_della_catena(monkeypatch):
    """Il configuratore della catena e le sedi escluse devono ARRIVARE alle
    osservazioni: un mock che ignora gli argomenti lasciava vivo un endpoint
    che le chiamava senza config o senza utente (due mutanti della review)."""
    sb, _ = _endpoint(monkeypatch, [], config=({"food_cost_alto"}, {"b"}))
    (a, k), = sb.argomenti
    assert a == (sb, ["a"], {"a": "PV Alfa"}, {"food_cost_alto"}, {"b"}, "u1"), (a, k)


def test_endpoint_dalla_cache_restituisce_le_osservazioni(monkeypatch):
    snap = {"segnali": [], "osservazioni": [OSS], "generated_at": "x",
            "code_version": gruppo._SEGNALI_CODE_VERSION}
    sb, resp = _endpoint(monkeypatch, [], snapshot=snap)
    assert [o.model_dump() for o in resp.osservazioni] == [OSS]
    assert sb.upsert == [], "servito dalla cache, niente ricalcolo"


def test_le_osservazioni_non_contano_come_segnali_aperti():
    """Il conteggio alimenta il «tutto in ordine» della narrativa: un fatto
    sull'incasso non e' una segnalazione aperta (come nel PV)."""
    snap = {"segnali": [], "osservazioni": [OSS, dict(OSS, ristorante_id="b")],
            "generated_at": "x", "code_version": gruppo._SEGNALI_CODE_VERSION}
    sb = _FakeSB()
    sb.table = lambda nome: _QueryConSnapshot(sb, snap)
    n, _sev = gruppo._conta_segnali_cache(sb, "u1")
    assert n == 0


def test_le_due_chiavi_nuove_sono_configurabili():
    """Senza la voce nel catalogo il salvataggio della config le scarterebbe
    (`k in _SEGNALI_KEYS`) e il cliente non potrebbe spegnerle."""
    assert set(gruppo._OSSERVAZIONI_CATENA) <= gruppo._SEGNALI_KEYS


def test_la_versione_dei_segnali_e_stata_alzata_per_la_fase_6():
    """Lo snapshot v2 (in produzione fino al deploy della fase 6) non ha le
    osservazioni e chiede il personale il 1° del mese: servito dalla cache,
    la catena resterebbe quella di prima fino a mezzanotte. Gli altri test
    leggono la costante da entrambi i lati, quindi un bump dimenticato li
    lascia verdi: qui si ancora il valore, come per `_BRIEFING_CODE_VERSION`."""
    assert gruppo._SEGNALI_CODE_VERSION >= 3
