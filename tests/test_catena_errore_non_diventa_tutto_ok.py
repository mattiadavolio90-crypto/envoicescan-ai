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
