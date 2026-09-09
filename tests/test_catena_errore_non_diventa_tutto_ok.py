"""In catena un errore NON puo' diventare "tutto a posto".

Regola di prodotto applicata ovunque nel PV: *dato assente != via libera*. La
catena la DICHIARAVA (il commento di card-segnali.tsx: "Un errore qui NON puo'
diventare 'tutto sotto controllo'") e la violava in sei punti, tutti con lo
stesso schema `except Exception:` -> valore che significa "va tutto bene":

  2a `gruppo_overview`      completezza = {}  -> pv_da_completare 0 -> "completo"
  2b dialog margini         incompleti_set = set() -> PV inaffidabili confrontati
  2c dialog spesa/coperti   idem
  2d `_calcola_segnali`     `pass` -> il segnale sparisce -> "Tutto sotto controllo"
  2e `_salute_componenti_raw` return [] -> ogni PV a indice 0 = falso ROSSO
  2f `_conta_segnali_cache` (0, "info") su cache ASSENTE -> "tutto in ordine"

Il 2f non e' un caso di errore ma il caso NORMALE: la cache la scrive
/api/gruppo/segnali, che il client chiama DOPO il render della pagina. Quindi al
primo caricamento di ogni giornata il briefing scriveva "Nessuna segnalazione
aperta: tutto in ordine." mentre la card sotto stava ancora calcolando e poteva
poi mostrare avvisi.

Questi test misurano il COMPORTAMENTO: un assert sul sorgente sopravviverebbe
alla rimessa dell'except.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from services.routers import gruppo  # noqa: E402

RID = "sede-1"
RID2 = "sede-2"


class _RpcRotta:
    """Client Supabase la cui RPC solleva: simula la RPC componenti non disponibile."""

    def rpc(self, *a, **k):
        raise RuntimeError("RPC gruppo_salute_componenti non disponibile")

    def table(self, *a, **k):
        raise RuntimeError("tabella non disponibile")


# ── 2e: la RPC che fallisce non diventa "ogni sede a zero" ────────────────────

def test_componenti_raw_non_confonde_nessuna_riga_con_non_lo_so():
    """None (non lo so) != [] (nessuna riga). Prima tornava [] su errore."""
    assert gruppo._salute_componenti_raw(_RpcRotta(), [RID]) is None


def test_indici_batch_non_inventa_zero_quando_la_rpc_fallisce(monkeypatch):
    """Falso ROSSO: con [] ogni sede finiva a indice 0, cioe' la card affermava
    un dato che non aveva — mentre nello stesso payload la completezza diceva
    "completo"."""
    monkeypatch.setattr(gruppo, "_voci_spente_per_sede", lambda sb, ids: {r: set() for r in ids})
    assert gruppo._salute_indici_batch(_RpcRotta(), [RID, RID2]) is None


def test_completezza_non_inventa_tutti_completi_quando_la_rpc_fallisce():
    """Il dict vuoto significa "nessun PV incompleto": la risposta piu' ottimista
    possibile, data proprio quando la lettura e' fallita."""
    assert gruppo._completezza_dati_pv(_RpcRotta(), [RID, RID2]) is None


def test_completezza_dict_vuoto_resta_un_dato_valido():
    """Contro-prova: con righe complete il risultato e' {} — che NON e' None.
    Se il fix confondesse i due casi, la catena direbbe "non lo so" sempre."""
    rows = [{"ristorante_id": RID, "n_fatture": 10, "n_needs_review": 0,
             "netto": 1000.0, "personale": 500.0}]
    assert gruppo._completezza_dati_pv(None, [RID], rows=rows) == {}


# ── 2f: cache assente != nessun segnale ──────────────────────────────────────

class _CacheVuota:
    """Nessuna riga per oggi: e' lo stato NORMALE al primo caricamento del giorno."""

    class _Q:
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self): return type("R", (), {"data": []})()

    def table(self, *a, **k): return self._Q()


class _CacheRotta:
    def table(self, *a, **k):
        raise RuntimeError("lettura cache fallita")


def test_cache_segnali_assente_non_significa_zero_segnali():
    n, _ = _conta = gruppo._conta_segnali_cache(_CacheVuota(), "u1")
    assert n is None, "cache assente deve dire 'non lo so', non 'zero segnali'"


def test_cache_segnali_illeggibile_non_significa_zero_segnali():
    n, _ = gruppo._conta_segnali_cache(_CacheRotta(), "u1")
    assert n is None


# ── Il gate tutto_ok ─────────────────────────────────────────────────────────

def _briefing(**kw):
    base = dict(
        nome_gruppo="G", ranking=[], salute_indice=90, salute_colore="verde",
        n_segnali=0, sev_max="info", salute_pv=[], incompleti_ids=set(),
        n_fatture_da_collocare=0, completezza_nota=True,
    )
    base.update(kw)
    return gruppo._build_briefing(**base)


TUTTO_OK = "tutto in ordine"


def test_tutto_ok_si_accende_quando_si_sa_davvero_che_va_bene():
    """Contro-prova: senza questa, i test sotto passerebbero anche se il gate
    fosse spento SEMPRE (fix che rompe la feature invece di ripararla)."""
    assert TUTTO_OK in _briefing().narrativa


def test_tutto_ok_spento_se_i_segnali_non_sono_noti():
    """Il falso verde di ogni mattina: cache non ancora generata."""
    assert TUTTO_OK not in _briefing(n_segnali=None).narrativa


def test_tutto_ok_spento_se_il_colore_salute_non_e_noto():
    """`salute_colore != "rosso"` era VERO per qualunque valore diverso da
    "rosso" — "grigio" (non lo so) compreso."""
    assert TUTTO_OK not in _briefing(salute_colore="grigio").narrativa


def test_tutto_ok_spento_se_la_completezza_non_e_nota():
    """n_incompleti == 0 non significa "nessuna sede incompleta" quando la
    lettura e' fallita."""
    assert TUTTO_OK not in _briefing(completezza_nota=False).narrativa


# ── 2d: il segnale che sparisce ──────────────────────────────────────────────

def test_segnale_dati_mancanti_parla_anche_quando_il_calcolo_fallisce(monkeypatch):
    """Prima l'except era `pass`: il segnale spariva e la card mostrava
    "Tutto sotto controllo" con la spunta verde — esattamente cio' che il
    commento di card-segnali.tsx dichiara di voler impedire."""
    monkeypatch.setattr(
        gruppo, "_completezza_dati_pv",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("giu'")),
    )
    monkeypatch.setattr(gruppo, "_costi_mese_per_sede", lambda *a, **k: None)
    # Gli altri segnali non devono interferire: si tengono spenti.
    segnali = gruppo._calcola_segnali(
        None, [RID], {RID: "Sede 1"},
        segnali_off={"margine_calo", "prezzi_sopra", "ricavi_mancanti"},
        user_id="u1",
    )
    assert segnali, "un errore non puo' produrre zero segnali: sarebbe un falso verde"
    assert any(s["tipo"] == "dati_mancanti" for s in segnali)


def test_segnale_dati_mancanti_tace_quando_va_tutto_bene(monkeypatch):
    """Contro-prova: il segnale d'errore non deve comparire sempre."""
    monkeypatch.setattr(gruppo, "_completezza_dati_pv", lambda *a, **k: {})
    monkeypatch.setattr(gruppo, "_costi_mese_per_sede", lambda *a, **k: None)
    segnali = gruppo._calcola_segnali(
        None, [RID], {RID: "Sede 1"},
        segnali_off={"margine_calo", "prezzi_sopra", "ricavi_mancanti"},
        user_id="u1",
    )
    assert segnali == []


# ── Il buco trovato rileggendo il diff, non dal piano ─────────────────────────

def test_briefing_non_confronta_i_pv_quando_la_completezza_non_e_nota():
    """Con la completezza non determinabile, `incompleti_ids` e' vuoto — ma NON
    significa "tutti completi".

    In gruppo_overview il ranking marca `dati_incompleti` anche su
    `not completezza_nota`, cosi' il margine% resta soppresso. Qui si presidia il
    consumatore a valle: un ranking di PV gia' marcati incompleti non deve
    produrre la frase "Va meglio X, piu' indietro Y", che presenterebbe come
    confrontabili dei margini che nessuno ha verificato.
    """
    ranking = [
        gruppo.RankingPV(
            ristorante_id=RID, nome="Sede 1", margine_perc=None,
            fatturato=1000.0, colore="grigio", dati_incompleti=True,
        ),
        gruppo.RankingPV(
            ristorante_id=RID2, nome="Sede 2", margine_perc=None,
            fatturato=900.0, colore="grigio", dati_incompleti=True,
        ),
    ]
    narrativa = _briefing(
        ranking=ranking, completezza_nota=False, salute_colore="grigio",
        salute_indice=None, n_segnali=None,
    ).narrativa
    assert "Va meglio" not in narrativa
    assert TUTTO_OK not in narrativa


# ── L'endpoint vero: il buco che il test sul briefing NON copriva ────────────
#
# Il primo presidio scritto per questo caso guardava solo _build_briefing e
# SOPRAVVIVEVA al mutante che toglie `not completezza_nota` dal ranking di
# gruppo_overview: la riga stava nell'endpoint, non nell'helper. Qui si chiama
# l'endpoint, come fa TestCatenaFoodCostSuNetto per la stessa ragione.

RIGA_COMPLETA = {
    "ristorante_id": "a", "mese": 6, "fatturato_iva10": 11_000,
    "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
    "altri_costi_fb": 0, "altri_costi_spese": 0,
    "quote_riparto_fb": 0, "quote_riparto_spese": 0,
    "costo_dipendenti": 1_000, "costo_personale_extra": 0,
}


def _overview_con_completezza(completezza):
    """gruppo_overview con la completezza forzata: {} = tutti completi,
    None = non determinabile."""
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "in_", "eq", "lte", "order", "limit"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[RIGA_COMPLETA])
    sb.table.return_value = q
    rpc_res = MagicMock()
    rpc_res.execute.return_value = MagicMock(data=[])
    sb.rpc.return_value = rpc_res

    with patch.object(gruppo, "_resolve_gruppo",
                      return_value=(sb, "u1", [{"id": "a"}], "Gruppo",
                                    {"a": "PV a"}, ["a"])), \
         patch.object(gruppo, "_anno_mese_corrente", return_value=(2026, 6)), \
         patch.object(gruppo, "_completezza_dati_pv", return_value=completezza), \
         patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
         patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
               return_value={"a": ({6: 4_000.0}, {})}), \
         patch.object(gruppo, "_calcola_segnali", return_value=[]):
        return gruppo.gruppo_overview(authorization="Bearer t")


def test_overview_completezza_nota_espone_il_margine():
    """Contro-prova: coi dati completi il ranking mostra il margine%."""
    resp = _overview_con_completezza({})

    assert resp.kpi.livello_dati == "completo"
    assert resp.ranking[0].dati_incompleti is False
    assert resp.ranking[0].margine_perc == 50.0


def test_overview_completezza_ignota_non_certifica_i_margini():
    """Il falso verde 2a, e la sua coda nel ranking.

    Con la completezza non determinabile `incompleti_ids` e' vuoto: senza un
    gate esplicito il ranking leggeva "nessuno incompleto" e pubblicava un
    margine% che nessuno ha verificato — lo stesso falso verde chiuso nella card
    Conti, rientrato dalla porta del ranking.
    """
    resp = _overview_con_completezza(None)

    assert resp.kpi.livello_dati == "non_determinabile"
    assert resp.kpi.pv_da_completare is None, "zero direbbe 'nessuno da completare'"
    assert resp.ranking[0].dati_incompleti is True
    assert resp.ranking[0].margine_perc is None


# ── I due dialog: correzione scritta ma NON presidiata ───────────────────────
#
# I punti 2b/2c erano stati corretti senza test: rimettendo `set()` al posto di
# `None`, l'intera suite restava verde (due mutanti sopravvissuti, trovati dal
# code-reviewer). Qui si chiamano i due endpoint veri, come per l'overview: la
# riga da presidiare vive nell'endpoint, non in un helper.

def _dialog(fn, completezza, **kw):
    """gruppo_margini_coperti / gruppo_spreco_categorie con la completezza
    forzata. mese=6 perche' `costi_mese` (e quindi il ramo che ci interessa) si
    attiva solo sul mese singolo, non sulla vista anno."""
    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "in_", "eq", "lte", "order", "limit"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[RIGA_COMPLETA])
    sb.table.return_value = q
    rpc_res = MagicMock()
    rpc_res.execute.return_value = MagicMock(data=[])
    sb.rpc.return_value = rpc_res

    with patch.object(gruppo, "_resolve_gruppo",
                      return_value=(sb, "u1", [{"id": "a"}], "Gruppo",
                                    {"a": "PV a"}, ["a"])), \
         patch.object(gruppo, "_anno_mese_corrente", return_value=(2026, 6)), \
         patch.object(gruppo, "_completezza_dati_pv", return_value=completezza), \
         patch.object(gruppo, "_costi_mese_per_sede", return_value={"a": 4_000.0}), \
         patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
         patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
               return_value={"a": ({6: 4_000.0}, {})}):
        return fn(mese=6, authorization="Bearer t", **kw)


def test_dialog_margini_completezza_nota_confronta_i_pv():
    """Contro-prova: coi dati completi il confronto si fa."""
    resp = _dialog(gruppo.gruppo_margini_coperti, {})

    assert resp.righe[0].dati_incompleti is False
    assert resp.righe[0].margine_perc is not None


def test_dialog_margini_non_confronta_i_pv_se_la_completezza_e_ignota():
    """2b: `incompleti_set = set()` su errore faceva entrare nel confronto dei PV
    di cui non si sapeva se avessero i costi — presentati come affidabili."""
    resp = _dialog(gruppo.gruppo_margini_coperti, None)

    assert resp.righe[0].dati_incompleti is True
    assert resp.righe[0].margine_perc is None


def test_dialog_spreco_completezza_nota_non_marca_incompleto():
    """Contro-prova per il secondo dialog."""
    resp = _dialog(gruppo.gruppo_spreco_categorie, {})

    assert resp.pv[0].dati_incompleti is False


def test_dialog_spreco_marca_incompleto_se_la_completezza_e_ignota():
    """2c: stesso difetto di 2b nella finestra Spreco per categoria."""
    resp = _dialog(gruppo.gruppo_spreco_categorie, None)

    assert resp.pv[0].dati_incompleti is True


# ── I due rilievi della review sul segnale d'errore ──────────────────────────

def _segnali_degradati(monkeypatch):
    monkeypatch.setattr(
        gruppo, "_completezza_dati_pv",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("giu'")),
    )
    monkeypatch.setattr(gruppo, "_costi_mese_per_sede", lambda *a, **k: None)
    return gruppo._calcola_segnali(
        None, [RID, RID2], {RID: "Sede 1", RID2: "Sede 2"},
        segnali_off={"margine_calo", "prezzi_sopra", "ricavi_mancanti"},
        user_id="u1",
    )


def test_segnale_di_errore_non_porta_a_un_pv_arbitrario(monkeypatch):
    """Con `ids[0]` il bottone "Vedi PV" COMMUTAVA la sede attiva del cliente
    (cookie + preferenza, effetto persistente) su un punto vendita scelto a caso,
    per un avviso che dice solo "riprova più tardi". L'id vuoto e' il segnale al
    client di non rendere il bottone."""
    seg = _segnali_degradati(monkeypatch)

    assert seg[0]["ristorante_id"] == ""


def test_calcolo_degradato_non_finisce_nella_cache_del_giorno(monkeypatch):
    """La cache dei segnali vive fino a mezzanotte: salvare un calcolo degradato
    avrebbe cancellato per 24 ore i `dati_mancanti` veri (2-3 al giorno su ogni
    snapshot in produzione), sostituiti da "riprova più tardi"."""
    scritture = []

    class _Sb:
        def table(self, nome):
            sb_self = self

            class _T:
                def upsert(self, payload, **k):
                    scritture.append(payload)
                    return self

                def select(self, *a, **k): return self
                def eq(self, *a, **k): return self
                def limit(self, *a, **k): return self
                def execute(self): return type("R", (), {"data": []})()

            return _T()

    monkeypatch.setattr(
        gruppo, "_resolve_gruppo",
        lambda auth: (_Sb(), "u1", [{"id": RID}], "Gruppo", {RID: "Sede 1"}, [RID]),
    )
    monkeypatch.setattr(gruppo, "_get_gruppo_config", lambda sb, uid: (set(), set()))
    monkeypatch.setattr(
        gruppo, "_calcola_segnali",
        lambda *a, **k: [{
            "tipo": "dati_mancanti", "severity": "warning", "ristorante_id": "",
            "pv_nome": "Catena", "testo": "Non è stato possibile controllare",
            "cta_page": "/catena", "_degradato": True,
        }],
    )
    resp = gruppo.gruppo_segnali(authorization="Bearer t")

    assert scritture == [], "un calcolo degradato non va cristallizzato per 24h"
    # L'avviso arriva comunque al cliente: non salvarlo != non dirlo.
    assert len(resp.segnali) == 1
    # Il marker interno non esce nel payload pubblico.
    assert not hasattr(resp.segnali[0], "_degradato")


def test_calcolo_sano_finisce_in_cache(monkeypatch):
    """Contro-prova: senza degrado la cache si scrive come sempre — altrimenti il
    fix avrebbe spento la cache per tutti."""
    scritture = []

    class _Sb:
        def table(self, nome):
            class _T:
                def upsert(self, payload, **k):
                    scritture.append(payload)
                    return self

                def select(self, *a, **k): return self
                def eq(self, *a, **k): return self
                def limit(self, *a, **k): return self
                def execute(self): return type("R", (), {"data": []})()

            return _T()

    monkeypatch.setattr(
        gruppo, "_resolve_gruppo",
        lambda auth: (_Sb(), "u1", [{"id": RID}], "Gruppo", {RID: "Sede 1"}, [RID]),
    )
    monkeypatch.setattr(gruppo, "_get_gruppo_config", lambda sb, uid: (set(), set()))
    monkeypatch.setattr(
        gruppo, "_calcola_segnali",
        lambda *a, **k: [{
            "tipo": "dati_mancanti", "severity": "warning", "ristorante_id": RID,
            "pv_nome": "Sede 1", "testo": "Mancano le fatture costo",
            "cta_page": "/dashboard",
        }],
    )
    gruppo.gruppo_segnali(authorization="Bearer t")

    assert len(scritture) == 1
